"""Rate Limiter con sliding window usando Redis sorted sets.

Implementa rate limiting por:
- API Key (para endpoints de agentes: ingest, heartbeat, commands)
- IP (para endpoints web: onboarding, dashboard, auth)
- Plan-aware: límites configurables por plan de suscripción
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import redis.asyncio as redis
from fastapi import HTTPException, Request, status

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.plan import PlanType

logger = get_logger(__name__)
settings = get_settings()


# ──────────────────────────────────────────────
# Configuración de límites por plan (rate limiting)
# ──────────────────────────────────────────────

# Requests por minuto por API Key (agentes)
RATE_LIMIT_API_BY_PLAN: dict[PlanType, int] = {
    PlanType.FREE: 60,       # 60 req/min
    PlanType.STARTER: 200,   # 200 req/min
    PlanType.GROWTH: 1000,   # 1000 req/min
    PlanType.ENTERPRISE: 5000,  # 5000 req/min
}

# Requests por minuto por IP (web)
RATE_LIMIT_WEB_BY_PLAN: dict[PlanType, int] = {
    PlanType.FREE: 30,       # 30 req/min
    PlanType.STARTER: 100,   # 100 req/min
    PlanType.GROWTH: 500,    # 500 req/min
    PlanType.ENTERPRISE: 2000,  # 2000 req/min
}

# ──────────────────────────────────────────────
# Rate Limiter Core
# ──────────────────────────────────────────────

@dataclass
class RateLimitResult:
    """Resultado de verificación de rate limit."""
    allowed: bool
    current: int
    limit: int
    reset_at: float  # Unix timestamp cuando se resetea la ventana
    retry_after: int | None = None  # Segundos hasta que se permita de nuevo


class RateLimiter:
    """
    Rate limiter con sliding window usando Redis sorted sets.
    
    Algoritmo:
    - Usa sorted set con score = timestamp (milisegundos)
    - Ventana: últimos N segundos (configurable)
    - Limpia entradas antiguas en cada request
    - Cuenta entradas en ventana actual
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        window_seconds: int = 60,
    ):
        self.redis = redis_client
        self.window_seconds = window_seconds
        self.window_ms = window_seconds * 1000

    async def check_limit(
        self,
        key: str,
        limit: int,
    ) -> RateLimitResult:
        """
        Verifica si la key ha excedido el límite.
        
        Args:
            key: Identificador único (ej: "api_key:spsk_..." o "ip:192.168.1.1")
            limit: Máximo requests permitidos en la ventana
            
        Returns:
            RateLimitResult con allowed, current count, limit, reset_at
        """
        now_ms = int(time.time() * 1000)
        window_start_ms = now_ms - self.window_ms

        # Pipeline para atomicidad: limpiar viejo + contar + agregar actual
        pipe = self.redis.pipeline()

        # 1. Remover entradas fuera de la ventana
        pipe.zremrangebyscore(key, 0, window_start_ms)

        # 2. Contar entradas actuales en ventana
        pipe.zcard(key)

        # 3. Agregar request actual (score = timestamp ms, member = unique request id)
        request_id = f"{now_ms}:{time.time_ns() % 1000000:06d}"
        pipe.zadd(key, {request_id: now_ms})

        # 4. Expirar la key automáticamente (window + buffer)
        pipe.expire(key, self.window_seconds + 10)

        results = await pipe.execute()

        current = results[1] + 1  # +1 por el request que acabamos de agregar

        # Calcular cuándo se resetea la ventana (próximo límite de ventana)
        reset_at = (now_ms // self.window_ms + 1) * self.window_ms / 1000

        allowed = current <= limit
        retry_after = None if allowed else int((reset_at - time.time()) + 1)

        return RateLimitResult(
            allowed=allowed,
            current=current,
            limit=limit,
            reset_at=reset_at,
            retry_after=retry_after,
        )


# ──────────────────────────────────────────────
# Redis Client Singleton
# ──────────────────────────────────────────────

_redis_client: redis.Redis | None = None
_rate_limiter: RateLimiter | None = None


async def get_redis_client() -> redis.Redis:
    """Obtiene cliente Redis singleton."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(
            str(settings.REDIS_URL),
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client


async def get_rate_limiter() -> RateLimiter:
    """Obtiene rate limiter singleton."""
    global _rate_limiter
    if _rate_limiter is None:
        client = await get_redis_client()
        _rate_limiter = RateLimiter(client, settings.RATE_LIMIT_WINDOW_SECONDS)
    return _rate_limiter


async def close_redis_client() -> None:
    """Cierra cliente Redis (para shutdown)."""
    global _redis_client, _rate_limiter
    if _redis_client:
        await _redis_client.aclose()
        _redis_client = None
        _rate_limiter = None


# ──────────────────────────────────────────────
# Helpers para extraer identificadores
# ──────────────────────────────────────────────

def get_client_ip(request: Request) -> str:
    """Extrae IP del cliente considerando proxies."""
    # Check X-Forwarded-For (primer IP en la cadena)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()

    # Check X-Real-IP
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip

    # Fallback a client host
    if request.client:
        return request.client.host

    return "unknown"


def get_api_key_identifier(request: Request) -> str | None:
    """Extrae API key del header X-Api-Key."""
    api_key = request.headers.get("X-Api-Key")
    if api_key and api_key.startswith(settings.API_KEY_PREFIX):
        return f"api_key:{api_key}"
    return None


def get_tenant_plan_from_context() -> PlanType | None:
    """Obtiene el plan del tenant desde el contexto actual (si hay)."""
    # En web endpoints, el tenant viene en session/user
    # En API key endpoints, viene en request.state.tenant_id
    # Por ahora retornamos None y los endpoints específicos lo resuelven
    return None


# ──────────────────────────────────────────────
# Rate Limit Dependencies para FastAPI
# ──────────────────────────────────────────────

async def rate_limit_api_dependency(request: Request) -> None:
    """
    Dependency para endpoints de API (agentes).
    Usa API Key como identificador y límites por plan del tenant.
    """
    if not settings.RATE_LIMIT_ENABLED:
        return

    api_key_id = get_api_key_identifier(request)
    if not api_key_id:
        # Sin API key, no aplicamos rate limit aquí (auth lo manejará)
        return

    # Obtener plan del tenant desde request.state (seteado por auth dependency)
    tenant_id = getattr(request.state, "tenant_id", None)
    plan = PlanType.FREE  # default

    if tenant_id:
        # TODO: obtener plan del tenant desde BD
        # Por ahora usamos default FREE, los endpoints con auth pueden pasarlo
        pass

    limit = RATE_LIMIT_API_BY_PLAN.get(plan, settings.RATE_LIMIT_API_DEFAULT)

    limiter = await get_rate_limiter()
    result = await limiter.check_limit(api_key_id, limit)

    # Headers informativos
    request.state.rate_limit = result

    if not result.allowed:
        logger.warning(
            "rate_limit_exceeded_api",
            identifier=api_key_id,
            plan=plan.value,
            current=result.current,
            limit=result.limit,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded: {result.limit} requests per minute",
            headers={
                "X-RateLimit-Limit": str(result.limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(result.reset_at)),
                "Retry-After": str(result.retry_after or 60),
            },
        )


async def rate_limit_web_dependency(request: Request) -> None:
    """
    Dependency para endpoints web (dashboard, onboarding, auth).
    Usa IP como identificador y límites por plan (si hay sesión).
    """
    if not settings.RATE_LIMIT_ENABLED:
        return

    ip = get_client_ip(request)
    key = f"ip:{ip}"

    # Obtener plan si hay tenant en contexto
    plan = PlanType.FREE

    limit = RATE_LIMIT_WEB_BY_PLAN.get(plan, settings.RATE_LIMIT_WEB_DEFAULT)

    limiter = await get_rate_limiter()
    result = await limiter.check_limit(key, limit)

    request.state.rate_limit = result

    if not result.allowed:
        logger.warning(
            "rate_limit_exceeded_web",
            ip=ip,
            plan=plan.value,
            current=result.current,
            limit=result.limit,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded: {result.limit} requests per minute",
            headers={
                "X-RateLimit-Limit": str(result.limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(result.reset_at)),
                "Retry-After": str(result.retry_after or 60),
            },
        )


# ──────────────────────────────────────────────
# Middleware Global de Rate Limiting (opcional)
# ──────────────────────────────────────────────

async def rate_limit_middleware(request: Request, call_next):
    """
    Middleware opcional para rate limiting global.
    Se puede usar en lugar de / además de dependencies.
    """
    if not settings.RATE_LIMIT_ENABLED:
        return await call_next(request)

    # Skip para health checks
    if request.url.path in ("/healthz", "/readyz", "/docs", "/redoc", "/openapi.json"):
        return await call_next(request)

    # Determinar si es endpoint API (agente) o web
    is_api = request.url.path.startswith("/api/v1/")

    if is_api:
        # Para API, usar API key si existe, sino IP
        api_key_id = get_api_key_identifier(request)
        if api_key_id:
            key = api_key_id
            plan = PlanType.FREE  # TODO: obtener del tenant
            limit = RATE_LIMIT_API_BY_PLAN.get(plan, settings.RATE_LIMIT_API_DEFAULT)
        else:
            ip = get_client_ip(request)
            key = f"ip:{ip}"
            limit = settings.RATE_LIMIT_API_DEFAULT
    else:
        # Para web, usar IP
        ip = get_client_ip(request)
        key = f"ip:{ip}"
        plan = PlanType.FREE
        limit = RATE_LIMIT_WEB_BY_PLAN.get(plan, settings.RATE_LIMIT_WEB_DEFAULT)

    limiter = await get_rate_limiter()
    result = await limiter.check_limit(key, limit)

    # Agregar headers de rate limit a la respuesta
    response = await call_next(request)

    response.headers["X-RateLimit-Limit"] = str(result.limit)
    response.headers["X-RateLimit-Remaining"] = str(max(0, result.limit - result.current))
    response.headers["X-RateLimit-Reset"] = str(int(result.reset_at))

    if not result.allowed:
        return HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded: {result.limit} requests per minute",
            headers={
                "X-RateLimit-Limit": str(result.limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(result.reset_at)),
                "Retry-After": str(result.retry_after or 60),
            },
        )

    return response
