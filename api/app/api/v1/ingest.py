"""Router de ingesta de métricas."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, status

from app.api.v1.schemas import (
    IngestResponse,
    MetricIngestPayload,
)
from app.core.auth.dependencies import ApiKeyAuth, SessionDep
from app.core.logging import get_logger
from app.repositories.metric import MetricRepository
from app.repositories.server import ServerRepository

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["ingest"])


@router.post(
    "/ingest/metrics",
    response_model=IngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def ingest_metrics(
    session: SessionDep,
    auth: ApiKeyAuth,
    payload: MetricIngestPayload,
) -> IngestResponse:
    """
    Ingiere un batch de métricas para un servidor.

    - Valida que el server_id pertenece al tenant de la API key (404 si no).
    - Inserta métricas con tenant_id forzado del contexto.
    - Batch cap: máx 1000 items (validado por schema).
    - Si múltiples métricas comparten el mismo ts, se añade offset microsegundos
      para evitar colisión en PK compuesta (ts, server_id).
    - Retorna 202 con conteo de recibidas/insertadas.
    """
    tenant, _ = auth

    # Validar que el server existe en este tenant
    server_repo = ServerRepository(session)
    server = await server_repo.get(payload.server_id)
    if not server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Server no encontrado",
        )

    # Preparar timestamp base
    base_ts = payload.ts if payload.ts is not None else datetime.now(UTC)

    # Preparar rows para bulk_create
    metric_repo = MetricRepository(session)
    items = []
    for i, m in enumerate(payload.metrics):
        # Si hay múltiples métricas con mismo ts, añadir offset microsegundos
        ts = base_ts + timedelta(microseconds=i) if i > 0 else base_ts
        items.append(
            {
                "ts": ts,
                "server_id": payload.server_id,
                "type": m.type,
                "value": m.value,
                "tags": m.tags or {},
            }
        )

    # Bulk insert (tenant_id se fuerza en TenantScopedRepository.bulk_create)
    await metric_repo.bulk_create(items)

    logger.info(
        "metrics_ingested",
        server_id=str(payload.server_id),
        tenant_id=str(tenant.id),
        count=len(items),
    )

    return IngestResponse(
        received=len(payload.metrics),
        inserted=len(items),
        server_id=payload.server_id,
    )
