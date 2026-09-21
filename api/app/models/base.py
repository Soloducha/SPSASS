"""Modelos base y mixins."""
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base declarativa para todos los modelos."""
    pass


class TimestampMixin:
    """Mixin para timestamps created_at / updated_at."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class UUIDMixin:
    """Mixin para primary key UUID."""

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        nullable=False,
    )


class TenantAwareMixin:
    """Mixin para tenant_id (todas las tablas de negocio llevan tenant_id)."""

    tenant_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )