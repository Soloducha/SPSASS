"""Servicio de auditoría para logging de eventos críticos."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit.models import AuditAction, AuditLog, AuditResourceType
from app.core.logging import get_logger
from app.core.tenant.context import get_tenant_context

logger = get_logger(__name__)


class AuditService:
    """Servicio para registrar eventos de auditoría."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def log(
        self,
        action: AuditAction,
        resource_type: AuditResourceType,
        *,
        user_id: UUID | None = None,
        user_email: str | None = None,
        user_role: str | None = None,
        tenant_id: UUID | None = None,
        resource_id: UUID | None = None,
        old_values: dict[str, Any] | None = None,
        new_values: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
        success: bool = True,
        error_message: str | None = None,
    ) -> AuditLog:
        """
        Registra un evento de auditoría.
        
        Args:
            action: Acción realizada
            resource_type: Tipo de recurso afectado
            user_id: ID del usuario que realizó la acción
            user_email: Email del usuario
            user_role: Rol del usuario
            tenant_id: ID del tenant (se infiere del contexto si no se pasa)
            resource_id: ID del recurso afectado
            old_values: Valores anteriores (para updates)
            new_values: Valores nuevos (para creates/updates)
            metadata: Metadatos adicionales
            ip_address: IP del cliente
            user_agent: User-Agent del cliente
            request_id: ID de request para correlación
            success: Si la acción fue exitosa
            error_message: Mensaje de error si falló
            
        Returns:
            AuditLog creado
        """
        # Inferir tenant_id del contexto si no se pasa
        if tenant_id is None:
            ctx = get_tenant_context()
            if ctx:
                tenant_id = ctx.tenant_id

        audit_log = AuditLog(
            user_id=user_id,
            user_email=user_email,
            user_role=user_role,
            tenant_id=tenant_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            old_values=old_values,
            new_values=new_values,
            metadata=metadata or {},
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
            success=success,
            error_message=error_message,
        )

        self.session.add(audit_log)
        await self.session.flush()

        logger.info(
            "audit_log_created",
            audit_log_id=str(audit_log.id),
            action=action.value,
            resource_type=resource_type.value,
            resource_id=str(resource_id) if resource_id else None,
            user_email=user_email,
            tenant_id=str(tenant_id) if tenant_id else None,
            success=success,
        )

        return audit_log


# ──────────────────────────────────────────────
# Helpers para acciones comunes
# ──────────────────────────────────────────────

async def audit_user_login(
    session: AsyncSession,
    user_id: UUID,
    user_email: str,
    user_role: str,
    tenant_id: UUID,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
    success: bool = True,
    error_message: str | None = None,
) -> AuditLog:
    """Registra login de usuario."""
    service = AuditService(session)
    return await service.log(
        action=AuditAction.USER_LOGIN,
        resource_type=AuditResourceType.USER,
        user_id=user_id,
        user_email=user_email,
        user_role=user_role,
        tenant_id=tenant_id,
        resource_id=user_id,
        ip_address=ip_address,
        user_agent=user_agent,
        request_id=request_id,
        success=success,
        error_message=error_message,
    )


