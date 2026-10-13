"""Security Headers Middleware para FastAPI.

Implementa headers de seguridad recomendados:
- Content-Security-Policy (CSP)
- Strict-Transport-Security (HSTS)
- X-Frame-Options
- X-Content-Type-Options
- Referrer-Policy
- Permissions-Policy
"""

from __future__ import annotations

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


# ──────────────────────────────────────────────
# Configuración CSP
# ──────────────────────────────────────────────

def build_csp_header(environment: str) -> str:
    """
    Construye header Content-Security-Policy según entorno.
    
    En development: más permisivo para hot reload, dev tools
    En production: estricto
    """
    if environment == "development":
        # Development: permitir inline scripts/styles para hot reload
        # y conexiones a localhost para Vite/Next.js dev server
        return (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' http://localhost:* ws://localhost:*; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "font-src 'self' data:; "
            "connect-src 'self' http://localhost:* ws://localhost:*; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )

    # Production: estricto
    return (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "object-src 'none'; "
        "frame-src 'none'"
    )


def build_permissions_policy() -> str:
    """Construye header Permissions-Policy (antes Feature-Policy)."""
    return (
        "accelerometer=(), "
        "camera=(), "
        "geolocation=(), "
        "gyroscope=(), "
        "magnetometer=(), "
        "microphone=(), "
        "payment=(), "
        "usb=(), "
        "interest-cohort=()"
    )


# ──────────────────────────────────────────────
# Security Headers Middleware
# ──────────────────────────────────────────────

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware que agrega headers de seguridad a todas las respuestas.
    
    Headers agregados:
    - Content-Security-Policy: previene XSS, injection
    - Strict-Transport-Security: fuerza HTTPS (solo prod)
    - X-Frame-Options: previene clickjacking
    - X-Content-Type-Options: previene MIME sniffing
    - Referrer-Policy: controla Referer header
    - Permissions-Policy: controla APIs del navegador
    - Cross-Origin-Opener-Policy: aislamiento de contexto
    - Cross-Origin-Resource-Policy: controla recursos cross-origin
    """

    def __init__(self, app, environment: str | None = None):
        super().__init__(app)
        self.environment = environment or settings.ENVIRONMENT

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Content-Security-Policy
        response.headers["Content-Security-Policy"] = build_csp_header(self.environment)

        # Strict-Transport-Security (HSTS) - solo en producción con HTTPS
        if self.environment == "production":
            # 1 año = 31536000 segundos, includeSubDomains, preload
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )

        # X-Frame-Options - previene clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # X-Content-Type-Options - previene MIME sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Referrer-Policy - controla información de referrer
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Permissions-Policy (antes Feature-Policy)
        response.headers["Permissions-Policy"] = build_permissions_policy()

        # Cross-Origin-Opener-Policy - aislamiento de contexto
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"

        # Cross-Origin-Resource-Policy - recursos cross-origin
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"

        # X-DNS-Prefetch-Control - controla DNS prefetch
        response.headers["X-DNS-Prefetch-Control"] = "off"

        # X-Download-Options - previene apertura automática de descargas en IE
        response.headers["X-Download-Options"] = "noopen"

        # X-Permitted-Cross-Domain-Policies - para Flash/PDF (legacy)
        response.headers["X-Permitted-Cross-Domain-Policies"] = "none"

        return response


# ──────────────────────────────────────────────
# Función helper para agregar a FastAPI app
# ──────────────────────────────────────────────

def add_security_headers(app, environment: str | None = None) -> None:
    """
    Agrega SecurityHeadersMiddleware a la app FastAPI.
    
    Debe llamarse DESPUÉS de CORS y ANTES de otros middlewares
    que modifiquen headers de respuesta.
    """
    app.add_middleware(SecurityHeadersMiddleware, environment=environment)
