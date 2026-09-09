"""Pydantic v2 schemas for parser request / response payloads."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class SymbolResponse(BaseModel):
    """Public representation of a single parsed code symbol.

    Attributes:
        id: Symbol UUID.
        repo_id: Parent repository UUID.
        file_path: Relative path within the repository.
        file_type: Classified file role.
        language: Programming language slug.
        symbol_kind: Kind of symbol (function, class, method, …).
        name: Unqualified symbol name.
        qualified_name: Fully scoped name.
        start_line: Starting line number (1-indexed).
        end_line: Ending line number (1-indexed).
        docstring: Extracted documentation comment.
        signature: Function/method signature.
        parent_name: Enclosing class or module name.
        decorators: List of decorator/annotation names.
        extras: Language-specific metadata blob.
        created_at: Record creation timestamp.
    """

    id: uuid.UUID
    repo_id: uuid.UUID
    file_path: str
    file_type: str
    language: str
    symbol_kind: str
    name: str
    qualified_name: str
    start_line: int
    end_line: int
    docstring: str | None
    signature: str | None
    parent_name: str | None
    decorators: list | None
    extras: dict | None
    created_at: datetime

    model_config = {"from_attributes": True}


class SymbolListResponse(BaseModel):
    """Paginated list of symbols.

    Attributes:
        total: Total symbols matching the query.
        page: Current page (1-indexed).
        limit: Items per page.
        has_next: Whether more pages exist.
        items: Symbol records for this page.
    """

    total: int
    page: int
    limit: int
    has_next: bool
    items: list[SymbolResponse]


class ParseStatusResponse(BaseModel):
    """Parsing progress for a repository.

    Attributes:
        repo_id: Repository UUID.
        parse_status: Current parse lifecycle state.
        total_files: Number of files discovered.
        parsed_files: Number of files successfully parsed.
        total_symbols: Total symbols extracted so far.
        languages: Detected language breakdown.
        error_message: Last error if parsing failed.
    """

    repo_id: uuid.UUID
    parse_status: str
    total_files: int
    parsed_files: int
    total_symbols: int
    languages: dict[str, int]
    error_message: str | None


class FileSymbolsResponse(BaseModel):
    """All symbols extracted from a single file.

    Attributes:
        file_path: Relative path within the repository.
        language: Detected programming language.
        file_type: Classified file role.
        symbol_count: Total symbols in this file.
        symbols: All symbol records for this file.
    """

    file_path: str
    language: str
    file_type: str
    symbol_count: int
    symbols: list[SymbolResponse]
