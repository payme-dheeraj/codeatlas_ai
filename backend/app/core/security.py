"""Cryptographic utilities: password hashing, JWT creation/verification, API key generation.

OWASP compliance:
- bcrypt with cost factor 12 (minimum recommended for 2024).
- Access tokens are short-lived (default 60 min).
- Refresh tokens are single-use; rotated on every refresh.
- API keys are 32-byte cryptographically random, stored as SHA-256 hashes.
"""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# ── Password hashing ───────────────────────────────────────────────────────────

_pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12,
)


def hash_password(plain: str) -> str:
    """Return a bcrypt hash of the given plaintext password.

    Args:
        plain: The plaintext password string.

    Returns:
        A bcrypt hash string suitable for database storage.
    """
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a stored bcrypt hash.

    Args:
        plain: The plaintext password provided by the user.
        hashed: The stored bcrypt hash.

    Returns:
        True if the password matches, False otherwise.
    """
    return _pwd_context.verify(plain, hashed)


# ── Token types ────────────────────────────────────────────────────────────────


class TokenType(StrEnum):
    """Enumeration of JWT token type claims."""

    ACCESS = "access"
    REFRESH = "refresh"


# ── JWT creation ───────────────────────────────────────────────────────────────


def create_access_token(
    subject: uuid.UUID,
    role: str,
    *,
    extra_claims: dict[str, Any] | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed JWT access token.

    The token payload includes:
    - ``sub``: user UUID as a string.
    - ``role``: RBAC role string.
    - ``type``: ``"access"``.
    - ``iat``: issued-at timestamp.
    - ``exp``: expiry timestamp.
    - ``jti``: unique token ID (for future revocation support).

    Args:
        subject: UUID of the authenticated user.
        role: RBAC role (admin | analyst | viewer).
        extra_claims: Optional additional claims merged into the payload.
        expires_delta: Custom expiry duration; defaults to config value.

    Returns:
        Signed JWT string.
    """
    now = datetime.now(UTC)
    expire = now + (
        expires_delta
        or timedelta(minutes=settings.jwt_access_token_expire_minutes)
    )
    payload: dict[str, Any] = {
        "sub": str(subject),
        "role": role,
        "type": TokenType.ACCESS,
        "iat": now,
        "exp": expire,
        "jti": str(uuid.uuid4()),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(
    subject: uuid.UUID,
    *,
    expires_delta: timedelta | None = None,
) -> tuple[str, str]:
    """Create a signed JWT refresh token and return it with its JTI.

    The JTI is stored in Redis so refresh tokens can be revoked or rotated.

    Args:
        subject: UUID of the authenticated user.
        expires_delta: Custom expiry duration; defaults to config value.

    Returns:
        Tuple of (signed JWT string, jti string).
    """
    now = datetime.now(UTC)
    jti = str(uuid.uuid4())
    expire = now + (
        expires_delta
        or timedelta(days=settings.jwt_refresh_token_expire_days)
    )
    payload: dict[str, Any] = {
        "sub": str(subject),
        "type": TokenType.REFRESH,
        "iat": now,
        "exp": expire,
        "jti": jti,
    }
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)
    return token, jti


# ── JWT verification ───────────────────────────────────────────────────────────


def decode_token(token: str, *, expected_type: TokenType) -> dict[str, Any]:
    """Decode and validate a JWT token.

    Verifies:
    - Signature.
    - Expiry (``exp`` claim).
    - Token type matches ``expected_type``.

    Args:
        token: Raw JWT string from the Authorization header or cookie.
        expected_type: The token type the caller expects (access or refresh).

    Returns:
        Decoded payload dictionary.

    Raises:
        JWTError: If the token is invalid, expired, or has the wrong type.
    """
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError as exc:
        logger.warning("jwt_decode_failed", error=str(exc))
        raise

    token_type = payload.get("type")
    if token_type != expected_type:
        raise JWTError(
            f"Expected token type '{expected_type}', got '{token_type}'."
        )
    return payload


def extract_user_id(payload: dict[str, Any]) -> uuid.UUID:
    """Extract and validate the ``sub`` claim as a UUID.

    Args:
        payload: Decoded JWT payload dictionary.

    Returns:
        User UUID.

    Raises:
        JWTError: If ``sub`` is missing or not a valid UUID.
    """
    sub = payload.get("sub")
    if not sub:
        raise JWTError("Missing 'sub' claim in token payload.")
    try:
        return uuid.UUID(sub)
    except ValueError as exc:
        raise JWTError(f"Invalid UUID in 'sub' claim: {sub}") from exc


# ── API keys ───────────────────────────────────────────────────────────────────


def generate_api_key() -> tuple[str, str]:
    """Generate a cryptographically random API key.

    The raw key is returned to the caller **once** and is never stored.
    Only the SHA-256 hash of the key is persisted in the database so that
    even a full DB compromise cannot recover active API keys.

    Returns:
        Tuple of (raw_key, sha256_hash):
        - ``raw_key``: The secret value shown to the user (prefix + random).
        - ``sha256_hash``: The value stored in the database.
    """
    random_bytes = secrets.token_bytes(32)
    raw_key = f"ca_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    return raw_key, key_hash


def hash_api_key(raw_key: str) -> str:
    """Compute the SHA-256 hash of a raw API key for lookup.

    Args:
        raw_key: The raw API key string provided in a request header.

    Returns:
        Hex-encoded SHA-256 hash string.
    """
    return hashlib.sha256(raw_key.encode()).hexdigest()


# ── Redis refresh-token helpers ────────────────────────────────────────────────

_REFRESH_TOKEN_PREFIX = "refresh_token:"


def refresh_token_redis_key(jti: str) -> str:
    """Build the Redis key used to store a valid refresh token JTI.

    Args:
        jti: The unique JWT ID of the refresh token.

    Returns:
        Redis key string.
    """
    return f"{_REFRESH_TOKEN_PREFIX}{jti}"
