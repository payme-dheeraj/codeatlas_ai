"""Add repositories.source_archive_key for ZIP-imported repositories.

Stores the MinIO object key of the uploaded archive so that re-indexing a
ZIP-imported repository can re-extract the original source. Without it,
``trigger_reindex`` had no source to hand the worker and the task failed with
"One of url, local_path, or zip_minio_key must be provided."

Revision ID: 0008
Revises: 0007
Create Date: 2024-01-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "repositories",
        sa.Column("source_archive_key", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("repositories", "source_archive_key")
