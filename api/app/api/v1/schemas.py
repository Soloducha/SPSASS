"""Esquemas Pydantic para API v1 (servidores, ingesta, alertas, procesos, servicios, jobs)."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import (
    BaseModel,
    EmailStr,
    Field,
    HttpUrl,
    computed_field,
    field_validator,
    model_validator,
)

from app.models.alert import AlertOperator, AlertSeverity, AlertStatus, EntityType
from app.models.job import JobKind, JobStatus
from app.models.metric import MetricType
from app.models.service import ServiceState


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


class TelegramChannel(BaseModel):
    """Configuración del canal telegram."""

    chat_id: Annotated[str, Field(min_length=1)]
    thread_id: int | None = None
    silent: bool = False


# Valid channel keys
ALLOWED_CHANNEL_KEYS = frozenset({"webhook", "email", "telegram"})


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

    # Validate and normalize telegram if present
    if "telegram" in v:
        telegram = TelegramChannel.model_validate(v["telegram"])
        telegram_config: dict = {"chat_id": telegram.chat_id}
        if telegram.thread_id is not None:
            telegram_config["thread_id"] = telegram.thread_id
        if telegram.silent:
            telegram_config["silent"] = True
        result["telegram"] = telegram_config

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
            raise ValueError("At least one channel (webhook, email or telegram) is required")
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
            raise ValueError("At least one channel (webhook, email or telegram) is required")
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
    rule_id: UUID | None
    server_id: UUID | None
    severity: AlertSeverity
    status: AlertStatus
    message: str
    triggered_at: datetime
    resolved_at: datetime | None
    acknowledged_at: datetime | None
    acknowledged_by: UUID | None
    value_at_trigger: float
    silenced_at: datetime | None = Field(default=None, exclude=True)
    created_at: datetime
    updated_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def silenced(self) -> bool:
        """Si un humano silenció esta alerta (la resolvió mientras violaba).

        Derivado de `silenced_at` para que el cliente no tenga que
        interpretar null. `silenced_at` queda excluido de la serialización:
        es estado interno del episodio, no parte del contrato público.
        """
        return self.silenced_at is not None

    model_config = {"from_attributes": True}


class AlertAckRequest(BaseModel):
    """Request para acknowledge de alerta.

    El campo `acknowledged_by` está **deprecated/ignorado**.
    El actor se deriva siempre del usuario autenticado (JWT `sub`).
    Se mantiene solo para compatibilidad hacia atrás.
    """

    acknowledged_by: UUID | None = None


class AlertAckResponse(BaseModel):
    """Response de acknowledge/resolve de alerta."""

    id: UUID
    status: AlertStatus
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    acknowledged_by: UUID | None
    silenced_at: datetime | None = Field(default=None, exclude=True)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def silenced(self) -> bool:
        """Derivado de `silenced_at`; ver `AlertResponse.silenced`."""
        return self.silenced_at is not None


# ──────────────────────────────────────────────
# Alert Query Schemas
# ──────────────────────────────────────────────
class AlertListParams(BaseModel):
    """Parámetros de consulta para listar alertas."""

    status: AlertStatus | None = None
    severity: AlertSeverity | None = None
    silenced: bool | None = None
    rule_id: UUID | None = None
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


# ──────────────────────────────────────────────
# Process Schemas (T1)
# ──────────────────────────────────────────────
class ProcessCreate(BaseModel):
    """Request para crear un proceso."""

    server_id: UUID
    name: str = Field(min_length=1, max_length=255)
    pattern: str = Field(min_length=1, max_length=500)
    expected_count: int = Field(default=1, ge=1)
    auto_restart: bool = False
    config: dict = Field(default_factory=dict)


class ProcessUpdate(BaseModel):
    """Request para actualizar un proceso (campos opcionales)."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    pattern: str | None = Field(default=None, min_length=1, max_length=500)
    expected_count: int | None = Field(default=None, ge=1)
    auto_restart: bool | None = None
    config: dict | None = None


class ProcessResponse(BaseModel):
    """Response de proceso."""

    id: UUID
    tenant_id: UUID
    server_id: UUID
    name: str
    pattern: str
    expected_count: int
    auto_restart: bool
    config: dict
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ──────────────────────────────────────────────
# Service Schemas (T1)
# ──────────────────────────────────────────────
class ServiceCreate(BaseModel):
    """Request para crear un servicio."""

    server_id: UUID
    name: str = Field(min_length=1, max_length=255)
    desired_state: ServiceState = ServiceState.RUNNING
    auto_restart: bool = False
    config: dict = Field(default_factory=dict)


