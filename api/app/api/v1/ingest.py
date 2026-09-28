"""Router de ingesta de métricas y estado de entidades."""

import re
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.api.v1.schemas import (
    EntitiesIngestResponse,
    EntityIngestPayload,
    EntityProcessItem,
    EntityServiceItem,
    IngestResponse,
    MetricIngestPayload,
)
from app.core.auth.dependencies import ApiKeyAuth, SessionDep
from app.core.logging import get_logger
from app.models.service import Service, ServiceState
from app.repositories.metric import MetricRepository
from app.repositories.process import ProcessRepository
from app.repositories.server import ServerRepository
from app.repositories.service import ServiceRepository

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["ingest"])


# ──────────────────────────────────────────────
# Ingest Metrics (existing)
# ──────────────────────────────────────────────

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


# ──────────────────────────────────────────────
# Ingest Entity State (T4)
# ──────────────────────────────────────────────

@router.post(
    "/ingest/entities",
    response_model=EntitiesIngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def ingest_entities(
    session: SessionDep,
    auth: ApiKeyAuth,
    payload: EntityIngestPayload,
) -> EntitiesIngestResponse:
    """
    Ingiere el estado de entidades (procesos y servicios) para un servidor.

    - Valida que el server_id pertenece al tenant de la API key (404 si no).
    - Services: actualiza last_status y last_checked_at en config rows que coinciden.
    - Processes: actualiza last_count (cuenta coincidencias de regex pattern) y last_checked_at.
    - Retorna 202 con conteo de recibidas/coincidencias.
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

    # Timestamp base (usado en services y processes para last_checked_at)
    ingest_ts = payload.ts if payload.ts is not None else datetime.now(UTC)

    # ──────────────────────────────────────────────
    # Services: actualizar last_status / last_checked_at
    # ──────────────────────────────────────────────
    matched_services = 0
    if payload.services:
        matched_services = await _update_services(
            session, payload.server_id, payload.services, ingest_ts
        )

    # ──────────────────────────────────────────────
    # Processes: actualizar last_count (regex match) y last_checked_at
    # ──────────────────────────────────────────────
    matched_processes = 0
    if payload.processes:
        matched_processes = await _update_processes(
            session, payload.server_id, payload.processes, payload.ts
        )

    logger.info(
        "entities_ingested",
        server_id=str(payload.server_id),
        tenant_id=str(tenant.id),
        received_processes=len(payload.processes),
        received_services=len(payload.services),
        matched_processes=matched_processes,
        matched_services=matched_services,
    )

    return EntitiesIngestResponse(
        received_processes=len(payload.processes),
        received_services=len(payload.services),
        matched_processes=matched_processes,
        matched_services=matched_services,
        server_id=payload.server_id,
    )


async def _update_services(
    session: SessionDep,
    server_id: UUID,
    reported_services: list[EntityServiceItem],
    ingest_ts: datetime,
) -> int:
    """Actualiza last_status y last_checked_at de servicios que coinciden."""
    service_repo = ServiceRepository(session)
    services = await service_repo.list_all(server_id=server_id)
    service_map = {s.name: s for s in services}

    matched_count: int = 0
    for svc in reported_services:
        # Match: exact case-insensitive name match
        matched_svc: Service | None = None
        for name, config_svc in service_map.items():
            if name.lower() == svc.name.lower():
                matched_svc = config_svc
                break

        if matched_svc:
            try:
                state = ServiceState(svc.state)
            except ValueError:
                state = ServiceState.UNKNOWN

            await service_repo.update(
                matched_svc.id,
                last_status=state,
                last_checked_at=ingest_ts,
            )
            matched_count += 1
    return matched_count


async def _update_processes(
    session: SessionDep,
    server_id: UUID,
    reported_processes: list[EntityProcessItem],
    payload_ts: datetime | None,
) -> int:
    """Actualiza last_count (regex match) y last_checked_at de procesos que coinciden."""
    process_repo = ProcessRepository(session)
    processes = list(await process_repo.list_all(server_id=server_id))

    ingest_ts = payload_ts if payload_ts is not None else datetime.now(UTC)
    matched: int = 0

    for proc_config in processes:
        count = 0
        for rp in reported_processes:
            try:
                if re.search(proc_config.pattern, rp.name) or (
                    rp.cmdline and re.search(proc_config.pattern, rp.cmdline)
                ):
                    count += 1
            except re.error:
                logger.warning(
                    "process_invalid_regex",
                    process_id=str(proc_config.id),
                    pattern=proc_config.pattern,
                )
                break

        # Always update last_checked_at; last_count reflects matches (0 if no matches)
        await process_repo.update(
            proc_config.id,
            last_count=count,
            last_checked_at=ingest_ts,
        )
        matched += 1
    return matched
