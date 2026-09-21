"""Punto de entrada principal de la API FastAPI."""

import time
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager

import redis.asyncio as redis
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api import auth_router
from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.core.tenant.middleware import TenantMiddleware
from app.db.session import close_db, get_engine, init_db

# Configurar logging al importar
setup_logging()

logger = get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Gestión del ciclo de vida de la aplicación."""
    # Startup
    logger.info("api_starting", environment=settings.ENVIRONMENT)
    await init_db()
    logger.info("api_started")

    yield

    # Shutdown
    logger.info("api_shutting_down")
    await close_db()
    logger.info("api_shutdown_complete")


app = FastAPI(
    title="SPSAAS API",
    description="API de monitoreo SaaS para entornos legacy y Linux",
    version="0.1.0",
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Tenant Middleware (debe ir después de CORS, antes de logging para tener contexto)
app.add_middleware(TenantMiddleware)


# ──────────────────────────────────────────────
# Middleware de logging de requests
# ──────────────────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next: Callable[[Request], Response]) -> Response:
    """Loggea requests entrantes y salientes."""
    start_time = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - start_time) * 1000

    logger.info(
        "http_request",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=round(duration_ms, 2),
    )
    return response


# ──────────────────────────────────────────────
# Health Check
# ──────────────────────────────────────────────
@app.get("/healthz", tags=["health"])
async def healthz() -> JSONResponse:
    """
    Health check endpoint.
    - 200: API sana
    - 503: API no disponible (BD, Redis, etc.)
    """
    checks = {
        "api": "ok",
        "database": "unknown",
        "redis": "unknown",
    }
    status_code = 200

    # Check DB
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        logger.exception("healthz_db_failed")
        checks["database"] = "failed"
        status_code = 503

    # Check Redis
    try:
        redis_client = redis.from_url(str(settings.REDIS_URL))
        await redis_client.ping()
        await redis_client.close()
        checks["redis"] = "ok"
    except Exception:
        logger.exception("healthz_redis_failed")
        checks["redis"] = "failed"
        status_code = 503

    return JSONResponse(content=checks, status_code=status_code)


@app.get("/readyz", tags=["health"])
async def readyz() -> JSONResponse:
    """
    Readiness check - más estricto que healthz.
    Verifica que la API puede servir tráfico (migraciones aplicadas, etc.).
    """
    # Por ahora mismo que healthz, en futuro verificar migraciones
    return await healthz()


# ──────────────────────────────────────────────
# Exception Handlers
# ──────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Manejo global de excepciones no capturadas."""
    logger.exception(
        "unhandled_exception",
        path=request.url.path,
        method=request.method,
        error=str(exc),
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# ──────────────────────────────────────────────
# Routers
# ──────────────────────────────────────────────
app.include_router(auth_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.ENVIRONMENT == "development",
    )
