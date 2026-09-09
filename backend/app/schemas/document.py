"""Pydantic v2 schemas for the Documentation Service."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DocType(str, Enum):
    readme = "readme"
    api_reference = "api_reference"
    deployment_guide = "deployment_guide"
    adr = "adr"
    wiki = "wiki"
    changelog = "changelog"
    onboarding = "onboarding"


class ExportFormat(str, Enum):
    markdown = "markdown"
    html = "html"
    confluence = "confluence"
    notion = "notion"


# ── Request schemas ───────────────────────────────────────────────────────────


class GenerateDocsRequest(BaseModel):
    """Payload to trigger document generation.

    Attributes:
        repo_id: UUID of the repository.
        doc_types: Document types to generate (defaults to readme + wiki).
        force_regenerate: If True, regenerate even if current version exists.
        llm_provider: Override LLM provider.
        llm_model: Override LLM model.
    """

    repo_id: uuid.UUID
    doc_types: list[DocType] = Field(
        default_factory=lambda: [DocType.readme, DocType.wiki]
    )
    force_regenerate: bool = False
    llm_provider: str | None = None
    llm_model: str | None = None


class ExportDocRequest(BaseModel):
    """Request to export a document in an alternative format.

    Attributes:
        format: Target export format.
    """

    format: ExportFormat = ExportFormat.markdown


# ── Response schemas ──────────────────────────────────────────────────────────


class DocumentResponse(BaseModel):
    """A generated document.

    Attributes:
        id: UUID of the document record.
        repo_id: UUID of the repository.
        doc_type: Document type slug.
        title: Document title.
        content_md: Markdown content.
        version: Version number.
        is_latest: True if this is the current version.
        generation_model: LLM model used.
        created_at: Creation timestamp.
    """

    id: uuid.UUID
    repo_id: uuid.UUID
    doc_type: str
    title: str
    content_md: str
    version: int
    is_latest: bool
    generation_model: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentSummaryResponse(BaseModel):
    """Lightweight document summary (without full content).

    Attributes:
        id: UUID of the document.
        repo_id: UUID of the repository.
        doc_type: Type slug.
        title: Title string.
        version: Version number.
        is_latest: Latest flag.
        created_at: Creation timestamp.
    """

    id: uuid.UUID
    repo_id: uuid.UUID
    doc_type: str
    title: str
    version: int
    is_latest: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class GenerationJobResponse(BaseModel):
    """Status of a document generation job.

    Attributes:
        id: UUID of the job.
        repo_id: UUID of the repository.
        doc_types: Requested document types.
        status: queued | running | complete | failed.
        progress: 0-100 percentage.
        current_stage: Human-readable stage.
        error_message: Error if failed.
        started_at: When job started.
        finished_at: When job finished.
        created_at: Job creation time.
    """

    id: uuid.UUID
    repo_id: uuid.UUID
    doc_types: list[str]
    status: str
    progress: int
    current_stage: str | None
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentVersionListResponse(BaseModel):
    """List of document versions.

    Attributes:
        doc_type: Document type slug.
        total: Total version count.
        versions: List of summaries ordered newest-first.
    """

    doc_type: str
    total: int
    versions: list[DocumentSummaryResponse]