class ServiceUpdate(BaseModel):
    """Request para actualizar un servicio (campos opcionales)."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    desired_state: ServiceState | None = None
    auto_restart: bool | None = None
    config: dict | None = None


class ServiceResponse(BaseModel):
    """Response de servicio."""

    id: UUID
    tenant_id: UUID
    server_id: UUID
    name: str
    desired_state: ServiceState
    auto_restart: bool
    last_status: ServiceState
    last_checked_at: datetime | None
    config: dict
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ──────────────────────────────────────────────
# Job Schemas (T1)
# ──────────────────────────────────────────────
class JobCreate(BaseModel):
    """Request para crear un job."""

    server_id: UUID
    name: str = Field(min_length=1, max_length=255)
    kind: JobKind
    schedule_cron: str | None = Field(default=None, max_length=100)
    command: str = Field(min_length=1)
    timeout_s: int = Field(default=3600, ge=1)
    alert_on_fail: bool = True
    auto_restart: bool = False
    status: JobStatus = JobStatus.ACTIVE
    config: dict = Field(default_factory=dict)

    @field_validator("config", mode="before")
    @classmethod
    def validate_config_channels(cls, v: dict) -> dict:
        """Valida y normaliza el sub-dict channels dentro de config si está presente."""
        if not isinstance(v, dict):
            raise ValueError("config must be a dict")  # noqa: TRY004 - Pydantic v2 mode="before" validators need ValueError

        # Only validate channels if the key is explicitly present
        if "channels" in v:
            channels = v["channels"]
            if not isinstance(channels, dict):
                raise ValueError("config.channels must be a dict")  # noqa: TRY004 - Pydantic v2 mode="before" validators need ValueError
            # Validate and normalize channels, but allow empty dict
            validated_channels = _validate_channels_dict(channels)
            # Replace with normalized version (may be empty)
            v = {**v, "channels": validated_channels}
        return v

    @model_validator(mode="after")
    def validate_cron_schedule(self) -> "JobCreate":
        """Valida que schedule_cron esté presente para jobs CRON."""
        if self.kind == JobKind.CRON and not self.schedule_cron:
            raise ValueError("schedule_cron is required for CRON jobs")
        return self


class JobUpdate(BaseModel):
    """Request para actualizar un job (campos opcionales)."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    kind: JobKind | None = None
    schedule_cron: str | None = Field(default=None, max_length=100)
    command: str | None = Field(default=None, min_length=1)
    timeout_s: int | None = Field(default=None, ge=1)
    alert_on_fail: bool | None = None
    auto_restart: bool | None = None
    status: JobStatus | None = None
    config: dict | None = None

    @field_validator("config", mode="before")
    @classmethod
    def validate_config_channels(cls, v: dict | None) -> dict | None:
        """Valida y normaliza el sub-dict channels dentro de config si está presente."""
        if v is None:
            return None
        if not isinstance(v, dict):
            raise ValueError("config must be a dict")  # noqa: TRY004 - Pydantic v2 mode="before" validators need ValueError

        # Only validate channels if the key is explicitly present
        if "channels" in v:
            channels = v["channels"]
            if not isinstance(channels, dict):
                raise ValueError("config.channels must be a dict")  # noqa: TRY004 - Pydantic v2 mode="before" validators need ValueError
            # Validate and normalize channels, but allow empty dict
            validated_channels = _validate_channels_dict(channels)
            # Replace with normalized version (may be empty), preserve other keys
            v = {**v, "channels": validated_channels}
        return v


class JobResponse(BaseModel):
    """Response de job."""

    id: UUID
    tenant_id: UUID
    server_id: UUID
    name: str
    kind: JobKind
    schedule_cron: str | None
    command: str
    timeout_s: int
    alert_on_fail: bool
    auto_restart: bool
    status: JobStatus
    config: dict
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ──────────────────────────────────────────────
# JobRun Schemas (T1)
# ──────────────────────────────────────────────
class JobRunResponse(BaseModel):
    """Response de ejecución de job."""

    id: UUID
    tenant_id: UUID
    job_id: UUID
    started_at: datetime
    finished_at: datetime | None
    exit_code: int | None
    status: str
    output_tail: str | None
    run_metadata: dict

    model_config = {"from_attributes": True}


class JobRunListParams(BaseModel):
    """Parámetros de consulta para listar ejecuciones de job."""

    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class JobListParams(BaseModel):
    """Parámetros de consulta para listar jobs."""

    server_id: UUID | None = None
    status: JobStatus | None = None
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


# ──────────────────────────────────────────────
# Entity Ingest Schemas (T4)
# ──────────────────────────────────────────────

class EntityProcessItem(BaseModel):
    """Proceso reportado por el agente."""

    name: str = Field(min_length=1, max_length=255)
    cmdline: str | None = None
    state: str = Field(min_length=1)  # "running" | "unknown"


class EntityServiceItem(BaseModel):
    """Servicio reportado por el agente."""

    name: str = Field(min_length=1, max_length=255)
    state: str = Field(min_length=1)  # "running" | "stopped" | "failed" | "unknown"


class EntityIngestPayload(BaseModel):
    """Payload para ingesta de estado de entidades (procesos y servicios)."""

    server_id: UUID
    ts: datetime | None = None
    processes: list[EntityProcessItem] = Field(default_factory=list)
    services: list[EntityServiceItem] = Field(default_factory=list)


class EntitiesIngestResponse(BaseModel):
    """Response de ingesta de estado de entidades."""

    received_processes: int
    received_services: int
    matched_processes: int
    matched_services: int
    server_id: UUID
