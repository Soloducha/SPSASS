"""Repositorios base con scoping de tenant automático."""
from app.repositories.alert import AlertRepository, AlertRuleRepository
from app.repositories.base import TenantScopedRepository
from app.repositories.job import JobRepository, JobRunRepository
from app.repositories.process import ProcessRepository
from app.repositories.server import ServerRepository
from app.repositories.service import ServiceRepository

__all__ = [
    "TenantScopedRepository",
    "ServerRepository",
    "ProcessRepository",
    "ServiceRepository",
    "JobRepository",
    "JobRunRepository",
    "AlertRuleRepository",
    "AlertRepository",
]
