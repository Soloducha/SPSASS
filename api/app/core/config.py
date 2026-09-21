"""Configuración de la aplicación usando Pydantic Settings v2."""

from functools import lru_cache
from typing import Annotated

from pydantic import Field, PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic.types import StringConstraints
from typing_extensions import Annotated as TypedAnnotated

# Type que acepta tanto PostgreSQL como SQLite (para tests)
DatabaseDsn = Annotated[
    str,
    StringConstraints(pattern=r"^(postgresql(\+\w+)?|sqlite(\+\w+)?)://"),
]


class Settings(BaseSettings):
    """Configuración centralizada de la API."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ──────────────────────────────────────────────
    # Entorno
    # ──────────────────────────────────────────────
    ENVIRONMENT: str = Field(
        default="development", description="development | staging | production"
    )
    LOG_LEVEL: str = Field(default="INFO", description="DEBUG | INFO | WARNING | ERROR")

    # ──────────────────────────────────────────────
    # Base de datos
    # ──────────────────────────────────────────────
    DATABASE_URL: DatabaseDsn = Field(
        default="postgresql+asyncpg://spsaas:spsaas@localhost:5432/spsaas",
        description="URL de conexión a PostgreSQL + TimescaleDB (asyncpg) o SQLite (tests)",
    )

    # ──────────────────────────────────────────────
    # Redis
    # ──────────────────────────────────────────────
    REDIS_URL: RedisDsn = Field(
        default="redis://localhost:6379/0",
        description="URL de conexión a Redis",
    )

    # ──────────────────────────────────────────────
    # JWT Auth
    # ──────────────────────────────────────────────
    JWT_SECRET: str = Field(
        default="dev-secret-change-me-32-chars-minimum-length",
        description="Clave secreta para firmar JWT (mínimo 32 chars en prod)",
        min_length=32,
    )
    JWT_ALGORITHM: str = Field(default="HS256", description="Algoritmo de firma JWT")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=15, ge=1, le=1440)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, ge=1, le=90)

    # ──────────────────────────────────────────────
    # API Keys (agentes)
    # ──────────────────────────────────────────────
    API_KEY_PREFIX: str = Field(default="spsk_", description="Prefijo visible de API keys")
    API_KEY_HASH_ALGORITHM: str = Field(
        default="bcrypt", description="Algoritmo para hashear API keys"
    )

    # ──────────────────────────────────────────────
    # Multi-tenant
    # ──────────────────────────────────────────────
    TENANT_HEADER: str = Field(
        default="X-Tenant-Slug", description="Header para identificar tenant"
    )
    TENANT_COOKIE: str = Field(default="tenant_slug", description="Cookie para tenant en web")

    # ──────────────────────────────────────────────
    # CORS
    # ──────────────────────────────────────────────
    CORS_ORIGINS: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"],
        description="Orígenes permitidos para CORS",
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    # ──────────────────────────────────────────────
    # Paginación
    # ──────────────────────────────────────────────
    DEFAULT_PAGE_SIZE: int = Field(default=20, ge=1, le=100)
    MAX_PAGE_SIZE: int = Field(default=100, ge=1, le=1000)


@lru_cache
def get_settings() -> Settings:
    """Instancia singleton de settings (cacheada)."""
    return Settings()
