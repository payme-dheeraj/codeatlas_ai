"""Pydantic v2 schemas for User request/response payloads."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class UserResponse(BaseModel):
    """Public representation of a user account.

    Attributes:
        id: User UUID.
        email: Email address.
        username: Display username.
        role: RBAC role: admin | analyst | viewer.
        is_active: Whether the account is active.
        created_at: Account creation timestamp.
        updated_at: Last modification timestamp.
    """

    id: uuid.UUID
    email: EmailStr
    username: str
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UpdateProfileRequest(BaseModel):
    """Partial update payload for user profile fields.

    All fields are optional — only provided values are applied.

    Attributes:
        username: New display username.
    """

    username: str | None = Field(
        default=None,
        min_length=3,
        max_length=50,
        description="New username (alphanumeric, hyphens, underscores)",
    )


class AdminUpdateUserRequest(BaseModel):
    """Admin-only payload for modifying any user account.

    Attributes:
        role: New RBAC role assignment.
        is_active: Enable or disable the account.
    """

    role: Literal["admin", "analyst", "viewer"] | None = None
    is_active: bool | None = None
