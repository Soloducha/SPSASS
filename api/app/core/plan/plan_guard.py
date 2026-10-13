"""Dependencias FastAPI para Plan Gates (enforcement de límites por plan)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import CurrentTenant, SessionDep
from app.core.logging import get_logger
from app.core.plan.plan_limits import (
    MAX_API_KEYS,
    MAX_JOBS_PER_SERVER,
    MAX_MEMBERS,
    MAX_PROCESSES_PER_SERVER,
    MAX_REPORTS_PER_MONTH,
    MAX_SERVERS,
    MAX_SERVICES_PER_SERVER,
    PlanLimitExceededError,
    PlanType,
    check_limit,
    get_allowed_channels,
    get_limit,
    get_retention_days,
    validate_alert_channels,
)
from app.models.api_key import ApiKey
from app.models.job import Job
from app.models.process import Process
from app.models.report import Report
from app.models.server import Server
from app.models.service import Service
from app.models.tenant import Tenant
from app.models.tenant_member import TenantMember

logger = get_logger(__name__)


# ──────────────────────────────────────────────
# Helpers de conteo (read-only, reutilizables)
# ──────────────────────────────────────────────

async def count_servers(session: AsyncSession, tenant_id: UUID) -> int:
    """Cuenta servidores activos del tenant."""
    result = await session.execute(
        select(func.count(Server.id)).where(Server.tenant_id == tenant_id)
    )
    return result.scalar_one() or 0


async def count_api_keys(session: AsyncSession, tenant_id: UUID) -> int:
    """Cuenta API keys del tenant."""
    result = await session.execute(
        select(func.count(ApiKey.id)).where(ApiKey.tenant_id == tenant_id)
    )
    return result.scalar_one() or 0


async def count_members(session: AsyncSession, tenant_id: UUID) -> int:
    """Cuenta miembros del tenant (incluye owner)."""
    result = await session.execute(
        select(func.count(TenantMember.id)).where(TenantMember.tenant_id == tenant_id)
    )
    return result.scalar_one() or 0


async def count_reports_this_month(session: AsyncSession, tenant_id: UUID) -> int:
    """Cuenta reportes generados en el mes actual."""
    now = datetime.now(UTC)
    month_start = datetime(now.year, now.month, 1, tzinfo=UTC)
    result = await session.execute(
        select(func.count(Report.id)).where(
            Report.tenant_id == tenant_id,
            Report.created_at >= month_start,
        )
    )
    return result.scalar_one() or 0


async def count_services_for_server(session: AsyncSession, server_id: UUID) -> int:
    """Cuenta servicios de un servidor."""
    result = await session.execute(
        select(func.count(Service.id)).where(Service.server_id == server_id)
    )
    return result.scalar_one() or 0


async def count_jobs_for_server(session: AsyncSession, server_id: UUID) -> int:
    """Cuenta jobs de un servidor."""
    result = await session.execute(
        select(func.count(Job.id)).where(Job.server_id == server_id)
    )
    return result.scalar_one() or 0


async def count_processes_for_server(session: AsyncSession, server_id: UUID) -> int:
    """Cuenta procesos de un servidor."""
    result = await session.execute(
        select(func.count(Process.id)).where(Process.server_id == server_id)
    )
    return result.scalar_one() or 0


# ──────────────────────────────────────────────
# Plan Guards por recurso
# ──────────────────────────────────────────────

async def guard_server_creation(
    session: SessionDep,
    tenant: CurrentTenant,
) -> None:
    """
    Valida que el tenant puede crear un servidor más.
    Lanza 403 si se excede el límite del plan.
    """
    current = await count_servers(session, tenant.id)
    limit = get_limit(MAX_SERVERS, tenant.plan)
    try:
        check_limit(current, limit, "servidores")
    except PlanLimitExceededError as e:
        logger.warning(
            "plan_limit_exceeded_server",
            tenant_id=str(tenant.id),
            plan=tenant.plan.value,
            current=current,
            limit=limit,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        ) from e


async def guard_api_key_creation(
    session: SessionDep,
    tenant: CurrentTenant,
) -> None:
    """
    Valida que el tenant puede crear una API key más.
    Lanza 403 si se excede el límite del plan.
    """
    current = await count_api_keys(session, tenant.id)
    limit = get_limit(MAX_API_KEYS, tenant.plan)
    try:
        check_limit(current, limit, "API keys")
    except PlanLimitExceededError as e:
        logger.warning(
            "plan_limit_exceeded_api_key",
            tenant_id=str(tenant.id),
            plan=tenant.plan.value,
            current=current,
            limit=limit,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        ) from e


async def guard_report_creation(
    session: SessionDep,
    tenant: CurrentTenant,
) -> None:
    """
    Valida que el tenant puede crear/generar un reporte más este mes.
    Lanza 403 si se excede el límite del plan.
    """
    current = await count_reports_this_month(session, tenant.id)
    limit = get_limit(MAX_REPORTS_PER_MONTH, tenant.plan)
    try:
        check_limit(current, limit, "reportes/mes")
    except PlanLimitExceededError as e:
        logger.warning(
            "plan_limit_exceeded_report",
            tenant_id=str(tenant.id),
            plan=tenant.plan.value,
            current=current,
            limit=limit,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        ) from e


async def guard_invitation_creation(
    session: SessionDep,
    tenant: CurrentTenant,
) -> None:
    """
    Valida que el tenant puede invitar un miembro más.
    Lanza 403 si se excede el límite de miembros del plan.
    """
    current = await count_members(session, tenant.id)
    limit = get_limit(MAX_MEMBERS, tenant.plan)
    try:
        check_limit(current, limit, "miembros")
    except PlanLimitExceededError as e:
        logger.warning(
            "plan_limit_exceeded_member",
            tenant_id=str(tenant.id),
            plan=tenant.plan.value,
            current=current,
            limit=limit,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        ) from e


async def guard_service_creation(
    session: SessionDep,
    tenant: CurrentTenant,
    server_id: UUID,
) -> None:
    """
    Valida que el servidor puede tener un servicio más.
    Lanza 403 si se excede el límite del plan.
    """
    current = await count_services_for_server(session, server_id)
    limit = get_limit(MAX_SERVICES_PER_SERVER, tenant.plan)
    try:
        check_limit(current, limit, "servicios por servidor")
    except PlanLimitExceededError as e:
        logger.warning(
            "plan_limit_exceeded_service",
            tenant_id=str(tenant.id),
            server_id=str(server_id),
            plan=tenant.plan.value,
            current=current,
            limit=limit,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        ) from e


async def guard_job_creation(
    session: SessionDep,
    tenant: CurrentTenant,
    server_id: UUID,
) -> None:
    """
    Valida que el servidor puede tener un job más.
    Lanza 403 si se excede el límite del plan.
    """
    current = await count_jobs_for_server(session, server_id)
    limit = get_limit(MAX_JOBS_PER_SERVER, tenant.plan)
    try:
        check_limit(current, limit, "jobs por servidor")
    except PlanLimitExceededError as e:
        logger.warning(
            "plan_limit_exceeded_job",
            tenant_id=str(tenant.id),
            server_id=str(server_id),
            plan=tenant.plan.value,
            current=current,
            limit=limit,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        ) from e


async def guard_process_creation(
    session: SessionDep,
    tenant: CurrentTenant,
    server_id: UUID,
) -> None:
    """
    Valida que el servidor puede tener un proceso más.
    Lanza 403 si se excede el límite del plan.
    """
    current = await count_processes_for_server(session, server_id)
    limit = get_limit(MAX_PROCESSES_PER_SERVER, tenant.plan)
    try:
        check_limit(current, limit, "procesos por servidor")
    except PlanLimitExceededError as e:
        logger.warning(
            "plan_limit_exceeded_process",
            tenant_id=str(tenant.id),
            server_id=str(server_id),
            plan=tenant.plan.value,
            current=current,
            limit=limit,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        ) from e


# ──────────────────────────────────────────────
# Dependency factories para FastAPI
# ──────────────────────────────────────────────

def require_server_limit() -> None:
    """Dependency factory para validar límite de servidores."""
    # Se usa como: Depends(require_server_limit)
    # FastAPI llamará a la función interna con los parámetros resueltos
    pass


# Para usar en endpoints: agregar `plan_guard: None = Depends(guard_server_creation)`
# y FastAPI la ejecutará antes del endpoint.


async def validate_alert_rule_channels(
    tenant: CurrentTenant,
    channels: set[str],
) -> None:
    """
    Valida que los canales de una alert rule estén permitidos para el plan.
    Lanza 403 si algún canal no está permitido.

    Uso: llamar desde el endpoint de creación de alert rules.
    """
    try:
        validate_alert_channels(tenant.plan, channels)
    except PlanLimitExceededError as e:
        logger.warning(
            "plan_limit_exceeded_alert_channels",
            tenant_id=str(tenant.id),
            plan=tenant.plan.value,
            requested_channels=sorted(channels),
            allowed_channels=sorted(get_allowed_channels(tenant.plan)),
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        ) from e


# ──────────────────────────────────────────────
# Helpers públicos para uso en servicios/web
# ──────────────────────────────────────────────

async def can_create_server(session: AsyncSession, tenant: Tenant) -> tuple[bool, int, int | None]:
    """
    Verifica si el tenant puede crear un servidor.

    Returns:
        (allowed, current_count, limit)
    """
    current = await count_servers(session, tenant.id)
    limit = get_limit(MAX_SERVERS, tenant.plan)
    allowed = limit is None or current < limit
    return allowed, current, limit


async def can_create_api_key(session: AsyncSession, tenant: Tenant) -> tuple[bool, int, int | None]:
    """Verifica si el tenant puede crear una API key."""
    current = await count_api_keys(session, tenant.id)
    limit = get_limit(MAX_API_KEYS, tenant.plan)
    allowed = limit is None or current < limit
    return allowed, current, limit


async def can_create_report(session: AsyncSession, tenant: Tenant) -> tuple[bool, int, int | None]:
    """Verifica si el tenant puede crear un reporte este mes."""
    current = await count_reports_this_month(session, tenant.id)
    limit = get_limit(MAX_REPORTS_PER_MONTH, tenant.plan)
    allowed = limit is None or current < limit
    return allowed, current, limit


async def can_invite_member(session: AsyncSession, tenant: Tenant) -> tuple[bool, int, int | None]:
    """Verifica si el tenant puede invitar un miembro más."""
    current = await count_members(session, tenant.id)
    limit = get_limit(MAX_MEMBERS, tenant.plan)
    allowed = limit is None or current < limit
    return allowed, current, limit


async def can_create_service(
    session: AsyncSession, tenant: Tenant, server_id: UUID
) -> tuple[bool, int, int | None]:
    """Verifica si el servidor puede tener un servicio más."""
    current = await count_services_for_server(session, server_id)
    limit = get_limit(MAX_SERVICES_PER_SERVER, tenant.plan)
    allowed = limit is None or current < limit
    return allowed, current, limit


async def can_create_job(
    session: AsyncSession, tenant: Tenant, server_id: UUID
) -> tuple[bool, int, int | None]:
    """Verifica si el servidor puede tener un job más."""
    current = await count_jobs_for_server(session, server_id)
    limit = get_limit(MAX_JOBS_PER_SERVER, tenant.plan)
    allowed = limit is None or current < limit
    return allowed, current, limit


async def can_create_process(
    session: AsyncSession, tenant: Tenant, server_id: UUID
) -> tuple[bool, int, int | None]:
    """Verifica si el servidor puede tener un proceso más."""
    current = await count_processes_for_server(session, server_id)
    limit = get_limit(MAX_PROCESSES_PER_SERVER, tenant.plan)
    allowed = limit is None or current < limit
    return allowed, current, limit


def get_plan_retention_days(plan: PlanType) -> int:
    """Retorna días de retención de métricas para el plan."""
    return get_retention_days(plan)


def get_plan_allowed_channels(plan: PlanType) -> set[str]:
    """Retorna canales de alerta permitidos para el plan."""
    return get_allowed_channels(plan)
