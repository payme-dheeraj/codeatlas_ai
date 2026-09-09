"""Diagram Generator endpoints.

Routes:
  POST /repos/{repo_id}/diagrams/generate   — trigger diagram generation
  GET  /repos/{repo_id}/diagrams             — list all latest diagrams
  GET  /repos/{repo_id}/diagrams/{type}      — get latest diagram by type
  GET  /diagrams/{diagram_id}                — get diagram by UUID
  GET  /diagrams/{diagram_id}/source         — download raw source code
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.deps import get_optional_current_user_id as get_current_user_id, get_diagram_service
from app.schemas.diagram import (
    DiagramGenerationJobResponse,
    DiagramResponse,
    DiagramSummaryResponse,
    GenerateDiagramRequest,
    RenderFormat,
)
from app.services.diagram_service import DiagramService

router = APIRouter(tags=["diagrams"])


@router.post(
    "/repos/{repo_id}/diagrams/generate",
    response_model=DiagramGenerationJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger diagram generation for a repository",
    responses={
        202: {"description": "Generation task queued"},
        401: {"description": "Not authenticated"},
    },
)
async def generate_diagrams(
    repo_id: uuid.UUID,
    request: GenerateDiagramRequest,
    _: uuid.UUID | None = Depends(get_current_user_id),
    service: DiagramService = Depends(get_diagram_service),
) -> DiagramGenerationJobResponse:
    """Queue diagram generation for a repository.

    Args:
        repo_id: UUID of the repository (path parameter).
        request: Generation parameters (diagram_types, format, options).
        _: Authenticated user UUID.
        service: Injected DiagramService.

    Returns:
        DiagramGenerationJobResponse with Celery task ID.
    """
    request.repo_id = repo_id
    return await service.trigger_generation(request)


@router.get(
    "/repos/{repo_id}/diagrams",
    response_model=list[DiagramSummaryResponse],
    summary="List all generated diagrams for a repository",
    responses={
        200: {"description": "List of latest diagram summaries"},
        401: {"description": "Not authenticated"},
    },
)
async def list_diagrams(
    repo_id: uuid.UUID,
    _: uuid.UUID | None = Depends(get_current_user_id),
    service: DiagramService = Depends(get_diagram_service),
) -> list[DiagramSummaryResponse]:
    """Return all latest-version diagrams for a repository.

    Args:
        repo_id: UUID of the repository.
        _: Authenticated user UUID.
        service: Injected DiagramService.

    Returns:
        List of DiagramSummaryResponse.
    """
    return await service.list_diagrams(repo_id)


@router.get(
    "/repos/{repo_id}/diagrams/{diagram_type}",
    response_model=DiagramResponse,
    summary="Get the latest diagram of a specific type",
    responses={
        200: {"description": "Diagram with source and render URLs"},
        401: {"description": "Not authenticated"},
        404: {"description": "Diagram not found"},
    },
)
async def get_diagram_by_type(
    repo_id: uuid.UUID,
    diagram_type: str,
    _: uuid.UUID | None = Depends(get_current_user_id),
    service: DiagramService = Depends(get_diagram_service),
) -> DiagramResponse:
    """Return the latest diagram of the specified type.

    Args:
        repo_id: UUID of the repository.
        diagram_type: Diagram type slug (architecture | dependency | sequence | er | deployment).
        _: Authenticated user UUID.
        service: Injected DiagramService.

    Returns:
        DiagramResponse including source_code and render URLs.

    Raises:
        HTTPException 404: If no diagram of this type has been generated.
    """
    result = await service.get_diagram(repo_id, diagram_type)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No '{diagram_type}' diagram found for repository '{repo_id}'. "
                   "Trigger generation first.",
        )
    return result


@router.get(
    "/diagrams/{diagram_id}",
    response_model=DiagramResponse,
    summary="Get a diagram by UUID",
    responses={
        200: {"description": "Diagram detail"},
        401: {"description": "Not authenticated"},
        404: {"description": "Diagram not found"},
    },
)
async def get_diagram(
    diagram_id: uuid.UUID,
    _: uuid.UUID | None = Depends(get_current_user_id),
    service: DiagramService = Depends(get_diagram_service),
) -> DiagramResponse:
    """Return a specific diagram by its UUID.

    Args:
        diagram_id: UUID of the diagram.
        _: Authenticated user UUID.
        service: Injected DiagramService.

    Returns:
        DiagramResponse.

    Raises:
        HTTPException 404: If the diagram does not exist.
    """
    result = await service.get_diagram_by_id(diagram_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Diagram '{diagram_id}' not found.",
        )
    return result


@router.get(
    "/diagrams/{diagram_id}/source",
    summary="Download raw diagram source code",
    description=(
        "Returns the raw Mermaid, PlantUML, or D2 source text. "
        "Use this to render diagrams client-side or in CI/CD pipelines."
    ),
    responses={
        200: {"description": "Diagram source text file"},
        401: {"description": "Not authenticated"},
        404: {"description": "Diagram not found"},
    },
)
async def get_diagram_source(
    diagram_id: uuid.UUID,
    _: uuid.UUID | None = Depends(get_current_user_id),
    service: DiagramService = Depends(get_diagram_service),
) -> Response:
    """Download the raw source code for a diagram.

    Args:
        diagram_id: UUID of the diagram.
        _: Authenticated user UUID.
        service: Injected DiagramService.

    Returns:
        Plain text response with the diagram source.

    Raises:
        HTTPException 404: If the diagram does not exist.
    """
    diagram = await service.get_diagram_by_id(diagram_id)
    if diagram is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Diagram '{diagram_id}' not found.",
        )

    ext_map = {"mermaid": "mmd", "plantuml": "puml", "d2": "d2"}
    ext = ext_map.get(diagram.diagram_format, "txt")
    filename = f"{diagram.diagram_type}_v{diagram.version}.{ext}"

    return Response(
        content=diagram.source_code,
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
