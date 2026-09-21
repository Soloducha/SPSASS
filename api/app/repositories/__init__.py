"""Repositorios base con scoping de tenant automático."""
from app.repositories.base import TenantScopedRepository

__all__ = ["TenantScopedRepository"]
