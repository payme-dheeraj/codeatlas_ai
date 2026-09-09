"""Add security_scans and security_findings tables.

Revision ID: 0004
Revises: 0003
Create Date: 2024-01-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "security_scans",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "repo_id",
            UUID(as_uuid=True),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scan_types", JSONB, nullable=False, server_default="[]"),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("progress", sa.Integer, nullable=False, server_default="0"),
        sa.Column("current_stage", sa.String(200), nullable=True),
        sa.Column("total_findings", sa.Integer, nullable=False, server_default="0"),
        sa.Column("critical_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("high_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("medium_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("low_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("info_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_security_scans_repo_status", "security_scans", ["repo_id", "status"])

    op.create_table(
        "security_findings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "scan_id",
            UUID(as_uuid=True),
            sa.ForeignKey("security_scans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "repo_id",
            UUID(as_uuid=True),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scanner", sa.String(20), nullable=False),
        sa.Column("rule_id", sa.String(200), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("severity", sa.String(10), nullable=False),
        sa.Column("cvss_score", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("file_path", sa.Text, nullable=False),
        sa.Column("start_line", sa.Integer, nullable=False, server_default="0"),
        sa.Column("end_line", sa.Integer, nullable=False, server_default="0"),
        sa.Column("snippet", sa.Text, nullable=True),
        sa.Column("category", sa.String(50), nullable=False, server_default="generic"),
        sa.Column("language", sa.String(30), nullable=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("remediation", JSONB, nullable=True),
        sa.Column("is_false_positive", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("suppressed", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("extra", JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("scan_id", "fingerprint", name="uq_finding_scan_fingerprint"),
    )
    op.create_index("ix_security_findings_scan", "security_findings", ["scan_id"])
    op.create_index("ix_security_findings_repo_severity", "security_findings", ["repo_id", "severity"])
    op.create_index("ix_security_findings_scanner", "security_findings", ["scan_id", "scanner"])
    op.create_index("ix_security_findings_file", "security_findings", ["scan_id", "file_path"])


def downgrade() -> None:
    op.drop_table("security_findings")
    op.drop_table("security_scans")
