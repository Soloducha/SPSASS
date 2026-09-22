"""Esquemas Pydantic para API v1 (servidores e ingesta)."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field

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
