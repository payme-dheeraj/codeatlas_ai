"""Pydantic v2 schemas for the Diagram Generator feature."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class DiagramType(str, Enum):
    architecture = "architecture"
    dependency = "dependency"
    sequence = "sequence"
    er = "er"
    deployment = "deployment"
    component_map = "component_map"
    data_flow = "data_flow"


class DiagramFormat(str, Enum):
    mermaid = "mermaid"
    plantuml = "plantuml"
    d2 = "d2"


class RenderFormat(str, Enum):
    svg = "svg"
    png = "png"
    source = "source"


# ── Request schemas ───────────────────────────────────────────────────────────


class GenerateDiagramRequest(BaseModel):
    """Payload to generate one or more diagrams.

    Attributes:
        repo_id: UUID of the repository.
        diagram_types: Types to generate (defaults to architecture + dependency + er).
        diagram_format: Source format for diagram code.
        force_regenerate: Skip checksum cache and regenerate.
        options: Generator-specific options dict (e.g. focus_symbol, max_nodes).
    """

    repo_id: uuid.UUID
    diagram_types: list[DiagramType] = Field(
        default_factory=lambda: [
            DiagramType.architecture,
            DiagramType.dependency,
            DiagramType.er,
        ]
    )
    diagram_format: DiagramFormat = DiagramFormat.mermaid
    force_regenerate: bool = False
    options: dict = Field(default_factory=dict)


# ── Response schemas ──────────────────────────────────────────────────────────


class DiagramResponse(BaseModel):
    """A generated diagram artifact.

    Attributes:
        id: UUID of the diagram record.
        repo_id: UUID of the repository.
        diagram_type: Type slug.
        diagram_format: Source format.
        title: Diagram title.
        source_code: Raw diagram source text.
        render_url_svg: SVG render URL (if available).
        render_url_png: PNG render URL (if available).
        version: Version number.
        is_latest: Latest version flag.
        created_at: Creation timestamp.
    """

    id: uuid.UUID
    repo_id: uuid.UUID
    diagram_type: str
    diagram_format: str
    title: str
    source_code: str
    render_url_svg: str | None
    render_url_png: str | None
    version: int
    is_latest: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class DiagramSummaryResponse(BaseModel):
    """Lightweight diagram summary (without source_code).

    Attributes:
        id: UUID of the diagram.
        repo_id: UUID of the repository.
        diagram_type: Type slug.
        diagram_format: Source format.
        title: Title.
        render_url_svg: SVG URL.
        render_url_png: PNG URL.
        version: Version number.
        is_latest: Latest flag.
        created_at: Creation timestamp.
    """

    id: uuid.UUID
    repo_id: uuid.UUID
    diagram_type: str
    diagram_format: str
    title: str
    render_url_svg: str | None
    render_url_png: str | None
    version: int
    is_latest: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class DiagramGenerationJobResponse(BaseModel):
    """Status response for a diagram generation batch.

    Attributes:
        job_id: Celery task ID.
        repo_id: UUID of the repository.
        diagram_types: Requested types.
        status: queued | running | complete | failed.
    """

    job_id: str
    repo_id: uuid.UUID
    diagram_types: list[str]
    status: str
