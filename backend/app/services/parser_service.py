"""Parser service — async orchestrator for the symbol extraction pipeline.

Responsibilities:
- Stream repository files from MinIO.
- Dispatch file parse jobs to the appropriate language parser.
- Persist extracted symbols to PostgreSQL via SymbolRepository.
- Return status and search results via the API.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.repositories.symbol_repository import SymbolRepository
from app.schemas.parser import (
    FileSymbolsResponse,
    ParseStatusResponse,
    SymbolListResponse,
    SymbolResponse,
)

logger = get_logger(__name__)


class ParserService:
    """Async service layer for symbol querying and parse status reporting.

    This service is used by the API layer. The actual parsing work runs
    inside Celery workers via ``parser_tasks.parse_repository``.

    Attributes:
        _symbol_repo: Data access layer for ParsedSymbol records.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialise with a database session.

        Args:
            session: Active async SQLAlchemy session.
        """
        self._symbol_repo = SymbolRepository(session)

    async def get_parse_status(self, repo_id: uuid.UUID) -> ParseStatusResponse:
        """Return the parsing progress summary for a repository.

        Args:
            repo_id: UUID of the target repository.

        Returns:
            ParseStatusResponse with file/symbol counts and language breakdown.
        """
        total_symbols = await self._symbol_repo.count_for_repo(repo_id)
        parsed_files = await self._symbol_repo.count_files_parsed(repo_id)
        language_breakdown = await self._symbol_repo.get_language_breakdown(repo_id)

        parse_status = "complete" if total_symbols > 0 else "pending"

        return ParseStatusResponse(
            repo_id=repo_id,
            parse_status=parse_status,
            total_files=parsed_files,
            parsed_files=parsed_files,
            total_symbols=total_symbols,
            languages=language_breakdown,
            error_message=None,
        )

    async def list_symbols(
        self,
        repo_id: uuid.UUID,
        *,
        page: int = 1,
        limit: int = 50,
        language: str | None = None,
        symbol_kind: str | None = None,
        file_path: str | None = None,
        name_query: str | None = None,
    ) -> SymbolListResponse:
        """Return a paginated, filtered list of symbols for a repository.

        Args:
            repo_id: UUID of the repository.
            page: 1-indexed page number.
            limit: Items per page.
            language: Optional language filter.
            symbol_kind: Optional symbol kind filter.
            file_path: Optional exact file path filter.
            name_query: Optional name substring search.

        Returns:
            Paginated SymbolListResponse.
        """
        offset = (page - 1) * limit
        symbols, total = await self._symbol_repo.list_for_repo(
            repo_id,
            offset=offset,
            limit=limit,
            language=language,
            symbol_kind=symbol_kind,
            file_path=file_path,
            name_query=name_query,
        )
        return SymbolListResponse(
            total=total,
            page=page,
            limit=limit,
            has_next=(offset + len(symbols)) < total,
            items=[SymbolResponse.model_validate(s) for s in symbols],
        )

    async def get_file_symbols(
        self, repo_id: uuid.UUID, file_path: str
    ) -> FileSymbolsResponse | None:
        """Return all symbols for a specific file in a repository.

        Args:
            repo_id: UUID of the repository.
            file_path: Relative file path within the repository.

        Returns:
            FileSymbolsResponse, or None if no symbols exist for this file.
        """
        symbols = await self._symbol_repo.list_for_file(repo_id, file_path)
        if not symbols:
            return None

        first = symbols[0]
        return FileSymbolsResponse(
            file_path=file_path,
            language=first.language,
            file_type=first.file_type,
            symbol_count=len(symbols),
            symbols=[SymbolResponse.model_validate(s) for s in symbols],
        )

    async def get_symbol(self, symbol_id: uuid.UUID) -> SymbolResponse | None:
        """Return a single symbol by its UUID.

        Args:
            symbol_id: UUID of the ParsedSymbol record.

        Returns:
            SymbolResponse, or None if not found.
        """
        symbol = await self._symbol_repo.get_by_id(symbol_id)
        if symbol is None:
            return None
        return SymbolResponse.model_validate(symbol)
