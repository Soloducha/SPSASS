"""Repositorio para métricas con scoping de tenant."""

from app.models.metric import Metric
from app.repositories.base import TenantScopedRepository


class MetricRepository(TenantScopedRepository):
    """Repositorio concreto para Metric."""

    model = Metric
