"""MinIO object storage client and helpers.

Provides an async-compatible wrapper around the synchronous MinIO SDK
by running blocking calls in a thread-pool executor.
"""

import asyncio
import io
from pathlib import Path
from typing import BinaryIO

from minio import Minio
from minio.error import S3Error

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class StorageClient:
    """Async-friendly MinIO client.

    All blocking MinIO SDK calls are delegated to the default asyncio
    thread-pool executor via ``asyncio.get_event_loop().run_in_executor``.

    Attributes:
        _client: The underlying synchronous Minio client instance.
        _bucket: The default bucket name for repository objects.
    """

    def __init__(self) -> None:
        """Initialise MinIO client and ensure the default bucket exists."""
        self._client = Minio(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        self._bucket = settings.minio_bucket_repos

    async def ensure_bucket(self, bucket: str | None = None) -> None:
        """Create a bucket if it does not already exist.

        Args:
            bucket: Bucket name; defaults to the configured repos bucket.
        """
        target = bucket or self._bucket
        loop = asyncio.get_event_loop()

        def _create() -> None:
            if not self._client.bucket_exists(target):
                self._client.make_bucket(target)
                logger.info("storage_bucket_created", bucket=target)

        await loop.run_in_executor(None, _create)

    async def put_object(
        self,
        object_name: str,
        data: bytes | BinaryIO,
        length: int = -1,
        content_type: str = "application/octet-stream",
        bucket: str | None = None,
    ) -> str:
        """Upload an object to MinIO.

        Args:
            object_name: Full object key (path within the bucket).
            data: Raw bytes or a file-like object.
            length: Content length; pass -1 to enable streaming upload.
            content_type: MIME type of the object.
            bucket: Target bucket; defaults to the repos bucket.

        Returns:
            The full MinIO object path ``bucket/object_name``.
        """
        target_bucket = bucket or self._bucket
        loop = asyncio.get_event_loop()

        if isinstance(data, bytes):
            stream: BinaryIO = io.BytesIO(data)
            size = len(data)
        else:
            stream = data
            size = length

        def _put() -> None:
            self._client.put_object(
                bucket_name=target_bucket,
                object_name=object_name,
                data=stream,
                length=size,
                content_type=content_type,
            )

        await loop.run_in_executor(None, _put)
        logger.debug("storage_object_uploaded", bucket=target_bucket, key=object_name)
        return f"{target_bucket}/{object_name}"

    async def get_object(
        self,
        object_name: str,
        bucket: str | None = None,
    ) -> bytes:
        """Download and return the full content of an object.

        Args:
            object_name: Object key within the bucket.
            bucket: Source bucket; defaults to the repos bucket.

        Returns:
            Raw bytes of the stored object.

        Raises:
            S3Error: If the object does not exist or access is denied.
        """
        target_bucket = bucket or self._bucket
        loop = asyncio.get_event_loop()

        def _get() -> bytes:
            response = self._client.get_object(target_bucket, object_name)
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()

        return await loop.run_in_executor(None, _get)

    async def delete_object(
        self,
        object_name: str,
        bucket: str | None = None,
    ) -> None:
        """Delete a single object from MinIO.

        Args:
            object_name: Object key to delete.
            bucket: Target bucket; defaults to the repos bucket.
        """
        target_bucket = bucket or self._bucket
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: self._client.remove_object(target_bucket, object_name),
        )

    async def delete_prefix(self, prefix: str, bucket: str | None = None) -> int:
        """Delete all objects whose keys start with the given prefix.

        Args:
            prefix: Key prefix to match (e.g. ``repos/<repo_id>/``).
            bucket: Target bucket; defaults to the repos bucket.

        Returns:
            Number of objects deleted.
        """
        target_bucket = bucket or self._bucket
        loop = asyncio.get_event_loop()

        def _list_and_delete() -> int:
            objects = self._client.list_objects(target_bucket, prefix=prefix, recursive=True)
            keys = [obj.object_name for obj in objects]
            for key in keys:
                self._client.remove_object(target_bucket, key)
            return len(keys)

        count = await loop.run_in_executor(None, _list_and_delete)
        logger.info("storage_prefix_deleted", prefix=prefix, count=count)
        return count

    async def object_exists(
        self,
        object_name: str,
        bucket: str | None = None,
    ) -> bool:
        """Check whether a specific object key exists.

        Args:
            object_name: Object key to probe.
            bucket: Target bucket; defaults to the repos bucket.

        Returns:
            True if the object exists, False otherwise.
        """
        target_bucket = bucket or self._bucket
        loop = asyncio.get_event_loop()

        def _stat() -> bool:
            try:
                self._client.stat_object(target_bucket, object_name)
                return True
            except S3Error:
                return False

        return await loop.run_in_executor(None, _stat)

    @staticmethod
    def repo_raw_key(repo_id: str, file_path: str) -> str:
        """Build the canonical MinIO key for a raw repository file.

        Args:
            repo_id: UUID string of the repository.
            file_path: Relative file path within the repository.

        Returns:
            MinIO object key string.
        """
        clean = file_path.lstrip("/")
        return f"repos/{repo_id}/raw/{clean}"

    @staticmethod
    def repo_artifact_key(repo_id: str, artifact: str) -> str:
        """Build the canonical MinIO key for a generated artifact.

        Args:
            repo_id: UUID string of the repository.
            artifact: Artifact filename (e.g. ``diagrams/architecture.png``).

        Returns:
            MinIO object key string.
        """
        return f"repos/{repo_id}/artifacts/{artifact}"

    async def check_health(self) -> bool:
        """Probe MinIO connectivity for the /ready health-check endpoint.

        Returns:
            True if the bucket can be listed, False otherwise.
        """
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, lambda: self._client.bucket_exists(self._bucket)
            )
            return True
        except Exception as exc:
            logger.error("storage_health_check_failed", error=str(exc))
            return False


# Module-level singleton — initialised once at import time
storage_client = StorageClient()
