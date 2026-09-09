"""Data access layer for Diagram model."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.diagram import Diagram


class DiagramRepository:
    """Repository for diagram records with versioning support.

    Attributes:
        _session: Active async SQLAlchemy session.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_diagram(
        self,
        repo_id: uuid.UUID,
        diagram_type: str,
        diagram_format: str,
        title: str,
        source_code: str,
        source_checksum: str,
        *,
        options: dict | None = None,
        generation_meta: dict | None = None,
    ) -> Diagram:
        """Save a new diagram version, marking all prior versions as not latest.

        Args:
            repo_id: UUID of the repository.
            diagram_type: Diagram type slug.
            diagram_format: Source format (mermaid | plantuml | d2).
            title: Human-readable title.
            source_code: Raw diagram source text.
            source_checksum: SHA-256 of source_code.
            options: Generator options dict.
            generation_meta: Additional generation metadata.

        Returns:
            Newly created Diagram record.
        """
        await self._session.execute(
            update(Diagram)
            .where(Diagram.repo_id == repo_id, Diagram.diagram_type == diagram_type)
            .values(is_latest=False)
        )

        max_ver = await self._session.scalar(
            select(func.max(Diagram.version)).where(
                Diagram.repo_id == repo_id, Diagram.diagram_type == diagram_type
            )
        )
        next_ver = (max_ver or 0) + 1

        diagram = Diagram(
            repo_id=repo_id,
            diagram_type=diagram_type,
            diagram_format=diagram_format,
            title=title,
            source_code=source_code,
            source_checksum=source_checksum,
            version=next_ver,
            is_latest=True,
            options=options or {},
            generation_meta=generation_meta or {},
        )
        self._session.add(diagram)
        await self._session.commit()
        await self._session.refresh(diagram)
        return diagram

    async def attach_renders(
        self,
        diagram_id: uuid.UUID,
        *,
        minio_key_svg: str | None = None,
        minio_key_png: str | None = None,
        render_url_svg: str | None = None,
        render_url_png: str | None = None,
    ) -> None:
        """Attach MinIO object keys and presigned URLs to a diagram record.

        Args:
            diagram_id: UUID of the diagram.
            minio_key_svg: MinIO object key for SVG.
            minio_key_png: MinIO object key for PNG.
            render_url_svg: Presigned URL for SVG.
            render_url_png: Presigned URL for PNG.
        """
        fields: dict[str, Any] = {}
        if minio_key_svg is not None:
            fields["minio_key_svg"] = minio_key_svg
        if minio_key_png is not None:
            fields["minio_key_png"] = minio_key_png
        if render_url_svg is not None:
            fields["render_url_svg"] = render_url_svg
        if render_url_png is not None:
            fields["render_url_png"] = render_url_png
        if fields:
            await self._session.execute(
                update(Diagram).where(Diagram.id == diagram_id).values(**fields)
            )
            await self._session.commit()

    async def get_latest(
        self, repo_id: uuid.UUID, diagram_type: str
    ) -> Diagram | None:
        """Return the latest version of a diagram type for a repository.

        Args:
            repo_id: UUID of the repository.
            diagram_type: Diagram type slug.

        Returns:
            Latest Diagram or None.
        """
        result = await self._session.execute(
            select(Diagram).where(
                Diagram.repo_id == repo_id,
                Diagram.diagram_type == diagram_type,
                Diagram.is_latest.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, diagram_id: uuid.UUID) -> Diagram | None:
        """Fetch a diagram by primary key.

        Args:
            diagram_id: UUID of the diagram.

        Returns:
            Diagram or None.
        """
        result = await self._session.execute(
            select(Diagram).where(Diagram.id == diagram_id)
        )
        return result.scalar_one_or_none()

    async def list_latest_for_repo(self, repo_id: uuid.UUID) -> list[Diagram]:
        """Return all latest-version diagrams for a repository.

        Args:
            repo_id: UUID of the repository.

        Returns:
            List of latest Diagram records ordered by diagram_type.
        """
        result = await self._session.execute(
            select(Diagram)
            .where(Diagram.repo_id == repo_id, Diagram.is_latest.is_(True))
            .order_by(Diagram.diagram_type)
        )
        return list(result.scalars().all())

    async def get_checksum(
        self, repo_id: uuid.UUID, diagram_type: str
    ) -> str | None:
        """Return the source_checksum of the latest diagram for cache comparison.

        Args:
            repo_id: UUID of the repository.
            diagram_type: Diagram type slug.

        Returns:
            Checksum string or None if no diagram exists.
        """
        result = await self._session.execute(
            select(Diagram.source_checksum).where(
                Diagram.repo_id == repo_id,
                Diagram.diagram_type == diagram_type,
                Diagram.is_latest.is_(True),
            )
        )
        return result.scalar_one_or_none()
