"""Esquemas Pydantic para API v1 (servidores, ingesta, alertas)."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, HttpUrl, field_validator

from app.models.alert import AlertOperator, AlertSeverity, AlertStatus, EntityType
from app.models.metric import MetricType


# ──────────────────────────────────────────────
# Server Schemas
# ──────────────────────────────────────────────
class ServerRegisterRequest(BaseModel):
    """Request para registrar/actualizar un servidor."""

    hostname: str = Field(min_length=1, max_length=255)
    ip: str | None = Field(default=None, max_length=45)
    os: str | None = Field(default=None, max_length=100)
    agent_version: str | None = Field(default=None, max_length=50)


class ServerRegisterResponse(BaseModel):
    """Response de registro de servidor."""

    id: UUID
    hostname: str
    status: str
    agent_version: str | None
    last_heartbeat_at: datetime | None

    model_config = {"from_attributes": True}


# ──────────────────────────────────────────────
# Ingest Schemas
# ──────────────────────────────────────────────
class MetricItem(BaseModel):
    """Item de métrica individual en un batch."""

    type: MetricType
    value: float
    tags: dict[str, str] | None = None


class MetricIngestPayload(BaseModel):
    """Payload para ingesta de métricas en batch."""

    server_id: UUID
    ts: datetime | None = None
    metrics: Annotated[list[MetricItem], Field(min_length=1, max_length=1000)]


class IngestResponse(BaseModel):
    """Response de ingesta de métricas."""

    received: int
    inserted: int
    server_id: UUID


# ──────────────────────────────────────────────
# Channel validation models
# ──────────────────────────────────────────────
class WebhookChannel(BaseModel):
    """Configuración del canal webhook."""

    url: HttpUrl
    headers: dict[str, str] = Field(default_factory=dict)


class EmailChannel(BaseModel):
    """Configuración del canal email."""

    to: Annotated[list[EmailStr], Field(min_length=1)]


# Valid channel keys
ALLOWED_CHANNEL_KEYS = frozenset({"webhook", "email"})


def _validate_channels_dict(v: dict) -> dict:
    """Valida la estructura del dict channels y retorna valores normalizados."""
    if not isinstance(v, dict):
        raise TypeError("channels must be a dict")

    # Check for unknown keys
    unknown_keys = set(v.keys()) - ALLOWED_CHANNEL_KEYS
    if unknown_keys:
        raise ValueError(f"Unknown channel keys: {sorted(unknown_keys)}. Allowed: {sorted(ALLOWED_CHANNEL_KEYS)}")

    result = {}

    # Validate and normalize webhook if present
    if "webhook" in v:
        webhook = WebhookChannel.model_validate(v["webhook"])
        result["webhook"] = {"url": str(webhook.url), "headers": webhook.headers}

    # Validate and normalize email if present
    if "email" in v:
        email = EmailChannel.model_validate(v["email"])
        result["email"] = {"to": email.to}

    return result


# ──────────────────────────────────────────────
# Alert Rule Schemas (T3)
# ──────────────────────────────────────────────
class AlertRuleCreate(BaseModel):
    """Request para crear una regla de alerta."""

    entity_type: EntityType
    entity_id: UUID | None = None
    metric: str = Field(min_length=1, max_length=100)
    operator: AlertOperator
    threshold: float
    duration_s: int = Field(default=60, ge=1)
    severity: AlertSeverity = AlertSeverity.WARNING
    channels: dict = Field(default_factory=dict)
    is_active: bool = True

    @field_validator("channels", mode="before")
    @classmethod
    def validate_channels_create(cls, v: dict) -> dict:
        validated = _validate_channels_dict(v)
        if not validated:
            raise ValueError("At least one channel (webhook or email) is required")
        return validated


class AlertRuleUpdate(BaseModel):
    """Request para actualizar una regla de alerta (campos opcionales)."""

    entity_type: EntityType | None = None
    entity_id: UUID | None = None
    metric: str | None = Field(default=None, min_length=1, max_length=100)
    operator: AlertOperator | None = None
    threshold: float | None = None
    duration_s: int | None = Field(default=None, ge=1)
    severity: AlertSeverity | None = None
    channels: dict | None = None
    is_active: bool | None = None

    @field_validator("channels", mode="before")
    @classmethod
    def validate_channels_update(cls, v: dict | None) -> dict | None:
        if v is None:
            return None
        validated = _validate_channels_dict(v)
        if not validated:
            raise ValueError("At least one channel (webhook or email) is required")
        return validated


class AlertRuleResponse(BaseModel):
    """Response de regla de alerta."""

    id: UUID
    tenant_id: UUID
    entity_type: EntityType
    entity_id: UUID | None
    metric: str
    operator: AlertOperator
    threshold: float
    duration_s: int
    severity: AlertSeverity
    channels: dict
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ──────────────────────────────────────────────
# Alert Schemas (T4)
# ──────────────────────────────────────────────
class AlertResponse(BaseModel):
    """Response de alerta."""

    id: UUID
    tenant_id: UUID
    rule_id: UUID
    server_id: UUID | None
    severity: AlertSeverity
    status: AlertStatus
    message: str
    triggered_at: datetime
    resolved_at: datetime | None
    acknowledged_at: datetime | None
    acknowledged_by: UUID | None
    value_at_trigger: float
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AlertAckRequest(BaseModel):
    """Request para acknowledge de alerta."""

    acknowledged_by: UUID


class AlertAckResponse(BaseModel):
    """Response de acknowledge/resolve de alerta."""

    id: UUID
    status: AlertStatus
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    acknowledged_by: UUID | None


# ──────────────────────────────────────────────
# Alert Query Schemas
# ──────────────────────────────────────────────
class AlertListParams(BaseModel):
    """Parámetros de consulta para listar alertas."""

    status: AlertStatus | None = None
    severity: AlertSeverity | None = None
    rule_id: UUID | None = None
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
