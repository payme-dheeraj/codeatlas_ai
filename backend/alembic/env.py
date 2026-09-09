"""Alembic migration environment configuration.

Supports both offline (SQL script generation) and online (live DB) modes.
Uses the synchronous psycopg2 driver; async engine is not required here.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Import all models so Alembic's autogenerate can discover them
from app.core.config import settings
from app.models.base import Base
from app.models.api_key import ApiKey  # noqa: F401
from app.models.index_job import IndexJob  # noqa: F401
from app.models.repository import Repository  # noqa: F401
from app.models.audit_log import AuditLog  # noqa: F401
from app.models.diagram import Diagram  # noqa: F401
from app.models.role import UserRepoRole  # noqa: F401
from app.models.webhook import Webhook, WebhookDelivery  # noqa: F401
from app.models.document import Document, DocumentGenerationJob  # noqa: F401
from app.models.security_finding import SecurityFinding, SecurityScan  # noqa: F401
from app.models.symbol import ParsedSymbol  # noqa: F401
from app.models.user import User  # noqa: F401

config = context.config

# Override sqlalchemy.url with the value from application settings
config.set_main_option("sqlalchemy.url", settings.database_url_sync)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Generate SQL migration script without a live DB connection.

    Writes SQL to stdout / a file, suitable for review before execution.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Apply migrations against a live database connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
