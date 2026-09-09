"""Unit tests for RepoService business logic.

Uses AsyncMock to isolate the service from database and Celery.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.index_job import IndexJob
from app.models.repository import Repository
from app.schemas.repository import ReindexRequest, RepositoryCreate, RepositoryUpdate
from app.services.repo_service import RepoService, _derive_name_from_url, _detect_provider


# ── Helpers ────────────────────────────────────────────────────────────────────


def make_repo(**kwargs) -> Repository:
    """Build a mock Repository ORM instance."""
    defaults = dict(
        id=uuid.uuid4(),
        name="test-repo",
        url="https://github.com/org/test-repo",
        provider="github",
        default_branch="main",
        is_private=False,
        description=None,
        tech_stack=None,
        stats=None,
        clone_path=None,
        index_status="pending",
        last_indexed_at=None,
        error_message=None,
    )
    defaults.update(kwargs)
    repo = MagicMock(spec=Repository)
    for k, v in defaults.items():
        setattr(repo, k, v)
    return repo


def make_job(**kwargs) -> IndexJob:
    """Build a mock IndexJob ORM instance."""
    defaults = dict(
        id=uuid.uuid4(),
        repo_id=uuid.uuid4(),
        job_type="full_index",
        status="queued",
        progress=0,
        current_stage=None,
        celery_task_id=None,
        error_message=None,
        started_at=None,
        finished_at=None,
    )
    defaults.update(kwargs)
    job = MagicMock(spec=IndexJob)
    for k, v in defaults.items():
        setattr(job, k, v)
    return job


# ── Pure unit tests (no DB) ────────────────────────────────────────────────────


class TestDeriveName:
    """Tests for _derive_name_from_url helper."""

    def test_https_url(self) -> None:
        assert _derive_name_from_url("https://github.com/org/my-service.git") == "my-service"

    def test_ssh_url(self) -> None:
        assert _derive_name_from_url("git@github.com:org/repo-name.git") == "repo-name"

    def test_no_git_suffix(self) -> None:
        assert _derive_name_from_url("https://github.com/org/tool") == "tool"

    def test_special_characters_replaced(self) -> None:
        name = _derive_name_from_url("https://github.com/org/my service")
        assert " " not in name


class TestDetectProvider:
    """Tests for _detect_provider helper."""

    def test_github(self) -> None:
        assert _detect_provider("https://github.com/org/repo") == "github"

    def test_gitlab(self) -> None:
        assert _detect_provider("https://gitlab.com/org/repo") == "gitlab"

    def test_bitbucket(self) -> None:
        assert _detect_provider("https://bitbucket.org/org/repo") == "bitbucket"

    def test_unknown(self) -> None:
        assert _detect_provider("https://my-git.internal/org/repo") is None


# ── Service unit tests (mocked repositories) ──────────────────────────────────


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(mock_session: AsyncMock) -> RepoService:
    return RepoService(mock_session)


class TestImportRepository:
    """Unit tests for RepoService.import_repository."""

    @pytest.mark.asyncio
    async def test_creates_repo_and_dispatches_task(self, service: RepoService) -> None:
        """Happy path: repo created, job queued, Celery task dispatched."""
        repo = make_repo()
        job = make_job(repo_id=repo.id)

        with (
            patch.object(service._repo_repo, "get_by_url", new=AsyncMock(return_value=None)),
            patch.object(
                service._repo_repo, "get_by_name_and_owner", new=AsyncMock(return_value=None)
            ),
            patch.object(service._repo_repo, "create", new=AsyncMock(return_value=repo)),
            patch.object(service._job_repo, "create", new=AsyncMock(return_value=job)),
            patch.object(service._job_repo, "update", new=AsyncMock(return_value=job)),
            patch("app.workers.tasks.repo_tasks.clone_and_index_repo") as mock_task,
        ):
            mock_task.apply_async.return_value = MagicMock(id="celery-task-id")

            result = await service.import_repository(
                RepositoryCreate(url="https://github.com/org/test-repo")
            )

        assert result.name == repo.name
        assert result.index_status == "pending"
        mock_task.apply_async.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_on_duplicate_url(self, service: RepoService) -> None:
        """Should raise ValueError when URL already exists."""
        existing = make_repo()
        with patch.object(
            service._repo_repo, "get_by_url", new=AsyncMock(return_value=existing)
        ):
            with pytest.raises(ValueError, match="already exists"):
                await service.import_repository(
                    RepositoryCreate(url="https://github.com/org/test-repo")
                )

    @pytest.mark.asyncio
    async def test_auto_derives_name_from_url(self, service: RepoService) -> None:
        """Name should be derived from URL if not provided in payload."""
        repo = make_repo(name="my-service")
        job = make_job(repo_id=repo.id)

        with (
            patch.object(service._repo_repo, "get_by_url", new=AsyncMock(return_value=None)),
            patch.object(
                service._repo_repo, "get_by_name_and_owner", new=AsyncMock(return_value=None)
            ),
            patch.object(service._repo_repo, "create", new=AsyncMock(return_value=repo)) as mock_create,
            patch.object(service._job_repo, "create", new=AsyncMock(return_value=job)),
            patch.object(service._job_repo, "update", new=AsyncMock(return_value=job)),
            patch("app.workers.tasks.repo_tasks.clone_and_index_repo") as mock_task,
        ):
            mock_task.apply_async.return_value = MagicMock(id="task-id")
            await service.import_repository(
                RepositoryCreate(url="https://github.com/org/my-service.git")
            )

        # Verify the create call used the derived name
        create_kwargs = mock_create.call_args.kwargs
        assert create_kwargs["name"] == "my-service"


class TestGetRepository:
    """Unit tests for RepoService.get_repository."""

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self, service: RepoService) -> None:
        with patch.object(service._repo_repo, "get_by_id", new=AsyncMock(return_value=None)):
            result = await service.get_repository(uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_response_with_latest_job(self, service: RepoService) -> None:
        repo = make_repo()
        job = make_job(repo_id=repo.id)
        with (
            patch.object(service._repo_repo, "get_by_id", new=AsyncMock(return_value=repo)),
            patch.object(
                service._job_repo, "get_latest_for_repo", new=AsyncMock(return_value=job)
            ),
        ):
            result = await service.get_repository(repo.id)
        assert result is not None
        assert result.latest_job is not None
        assert result.latest_job.job_type == "full_index"


class TestDeleteRepository:
    """Unit tests for RepoService.delete_repository."""

    @pytest.mark.asyncio
    async def test_returns_false_when_not_found(self, service: RepoService) -> None:
        with patch.object(service._repo_repo, "get_by_id", new=AsyncMock(return_value=None)):
            result = await service.delete_repository(uuid.uuid4())
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_true_and_dispatches_cleanup(self, service: RepoService) -> None:
        repo = make_repo()
        with (
            patch.object(service._repo_repo, "get_by_id", new=AsyncMock(return_value=repo)),
            patch.object(service._repo_repo, "delete", new=AsyncMock()),
            patch("app.workers.tasks.repo_tasks.delete_repo_artifacts") as mock_cleanup,
        ):
            mock_cleanup.apply_async.return_value = MagicMock()
            result = await service.delete_repository(repo.id)
        assert result is True


class TestReindexRepository:
    """Unit tests for RepoService.trigger_reindex."""

    @pytest.mark.asyncio
    async def test_blocks_when_active_job_exists(self, service: RepoService) -> None:
        repo = make_repo()
        active_job = make_job(status="running")
        with (
            patch.object(service._repo_repo, "get_by_id", new=AsyncMock(return_value=repo)),
            patch.object(
                service._job_repo,
                "get_active_job_for_repo",
                new=AsyncMock(return_value=active_job),
            ),
        ):
            with pytest.raises(ValueError, match="already being indexed"):
                await service.trigger_reindex(repo.id, ReindexRequest(force_full=False))

    @pytest.mark.asyncio
    async def test_force_full_bypasses_active_check(self, service: RepoService) -> None:
        repo = make_repo()
        active_job = make_job(status="running")
        new_job = make_job(repo_id=repo.id)

        with (
            patch.object(service._repo_repo, "get_by_id", new=AsyncMock(return_value=repo)),
            patch.object(
                service._job_repo,
                "get_active_job_for_repo",
                new=AsyncMock(return_value=active_job),
            ),
            patch.object(service._job_repo, "create", new=AsyncMock(return_value=new_job)),
            patch.object(service._job_repo, "update", new=AsyncMock(return_value=new_job)),
            patch.object(
                service._repo_repo, "update_status", new=AsyncMock(return_value=repo)
            ),
            patch.object(
                service, "get_repository", new=AsyncMock(return_value=MagicMock())
            ),
            patch("app.workers.tasks.repo_tasks.clone_and_index_repo") as mock_task,
        ):
            mock_task.apply_async.return_value = MagicMock(id="task-id")
            result = await service.trigger_reindex(repo.id, ReindexRequest(force_full=True))

        assert result is not None


class TestRepoStatusStream:
    """Unit tests for the SSE status streaming endpoint."""

    @pytest.mark.asyncio
    async def test_stream_status_not_found(self, service: RepoService) -> None:
        from fastapi import HTTPException
        from app.api.v1.endpoints.repositories import stream_repository_status

        repo_id = uuid.uuid4()
        with patch.object(service, "get_status", new=AsyncMock(return_value=None)):
            with pytest.raises(HTTPException) as exc_info:
                await stream_repository_status(repo_id, service)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_stream_status_generator(self, service: RepoService) -> None:
        from app.api.v1.endpoints.repositories import stream_repository_status
        from app.schemas.repository import RepositoryStatusResponse

        repo_id = uuid.uuid4()
        status_resp = RepositoryStatusResponse(
            repo_id=repo_id,
            index_status="complete",
            latest_job=None,
        )

        with patch.object(service, "get_status", new=AsyncMock(return_value=status_resp)):
            resp = await stream_repository_status(repo_id, service)
            assert resp.media_type == "text/event-stream"
            assert resp.headers["Cache-Control"] == "no-cache"

            chunks = []
            async for chunk in resp.body_iterator:
                chunks.append(chunk)

            combined = "".join(chunks)
            assert "complete" in combined
            assert "[DONE]" in combined