async def audit_user_register(
    session: AsyncSession,
    user_id: UUID,
    user_email: str,
    tenant_id: UUID,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> AuditLog:
    """Registra registro de usuario."""
    service = AuditService(session)
    return await service.log(
        action=AuditAction.USER_REGISTER,
        resource_type=AuditResourceType.USER,
        user_id=user_id,
        user_email=user_email,
        user_role="owner",
        tenant_id=tenant_id,
        resource_id=user_id,
        ip_address=ip_address,
        user_agent=user_agent,
        request_id=request_id,
    )


async def audit_api_key_create(
    session: AsyncSession,
    api_key_id: UUID,
    api_key_name: str,
    user_id: UUID,
    user_email: str,
    tenant_id: UUID,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> AuditLog:
    """Registra creación de API key."""
    service = AuditService(session)
    return await service.log(
        action=AuditAction.API_KEY_CREATE,
        resource_type=AuditResourceType.API_KEY,
        user_id=user_id,
        user_email=user_email,
        tenant_id=tenant_id,
        resource_id=api_key_id,
        new_values={"name": api_key_name},
        ip_address=ip_address,
        user_agent=user_agent,
        request_id=request_id,
    )


async def audit_api_key_revoke(
    session: AsyncSession,
    api_key_id: UUID,
    api_key_name: str,
    user_id: UUID,
    user_email: str,
    tenant_id: UUID,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> AuditLog:
    """Registra revocación de API key."""
    service = AuditService(session)
    return await service.log(
        action=AuditAction.API_KEY_REVOKE,
        resource_type=AuditResourceType.API_KEY,
        user_id=user_id,
        user_email=user_email,
        tenant_id=tenant_id,
        resource_id=api_key_id,
        old_values={"name": api_key_name},
        ip_address=ip_address,
        user_agent=user_agent,
        request_id=request_id,
    )


async def audit_invitation_create(
    session: AsyncSession,
    invitation_id: UUID,
    email: str,
    role: str,
    user_id: UUID,
    user_email: str,
    tenant_id: UUID,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> AuditLog:
    """Registra creación de invitación."""
    service = AuditService(session)
    return await service.log(
        action=AuditAction.INVITATION_CREATE,
        resource_type=AuditResourceType.INVITATION,
        user_id=user_id,
        user_email=user_email,
        tenant_id=tenant_id,
        resource_id=invitation_id,
        new_values={"email": email, "role": role},
        ip_address=ip_address,
        user_agent=user_agent,
        request_id=request_id,
    )


async def audit_member_add(
    session: AsyncSession,
    member_user_id: UUID,
    member_email: str,
    role: str,
    user_id: UUID,
    user_email: str,
    tenant_id: UUID,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> AuditLog:
    """Registra adición de miembro."""
    service = AuditService(session)
    return await service.log(
        action=AuditAction.MEMBER_ADD,
        resource_type=AuditResourceType.TENANT_MEMBER,
        user_id=user_id,
        user_email=user_email,
        tenant_id=tenant_id,
        resource_id=member_user_id,
        new_values={"email": member_email, "role": role},
        ip_address=ip_address,
        user_agent=user_agent,
        request_id=request_id,
    )


async def audit_alert_rule_create(
    session: AsyncSession,
    rule_id: UUID,
    rule_data: dict[str, Any],
    user_id: UUID,
    user_email: str,
    tenant_id: UUID,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> AuditLog:
    """Registra creación de regla de alerta."""
    service = AuditService(session)
    return await service.log(
        action=AuditAction.ALERT_RULE_CREATE,
        resource_type=AuditResourceType.ALERT_RULE,
        user_id=user_id,
        user_email=user_email,
        tenant_id=tenant_id,
        resource_id=rule_id,
        new_values=rule_data,
        ip_address=ip_address,
        user_agent=user_agent,
        request_id=request_id,
    )


async def audit_report_create(
    session: AsyncSession,
    report_id: UUID,
    report_type: str,
    user_id: UUID,
    user_email: str,
    tenant_id: UUID,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> AuditLog:
    """Registra creación de reporte."""
    service = AuditService(session)
    return await service.log(
        action=AuditAction.REPORT_CREATE,
        resource_type=AuditResourceType.REPORT,
        user_id=user_id,
        user_email=user_email,
        tenant_id=tenant_id,
        resource_id=report_id,
        new_values={"type": report_type},
        ip_address=ip_address,
        user_agent=user_agent,
        request_id=request_id,
    )


async def audit_tenant_plan_change(
    session: AsyncSession,
    tenant_id: UUID,
    old_plan: str,
    new_plan: str,
    user_id: UUID,
    user_email: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> AuditLog:
    """Registra cambio de plan de tenant."""
    service = AuditService(session)
    return await service.log(
        action=AuditAction.TENANT_PLAN_CHANGE,
        resource_type=AuditResourceType.TENANT,
        user_id=user_id,
        user_email=user_email,
        tenant_id=tenant_id,
        resource_id=tenant_id,
        old_values={"plan": old_plan},
        new_values={"plan": new_plan},
        ip_address=ip_address,
        user_agent=user_agent,
        request_id=request_id,
    )
