"""Generic async repository base class implementing common CRUD operations."""

import uuid
from typing import Any, Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """Provides generic async CRUD operations for a SQLAlchemy ORM model.

    Subclasses set ``model`` at class level and gain get/list/create/update/delete
    without boilerplate.

    Type Parameters:
        ModelT: The SQLAlchemy ORM model class this repository manages.

    Attributes:
        model: The ORM model class.
        _session: The injected async database session.
    """

    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        """Initialise with an active database session.

        Args:
            session: An async SQLAlchemy session (typically injected by FastAPI).
        """
        self._session = session

    async def get_by_id(self, record_id: uuid.UUID) -> ModelT | None:
        """Fetch a single record by primary key.

        Args:
            record_id: UUID of the record to retrieve.

        Returns:
            The ORM instance, or None if not found.
        """
        result = await self._session.execute(
            select(self.model).where(self.model.id == record_id)  # type: ignore[attr-defined]
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        *,
        offset: int = 0,
        limit: int = 20,
        filters: list[Any] | None = None,
        order_by: Any | None = None,
    ) -> tuple[list[ModelT], int]:
        """Return a paginated list of records and the total count.

        Args:
            offset: Number of records to skip.
            limit: Maximum number of records to return.
            filters: Optional list of SQLAlchemy WHERE clause expressions.
            order_by: Optional column expression for ordering.

        Returns:
            A tuple of (records, total_count).
        """
        query = select(self.model)
        count_query = select(func.count()).select_from(self.model)

        if filters:
            for f in filters:
                query = query.where(f)
                count_query = count_query.where(f)

        if order_by is not None:
            query = query.order_by(order_by)

        total_result = await self._session.execute(count_query)
        total: int = total_result.scalar_one()

        query = query.offset(offset).limit(limit)
        result = await self._session.execute(query)
        records = list(result.scalars().all())

        return records, total

    async def create(self, **kwargs: Any) -> ModelT:
        """Insert a new record and return the persisted instance.

        Args:
            **kwargs: Column values for the new record.

        Returns:
            The newly created ORM instance (with server defaults populated
            after a flush).
        """
        instance = self.model(**kwargs)  # type: ignore[call-arg]
        self._session.add(instance)
        await self._session.flush()
        await self._session.refresh(instance)
        return instance

    async def update(self, instance: ModelT, **kwargs: Any) -> ModelT:
        """Apply partial updates to an existing ORM instance.

        Args:
            instance: The ORM instance to update.
            **kwargs: Attribute names and their new values.

        Returns:
            The updated ORM instance after a flush.
        """
        for key, value in kwargs.items():
            setattr(instance, key, value)
        await self._session.flush()
        await self._session.refresh(instance)
        return instance

    async def delete(self, instance: ModelT) -> None:
        """Delete an ORM instance from the database.

        Args:
            instance: The ORM instance to delete.
        """
        await self._session.delete(instance)
        await self._session.flush()
