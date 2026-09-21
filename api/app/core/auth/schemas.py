"""Esquemas Pydantic para auth."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


# ──────────────────────────────────────────────
# Requests
# ──────────────────────────────────────────────
class RegisterRequest(BaseModel):
    """Request para registro de usuario."""
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)
    tenant_slug: str | None = Field(default=None, max_length=100, description="Slug del tenant (opcional, para crear tenant nuevo)")


class LoginRequest(BaseModel):
    """Request para login."""
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    """Request para refresh de access token."""
    refresh_token: str


class ApiKeyCreateRequest(BaseModel):
    """Request para crear API key de agente."""
    name: str = Field(min_length=1, max_length=100, description="Nombre identificador de la key")


# ──────────────────────────────────────────────
# Responses
# ──────────────────────────────────────────────
class TokenResponse(BaseModel):
    """Response con tokens de acceso."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # segundos


class RefreshResponse(BaseModel):
    """Response de refresh token."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(BaseModel):
    """Usuario serializado para responses."""
    id: UUID
    email: str
    full_name: str | None
    role: str
    is_active: bool
    is_superuser: bool
    tenant_id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class ApiKeyResponse(BaseModel):
    """API key creada (raw key solo se muestra una vez)."""
    id: UUID
    name: str
    prefix: str  # ej: "spsk_"
    raw_key: str  # solo en creación
    created_at: datetime
    last_used_at: datetime | None = None

    model_config = {"from_attributes": True}


class ApiKeyListResponse(BaseModel):
    """API key para listado (sin raw key)."""
    id: UUID
    name: str
    prefix: str
    created_at: datetime
    last_used_at: datetime | None = None

    model_config = {"from_attributes": True}


class TenantResponse(BaseModel):
    """Tenant serializado."""
    id: UUID
    name: str
    slug: str
    plan: str
    created_at: datetime

    model_config = {"from_attributes": True}
