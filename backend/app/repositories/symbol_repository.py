"""Repository pattern implementation for ParsedSymbol model."""

import uuid
from typing import Any

from sqlalchemy import delete, desc, distinct, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.symbol import ParsedSymbol
from app.repositories.base import BaseRepository


class SymbolRepository(BaseRepository[ParsedSymbol]):
    """Data access layer for the ``parsed_symbols`` table.

    Attributes:
        model: Bound to ParsedSymbol ORM model.
    """

    model = ParsedSymbol

    async def list_for_repo(
        self,
        repo_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 50,
        language: str | None = None,
        symbol_kind: str | None = None,
        file_path: str | None = None,
        name_query: str | None = None,
    ) -> tuple[list[ParsedSymbol], int]:
        """Return a paginated, filtered list of symbols for a repository.

        Args:
            repo_id: UUID of the parent repository.
            offset: Records to skip.
            limit: Maximum records to return.
            language: Optional language filter.
            symbol_kind: Optional kind filter (function, class, …).
            file_path: Optional exact file path filter.
            name_query: Optional prefix/substring search on ``name``.

        Returns:
            Tuple of (symbols, total_count).
        """
        filters: list[Any] = [ParsedSymbol.repo_id == repo_id]
        if language:
            filters.append(ParsedSymbol.language == language)
        if symbol_kind:
            filters.append(ParsedSymbol.symbol_kind == symbol_kind)
        if file_path:
            filters.append(ParsedSymbol.file_path == file_path)
        if name_query:
            filters.append(
                ParsedSymbol.name.ilike(f"%{name_query}%")
            )
        return await self.list(
            offset=offset,
            limit=limit,
            filters=filters,
            order_by=ParsedSymbol.file_path,
        )

    async def list_for_file(
        self, repo_id: uuid.UUID, file_path: str
    ) -> list[ParsedSymbol]:
        """Return all symbols in a specific file, ordered by line number.

        Args:
            repo_id: UUID of the parent repository.
            file_path: Relative file path within the repository.

        Returns:
            List of ParsedSymbol instances ordered by start_line.
        """
        result = await self._session.execute(
            select(ParsedSymbol)
            .where(
                ParsedSymbol.repo_id == repo_id,
                ParsedSymbol.file_path == file_path,
            )
            .order_by(ParsedSymbol.start_line)
        )
        return list(result.scalars().all())

    async def get_language_breakdown(
        self, repo_id: uuid.UUID
    ) -> dict[str, int]:
        """Return symbol counts grouped by language for a repository.

        Args:
            repo_id: UUID of the repository.

        Returns:
            Dict mapping language slug to symbol count.
        """
        result = await self._session.execute(
            select(ParsedSymbol.language, func.count(ParsedSymbol.id).label("cnt"))
            .where(ParsedSymbol.repo_id == repo_id)
            .group_by(ParsedSymbol.language)
        )
        return {row.language: row.cnt for row in result}

    async def count_for_repo(self, repo_id: uuid.UUID) -> int:
        """Return the total number of symbols for a repository.

        Args:
            repo_id: UUID of the repository.

        Returns:
            Integer count.
        """
        result = await self._session.execute(
            select(func.count(ParsedSymbol.id)).where(
                ParsedSymbol.repo_id == repo_id
            )
        )
        return result.scalar_one()

    async def count_files_parsed(self, repo_id: uuid.UUID) -> int:
        """Return the number of distinct files that have symbols.

        Args:
            repo_id: UUID of the repository.

        Returns:
            Distinct file count.
        """
        result = await self._session.execute(
            select(func.count(distinct(ParsedSymbol.file_path))).where(
                ParsedSymbol.repo_id == repo_id
            )
        )
        return result.scalar_one()

    async def delete_for_repo(self, repo_id: uuid.UUID) -> int:
        """Delete all symbols for a repository (used before re-indexing).

        Args:
            repo_id: UUID of the repository to clear.

        Returns:
            Number of rows deleted.
        """
        result = await self._session.execute(
            delete(ParsedSymbol).where(ParsedSymbol.repo_id == repo_id)
        )
        return result.rowcount

    async def bulk_upsert(self, symbols: list[dict[str, Any]]) -> int:
        """Insert or update multiple symbol records efficiently.

        Uses PostgreSQL ``INSERT ... ON CONFLICT DO UPDATE`` via raw SQL
        for maximum throughput on large repos.

        Args:
            symbols: List of dicts with ParsedSymbol column values.

        Returns:
            Number of rows affected.
        """
        if not symbols:
            return 0

        stmt = text(
            """
            INSERT INTO parsed_symbols (
                id, repo_id, file_path, file_type, language, symbol_kind,
                name, qualified_name, start_line, end_line,
                docstring, signature, parent_name, decorators, extras,
                created_at, updated_at
            ) VALUES (
                gen_random_uuid(), :repo_id, :file_path, :file_type, :language,
                :symbol_kind, :name, :qualified_name, :start_line, :end_line,
                :docstring, :signature, :parent_name,
                CAST(:decorators AS jsonb), CAST(:extras AS jsonb),
                now(), now()
            )
            ON CONFLICT (repo_id, file_path, symbol_kind, qualified_name)
            DO UPDATE SET
                start_line    = EXCLUDED.start_line,
                end_line      = EXCLUDED.end_line,
                docstring     = EXCLUDED.docstring,
                signature     = EXCLUDED.signature,
                decorators    = EXCLUDED.decorators,
                extras        = EXCLUDED.extras,
                updated_at    = now()
            """
        )
        import json

        rows = []
        for s in symbols:
            rows.append(
                {
                    **s,
                    "decorators": json.dumps(s.get("decorators") or []),
                    "extras": json.dumps(s.get("extras") or {}),
                }
            )

        await self._session.execute(stmt, rows)
        return len(rows)
