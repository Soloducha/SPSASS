"""Modelo AuditLog para trazabilidad de cambios críticos."""

from __future__ import annotations

import enum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import JSON, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    pass


class AuditAction(enum.StrEnum):
    """Tipos de acciones auditadas."""
    # Auth
    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"
    USER_REGISTER = "user_register"
    PASSWORD_CHANGE = "password_change"
    PASSWORD_RESET_REQUEST = "password_reset_request"
    PASSWORD_RESET = "password_reset"

    # API Keys
    API_KEY_CREATE = "api_key_create"
    API_KEY_REVOKE = "api_key_revoke"
    API_KEY_LIST = "api_key_list"

    # Tenant
    TENANT_CREATE = "tenant_create"
    TENANT_UPDATE = "tenant_update"
    TENANT_PLAN_CHANGE = "tenant_plan_change"
    TENANT_DELETE = "tenant_delete"

    # Invitations
    INVITATION_CREATE = "invitation_create"
    INVITATION_ACCEPT = "invitation_accept"
    INVITATION_REVOKE = "invitation_revoke"

    # Members
    MEMBER_ADD = "member_add"
    MEMBER_REMOVE = "member_remove"
    MEMBER_ROLE_CHANGE = "member_role_change"

    # Servers
    SERVER_REGISTER = "server_register"
    SERVER_UPDATE = "server_update"
    SERVER_DELETE = "server_delete"

    # Alert Rules
    ALERT_RULE_CREATE = "alert_rule_create"
    ALERT_RULE_UPDATE = "alert_rule_update"
    ALERT_RULE_DELETE = "alert_rule_delete"

    # Reports
    REPORT_CREATE = "report_create"
    REPORT_GENERATE = "report_generate"
    REPORT_DELETE = "report_delete"

    # Services/Jobs/Processes
    SERVICE_CREATE = "service_create"
    SERVICE_UPDATE = "service_update"
    SERVICE_DELETE = "service_delete"
    JOB_CREATE = "job_create"
    JOB_UPDATE = "job_update"
    JOB_DELETE = "job_delete"
    PROCESS_CREATE = "process_create"
    PROCESS_UPDATE = "process_update"
    PROCESS_DELETE = "process_delete"

    # Settings
    SETTINGS_UPDATE = "settings_update"


class AuditResourceType(enum.StrEnum):
    """Tipos de recursos auditados."""
    USER = "user"
    API_KEY = "api_key"
    TENANT = "tenant"
    INVITATION = "invitation"
    TENANT_MEMBER = "tenant_member"
    SERVER = "server"
    ALERT_RULE = "alert_rule"
    REPORT = "report"
    SERVICE = "service"
    JOB = "job"
    PROCESS = "process"
    SETTINGS = "settings"


class AuditLog(Base, UUIDMixin, TimestampMixin):
    """Log de auditoría para cambios críticos."""

    __tablename__ = "audit_logs"

    # Quién realizó la acción
    user_id: Mapped[UUID | None] = mapped_column(nullable=True, index=True)
    user_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    user_role: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Contexto de tenant
    tenant_id: Mapped[UUID | None] = mapped_column(nullable=True, index=True)

    # Qué acción
    action: Mapped[AuditAction] = mapped_column(
        SAEnum(AuditAction, name="audit_action", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        index=True,
    )
    resource_type: Mapped[AuditResourceType] = mapped_column(
        SAEnum(AuditResourceType, name="audit_resource_type", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        index=True,
    )
    resource_id: Mapped[UUID | None] = mapped_column(nullable=True, index=True)

    # Detalles
    old_values: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_values: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    extra_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # Request context
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)  # IPv4 o IPv6
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    # Resultado
    success: Mapped[bool] = mapped_column(default=True, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<AuditLog(action={self.action.value}, resource={self.resource_type.value}, user={self.user_email})>"
