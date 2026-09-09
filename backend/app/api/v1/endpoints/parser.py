"""Parser / symbol endpoints.

Route prefix: /api/v1/repos/{repo_id}/symbols
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_optional_current_user_id as get_current_user_id, get_parser_service
from app.schemas.parser import (
    FileSymbolsResponse,
    ParseStatusResponse,
    SymbolListResponse,
    SymbolResponse,
)
from app.services.parser_service import ParserService

router = APIRouter(tags=["parser"])


@router.get(
    "/repos/{repo_id}/parse-status",
    response_model=ParseStatusResponse,
    summary="Get parsing status for a repository",
    responses={
        200: {"description": "Parse status and symbol counts"},
        401: {"description": "Not authenticated"},
    },
)
async def get_parse_status(
    repo_id: uuid.UUID,
    _: uuid.UUID | None = Depends(get_current_user_id),
    service: ParserService = Depends(get_parser_service),
) -> ParseStatusResponse:
    """Return symbol extraction progress for a repository.

    Args:
        repo_id: UUID of the target repository.
        _: Authenticated user (access guard).
        service: Injected ParserService.

    Returns:
        ParseStatusResponse with file/symbol counts and language breakdown.
    """
    return await service.get_parse_status(repo_id)


@router.get(
    "/repos/{repo_id}/symbols",
    response_model=SymbolListResponse,
    summary="List symbols extracted from a repository",
    description=(
        "Returns a paginated, filterable list of all code symbols "
        "(functions, classes, methods, interfaces, …) extracted from the "
        "repository source files."
    ),
    responses={
        200: {"description": "Paginated symbol list"},
        401: {"description": "Not authenticated"},
    },
)
async def list_symbols(
    repo_id: uuid.UUID,
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)"),
    limit: int = Query(default=50, ge=1, le=200, description="Items per page"),
    language: str | None = Query(default=None, description="Filter by language slug"),
    symbol_kind: str | None = Query(
        default=None,
        alias="kind",
        description="Filter by symbol kind: function | class | method | interface | …",
    ),
    file_path: str | None = Query(default=None, description="Filter to a specific file path"),
    name_query: str | None = Query(
        default=None, alias="q", description="Substring search on symbol name"
    ),
    _: uuid.UUID | None = Depends(get_current_user_id),
    service: ParserService = Depends(get_parser_service),
) -> SymbolListResponse:
    """Return symbols for a repository with optional filters.

    Args:
        repo_id: UUID of the repository.
        page: Page number.
        limit: Page size.
        language: Language slug filter.
        symbol_kind: Symbol kind filter.
        file_path: Exact file path filter.
        name_query: Name substring filter.
        _: Authenticated user.
        service: Injected ParserService.

    Returns:
        Paginated SymbolListResponse.
    """
    return await service.list_symbols(
        repo_id,
        page=page,
        limit=limit,
        language=language,
        symbol_kind=symbol_kind,
        file_path=file_path,
        name_query=name_query,
    )


@router.get(
    "/repos/{repo_id}/symbols/file",
    response_model=FileSymbolsResponse,
    summary="Get all symbols for a specific file",
    responses={
        200: {"description": "File symbols"},
        401: {"description": "Not authenticated"},
        404: {"description": "No symbols found for this file"},
    },
)
async def get_file_symbols(
    repo_id: uuid.UUID,
    path: str = Query(description="Relative file path within the repository"),
    _: uuid.UUID | None = Depends(get_current_user_id),
    service: ParserService = Depends(get_parser_service),
) -> FileSymbolsResponse:
    """Return all symbols extracted from a specific source file.

    Args:
        repo_id: UUID of the repository.
        path: Relative file path (e.g. ``src/services/auth.py``).
        _: Authenticated user.
        service: Injected ParserService.

    Returns:
        FileSymbolsResponse with all symbols in the file.

    Raises:
        HTTPException 404: If no symbols exist for this file.
    """
    result = await service.get_file_symbols(repo_id, path)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No symbols found for file '{path}' in repository '{repo_id}'.",
        )
    return result


@router.get(
    "/symbols/{symbol_id}",
    response_model=SymbolResponse,
    summary="Get a symbol by ID",
    responses={
        200: {"description": "Symbol details"},
        401: {"description": "Not authenticated"},
        404: {"description": "Symbol not found"},
    },
)
async def get_symbol(
    symbol_id: uuid.UUID,
    _: uuid.UUID | None = Depends(get_current_user_id),
    service: ParserService = Depends(get_parser_service),
) -> SymbolResponse:
    """Retrieve a single parsed symbol by its UUID.

    Args:
        symbol_id: UUID of the ParsedSymbol record.
        _: Authenticated user.
        service: Injected ParserService.

    Returns:
        SymbolResponse.

    Raises:
        HTTPException 404: If the symbol does not exist.
    """
    result = await service.get_symbol(symbol_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Symbol '{symbol_id}' not found.",
        )
    return result
