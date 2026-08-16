"""
Sushruta — Alembic Migration Environment
==========================================

This module configures Alembic to run database migrations against a PostgreSQL
database using **async** SQLAlchemy (asyncpg driver).

Key design decisions:
  1. DATABASE_URL is loaded from ``app.config.get_settings()`` so credentials
     are centralised in one place (the .env file) rather than duplicated in
     alembic.ini.
  2. All ORM models are imported from ``app.db.models`` so that Alembic's
     ``--autogenerate`` flag can diff the current database state against the
     full set of mapped tables.
  3. Both **offline** (emit SQL to stdout / file) and **online** (apply
     directly via asyncpg) modes are supported.

Usage:
  # Generate a new migration after changing models
  alembic revision --autogenerate -m "describe change"

  # Apply all pending migrations
  alembic upgrade head

  # Downgrade one revision
  alembic downgrade -1

  # Emit SQL without applying (offline mode)
  alembic upgrade head --sql
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# ---------------------------------------------------------------------------
# Application imports
# ---------------------------------------------------------------------------
# Import the declarative Base whose .metadata contains all table definitions.
from app.db.database import Base  # noqa: F401

# Import every model module so that the ORM classes are registered on
# Base.metadata BEFORE Alembic inspects it for autogenerate.  Even though
# we don't reference these names directly, the import triggers class
# registration via SQLAlchemy's metaclass machinery.
import app.db.models  # noqa: F401

# Import settings to read the canonical DATABASE_URL.
from app.config import get_settings

# ---------------------------------------------------------------------------
# Alembic Config object — provides access to values in alembic.ini
# ---------------------------------------------------------------------------
config = context.config

# ---------------------------------------------------------------------------
# Python logging — set up from the [loggers] section of alembic.ini
# ---------------------------------------------------------------------------
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ---------------------------------------------------------------------------
# Target metadata for autogenerate support
# ---------------------------------------------------------------------------
# Alembic compares this metadata (derived from your ORM models) against the
# live database schema to produce migration diffs.
target_metadata = Base.metadata

# ---------------------------------------------------------------------------
# Override sqlalchemy.url with the real DATABASE_URL from app settings
# ---------------------------------------------------------------------------
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)


# ==========================================================================
# Offline migrations — generates SQL script without connecting to the DB
# ==========================================================================
def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    In this mode Alembic emits the DDL SQL to stdout (or a file) instead of
    executing it against a live database.  This is useful for generating SQL
    scripts to be reviewed or applied by a DBA.

    Calls to ``context.execute()`` emit the given string to the script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Compare column types so that type changes are detected by autogenerate
        compare_type=True,
        # Compare server defaults (e.g. default=func.now()) between models and DB
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


# ==========================================================================
# Online migrations — connects to the live database via asyncpg
# ==========================================================================
def do_run_migrations(connection: Connection) -> None:
    """Execute migrations against an active database connection.

    This helper is called from within a sync context provided by
    ``AsyncConnection.run_sync()``.
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # Compare column types so that type changes are detected by autogenerate
        compare_type=True,
        # Compare server defaults (e.g. default=func.now()) between models and DB
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine from config and run migrations.

    This is the core of the online migration flow:
      1. Build an ``AsyncEngine`` from the [alembic] section of alembic.ini
         (which now contains the real DATABASE_URL we set earlier).
      2. Open an ``AsyncConnection``.
      3. Use ``run_sync()`` to bridge into the synchronous Alembic context.
      4. Dispose the engine cleanly to release the connection pool.

    We use ``poolclass=pool.NullPool`` because migration scripts are
    short-lived processes that don't benefit from connection pooling and
    should release connections immediately.
    """
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Kicks off the async migration flow by running ``run_async_migrations()``
    inside an asyncio event loop.
    """
    asyncio.run(run_async_migrations())


# ---------------------------------------------------------------------------
# Entry point — Alembic calls this when you run `alembic upgrade/downgrade`
# ---------------------------------------------------------------------------
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
