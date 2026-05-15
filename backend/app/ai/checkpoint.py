"""LangGraph PostgreSQL checkpointer for persistent conversation memory.

Why a module-level singleton?
  AsyncPostgresSaver maintains a psycopg connection pool. Creating it per
  request would exhaust PostgreSQL connections under load. A singleton
  initialized once at startup is the correct pattern for connection pools.

  setup() (creates checkpoint_* tables) is called once at init, not per request.

Graceful degradation:
  If PostgreSQL is unreachable at startup (e.g., test environment), the
  checkpointer is set to None and the agent falls back to stateless mode —
  the frontend sends the full conversation history on every request.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_checkpointer = None
_pool = None


async def init_checkpointer() -> None:
    """Initializes the PostgreSQL conversational state checkpointer asynchronously.

    Configures a dedicated AsyncConnectionPool using psycopg and instantiates the
    AsyncPostgresSaver checkpointer instance. Executes necessary table initialization.
    Fails gracefully falling back to stateless mode if connectivity issues arise.
    """
    global _checkpointer, _pool

    try:
        from psycopg_pool import AsyncConnectionPool
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from app.core.config import settings
        
        # Use a more visible logger for startup
        v_logger = logging.getLogger("uvicorn.error")

        # Ensure we have a standard postgresql:// URL for psycopg (no +asyncpg)
        db_url = settings.DATABASE_URL
        if "+asyncpg" in db_url:
            db_url = db_url.replace("+asyncpg", "")
        
        v_logger.info("Initializing checkpointer with URL: %s", db_url.split("@")[-1])

        _pool = AsyncConnectionPool(
            conninfo=db_url,
            min_size=1,
            max_size=3,
            open=False,
            kwargs={"autocommit": True, "prepare_threshold": 0},
        )
        await _pool.open(wait=True, timeout=10.0)

        # Initialize the checkpointer with the pool
        _checkpointer = AsyncPostgresSaver(_pool)
        
        # CRITICAL: Ensure tables exist
        await _checkpointer.setup()
        
        v_logger.info("✅ LangGraph Checkpointer fully initialized and persistent")
        return _checkpointer

    except Exception as exc:
        logging.getLogger("uvicorn.error").error("❌ Checkpointer FAILED to initialize: %s", exc, exc_info=True)
        _checkpointer = None
        _pool = None


def get_checkpointer():
    """Retrieves the active persistent conversational checkpointer instance.

    Returns:
        Optional[AsyncPostgresSaver]: The global checkpointer singleton, or None if the
            system is running in stateless fallback mode.
    """
    return _checkpointer


async def close_pool() -> None:
    """Closes the dedicated PostgreSQL connection pool gracefully on shutdown.

    Ensures database connection resources are properly returned to the database engine
    during clean application teardown cycles.
    """
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("LangGraph checkpointer pool closed")
