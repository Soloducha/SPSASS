"""Router de servidores: registro y heartbeat."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status

from app.api.v1.schemas import (
    ServerRegisterRequest,
    ServerRegisterResponse,
)
from app.core.auth.dependencies import ApiKeyAuth, SessionDep
from app.core.logging import get_logger
from app.models.server import ServerStatus
from app.repositories.server import ServerRepository

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/servers", tags=["servers"])


@router.post("/register", response_model=ServerRegisterResponse)
async def register_server(
    session: SessionDep,
    auth: ApiKeyAuth,
    data: ServerRegisterRequest,
    response: Response,
) -> ServerRegisterResponse:
    """
    Registra un nuevo servidor o actualiza uno existente (upsert por tenant+hostname).

    - Si el servidor ya existe en el tenant: actualiza ip, os, agent_version (si vienen),
      marca status=ONLINE y actualiza last_heartbeat_at -> 200 OK.
    - Si no existe: crea con status=ONLINE y last_heartbeat_at=now -> 201 Created.
    """
    tenant, _ = auth
    repo = ServerRepository(session)

    # Buscar server existente por (tenant_id, hostname)
    existing = await repo.get_by(hostname=data.hostname)

    now = datetime.now(UTC)

    if existing:
        # Actualizar campos si vienen no-None
        update_data = {"status": ServerStatus.ONLINE, "last_heartbeat_at": now}
        if data.ip is not None:
            update_data["ip"] = data.ip
        if data.os is not None:
            update_data["os"] = data.os
        if data.agent_version is not None:
            update_data["agent_version"] = data.agent_version

        server = await repo.update(existing.id, **update_data)
        assert server is not None  # Ya verificamos que existe
        logger.info("server_updated", server_id=str(server.id), hostname=data.hostname)
        response.status_code = status.HTTP_200_OK
    else:
        # Crear nuevo
        server = await repo.create(
            hostname=data.hostname,
            ip=data.ip,
            os=data.os,
            agent_version=data.agent_version,
            status=ServerStatus.ONLINE,
            last_heartbeat_at=now,
        )
        logger.info("server_created", server_id=str(server.id), hostname=data.hostname)
        response.status_code = status.HTTP_201_CREATED

    return ServerRegisterResponse(
        id=server.id,
        hostname=server.hostname,
        status=server.status.value,
        agent_version=server.agent_version,
        last_heartbeat_at=server.last_heartbeat_at,
    )


@router.post("/{server_id}/heartbeat", status_code=status.HTTP_200_OK)
async def heartbeat_server(
    session: SessionDep,
    auth: ApiKeyAuth,
    server_id: UUID,
) -> dict:
    """
    Actualiza heartbeat del servidor: last_heartbeat_at=now, status=ONLINE.

    Solo funciona si el servidor pertenece al tenant de la API key (404 si no).
    """
    tenant, _ = auth
    repo = ServerRepository(session)

    server = await repo.get(server_id)
    if not server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Server no encontrado",
        )

    now = datetime.now(UTC)
    await repo.update(server_id, status=ServerStatus.ONLINE, last_heartbeat_at=now)

    logger.info("server_heartbeat", server_id=str(server_id), tenant_id=str(tenant.id))

    return {"server_id": str(server_id), "heartbeat_at": now.isoformat()}
