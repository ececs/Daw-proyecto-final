"""Creates and configures the FastAPI application instance.

Key responsibilities:
  1. CORS: allow the Next.js frontend to call the API from a different origin.
  2. Lifespan: on startup, create the MinIO bucket if it doesn't exist, then start
     the PostgreSQL LISTEN loop that pushes notifications to WebSocket clients.
  3. Router registration: mount all v1 API routers under /api/v1.

The lifespan pattern (instead of deprecated @app.on_event) ensures cleanup code
(graceful shutdown) runs even when the server receives a SIGTERM.
"""

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager

import asyncpg
import boto3
from botocore.exceptions import ClientError
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.websocket_manager import manager
from app.api.v1 import auth, tickets, comments, attachments, users, notifications, ws, knowledge
from app.ai import router as ai_router
from app.ai.checkpoint import init_checkpointer, close_pool
from app.services.cache_service import init_cache, close_cache
from app.services import pubsub_service

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manages the FastAPI application lifecycle.

    On startup, it executes environment variable diagnostics, configures LangSmith,
    initializes object storage and checkpointer resources, and launches the background
    real-time notification listeners.
    On shutdown, it gracefully cancels listeners and tears down resource pools.

    Args:
        app: The FastAPI application instance.
    """
    # Startup diagnostics
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info("Checking environment variables...")
    if settings.GOOGLE_API_KEY:
        logger.info(f"✅ GOOGLE_API_KEY loaded (starts with {settings.GOOGLE_API_KEY[:4]}...)")
    else:
        logger.warning("❌ GOOGLE_API_KEY is MISSING!")
        
    if settings.OPENAI_API_KEY:
        logger.info(f"✅ OPENAI_API_KEY loaded (starts with {settings.OPENAI_API_KEY[:7]}...)")
    else:
        logger.warning("❌ OPENAI_API_KEY is MISSING!")
    
    # Initialize background notification listener (PostgreSQL)
    _init_langsmith()
    await _init_storage()
    await init_checkpointer()
    await init_cache()

    # Warm up the LLM singleton so observability status is populated from the start
    try:
        from app.ai.agent import get_llm
        get_llm()
        logger.info("✅ AI LLM initialized")
    except Exception as e:
        logger.warning("⚠️  AI LLM warm-up failed: %s", e)
    # Redis Pub/Sub when available; PG LISTEN/NOTIFY as fallback
    if pubsub_service.is_redis_available():
        logger.info("Real-time transport: Redis Pub/Sub")
        listen_task = asyncio.create_task(pubsub_service.redis_listen_loop())
    else:
        logger.info("Real-time transport: PostgreSQL LISTEN/NOTIFY")
        listen_task = asyncio.create_task(_pg_listen_loop())

    yield

    # --- Shutdown ---
    listen_task.cancel()
    try:
        await listen_task
    except asyncio.CancelledError:
        pass
    await close_pool()
    await close_cache()


def _init_langsmith() -> None:
    """Configures LangSmith tracing by propagating settings to system environment variables.

    Maps application settings directly to the environment keys auto-detected by LangChain,
    enabling transparent agent lifecycle tracing in both dev and production runners.
    """
    if not settings.LANGSMITH_TRACING or not settings.LANGSMITH_API_KEY:
        logger.info("LangSmith tracing disabled")
        return

    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = settings.LANGSMITH_API_KEY
    os.environ["LANGCHAIN_PROJECT"] = settings.LANGSMITH_PROJECT
    os.environ["LANGCHAIN_ENDPOINT"] = settings.LANGSMITH_ENDPOINT
    logger.info("LangSmith tracing enabled — project: %s", settings.LANGSMITH_PROJECT)


async def _init_storage() -> None:
    """Initializes the object storage bucket for attachments.

    Checks for the existence of the configured bucket in MinIO or Cloudflare R2 and
    creates it if missing. Runs as an idempotent procedure during application startup.

    Raises:
        ClientError: If connectivity or credentials prevent bucket interrogation or creation.
    """
    s3 = boto3.client(
        "s3",
        endpoint_url=settings.STORAGE_ENDPOINT,
        aws_access_key_id=settings.STORAGE_ACCESS_KEY,
        aws_secret_access_key=settings.STORAGE_SECRET_KEY,
        region_name=settings.STORAGE_REGION,
    )
    try:
        s3.head_bucket(Bucket=settings.STORAGE_BUCKET)
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "404":
            s3.create_bucket(Bucket=settings.STORAGE_BUCKET)
        # Other errors (auth, network) will propagate and crash startup — intentional


async def _pg_listen_loop() -> None:
    """Listens for database notification triggers in a persistent background task.

    Establishes a dedicated, long-lived database connection via asyncpg to subscribe
    to the 'notifications' channel. Relays any incoming JSON payloads to WebSocket clients.

    Uses asyncpg directly instead of SQLAlchemy as SQLAlchemy is structurally designed
    for discrete request-response cycles rather than long-running callbacks.
    """
    # Build a raw asyncpg connection URL (asyncpg uses its own URL format)
    raw_url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")

    conn: asyncpg.Connection = await asyncpg.connect(raw_url)

    async def on_notification(connection, pid, channel, payload):
        """Handles incoming PostgreSQL NOTIFY message payloads.

        Args:
            connection: The current active asyncpg connection.
            pid: The process ID of the notifying database backend.
            channel: The string identifier of the notification channel.
            payload: The JSON string frame delivered by the trigger.
        """
        try:
            data = json.loads(payload)
            user_id = data.get("user_id")
            if user_id:
                if user_id == "*":
                    await manager.broadcast_to_all(data)
                else:
                    await manager.broadcast_to_user(user_id, data)
        except Exception as e:
            logger.error(f"WebSocket Listener: Failed to process notification: {str(e)}")

    await conn.add_listener("notifications", on_notification)

    try:
        # Wait forever (until CancelledError on shutdown)
        await asyncio.Future()
    finally:
        await conn.remove_listener("notifications", on_notification)
        await conn.close()


# --- Application factory ---

app = FastAPI(
    title="D4-Ticket AI",
    description="Collaborative ticketing system with AI assistant powered by LangGraph.",
    version="1.0.0",
    docs_url="/docs",      # Swagger UI
    redoc_url="/redoc",    # ReDoc
    lifespan=lifespan,
)

# CORS: allow the frontend origin to make cross-origin requests.
allowed_origins = list(set(
    settings.CORS_ORIGINS + 
    [settings.FRONTEND_URL, "http://localhost:3000", "http://127.0.0.1:3000"]
))
print(f"🔓 Allowed Origins: {allowed_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount all API routers under /api/v1
# Each router file is responsible for its own prefix and tags
app.include_router(auth.router, prefix="/api/v1")
app.include_router(tickets.router, prefix="/api/v1")
app.include_router(comments.router, prefix="/api/v1")
app.include_router(attachments.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(notifications.router, prefix="/api/v1")
app.include_router(ws.router)  # WebSocket doesn't follow the /api/v1 pattern
app.include_router(ai_router.router, prefix="/api/v1")
app.include_router(knowledge.router, prefix="/api/v1")


@app.get("/health", tags=["Health"])
async def health_check():
    """Executes a basic service health check.

    Returns:
        dict: A dictionary status report containing health metrics and versions.
    """
    return {"status": "ok", "version": "0.1.1"}
