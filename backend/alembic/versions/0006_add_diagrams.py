"""Add diagrams table.

Revision ID: 0006
Revises: 0005
Create Date: 2024-01-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "diagrams",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "repo_id",
            UUID(as_uuid=True),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("diagram_type", sa.String(30), nullable=False),
        sa.Column("diagram_format", sa.String(15), nullable=False, server_default="mermaid"),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("source_code", sa.Text, nullable=False),
        sa.Column("render_url_svg", sa.Text, nullable=True),
        sa.Column("render_url_png", sa.Text, nullable=True),
        sa.Column("minio_key_svg", sa.Text, nullable=True),
        sa.Column("minio_key_png", sa.Text, nullable=True),
        sa.Column("source_checksum", sa.String(64), nullable=True),
        sa.Column("generation_meta", JSONB, nullable=False, server_default="{}"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("is_latest", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("options", JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_diagrams_repo_type", "diagrams", ["repo_id", "diagram_type"])
    op.create_index("ix_diagrams_repo_latest", "diagrams", ["repo_id", "diagram_type", "is_latest"])


def downgrade() -> None:
    op.drop_table("diagrams")
