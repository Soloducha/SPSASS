"""Repositorio para procesos con scoping de tenant."""

from app.models.process import Process
from app.repositories.base import TenantScopedRepository


class ProcessRepository(TenantScopedRepository):
    """Repositorio concreto para Process."""

    model = Process
