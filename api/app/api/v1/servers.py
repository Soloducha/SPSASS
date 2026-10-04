"""Router de servidores: registro, heartbeat y comandos de agente (auto-restart)."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status

from app.api.v1.schemas import (
    AgentCommandCreate,
    AgentCommandPendingResponse,
    AgentCommandResponse,
    AgentCommandResultRequest,
    ServerRegisterRequest,
    ServerRegisterResponse,
)
from app.core.auth.dependencies import ApiKeyAuth, CurrentUser, SessionDep
from app.core.logging import get_logger
from app.models.agent_command import AgentCommand, AgentCommandStatus
from app.models.server import ServerStatus
from app.repositories.agent_command import AgentCommandRepository
from app.repositories.process import ProcessRepository
from app.repositories.server import ServerRepository
from app.repositories.service import ServiceRepository

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


# ──────────────────────────────────────────────
# Agent Commands (Auto-restart)
# ──────────────────────────────────────────────

@router.post("/{server_id}/restart", response_model=AgentCommandResponse, status_code=status.HTTP_201_CREATED)
async def enqueue_restart_command(
    session: SessionDep,
    user: CurrentUser,
    server_id: UUID,
    data: AgentCommandCreate,
) -> AgentCommandResponse:
    """
    Encola un comando de restart para un servicio o proceso en el servidor.

    Requiere JWT de usuario (CurrentUser). Valida que el servidor y la entidad
    pertenecen al tenant del usuario. Evita duplicados (pending/running para
    misma entidad).
    """
    cmd_repo = AgentCommandRepository(session)
    server_repo = ServerRepository(session)

    # Verificar servidor
    server = await server_repo.get(server_id)
    if not server:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Server no encontrado")

    # Validar entity_type
    if data.entity_type not in ("service", "process"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"entity_type inválido: {data.entity_type}. Permitidos: service, process",
        )
    entity_type_enum = data.entity_type  # type: ignore[assignment]

    # Verificar entidad existe y pertenece al tenant+server
    if entity_type_enum == "service":
        svc_repo = ServiceRepository(session)
        entity = await svc_repo.get_by(name=data.entity_name, server_id=server_id)
        if not entity:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Service '{data.entity_name}' no encontrado en este servidor",
            )
    elif entity_type_enum == "process":
        proc_repo = ProcessRepository(session)
        entity = await proc_repo.get_by(name=data.entity_name, server_id=server_id)
        if not entity:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Process '{data.entity_name}' no encontrado en este servidor",
            )

    # Idempotencia: no encolar si ya hay pending/running para misma entidad
    if await cmd_repo.has_pending_for_entity(server_id, data.entity_type, data.entity_name):
        logger.info(
            "restart_command_skipped_duplicate",
            server_id=str(server_id),
            entity_type=data.entity_type,
            entity_name=data.entity_name,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya hay un comando pendiente/ejecutándose para {data.entity_type}:{data.entity_name}",
        )

    # Crear comando
    command = AgentCommand(
        tenant_id=user.tenant_id,
        server_id=server_id,
        entity_type=entity_type_enum,
        entity_name=data.entity_name,
        command=data.command,
        status=AgentCommandStatus.PENDING,
        scheduled_at=datetime.now(UTC),
    )
    session.add(command)
    await session.flush()

    logger.info(
        "restart_command_enqueued",
        command_id=str(command.id),
        server_id=str(server_id),
        entity_type=data.entity_type,
        entity_name=data.entity_name,
        tenant_id=str(user.tenant_id),
    )
    return AgentCommandResponse.model_validate(command)


@router.get("/{server_id}/commands", response_model=list[AgentCommandPendingResponse])
async def get_pending_commands(
    session: SessionDep,
    auth: ApiKeyAuth,
    server_id: UUID,
) -> list[AgentCommandPendingResponse]:
    """
    Obtiene comandos pendientes para un servidor (polling del agente).

    Requiere API key. Devuelve comandos con status=PENDING y scheduled_at <= now.
    Marca los comandos devueltos como RUNNING (started_at=now) para evitar
    que otro agente los tome.
    """
    tenant, _ = auth
    cmd_repo = AgentCommandRepository(session)
    server_repo = ServerRepository(session)

    # Verificar servidor pertenece al tenant
    server = await server_repo.get(server_id)
    if not server:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Server no encontrado")

    # Obtener comandos pendientes
    commands = await cmd_repo.list_pending_for_server(server_id)

    if not commands:
        return []

    # Marcar como RUNNING
    command_ids = [c.id for c in commands]
    await cmd_repo.mark_running(command_ids)

    logger.info(
        "agent_commands_fetched",
        server_id=str(server_id),
        count=len(commands),
        command_ids=[str(c.id) for c in commands],
    )

    return [
        AgentCommandPendingResponse(
            id=c.id,
            entity_type=c.entity_type.value,
            entity_name=c.entity_name,
            command=c.command,
            max_attempts=c.max_attempts,
            backoff_s=c.backoff_s,
        )
        for c in commands
    ]


@router.patch("/agent-commands/{command_id}/result", response_model=AgentCommandResponse)
async def report_command_result(
    session: SessionDep,
    auth: ApiKeyAuth,
    command_id: UUID,
    data: AgentCommandResultRequest,
) -> AgentCommandResponse:
    """
    Reporta el resultado de la ejecución de un comando (agente).

    Requiere API key. Actualiza status, exit_code, output_tail, finished_at.
    """
    from app.core.logging import get_logger
    logger = get_logger(__name__)
    
    tenant, _ = auth
    
    cmd_repo = AgentCommandRepository(session)

    # data.status ya es AgentCommandStatus enum (validado por Pydantic)
    status_enum = data.status

    command = await cmd_repo.set_result(
        command_id,
        tenant.id,
        status=status_enum,
        exit_code=data.exit_code,
        output_tail=data.output_tail,
    )
    if not command:
        logger.warning("Command not found for command_id=%s, tenant_id=%s", command_id, tenant.id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Command no encontrado")

    logger.info(
        "agent_command_result",
        command_id=str(command_id),
        status=data.status.value,
        exit_code=data.exit_code,
    )
    return AgentCommandResponse.model_validate(command)
