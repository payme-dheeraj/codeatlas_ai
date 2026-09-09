"""Authentication and authorization business logic.

Responsibilities:
- User registration with duplicate detection.
- Password-based login with constant-time comparison.
- JWT access + refresh token issuance and rotation.
- Refresh token revocation via Redis.
- API key creation, listing, and revocation.
- Profile update and password change.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import (
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    extract_user_id,
    generate_api_key,
    hash_api_key,
    hash_password,
    refresh_token_redis_key,
    verify_password,
)
from app.models.api_key import ApiKey
from app.models.user import User
from app.repositories.user_repository import ApiKeyRepository, UserRepository
from app.schemas.auth import (
    ApiKeyListItem,
    ApiKeyResponse,
    ChangePasswordRequest,
    CreateApiKeyRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from app.schemas.user import AdminUpdateUserRequest, UpdateProfileRequest, UserResponse

logger = get_logger(__name__)

# Redis TTL for refresh token JTI records (matches JWT expiry + 1 day buffer)
_REFRESH_TTL_SECONDS = (settings.jwt_refresh_token_expire_days + 1) * 86400


def _user_to_response(user: User) -> UserResponse:
    """Convert a User ORM instance to its public response schema.

    Args:
        user: ORM User instance.

    Returns:
        Serialised UserResponse.
    """
    return UserResponse.model_validate(user)


def _build_token_response(user: User, refresh_token: str) -> TokenResponse:
    """Create a full TokenResponse for an authenticated user.

    Args:
        user: Authenticated User ORM instance.
        refresh_token: Pre-created refresh JWT string.

    Returns:
        TokenResponse containing access and refresh tokens.
    """
    access_token = create_access_token(subject=user.id, role=user.role)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


class AuthService:
    """Orchestrates user authentication, token management, and API key lifecycle.

    Attributes:
        _user_repo: Data access layer for User records.
        _key_repo: Data access layer for ApiKey records.
        _redis: Async Redis client for refresh token storage.
    """

    def __init__(self, session: AsyncSession, redis: Redis) -> None:
        """Initialise with DB session and Redis client.

        Args:
            session: Active async SQLAlchemy session.
            redis: Async Redis client instance.
        """
        self._user_repo = UserRepository(session)
        self._key_repo = ApiKeyRepository(session)
        self._redis = redis

    # ── Registration ───────────────────────────────────────────────────────────

    async def register(self, payload: RegisterRequest) -> UserResponse:
        """Create a new user account.

        Args:
            payload: Validated registration request body.

        Returns:
            Newly created UserResponse.

        Raises:
            ValueError: If the email or username is already taken.
        """
        email = payload.email.lower()
        username = payload.username.lower()

        if await self._user_repo.email_exists(email):
            raise ValueError(f"Email '{email}' is already registered.")
        if await self._user_repo.username_exists(username):
            raise ValueError(f"Username '{username}' is already taken.")

        user = await self._user_repo.create(
            email=email,
            username=username,
            password_hash=hash_password(payload.password),
            role="viewer",
            is_active=True,
        )
        logger.info("user_registered", user_id=str(user.id), username=username)
        return _user_to_response(user)

    # ── Login ──────────────────────────────────────────────────────────────────

    async def login(self, payload: LoginRequest) -> TokenResponse:
        """Authenticate a user with email and password.

        Uses constant-time password verification to prevent timing attacks.

        Args:
            payload: Validated login request body.

        Returns:
            TokenResponse with access and refresh tokens.

        Raises:
            ValueError: If credentials are invalid or account is inactive.
        """
        user = await self._user_repo.get_by_email(payload.email.lower())

        # Always run verify_password even on missing user to prevent timing attacks
        dummy_hash = "$2b$12$" + "a" * 53
        stored_hash = user.password_hash if (user and user.password_hash) else dummy_hash
        password_valid = verify_password(payload.password, stored_hash)

        if not user or not password_valid or not user.is_active:
            logger.warning(
                "login_failed",
                email=payload.email,
                reason="invalid_credentials" if not user else "inactive_account",
            )
            raise ValueError("Invalid email or password.")

        refresh_token, jti = create_refresh_token(subject=user.id)
        await self._store_refresh_token(jti, str(user.id))

        logger.info("user_logged_in", user_id=str(user.id))
        return _build_token_response(user, refresh_token)

    # ── Token refresh ──────────────────────────────────────────────────────────

    async def refresh_tokens(self, payload: RefreshRequest) -> TokenResponse:
        """Exchange a valid refresh token for a new token pair.

        Implements refresh token rotation:
        1. Verify the incoming refresh token.
        2. Check the JTI exists in Redis (not revoked).
        3. Delete the old JTI from Redis.
        4. Issue new access + refresh tokens with a new JTI.

        Args:
            payload: Request body containing the refresh JWT.

        Returns:
            New TokenResponse.

        Raises:
            ValueError: If the token is invalid, expired, or already revoked.
        """
        try:
            token_payload = decode_token(
                payload.refresh_token, expected_type=TokenType.REFRESH
            )
        except JWTError as exc:
            raise ValueError(f"Invalid refresh token: {exc}") from exc

        jti: str = token_payload.get("jti", "")
        user_id = extract_user_id(token_payload)

        redis_key = refresh_token_redis_key(jti)
        stored = await self._redis.get(redis_key)
        if not stored:
            logger.warning("refresh_token_reuse_attempt", jti=jti, user_id=str(user_id))
            raise ValueError("Refresh token has been revoked or already used.")

        # Rotate: delete old JTI
        await self._redis.delete(redis_key)

        user = await self._user_repo.get_by_id(user_id)
        if not user or not user.is_active:
            raise ValueError("User account not found or inactive.")

        new_refresh, new_jti = create_refresh_token(subject=user.id)
        await self._store_refresh_token(new_jti, str(user.id))

        logger.info("tokens_refreshed", user_id=str(user.id))
        return _build_token_response(user, new_refresh)

    # ── Logout ─────────────────────────────────────────────────────────────────

    async def logout(self, refresh_token: str) -> None:
        """Revoke a refresh token by deleting its JTI from Redis.

        Args:
            refresh_token: The refresh JWT to invalidate.
        """
        try:
            token_payload = decode_token(refresh_token, expected_type=TokenType.REFRESH)
            jti: str = token_payload.get("jti", "")
            await self._redis.delete(refresh_token_redis_key(jti))
            logger.info("user_logged_out", jti=jti)
        except JWTError:
            # Token already invalid — treat as successful logout
            pass

    # ── Profile ────────────────────────────────────────────────────────────────

    async def get_profile(self, user_id: uuid.UUID) -> UserResponse | None:
        """Retrieve the profile of the authenticated user.

        Args:
            user_id: UUID of the requesting user.

        Returns:
            UserResponse, or None if the user no longer exists.
        """
        user = await self._user_repo.get_by_id(user_id)
        return _user_to_response(user) if user else None

    async def update_profile(
        self, user_id: uuid.UUID, payload: UpdateProfileRequest
    ) -> UserResponse:
        """Apply profile updates for the authenticated user.

        Args:
            user_id: UUID of the user to update.
            payload: Fields to update (all optional).

        Returns:
            Updated UserResponse.

        Raises:
            ValueError: If user not found or username already taken.
        """
        user = await self._user_repo.get_by_id(user_id)
        if user is None:
            raise ValueError("User not found.")

        updates: dict[str, Any] = {}
        if payload.username is not None:
            username = payload.username.lower()
            existing = await self._user_repo.get_by_username(username)
            if existing and existing.id != user_id:
                raise ValueError(f"Username '{username}' is already taken.")
            updates["username"] = username

        if updates:
            user = await self._user_repo.update(user, **updates)
        return _user_to_response(user)

    async def change_password(
        self, user_id: uuid.UUID, payload: ChangePasswordRequest
    ) -> None:
        """Change the authenticated user's password.

        Args:
            user_id: UUID of the requesting user.
            payload: Current and new password values.

        Raises:
            ValueError: If the current password is incorrect or user not found.
        """
        user = await self._user_repo.get_by_id(user_id)
        if user is None:
            raise ValueError("User not found.")
        if not user.password_hash or not verify_password(
            payload.current_password, user.password_hash
        ):
            raise ValueError("Current password is incorrect.")

        await self._user_repo.update(user, password_hash=hash_password(payload.new_password))
        logger.info("password_changed", user_id=str(user_id))

    # ── Admin ──────────────────────────────────────────────────────────────────

    async def admin_update_user(
        self, target_user_id: uuid.UUID, payload: AdminUpdateUserRequest
    ) -> UserResponse:
        """Allow admins to update role or account status of any user.

        Args:
            target_user_id: UUID of the user to modify.
            payload: Role and/or is_active update.

        Returns:
            Updated UserResponse.

        Raises:
            ValueError: If the target user is not found.
        """
        user = await self._user_repo.get_by_id(target_user_id)
        if user is None:
            raise ValueError(f"User '{target_user_id}' not found.")
        updates = payload.model_dump(exclude_none=True)
        if updates:
            user = await self._user_repo.update(user, **updates)
        return _user_to_response(user)

    # ── API keys ───────────────────────────────────────────────────────────────

    async def create_api_key(
        self, user_id: uuid.UUID, payload: CreateApiKeyRequest
    ) -> ApiKeyResponse:
        """Generate a new API key for the authenticated user.

        The raw key is returned in the response **once only**.

        Args:
            user_id: UUID of the requesting user.
            payload: Key name and optional expiry.

        Returns:
            ApiKeyResponse containing the one-time raw key value.
        """
        raw_key, key_hash = generate_api_key()
        prefix = raw_key[:8]

        expires_at: datetime | None = None
        if payload.expires_days is not None:
            expires_at = datetime.now(UTC) + timedelta(days=payload.expires_days)

        api_key = await self._key_repo.create(
            user_id=user_id,
            name=payload.name,
            key_hash=key_hash,
            prefix=prefix,
            expires_at=expires_at,
        )
        logger.info("api_key_created", user_id=str(user_id), key_id=str(api_key.id))

        return ApiKeyResponse(
            id=api_key.id,
            name=api_key.name,
            key=raw_key,
            prefix=prefix,
            expires_at=expires_at,
            created_at=api_key.created_at,
        )

    async def list_api_keys(self, user_id: uuid.UUID) -> list[ApiKeyListItem]:
        """Return all active API keys for the authenticated user.

        Args:
            user_id: UUID of the requesting user.

        Returns:
            List of ApiKeyListItem (no raw key values).
        """
        keys = await self._key_repo.list_for_user(user_id)
        return [ApiKeyListItem.model_validate(k) for k in keys]

    async def revoke_api_key(self, key_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """Revoke an API key owned by the authenticated user.

        Args:
            key_id: UUID of the API key to revoke.
            user_id: UUID of the requesting user (ownership enforced).

        Returns:
            True if revoked, False if not found or not owned by user.
        """
        revoked = await self._key_repo.revoke(key_id, user_id)
        if revoked:
            logger.info("api_key_revoked", key_id=str(key_id), user_id=str(user_id))
        return revoked

    # ── Internal helpers ───────────────────────────────────────────────────────

    async def _store_refresh_token(self, jti: str, user_id: str) -> None:
        """Persist a refresh token JTI in Redis with appropriate TTL.

        Args:
            jti: The JWT ID of the refresh token.
            user_id: String UUID of the owning user (stored as value).
        """
        await self._redis.setex(
            refresh_token_redis_key(jti),
            _REFRESH_TTL_SECONDS,
            user_id,
        )

    async def authenticate_api_key(self, raw_key: str) -> User | None:
        """Verify a raw API key and return the owning user on success.

        Also updates ``last_used_at`` on the key record asynchronously.

        Args:
            raw_key: The raw API key string from the request header.

        Returns:
            The owning User if the key is valid and active, else None.
        """
        key_hash = hash_api_key(raw_key)
        api_key = await self._key_repo.get_by_hash(key_hash)
        if api_key is None:
            return None
        user = await self._user_repo.get_by_id(api_key.user_id)
        if user is None or not user.is_active:
            return None
        # Fire-and-forget last_used update (best effort)
        try:
            await self._key_repo.touch_last_used(api_key.id)
        except Exception:
            pass
        return user
