"""Repositorio para servidores con scoping de tenant."""

from app.models.server import Server
from app.repositories.base import TenantScopedRepository


class ServerRepository(TenantScopedRepository):
    """Repositorio concreto para Server."""

    model = Server
