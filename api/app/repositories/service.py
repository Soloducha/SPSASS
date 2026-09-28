"""Repositorio para servicios con scoping de tenant."""

from app.models.service import Service
from app.repositories.base import TenantScopedRepository


class ServiceRepository(TenantScopedRepository):
    """Repositorio concreto para Service."""

    model = Service
