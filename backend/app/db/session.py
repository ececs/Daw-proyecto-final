"""Async SQLAlchemy engine, session factory and FastAPI dependency.

The engine is configured with a small pool (`pool_size=5`,
`max_overflow=10`) tuned for a single uvicorn worker; production setups
with multiple workers should still fit within typical PostgreSQL
defaults. `expire_on_commit=False` keeps ORM instances usable after a
commit, which the service layer relies on when broadcasting events.
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=1800,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

# Alias: some services use the more conventional `_factory` name.
async_session_factory = AsyncSessionLocal


async def get_db() -> AsyncSession:
    """FastAPI dependency that yields a fresh `AsyncSession` per request.

    The session is closed automatically when the request finishes,
    rolling back any uncommitted state.

    Yields:
        AsyncSession: The active session.
    """
    async with AsyncSessionLocal() as session:
        yield session
