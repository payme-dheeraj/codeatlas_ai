"""Pydantic v2 schemas for authentication request/response payloads."""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


# ── Request schemas ────────────────────────────────────────────────────────────


class RegisterRequest(BaseModel):
    """Payload for creating a new user account.

    Attributes:
        email: Valid email address; used as login identifier.
        username: Alphanumeric username (3–50 characters).
        password: Plaintext password; hashed before storage.
    """

    email: EmailStr = Field(description="User's email address")
    username: str = Field(
        min_length=3,
        max_length=50,
        description="Alphanumeric username (letters, digits, hyphens, underscores)",
        examples=["john_doe"],
    )
    password: str = Field(
        min_length=8,
        max_length=128,
        description="Password (minimum 8 characters)",
    )

    @field_validator("username")
    @classmethod
    def username_alphanumeric(cls, v: str) -> str:
        """Enforce alphanumeric + hyphen/underscore characters only."""
        import re

        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError(
                "Username may only contain letters, digits, hyphens, and underscores."
            )
        return v.lower()

    @field_validator("password")
    @classmethod
    def password_complexity(cls, v: str) -> str:
        """Enforce minimum password complexity (OWASP recommendation)."""
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter.")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit.")
        return v


class LoginRequest(BaseModel):
    """Payload for email/password login.

    Attributes:
        email: Registered email address.
        password: Plaintext password.
    """

    email: EmailStr
    password: str = Field(min_length=1)


class RefreshRequest(BaseModel):
    """Payload for exchanging a refresh token for a new token pair.

    Attributes:
        refresh_token: A valid, non-revoked refresh JWT.
    """

    refresh_token: str = Field(min_length=1, description="Valid refresh JWT")


class ChangePasswordRequest(BaseModel):
    """Payload for authenticated password change.

    Attributes:
        current_password: The user's existing plaintext password.
        new_password: The desired new plaintext password.
    """

    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def new_password_complexity(cls, v: str) -> str:
        """Enforce complexity on the new password."""
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter.")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit.")
        return v


class CreateApiKeyRequest(BaseModel):
    """Payload for generating a new API key.

    Attributes:
        name: Human-readable label for the key (e.g. ``"CI/CD Pipeline"``).
        expires_days: Optional expiry in days; None means the key never expires.
    """

    name: str = Field(min_length=1, max_length=100, description="Descriptive label for the key")
    expires_days: int | None = Field(
        default=None,
        ge=1,
        le=365,
        description="Days until the key expires (1–365); omit for no expiry",
    )


# ── Response schemas ───────────────────────────────────────────────────────────


class TokenResponse(BaseModel):
    """Response returned on successful login or token refresh.

    Attributes:
        access_token: Short-lived JWT for API authentication.
        refresh_token: Long-lived JWT for obtaining new access tokens.
        token_type: Always ``"bearer"``.
        expires_in: Access token lifetime in seconds.
    """

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class ApiKeyResponse(BaseModel):
    """Response returned immediately after API key creation.

    The ``key`` field is shown **only once** and is never retrievable again.

    Attributes:
        id: UUID of the ApiKey record.
        name: Descriptive label.
        key: The raw API key value (shown once; store securely).
        prefix: First 8 characters of the key for identification.
        expires_at: Expiry timestamp, or None if perpetual.
        created_at: Creation timestamp.
    """

    id: uuid.UUID
    name: str
    key: str  # raw key — shown once only
    prefix: str
    expires_at: datetime | None
    created_at: datetime


class ApiKeyListItem(BaseModel):
    """Safe API key representation for list endpoints (no raw key exposed).

    Attributes:
        id: UUID of the ApiKey record.
        name: Descriptive label.
        prefix: First 8 characters for identification.
        expires_at: Expiry timestamp or None.
        last_used_at: When the key was last used for authentication.
        created_at: Creation timestamp.
    """

    id: uuid.UUID
    name: str
    prefix: str
    expires_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
