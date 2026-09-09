"""Repository pattern implementation for User and ApiKey models."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_key import ApiKey
from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """Data access layer for the ``users`` table.

    Attributes:
        model: Bound to the User ORM model.
    """

    model = User

    async def get_by_email(self, email: str) -> User | None:
        """Look up a user by their email address.

        Args:
            email: Email address to search (case-insensitive).

        Returns:
            Matching User instance, or None.
        """
        result = await self._session.execute(
            select(User).where(User.email == email.lower())
        )
        return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> User | None:
        """Look up a user by their username.

        Args:
            username: Username to search (case-insensitive).

        Returns:
            Matching User instance, or None.
        """
        result = await self._session.execute(
            select(User).where(User.username == username.lower())
        )
        return result.scalar_one_or_none()

    async def email_exists(self, email: str) -> bool:
        """Check whether an email address is already registered.

        Args:
            email: Email address to test.

        Returns:
            True if the email is taken, False otherwise.
        """
        return await self.get_by_email(email) is not None

    async def username_exists(self, username: str) -> bool:
        """Check whether a username is already taken.

        Args:
            username: Username to test.

        Returns:
            True if the username is taken, False otherwise.
        """
        return await self.get_by_username(username) is not None


class ApiKeyRepository(BaseRepository[ApiKey]):
    """Data access layer for the ``api_keys`` table.

    Attributes:
        model: Bound to the ApiKey ORM model.
    """

    model = ApiKey

    async def get_by_hash(self, key_hash: str) -> ApiKey | None:
        """Look up an active, non-expired API key by its SHA-256 hash.

        Args:
            key_hash: SHA-256 hex digest of the raw API key value.

        Returns:
            Matching ApiKey if it is active and not expired, else None.
        """
        now = datetime.now(UTC)
        result = await self._session.execute(
            select(ApiKey).where(
                ApiKey.key_hash == key_hash,
                ApiKey.is_active.is_(True),
                (ApiKey.expires_at.is_(None)) | (ApiKey.expires_at > now),
            )
        )
        return result.scalar_one_or_none()

    async def list_for_user(self, user_id: uuid.UUID) -> list[ApiKey]:
        """Return all active API keys for a given user.

        Args:
            user_id: UUID of the owning user.

        Returns:
            List of active ApiKey instances ordered by creation date.
        """
        result = await self._session.execute(
            select(ApiKey)
            .where(ApiKey.user_id == user_id, ApiKey.is_active.is_(True))
            .order_by(ApiKey.created_at.desc())
        )
        return list(result.scalars().all())

    async def revoke(self, key_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """Soft-revoke an API key.

        Only revokes keys owned by the given user to prevent cross-user tampering.

        Args:
            key_id: UUID of the ApiKey record to revoke.
            user_id: UUID of the authenticated user (ownership check).

        Returns:
            True if the key was found and revoked, False if not found.
        """
        key = await self.get_by_id(key_id)
        if key is None or key.user_id != user_id:
            return False
        await self.update(key, is_active=False)
        return True

    async def touch_last_used(self, key_id: uuid.UUID) -> None:
        """Update the ``last_used_at`` timestamp without loading the full object.

        Args:
            key_id: UUID of the ApiKey record to update.
        """
        await self._session.execute(
            update(ApiKey)
            .where(ApiKey.id == key_id)
            .values(last_used_at=datetime.now(UTC))
        )
