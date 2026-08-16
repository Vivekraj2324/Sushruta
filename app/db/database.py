"""
Sushruta — Database Engine & Session Factory
=============================================

Async SQLAlchemy setup with asyncpg driver and connection pooling.

Architecture decisions:
- create_async_engine: Non-blocking I/O for all DB operations.
- asyncpg: The fastest PostgreSQL driver for Python async.
- Connection pooling: pool_size=10 handles concurrent doctor sessions;
  max_overflow=20 absorbs traffic spikes without blocking.
- async_sessionmaker: Creates scoped sessions per-request via DI.
- get_db() generator: Ensures sessions are committed/rolled-back/closed
  properly even if an exception occurs mid-request.

Scalability:
- Stateless sessions (no server-side session storage).
- Pool can be tuned via environment variables.
- Ready for read-replica routing in future.
"""

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()

# ── Async Engine ─────────────────────────────────────────────────
# The engine manages the connection pool to PostgreSQL.
# echo=True in debug mode logs all SQL for development visibility.
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=True,  # Verify connections are alive before use
)

# ── Session Factory ──────────────────────────────────────────────
# async_sessionmaker creates AsyncSession instances.
# expire_on_commit=False: Prevents lazy-load issues after commit
# in async context (SQLAlchemy async doesn't support implicit IO).
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ── Declarative Base ─────────────────────────────────────────────
# All ORM models inherit from this base.
# Using the modern DeclarativeBase (SQLAlchemy 2.0 style).
class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass


# ── Dependency Injection ─────────────────────────────────────────
async def get_db():
    """
    FastAPI dependency that provides a database session per request.

    Yields an AsyncSession, ensuring proper cleanup:
    - On success: session is available for commit in the service layer.
    - On exception: session is rolled back automatically.
    - Always: session is closed after the request completes.

    Usage in routes:
        @router.get("/example")
        async def example(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
