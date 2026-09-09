"""Add parsed_symbols table.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create parsed_symbols table."""
    op.create_table(
        "parsed_symbols",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("repo_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("file_type", sa.String(50), nullable=False, server_default="generic"),
        sa.Column("language", sa.String(30), nullable=False),
        sa.Column("symbol_kind", sa.String(30), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("qualified_name", sa.Text(), nullable=False),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("docstring", sa.Text(), nullable=True),
        sa.Column("signature", sa.Text(), nullable=True),
        sa.Column("parent_name", sa.String(255), nullable=True),
        sa.Column(
            "decorators",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "extras",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("neo4j_node_id", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "repo_id", "file_path", "symbol_kind", "qualified_name",
            name="uq_symbol_repo_file_kind_name",
        ),
    )

    op.create_index("ix_parsed_symbols_repo_id", "parsed_symbols", ["repo_id"])
    op.create_index("ix_parsed_symbols_name", "parsed_symbols", ["name"])
    op.create_index("ix_parsed_symbols_language", "parsed_symbols", ["language"])
    op.create_index(
        "ix_symbols_repo_language", "parsed_symbols", ["repo_id", "language"]
    )
    op.create_index(
        "ix_symbols_repo_file", "parsed_symbols", ["repo_id", "file_path"]
    )
    op.create_index(
        "ix_symbols_repo_kind", "parsed_symbols", ["repo_id", "symbol_kind"]
    )

    op.execute(
        """
        CREATE TRIGGER trigger_parsed_symbols_updated_at
        BEFORE UPDATE ON parsed_symbols
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """
    )


def downgrade() -> None:
    """Drop parsed_symbols table."""
    op.execute(
        "DROP TRIGGER IF EXISTS trigger_parsed_symbols_updated_at ON parsed_symbols;"
    )
    op.drop_table("parsed_symbols")
