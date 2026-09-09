"""Pydantic v2 schemas for Repository request / response payloads."""

import uuid
from datetime import datetime

from pydantic import AnyHttpUrl, BaseModel, Field, field_validator, model_validator


# ── Request schemas ───────────────────────────────────────────────────────────


class RepositoryCreate(BaseModel):
    """Payload for importing a new repository.

    Either ``url`` (remote clone) or ``local_path`` (pre-mounted volume)
    must be provided, but not both.

    Attributes:
        url: HTTPS or SSH remote clone URL.
        local_path: Absolute path inside the container (for local imports).
        name: Optional display name; auto-derived from the URL/path if omitted.
        provider: Hint for the hosting provider (github, gitlab, bitbucket).
        default_branch: Branch to clone and index.
        auth_token: Personal access token for private HTTPS repos.
        ssh_key_id: UUID of a stored SSH key for private SSH repos.
        is_private: Mark the repository as private.
    """

    url: str | None = Field(
        default=None,
        description="HTTPS or SSH clone URL of the repository",
        examples=["https://github.com/org/repo"],
    )
    local_path: str | None = Field(
        default=None,
        description="Absolute container path for local imports",
        examples=["/mnt/repos/my-service"],
    )
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="Display name; auto-derived if omitted",
    )
    provider: str | None = Field(
        default=None,
        description="Hosting provider hint: github | gitlab | bitbucket | local",
        examples=["github"],
    )
    default_branch: str = Field(
        default="main",
        min_length=1,
        max_length=100,
        description="Branch to clone and index",
    )
    auth_token: str | None = Field(
        default=None,
        description="PAT for private HTTPS repos (never stored, used only at clone time)",
    )
    ssh_key_id: uuid.UUID | None = Field(
        default=None,
        description="UUID of a stored SSH key credential",
    )
    is_private: bool = Field(default=False)
    zip_minio_key: str | None = Field(
        default=None,
        description="MinIO object key of a pre-uploaded ZIP archive (set by upload endpoint)",
    )

    @model_validator(mode="after")
    def require_url_or_local_path(self) -> "RepositoryCreate":
        """Ensure exactly one of url / local_path / zip_minio_key is provided."""
        sources = [v for v in (self.url, self.local_path, self.zip_minio_key) if v]
        if not sources:
            raise ValueError("One of 'url', 'local_path', or 'zip_minio_key' must be provided.")
        if len(sources) > 1:
            raise ValueError("Provide only one of 'url', 'local_path', or 'zip_minio_key'.")
        return self

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str | None) -> str | None:
        """Accept HTTPS and SSH git URLs."""
        if v is None:
            return v
        if not (v.startswith("https://") or v.startswith("git@") or v.startswith("ssh://")):
            raise ValueError("URL must be an HTTPS or SSH git URL.")
        return v


class RepositoryUpdate(BaseModel):
    """Partial update payload for an existing repository.

    All fields are optional — only provided fields are updated.

    Attributes:
        name: New display name.
        description: Updated description.
        default_branch: New default branch for future re-indexing.
    """

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    default_branch: str | None = Field(default=None, min_length=1, max_length=100)


class ReindexRequest(BaseModel):
    """Payload for triggering a re-indexing run.

    Attributes:
        job_type: Type of re-index to perform.
        force_full: Force a full re-index even if incremental is possible.
    """

    job_type: str = Field(
        default="full_index",
        description="full_index | incremental | parse_only | embed_only",
    )
    force_full: bool = Field(
        default=False,
        description="Bypass incremental detection and run a full re-index",
    )


# ── Response schemas ──────────────────────────────────────────────────────────


class IndexJobResponse(BaseModel):
    """Minimal representation of an IndexJob returned alongside repository responses.

    Attributes:
        id: Job UUID.
        job_type: Type of indexing work.
        status: Lifecycle status.
        progress: Completion percentage 0-100.
        current_stage: Label of the active pipeline stage.
        celery_task_id: The Celery task identifier for external polling.
        started_at: When the worker picked up the task.
        finished_at: When the task reached a terminal state.
        created_at: When the job record was inserted.
    """

    id: uuid.UUID
    job_type: str
    status: str
    progress: int
    current_stage: str | None
    celery_task_id: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class RepositoryResponse(BaseModel):
    """Full repository representation returned by the API.

    Attributes:
        id: Repository UUID.
        name: Display name.
        url: Remote clone URL.
        provider: Hosting provider.
        default_branch: Indexed branch.
        description: Short description.
        tech_stack: Detected technology stack as a nested JSON object.
        stats: Aggregate statistics (files, LOC, contributors).
        index_status: Current lifecycle status.
        last_indexed_at: Most recent successful full-index timestamp.
        error_message: Last error if status is 'failed'.
        is_private: Whether the repository is private.
        created_at: Record creation timestamp.
        updated_at: Record last-update timestamp.
        latest_job: The most recent IndexJob for this repository, if any.
    """

    id: uuid.UUID
    name: str
    url: str | None
    provider: str | None
    default_branch: str
    description: str | None
    tech_stack: dict | None
    stats: dict | None
    index_status: str
    last_indexed_at: datetime | None
    error_message: str | None
    is_private: bool
    created_at: datetime
    updated_at: datetime
    latest_job: IndexJobResponse | None = None

    model_config = {"from_attributes": True}


class RepositoryListResponse(BaseModel):
    """Paginated list of repositories.

    Attributes:
        total: Total number of repositories matching the query.
        page: Current page number (1-indexed).
        limit: Number of items per page.
        has_next: Whether a subsequent page exists.
        items: Repository records for this page.
    """

    total: int
    page: int
    limit: int
    has_next: bool
    items: list[RepositoryResponse]


class RepositoryStatusResponse(BaseModel):
    """Detailed indexing status response for a single repository.

    Attributes:
        repo_id: Repository UUID.
        index_status: Repository-level lifecycle status.
        latest_job: Full details of the most recent IndexJob.
    """

    repo_id: uuid.UUID
    index_status: str
    latest_job: IndexJobResponse | None
