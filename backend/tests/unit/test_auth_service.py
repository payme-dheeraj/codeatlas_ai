"""Unit tests for AuthService business logic.

All external dependencies (DB repositories, Redis) are mocked so tests
run without infrastructure.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from jose import jwt

from app.core.config import settings
from app.core.security import (
    create_refresh_token,
    hash_password,
    refresh_token_redis_key,
)
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest,
    CreateApiKeyRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
)
from app.services.auth_service import AuthService


# ── Fixtures ───────────────────────────────────────────────────────────────────


def make_user(**kwargs) -> User:
    """Build a mock User ORM instance."""
    defaults = dict(
        id=uuid.uuid4(),
        email="test@example.com",
        username="testuser",
        password_hash=hash_password("Password1"),
        role="viewer",
        is_active=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    defaults.update(kwargs)
    user = MagicMock(spec=User)
    for k, v in defaults.items():
        setattr(user, k, v)
    return user


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_redis() -> AsyncMock:
    r = AsyncMock()
    r.get = AsyncMock(return_value=None)
    r.setex = AsyncMock()
    r.delete = AsyncMock()
    return r


@pytest.fixture
def service(mock_session: AsyncMock, mock_redis: AsyncMock) -> AuthService:
    return AuthService(mock_session, mock_redis)


# ── Registration tests ─────────────────────────────────────────────────────────


class TestRegister:
    @pytest.mark.asyncio
    async def test_register_success(self, service: AuthService) -> None:
        user = make_user()
        with (
            patch.object(service._user_repo, "email_exists", AsyncMock(return_value=False)),
            patch.object(service._user_repo, "username_exists", AsyncMock(return_value=False)),
            patch.object(service._user_repo, "create", AsyncMock(return_value=user)),
        ):
            result = await service.register(
                RegisterRequest(
                    email="new@example.com",
                    username="newuser",
                    password="Password1",
                )
            )
        assert result.email == user.email

    @pytest.mark.asyncio
    async def test_register_duplicate_email_raises(self, service: AuthService) -> None:
        with patch.object(service._user_repo, "email_exists", AsyncMock(return_value=True)):
            with pytest.raises(ValueError, match="already registered"):
                await service.register(
                    RegisterRequest(
                        email="taken@example.com",
                        username="newuser",
                        password="Password1",
                    )
                )

    @pytest.mark.asyncio
    async def test_register_duplicate_username_raises(self, service: AuthService) -> None:
        with (
            patch.object(service._user_repo, "email_exists", AsyncMock(return_value=False)),
            patch.object(
                service._user_repo, "username_exists", AsyncMock(return_value=True)
            ),
        ):
            with pytest.raises(ValueError, match="already taken"):
                await service.register(
                    RegisterRequest(
                        email="new@example.com",
                        username="taken",
                        password="Password1",
                    )
                )


# ── Login tests ────────────────────────────────────────────────────────────────


class TestLogin:
    @pytest.mark.asyncio
    async def test_login_success_returns_tokens(
        self, service: AuthService, mock_redis: AsyncMock
    ) -> None:
        user = make_user()
        with patch.object(
            service._user_repo, "get_by_email", AsyncMock(return_value=user)
        ):
            result = await service.login(
                LoginRequest(email="test@example.com", password="Password1")
            )
        assert result.access_token
        assert result.refresh_token
        assert result.token_type == "bearer"
        mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_login_wrong_password_raises(self, service: AuthService) -> None:
        user = make_user()
        with patch.object(
            service._user_repo, "get_by_email", AsyncMock(return_value=user)
        ):
            with pytest.raises(ValueError, match="Invalid email or password"):
                await service.login(
                    LoginRequest(email="test@example.com", password="WrongPass1")
                )

    @pytest.mark.asyncio
    async def test_login_unknown_email_raises(self, service: AuthService) -> None:
        with patch.object(
            service._user_repo, "get_by_email", AsyncMock(return_value=None)
        ):
            with pytest.raises(ValueError, match="Invalid email or password"):
                await service.login(
                    LoginRequest(email="unknown@example.com", password="Password1")
                )

    @pytest.mark.asyncio
    async def test_login_inactive_account_raises(self, service: AuthService) -> None:
        user = make_user(is_active=False)
        with patch.object(
            service._user_repo, "get_by_email", AsyncMock(return_value=user)
        ):
            with pytest.raises(ValueError, match="Invalid email or password"):
                await service.login(
                    LoginRequest(email="test@example.com", password="Password1")
                )


# ── Token refresh tests ────────────────────────────────────────────────────────


class TestRefreshTokens:
    @pytest.mark.asyncio
    async def test_refresh_success(
        self, service: AuthService, mock_redis: AsyncMock
    ) -> None:
        user = make_user()
        refresh_jwt, jti = create_refresh_token(subject=user.id)
        mock_redis.get = AsyncMock(return_value=str(user.id))

        with patch.object(
            service._user_repo, "get_by_id", AsyncMock(return_value=user)
        ):
            result = await service.refresh_tokens(RefreshRequest(refresh_token=refresh_jwt))

        assert result.access_token
        assert result.refresh_token != refresh_jwt  # rotated
        mock_redis.delete.assert_called_once_with(refresh_token_redis_key(jti))

    @pytest.mark.asyncio
    async def test_refresh_revoked_token_raises(
        self, service: AuthService, mock_redis: AsyncMock
    ) -> None:
        user = make_user()
        refresh_jwt, _ = create_refresh_token(subject=user.id)
        mock_redis.get = AsyncMock(return_value=None)  # not in Redis = revoked

        with pytest.raises(ValueError, match="revoked or already used"):
            await service.refresh_tokens(RefreshRequest(refresh_token=refresh_jwt))

    @pytest.mark.asyncio
    async def test_refresh_invalid_jwt_raises(self, service: AuthService) -> None:
        with pytest.raises(ValueError, match="Invalid refresh token"):
            await service.refresh_tokens(RefreshRequest(refresh_token="not.a.jwt"))


# ── Password change tests ──────────────────────────────────────────────────────


class TestChangePassword:
    @pytest.mark.asyncio
    async def test_change_password_success(self, service: AuthService) -> None:
        user = make_user()
        with (
            patch.object(service._user_repo, "get_by_id", AsyncMock(return_value=user)),
            patch.object(service._user_repo, "update", AsyncMock(return_value=user)),
        ):
            await service.change_password(
                user.id,
                ChangePasswordRequest(
                    current_password="Password1", new_password="NewPass2"
                ),
            )
        service._user_repo.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_change_password_wrong_current_raises(self, service: AuthService) -> None:
        user = make_user()
        with patch.object(service._user_repo, "get_by_id", AsyncMock(return_value=user)):
            with pytest.raises(ValueError, match="Current password is incorrect"):
                await service.change_password(
                    user.id,
                    ChangePasswordRequest(
                        current_password="WrongCurrent1", new_password="NewPass2"
                    ),
                )


# ── API key tests ──────────────────────────────────────────────────────────────


class TestApiKeys:
    @pytest.mark.asyncio
    async def test_create_api_key_returns_raw_key(self, service: AuthService) -> None:
        user_id = uuid.uuid4()
        from app.models.api_key import ApiKey

        key_record = MagicMock(spec=ApiKey)
        key_record.id = uuid.uuid4()
        key_record.name = "CI Key"
        key_record.prefix = "ca_abc123"
        key_record.expires_at = None
        key_record.created_at = datetime.now(UTC)

        with patch.object(service._key_repo, "create", AsyncMock(return_value=key_record)):
            result = await service.create_api_key(
                user_id, CreateApiKeyRequest(name="CI Key")
            )

        assert result.key.startswith("ca_")
        assert len(result.key) > 10
        assert result.name == "CI Key"

    @pytest.mark.asyncio
    async def test_revoke_api_key_returns_true(self, service: AuthService) -> None:
        user_id = uuid.uuid4()
        key_id = uuid.uuid4()
        with patch.object(service._key_repo, "revoke", AsyncMock(return_value=True)):
            result = await service.revoke_api_key(key_id, user_id)
        assert result is True

    @pytest.mark.asyncio
    async def test_revoke_nonexistent_key_returns_false(self, service: AuthService) -> None:
        with patch.object(service._key_repo, "revoke", AsyncMock(return_value=False)):
            result = await service.revoke_api_key(uuid.uuid4(), uuid.uuid4())
        assert result is False
