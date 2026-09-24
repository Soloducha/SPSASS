"""Repositorios base con scoping de tenant automático."""
from app.repositories.alert import AlertRepository, AlertRuleRepository
from app.repositories.base import TenantScopedRepository

__all__ = ["TenantScopedRepository", "AlertRuleRepository", "AlertRepository"]
