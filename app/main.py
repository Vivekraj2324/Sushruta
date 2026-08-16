"""
Sushruta — Application Entry Point
=====================================

FastAPI application with lifespan management, CORS middleware,
route registration, and health check endpoint.

Named after Sushruta (6th century BCE) — Father of Surgery,
author of the Sushruta Samhita. The first documented physician-scientist
in human history.

Architecture:
- Lifespan context manager handles startup/shutdown (table creation in dev).
- CORS is configured for allowed origins (wildcard in dev, restricted in prod).
- All v1 routes are mounted via the aggregated api_v1_router.
- /health is at the root level (no auth required) for deployment liveness checks.
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, Response, status, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import uuid
from app.api.v1 import api_v1_router
from app.config import get_settings
from app.db.database import Base, engine, get_db
from app.core.logging_config import setup_logging, correlation_id_ctx

# Initialize structured JSON logging
setup_logging()

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.

    Startup:
    - In development: Creates all tables via SQLAlchemy metadata.
      This is a convenience for local dev — production uses Alembic.
    - Creates the upload directory if it doesn't exist.

    Shutdown:
    - Disposes the database engine (closes all pooled connections).
    """
    # ── Startup ──────────────────────────────────────────────────
    if settings.ENVIRONMENT == "development":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    # Ensure upload directory exists
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

    yield

    # ── Shutdown ─────────────────────────────────────────────────
    await engine.dispose()


# ── FastAPI Application ──────────────────────────────────────────
app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "AI-powered clinical workflow automation platform. "
        "Helps doctors spend less time on paperwork and more time on patients. "
        "Named after Sushruta (6th century BCE) — Father of Surgery."
    ),
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS Middleware ──────────────────────────────────────────────
# In development: Allow all origins for Postman/browser testing.
# In production: Restrict to specific frontend domains.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.DEBUG else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Error Handling & Observability Middleware ────────────────────
logger = logging.getLogger(__name__)

@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    """
    Extract or generate a unique correlation ID and store it in contextvars
    so it is present in all log messages and returned in headers.
    """
    corr_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
    token = correlation_id_ctx.set(corr_id)
    try:
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = corr_id
        return response
    finally:
        correlation_id_ctx.reset(token)

@app.middleware("http")
async def exception_handling_middleware(request: Request, call_next):
    """
    Global unhandled exception interceptor. Logs details and returns a
    uniform 500 error response instead of leaking internal tracebacks.
    """
    try:
        return await call_next(request)
    except Exception as e:
        logger.exception(f"Unhandled exception during {request.method} {request.url.path}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": "An unexpected error occurred. Please try again later or contact support."
            }
        )


# ── Route Registration ───────────────────────────────────────────
app.include_router(api_v1_router)

# Serve frontend static assets and index page
app.mount("/static", StaticFiles(directory="frontend"), name="static")

@app.get("/")
async def read_index():
    """Serves the main frontend Single Page Application (SPA)."""
    return FileResponse("frontend/index.html")


# ── Health Check ─────────────────────────────────────────────────
@app.get(
    "/health",
    tags=["Health"],
    summary="Health check",
    description="Liveness probe for deployment platforms including database connectivity check.",
)
async def health_check(response: Response, db: AsyncSession = Depends(get_db)):
    """
    Health check endpoint.

    Returns application status, name, version, environment, and database status.
    No authentication required — used by load balancers and
    orchestrators (Docker, K8s) to verify the service is alive.
    """
    db_status = "healthy"
    try:
        # Simple query to verify database connection
        await db.execute(select(1))
    except Exception as e:
        db_status = f"unhealthy: {e}"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    status_code = "healthy" if "unhealthy" not in db_status else "unhealthy"
    return {
        "status": status_code,
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "database": db_status,
    }
