"""MinIO storage for rendered diagram artifacts.

Stores PNG and SVG renders at:
  repos/{repo_id}/artifacts/diagrams/{diagram_type}/{diagram_id}.{ext}

Returns presigned GET URLs valid for 7 days.
"""

from __future__ import annotations

import io
from datetime import timedelta

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_PRESIGN_EXPIRY = timedelta(days=7)
_BUCKET = "codeatlas-diagrams"


def _client():
    from minio import Minio
    return Minio(
        endpoint=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )


def _ensure_bucket(client) -> None:
    if not client.bucket_exists(_BUCKET):
        client.make_bucket(_BUCKET)


def upload_render(
    repo_id: str,
    diagram_id: str,
    diagram_type: str,
    content: bytes,
    ext: str,
) -> tuple[str, str]:
    """Upload a rendered diagram file to MinIO.

    Args:
        repo_id: UUID string of the repository.
        diagram_id: UUID string of the diagram record.
        diagram_type: Diagram type slug.
        content: Raw bytes of the rendered file.
        ext: File extension (svg | png).

    Returns:
        Tuple of (minio_object_key, presigned_url).
        Returns ("", "") if MinIO is unavailable or content is empty.
    """
    if not content:
        return "", ""

    key = f"repos/{repo_id}/artifacts/diagrams/{diagram_type}/{diagram_id}.{ext}"
    content_type = "image/svg+xml" if ext == "svg" else "image/png"

    try:
        client = _client()
        _ensure_bucket(client)
        client.put_object(
            _BUCKET,
            key,
            data=io.BytesIO(content),
            length=len(content),
            content_type=content_type,
        )
        url = client.presigned_get_object(_BUCKET, key, expires=_PRESIGN_EXPIRY)
        logger.info("diagram_uploaded", key=key, bytes=len(content))
        return key, url

    except Exception as exc:
        logger.warning("diagram_upload_failed", key=key, error=str(exc))
        return "", ""


def get_presigned_url(minio_key: str) -> str:
    """Refresh a presigned URL for an existing MinIO object.

    Args:
        minio_key: Full MinIO object key.

    Returns:
        New presigned URL string, or empty string on failure.
    """
    if not minio_key:
        return ""
    try:
        client = _client()
        return client.presigned_get_object(_BUCKET, minio_key, expires=_PRESIGN_EXPIRY)
    except Exception as exc:
        logger.warning("presign_failed", key=minio_key, error=str(exc))
        return ""
