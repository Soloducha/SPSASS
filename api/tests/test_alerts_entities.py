"""Tests para alert engine multi-entidad (T5): SERVICE, PROCESS, JOB.

Cubre: disparo por estado derivado, idempotencia, resolución automática,
regla entity_id=None (todos los targets), cross-tenant safety, no-fire
en never-ingested, y no-double-alert para jobs ya alertados por runner.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from app.models.alert import (
    Alert,
    AlertDelivery,
    AlertOperator,
    AlertRule,
    AlertSeverity,
    AlertStatus,
    EntityType,
)
from app.models.job import Job, JobKind, JobRun, JobStatus
from app.models.metric import Metric, MetricType
from app.models.process import Process
from app.models.server import Server, ServerStatus
from app.models.service import Service, ServiceState
from app.models.tenant import Tenant
from app.workers.alerts import evaluate_alerts
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


# ──────────────────────────────────────────────
# Helpers de métricas (compartidos con test_alerts.py)
# ──────────────────────────────────────────────

class _MetricSeed:
    """Parámetros para _add_metrics (evita PLR0913)."""

    def __init__(
        self,
        server: Server,
        tenant: Tenant,
        metric_type: MetricType,
        values: list[float],
        base_ts: datetime | None = None,
    ) -> None:
        self.server = server
        self.tenant = tenant
        self.metric_type = metric_type
        self.values = values
        self.base_ts = base_ts
        self.interval_seconds = 10


async def _add_metrics(session: AsyncSession, seed: _MetricSeed) -> list[datetime]:
    """Inserta métricas con timestamps consecutivos. Devuelve lista de timestamps usados."""
    if seed.base_ts is None:
        seed.base_ts = datetime.now(UTC) - timedelta(seconds=len(seed.values) * seed.interval_seconds)
    timestamps = []
    for i, value in enumerate(seed.values):
        ts = seed.base_ts + timedelta(seconds=i * seed.interval_seconds)
        session.add(
            Metric(
                ts=ts,
                server_id=seed.server.id,
                tenant_id=seed.tenant.id,
                type=seed.metric_type,
                value=value,
            )
        )
        timestamps.append(ts)
    await session.flush()
    return timestamps


# ──────────────────────────────────────────────
# Helpers de seed
# ──────────────────────────────────────────────

async def _seed_tenant_server(session: AsyncSession) -> tuple[Tenant, Server]:
    """Crea tenant + server de prueba."""
    tenant = Tenant(name="alert-tenant", slug=f"alert-{uuid4().hex[:8]}")
    session.add(tenant)
    await session.flush()

    server = Server(
        tenant_id=tenant.id,
        hostname=f"server-{uuid4().hex[:8]}",
        ip="10.0.0.1",
        os="linux",
        status=ServerStatus.ONLINE,
    )
    session.add(server)
    await session.flush()
    return tenant, server


async def _seed_service(  # noqa: PLR0913
    session: AsyncSession,
    tenant: Tenant,
    server: Server,
    *,
    name: str = "test-service",
    desired_state: ServiceState = ServiceState.RUNNING,
    last_status: ServiceState = ServiceState.UNKNOWN,
    last_checked_at: datetime | None = None,
) -> Service:
    """Crea un servicio con estado derivado opcional."""
    svc = Service(
        tenant_id=tenant.id,
        server_id=server.id,
        name=name,
        desired_state=desired_state,
        last_status=last_status,
        last_checked_at=last_checked_at,
    )
    session.add(svc)
    await session.flush()
    return svc


async def _seed_process(  # noqa: PLR0913
    session: AsyncSession,
    tenant: Tenant,
    server: Server,
    *,
    name: str = "test-process",
    pattern: str = "test.*",
    expected_count: int = 1,
    last_count: int = 0,
    last_checked_at: datetime | None = None,
) -> Process:
    """Crea un proceso con estado derivado opcional."""
    proc = Process(
        tenant_id=tenant.id,
        server_id=server.id,
        name=name,
        pattern=pattern,
        expected_count=expected_count,
        last_count=last_count,
        last_checked_at=last_checked_at,
    )
    session.add(proc)
    await session.flush()
    return proc


async def _seed_job(  # noqa: PLR0913
    session: AsyncSession,
    tenant: Tenant,
    server: Server,
    *,
    name: str = "test-job",
    kind: JobKind = JobKind.CRON,
    schedule_cron: str | None = "* * * * *",
    command: str = "echo hello",
    timeout_s: int = 60,
    alert_on_fail: bool = True,
    status: JobStatus = JobStatus.ACTIVE,
) -> Job:
    """Crea un job."""
    job = Job(
        tenant_id=tenant.id,
        server_id=server.id,
        name=name,
        kind=kind,
        schedule_cron=schedule_cron,
        command=command,
        timeout_s=timeout_s,
        alert_on_fail=alert_on_fail,
        status=status,
    )
    session.add(job)
    await session.flush()
    return job


async def _seed_job_run(  # noqa: PLR0913
    session: AsyncSession,
    job: Job,
    *,
    status: str = "failed",
    exit_code: int | None = 1,
    started_at: datetime | None = None,
    run_metadata: dict | None = None,
) -> JobRun:
    """Crea un JobRun."""
    now = datetime.now(UTC)
    run = JobRun(
        job_id=job.id,
        tenant_id=job.tenant_id,
        started_at=started_at or now - timedelta(seconds=10),
        finished_at=now,
        exit_code=exit_code,
        status=status,
        output_tail="output",
        run_metadata=run_metadata or {},
    )
    session.add(run)
    await session.flush()
    return run


async def _create_rule(
    session: AsyncSession,
    tenant: Tenant,
    entity_type: EntityType,
    entity_id: UUID | None = None,
    **kwargs: Any,  # noqa: ANN401
) -> AlertRule:
    """Crea una AlertRule con defaults sensatos por entity_type."""
    defaults = {
        EntityType.SERVER: {
            "metric": "cpu_usage",
            "operator": AlertOperator.GT,
            "threshold": 80.0,
            "duration_s": 60,
        },
        EntityType.SERVICE: {
            "metric": "service_status",
            "operator": AlertOperator.EQ,
            "threshold": 1.0,
            "duration_s": 60,
        },
        EntityType.PROCESS: {
            "metric": "process_count",
            "operator": AlertOperator.LT,
            "threshold": 1.0,
            "duration_s": 60,
        },
        EntityType.JOB: {
            "metric": "job_status",
            "operator": AlertOperator.EQ,
            "threshold": 1.0,
            "duration_s": 60,
        },
    }
    rule_data = {
        "tenant_id": tenant.id,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "severity": AlertSeverity.WARNING,
        "channels": {"email": {"to": ["ops@example.com"]}},
        "is_active": True,
        **defaults.get(entity_type, {}),
        **kwargs,
    }
    rule = AlertRule(**rule_data)
    session.add(rule)
    await session.flush()
    return rule


# ──────────────────────────────────────────────
# Tests SERVICE
# ──────────────────────────────────────────────

class TestServiceAlerts:
    """Tests para reglas SERVICE."""

    @pytest.mark.asyncio
    async def test_fires_when_last_status_differs_from_desired(
        self, db_session: AsyncSession
    ) -> None:
        """Servicio con last_status != desired_state → dispara alerta."""
        tenant, server = await _seed_tenant_server(db_session)

        # Servicio: desired=RUNNING, last_status=STOPPED (violación)
        svc = await _seed_service(
            db_session, tenant, server,
            desired_state=ServiceState.RUNNING,
            last_status=ServiceState.STOPPED,
            last_checked_at=datetime.now(UTC),
        )

        rule = await _create_rule(db_session, tenant, EntityType.SERVICE, entity_id=svc.id)

        created = await evaluate_alerts(db_session)

        assert created == 1
        alert = await db_session.scalar(select(Alert).where(Alert.rule_id == rule.id))
        assert alert is not None
        assert alert.status == AlertStatus.OPEN
        assert alert.target_entity_id == svc.id
        assert "stopped" in alert.message.lower()
        assert "running" in alert.message.lower()

    @pytest.mark.asyncio
    async def test_does_not_fire_when_last_status_unknown(
        self, db_session: AsyncSession
    ) -> None:
        """Servicio nunca ingerido (last_status=UNKNOWN) → NO dispara."""
        tenant, server = await _seed_tenant_server(db_session)

        svc = await _seed_service(
            db_session, tenant, server,
            desired_state=ServiceState.RUNNING,
            last_status=ServiceState.UNKNOWN,
            last_checked_at=None,
        )

        rule = await _create_rule(db_session, tenant, EntityType.SERVICE, entity_id=svc.id)

        created = await evaluate_alerts(db_session)

        assert created == 0
        alert = await db_session.scalar(select(Alert).where(Alert.rule_id == rule.id))
        assert alert is None

    @pytest.mark.asyncio
    async def test_resolves_when_status_returns_to_desired(
        self, db_session: AsyncSession
    ) -> None:
        """Al volver last_status == desired_state, alerta se resuelve."""
        tenant, server = await _seed_tenant_server(db_session)

        # Fase 1: violación
        svc = await _seed_service(
            db_session, tenant, server,
            desired_state=ServiceState.RUNNING,
            last_status=ServiceState.STOPPED,
            last_checked_at=datetime.now(UTC),
        )

        rule = await _create_rule(db_session, tenant, EntityType.SERVICE, entity_id=svc.id)

        created1 = await evaluate_alerts(db_session)
        assert created1 == 1

        alert = await db_session.scalar(select(Alert).where(Alert.rule_id == rule.id))
        assert alert is not None
        assert alert.status == AlertStatus.OPEN

        # Fase 2: estado vuelve a desired
        await db_session.refresh(svc)
        svc.last_status = ServiceState.RUNNING
        svc.last_checked_at = datetime.now(UTC)
        await db_session.flush()

        created2 = await evaluate_alerts(db_session)
        assert created2 == 0

        await db_session.refresh(alert)
        assert alert.status == AlertStatus.RESOLVED
        assert alert.resolved_at is not None

    @pytest.mark.asyncio
    async def test_idempotent_no_duplicate_on_reeval(
        self, db_session: AsyncSession
    ) -> None:
        """Segunda evaluación con misma violación → NO crea duplicado."""
        tenant, server = await _seed_tenant_server(db_session)

        svc = await _seed_service(
            db_session, tenant, server,
            desired_state=ServiceState.RUNNING,
            last_status=ServiceState.FAILED,
            last_checked_at=datetime.now(UTC),
        )

        rule = await _create_rule(db_session, tenant, EntityType.SERVICE, entity_id=svc.id)

        created1 = await evaluate_alerts(db_session)
        assert created1 == 1

        alert = await db_session.scalar(select(Alert).where(Alert.rule_id == rule.id))
        alert_id_1 = alert.id

        created2 = await evaluate_alerts(db_session)
        assert created2 == 0

        alert2 = await db_session.scalar(select(Alert).where(Alert.rule_id == rule.id))
        assert alert2.id == alert_id_1

    @pytest.mark.asyncio
    async def test_entity_id_none_targets_all_services_of_tenant(
        self, db_session: AsyncSession
    ) -> None:
        """Regla sin entity_id → alerta por CADA servicio violador del tenant."""
        tenant, server = await _seed_tenant_server(db_session)

        # Dos servicios: uno violando, otro sano
        svc1 = await _seed_service(
            db_session, tenant, server, name="svc-1",
            desired_state=ServiceState.RUNNING,
            last_status=ServiceState.STOPPED,
            last_checked_at=datetime.now(UTC),
        )
        _ = await _seed_service(
            db_session, tenant, server, name="svc-2",
            desired_state=ServiceState.RUNNING,
            last_status=ServiceState.RUNNING,
            last_checked_at=datetime.now(UTC),
        )

        # Regla sin entity_id → todos los servicios del tenant
        rule = await _create_rule(db_session, tenant, EntityType.SERVICE, entity_id=None)

        created = await evaluate_alerts(db_session)

        assert created == 1  # solo svc1 viola
        alerts = (await db_session.scalars(
            select(Alert).where(Alert.rule_id == rule.id)
        )).all()
        assert len(alerts) == 1
        assert alerts[0].target_entity_id == svc1.id

    @pytest.mark.asyncio
    async def test_cross_tenant_service_skipped(
        self, db_session: AsyncSession
    ) -> None:
        """Regla tenant A con entity_id de servicio tenant B → skip (no crash)."""
        tenant_a, server_a = await _seed_tenant_server(db_session)

        tenant_b = Tenant(name="tenant-b", slug=f"tenant-b-{uuid4().hex[:8]}")
        db_session.add(tenant_b)
        await db_session.flush()

        server_b = Server(
            tenant_id=tenant_b.id,
            hostname=f"server-b-{uuid4().hex[:8]}",
            ip="10.0.0.2",
            os="linux",
            status=ServerStatus.ONLINE,
        )
        db_session.add(server_b)
        await db_session.flush()

        svc_b = await _seed_service(
            db_session, tenant_b, server_b, name="svc-b",
            desired_state=ServiceState.RUNNING,
            last_status=ServiceState.STOPPED,
            last_checked_at=datetime.now(UTC),
        )

        # Regla de tenant A apuntando a servicio de tenant B
        rule = await _create_rule(db_session, tenant_a, EntityType.SERVICE, entity_id=svc_b.id)

        created = await evaluate_alerts(db_session)

        assert created == 0
        alert = await db_session.scalar(select(Alert).where(Alert.rule_id == rule.id))
        assert alert is None


# ──────────────────────────────────────────────
# Tests PROCESS
# ──────────────────────────────────────────────

class TestProcessAlerts:
    """Tests para reglas PROCESS."""

    @pytest.mark.asyncio
    async def test_fires_when_last_count_below_expected(
        self, db_session: AsyncSession
    ) -> None:
        """Proceso con last_count < expected_count → dispara alerta."""
        tenant, server = await _seed_tenant_server(db_session)

        proc = await _seed_process(
            db_session, tenant, server,
            name="worker",
            pattern="worker.*",
            expected_count=3,
            last_count=1,
            last_checked_at=datetime.now(UTC),
        )

        rule = await _create_rule(db_session, tenant, EntityType.PROCESS, entity_id=proc.id)

        created = await evaluate_alerts(db_session)

        assert created == 1
        alert = await db_session.scalar(select(Alert).where(Alert.rule_id == rule.id))
        assert alert is not None
        assert alert.status == AlertStatus.OPEN
        assert alert.target_entity_id == proc.id
        assert "1" in alert.message
        assert "3" in alert.message

    @pytest.mark.asyncio
    async def test_does_not_fire_when_never_ingested(
        self, db_session: AsyncSession
    ) -> None:
        """Proceso nunca ingerido (last_checked_at=None) → NO dispara."""
        tenant, server = await _seed_tenant_server(db_session)

        proc = await _seed_process(
            db_session, tenant, server,
            expected_count=2,
            last_count=0,
            last_checked_at=None,
        )

        rule = await _create_rule(db_session, tenant, EntityType.PROCESS, entity_id=proc.id)

        created = await evaluate_alerts(db_session)

        assert created == 0
        alert = await db_session.scalar(select(Alert).where(Alert.rule_id == rule.id))
        assert alert is None

    @pytest.mark.asyncio
    async def test_resolves_when_count_meets_expected(
        self, db_session: AsyncSession
    ) -> None:
        """Al subir last_count >= expected_count, alerta se resuelve."""
        tenant, server = await _seed_tenant_server(db_session)

        proc = await _seed_process(
            db_session, tenant, server,
            expected_count=2,
            last_count=1,
            last_checked_at=datetime.now(UTC),
        )

        rule = await _create_rule(db_session, tenant, EntityType.PROCESS, entity_id=proc.id)

        created1 = await evaluate_alerts(db_session)
        assert created1 == 1

        alert = await db_session.scalar(select(Alert).where(Alert.rule_id == rule.id))
        assert alert.status == AlertStatus.OPEN

        # Recuperar count
        await db_session.refresh(proc)
        proc.last_count = 2
        proc.last_checked_at = datetime.now(UTC)
        await db_session.flush()

        created2 = await evaluate_alerts(db_session)
        assert created2 == 0

        await db_session.refresh(alert)
        assert alert.status == AlertStatus.RESOLVED

    @pytest.mark.asyncio
    async def test_idempotent_no_duplicate_on_reeval(
        self, db_session: AsyncSession
    ) -> None:
        """Segunda evaluación con misma violación → NO crea duplicado."""
        tenant, server = await _seed_tenant_server(db_session)

        proc = await _seed_process(
            db_session, tenant, server,
            expected_count=2,
            last_count=0,
            last_checked_at=datetime.now(UTC),
        )

        rule = await _create_rule(db_session, tenant, EntityType.PROCESS, entity_id=proc.id)

        created1 = await evaluate_alerts(db_session)
        assert created1 == 1

        alert = await db_session.scalar(select(Alert).where(Alert.rule_id == rule.id))
        alert_id_1 = alert.id

        created2 = await evaluate_alerts(db_session)
        assert created2 == 0

        alert2 = await db_session.scalar(select(Alert).where(Alert.rule_id == rule.id))
        assert alert2.id == alert_id_1

    @pytest.mark.asyncio
    async def test_entity_id_none_targets_all_processes_of_tenant(
        self, db_session: AsyncSession
    ) -> None:
        """Regla sin entity_id → alerta por CADA proceso violador del tenant."""
        tenant, server = await _seed_tenant_server(db_session)

        proc1 = await _seed_process(
            db_session, tenant, server, name="proc-1",
            expected_count=2, last_count=1, last_checked_at=datetime.now(UTC),
        )
        _ = await _seed_process(
            db_session, tenant, server, name="proc-2",
            expected_count=1, last_count=1, last_checked_at=datetime.now(UTC),
        )

        rule = await _create_rule(db_session, tenant, EntityType.PROCESS, entity_id=None)

        created = await evaluate_alerts(db_session)

        assert created == 1  # solo proc1 viola
        alerts = (await db_session.scalars(
            select(Alert).where(Alert.rule_id == rule.id)
        )).all()
        assert len(alerts) == 1
        assert alerts[0].target_entity_id == proc1.id

    @pytest.mark.asyncio
    async def test_cross_tenant_process_skipped(
        self, db_session: AsyncSession
    ) -> None:
        """Regla tenant A con entity_id de proceso tenant B → skip."""
        tenant_a, server_a = await _seed_tenant_server(db_session)

        tenant_b = Tenant(name="tenant-b", slug=f"tenant-b-{uuid4().hex[:8]}")
        db_session.add(tenant_b)
        await db_session.flush()

        server_b = Server(
            tenant_id=tenant_b.id,
            hostname=f"server-b-{uuid4().hex[:8]}",
            ip="10.0.0.2",
            os="linux",
            status=ServerStatus.ONLINE,
        )
        db_session.add(server_b)
        await db_session.flush()

        proc_b = await _seed_process(
            db_session, tenant_b, server_b,
            expected_count=2, last_count=1, last_checked_at=datetime.now(UTC),
        )

        rule = await _create_rule(db_session, tenant_a, EntityType.PROCESS, entity_id=proc_b.id)

        created = await evaluate_alerts(db_session)

        assert created == 0
        alert = await db_session.scalar(select(Alert).where(Alert.rule_id == rule.id))
        assert alert is None


# ──────────────────────────────────────────────
# Tests JOB
# ──────────────────────────────────────────────

class TestJobAlerts:
    """Tests para reglas JOB."""

    @pytest.mark.asyncio
    async def test_fires_on_recent_failed_run(
        self, db_session: AsyncSession
    ) -> None:
        """JobRun failed reciente (dentro de duration_s) → dispara alerta."""
        tenant, server = await _seed_tenant_server(db_session)

        job = await _seed_job(db_session, tenant, server, name="backup-job")
        await _seed_job_run(
            db_session, job,
            status="failed",
            exit_code=1,
            started_at=datetime.now(UTC) - timedelta(seconds=30),
        )

        # duration_s=120 para que el run de 30s atrás esté en la ventana
        rule = await _create_rule(db_session, tenant, EntityType.JOB, entity_id=job.id, duration_s=120)

        created = await evaluate_alerts(db_session)

        assert created == 1
        alert = await db_session.scalar(select(Alert).where(Alert.rule_id == rule.id))
        assert alert is not None
        assert alert.status == AlertStatus.OPEN
        assert alert.target_entity_id == job.id
        assert "failed" in alert.message.lower()
        assert "exit=1" in alert.message

    @pytest.mark.asyncio
    async def test_fires_on_recent_timeout_run(
        self, db_session: AsyncSession
    ) -> None:
        """JobRun timeout reciente → dispara alerta."""
        tenant, server = await _seed_tenant_server(db_session)

        job = await _seed_job(db_session, tenant, server, name="long-job", timeout_s=30)
        await _seed_job_run(
            db_session, job,
            status="timeout",
            exit_code=None,
            started_at=datetime.now(UTC) - timedelta(seconds=20),
        )

        rule = await _create_rule(db_session, tenant, EntityType.JOB, entity_id=job.id, duration_s=120)

        created = await evaluate_alerts(db_session)

        assert created == 1
        alert = await db_session.scalar(select(Alert).where(Alert.rule_id == rule.id))
        assert alert is not None
        assert "timed out" in alert.message.lower()
        assert "30s" in alert.message

    @pytest.mark.asyncio
    async def test_does_not_fire_if_run_already_alerted_by_runner(
        self, db_session: AsyncSession
    ) -> None:
        """JobRun con run_metadata['alerted']=True → NO dispara (idempotencia runner)."""
        tenant, server = await _seed_tenant_server(db_session)

        job = await _seed_job(db_session, tenant, server, name="job-runner-alerted")
        await _seed_job_run(
            db_session, job,
            status="failed",
            exit_code=1,
            started_at=datetime.now(UTC) - timedelta(seconds=30),
            run_metadata={"alerted": True},  # runner ya alertó
        )

        rule = await _create_rule(db_session, tenant, EntityType.JOB, entity_id=job.id, duration_s=120)

        created = await evaluate_alerts(db_session)

        assert created == 0
        alert = await db_session.scalar(select(Alert).where(Alert.rule_id == rule.id))
        assert alert is None

    @pytest.mark.asyncio
    async def test_resolves_when_latest_run_is_success(
        self, db_session: AsyncSession
    ) -> None:
        """Al tener JobRun success reciente, alerta se resuelve."""
        tenant, server = await _seed_tenant_server(db_session)

        job = await _seed_job(db_session, tenant, server, name="flaky-job")
        # Run fallido inicial
        await _seed_job_run(
            db_session, job,
            status="failed",
            exit_code=1,
            started_at=datetime.now(UTC) - timedelta(seconds=60),
        )

        rule = await _create_rule(db_session, tenant, EntityType.JOB, entity_id=job.id, duration_s=120)

        created1 = await evaluate_alerts(db_session)
        assert created1 == 1

        alert = await db_session.scalar(select(Alert).where(Alert.rule_id == rule.id))
        assert alert.status == AlertStatus.OPEN

        # Nuevo run exitoso
        await _seed_job_run(
            db_session, job,
            status="success",
            exit_code=0,
            started_at=datetime.now(UTC) - timedelta(seconds=10),
        )

        created2 = await evaluate_alerts(db_session)
        assert created2 == 0

        await db_session.refresh(alert)
        assert alert.status == AlertStatus.RESOLVED

    @pytest.mark.asyncio
    async def test_resolves_when_latest_run_is_runner_alerted_failure(
        self, db_session: AsyncSession
    ) -> None:
        """Si el run más reciente es fallo YA alertado por runner → resuelve."""
        tenant, server = await _seed_tenant_server(db_session)

        job = await _seed_job(db_session, tenant, server, name="job-runner-alerted")
        # Run fallido que el runner YA alertó
        await _seed_job_run(
            db_session, job,
            status="failed",
            exit_code=1,
            started_at=datetime.now(UTC) - timedelta(seconds=30),
            run_metadata={"alerted": True},
        )

        rule = await _create_rule(db_session, tenant, EntityType.JOB, entity_id=job.id, duration_s=120)

        created1 = await evaluate_alerts(db_session)
        assert created1 == 0  # runner ya alertó, no crea

        # Crear alerta manualmente para probar resolución
        alert = Alert(
            rule_id=rule.id,
            server_id=server.id,
            target_entity_id=job.id,
            tenant_id=tenant.id,
            severity=AlertSeverity.WARNING,
            status=AlertStatus.OPEN,
            message="Manual alert for test",
            triggered_at=datetime.now(UTC),
            value_at_trigger=1.0,
        )
        db_session.add(alert)
        await db_session.flush()

        # Re-evaluar: el run más reciente es fallo alertado por runner → debe resolver
        created2 = await evaluate_alerts(db_session)
        assert created2 == 0

        await db_session.refresh(alert)
        assert alert.status == AlertStatus.RESOLVED

    @pytest.mark.asyncio
    async def test_does_not_fire_if_failed_run_outside_window(
        self, db_session: AsyncSession
    ) -> None:
        """JobRun failed fuera de duration_s → NO dispara."""
        tenant, server = await _seed_tenant_server(db_session)

        job = await _seed_job(db_session, tenant, server, name="old-fail-job")
        # Run fallido hace 200s, ventana duration_s=120
        await _seed_job_run(
            db_session, job,
            status="failed",
            exit_code=1,
            started_at=datetime.now(UTC) - timedelta(seconds=200),
        )

        rule = await _create_rule(db_session, tenant, EntityType.JOB, entity_id=job.id, duration_s=120)

        created = await evaluate_alerts(db_session)

        assert created == 0
        alert = await db_session.scalar(select(Alert).where(Alert.rule_id == rule.id))
        assert alert is None

    @pytest.mark.asyncio
    async def test_idempotent_no_duplicate_on_reeval(
        self, db_session: AsyncSession
    ) -> None:
        """Segunda evaluación con mismo run fallido → NO crea duplicado."""
        tenant, server = await _seed_tenant_server(db_session)

        job = await _seed_job(db_session, tenant, server, name="persistent-fail")
        await _seed_job_run(
            db_session, job,
            status="failed",
            exit_code=1,
            started_at=datetime.now(UTC) - timedelta(seconds=30),
        )

        rule = await _create_rule(db_session, tenant, EntityType.JOB, entity_id=job.id, duration_s=120)

        created1 = await evaluate_alerts(db_session)
        assert created1 == 1

        alert = await db_session.scalar(select(Alert).where(Alert.rule_id == rule.id))
        alert_id_1 = alert.id

        created2 = await evaluate_alerts(db_session)
        assert created2 == 0

        alert2 = await db_session.scalar(select(Alert).where(Alert.rule_id == rule.id))
        assert alert2.id == alert_id_1

    @pytest.mark.asyncio
    async def test_entity_id_none_targets_all_jobs_of_tenant(
        self, db_session: AsyncSession
    ) -> None:
        """Regla sin entity_id → alerta por CADA job con run fallido en ventana."""
        tenant, server = await _seed_tenant_server(db_session)

        job1 = await _seed_job(db_session, tenant, server, name="job-fail")
        await _seed_job_run(
            db_session, job1,
            status="failed", exit_code=1,
            started_at=datetime.now(UTC) - timedelta(seconds=30),
        )

        job2 = await _seed_job(db_session, tenant, server, name="job-success")
        await _seed_job_run(
            db_session, job2,
            status="success", exit_code=0,
            started_at=datetime.now(UTC) - timedelta(seconds=30),
        )

        rule = await _create_rule(db_session, tenant, EntityType.JOB, entity_id=None, duration_s=120)

        created = await evaluate_alerts(db_session)

        assert created == 1  # solo job1 falla
        alerts = (await db_session.scalars(
            select(Alert).where(Alert.rule_id == rule.id)
        )).all()
        assert len(alerts) == 1
        assert alerts[0].target_entity_id == job1.id

    @pytest.mark.asyncio
    async def test_cross_tenant_job_skipped(
        self, db_session: AsyncSession
    ) -> None:
        """Regla tenant A con entity_id de job tenant B → skip."""
        tenant_a, server_a = await _seed_tenant_server(db_session)

        tenant_b = Tenant(name="tenant-b", slug=f"tenant-b-{uuid4().hex[:8]}")
        db_session.add(tenant_b)
        await db_session.flush()

        server_b = Server(
            tenant_id=tenant_b.id,
            hostname=f"server-b-{uuid4().hex[:8]}",
            ip="10.0.0.2",
            os="linux",
            status=ServerStatus.ONLINE,
        )
        db_session.add(server_b)
        await db_session.flush()

        job_b = await _seed_job(db_session, tenant_b, server_b, name="job-b")
        await _seed_job_run(
            db_session, job_b,
            status="failed", exit_code=1,
            started_at=datetime.now(UTC) - timedelta(seconds=30),
        )

        rule = await _create_rule(db_session, tenant_a, EntityType.JOB, entity_id=job_b.id, duration_s=120)

        created = await evaluate_alerts(db_session)

        assert created == 0
        alert = await db_session.scalar(select(Alert).where(Alert.rule_id == rule.id))
        assert alert is None

    @pytest.mark.asyncio
    async def test_job_without_runs_in_window_resolves_existing_alert(
        self, db_session: AsyncSession
    ) -> None:
        """Sin runs en la ventana → resuelve alerta existente."""
        tenant, server = await _seed_tenant_server(db_session)

        job = await _seed_job(db_session, tenant, server, name="no-recent-runs")
        # Run fallido FUERA de la ventana (más antiguo que duration_s)
        await _seed_job_run(
            db_session, job,
            status="failed", exit_code=1,
            started_at=datetime.now(UTC) - timedelta(seconds=200),
        )

        rule = await _create_rule(db_session, tenant, EntityType.JOB, entity_id=job.id, duration_s=120)

        # Crear alerta manualmente
        alert = Alert(
            rule_id=rule.id,
            server_id=server.id,
            target_entity_id=job.id,
            tenant_id=tenant.id,
            severity=AlertSeverity.WARNING,
            status=AlertStatus.OPEN,
            message="Old alert",
            triggered_at=datetime.now(UTC) - timedelta(seconds=300),
            value_at_trigger=1.0,
        )
        db_session.add(alert)
        await db_session.flush()

        # Evaluar: no hay runs en ventana → debe resolver
        created = await evaluate_alerts(db_session)
        assert created == 0

        await db_session.refresh(alert)
        assert alert.status == AlertStatus.RESOLVED


# ──────────────────────────────────────────────
# Regresión SERVER (sanity check rápido)
# ──────────────────────────────────────────────

class TestServerRegression:
    """Sanity check: SERVER path intacto."""

    @pytest.mark.asyncio
    async def test_server_sustained_breach_still_works(
        self, db_session: AsyncSession
    ) -> None:
        """Regla SERVER con métricas sostenidas → dispara como antes."""
        tenant, server = await _seed_tenant_server(db_session)

        now = datetime.now(UTC)
        window_start = now - timedelta(seconds=60)
        for i, val in enumerate([85.0, 87.0, 82.0, 88.0, 90.0]):
            ts = window_start + timedelta(seconds=i * 10)
            db_session.add(Metric(
                ts=ts, server_id=server.id, tenant_id=tenant.id,
                type=MetricType.CPU_USAGE, value=val,
            ))
        await db_session.flush()

        rule = await _create_rule(db_session, tenant, EntityType.SERVER, entity_id=server.id)

        created = await evaluate_alerts(db_session)

        assert created == 1
        alert = await db_session.scalar(select(Alert).where(Alert.rule_id == rule.id))
        assert alert is not None
        assert alert.status == AlertStatus.OPEN
        assert alert.server_id == server.id
        assert alert.target_entity_id == server.id  # SERVER usa target_entity_id = server_id


# ──────────────────────────────────────────────
# Silencing / Episode dedup tests — all entity types (T4)
# ──────────────────────────────────────────────

class TestSilencingAllEntities:
    """Tests de silenciamiento para las 4 entidades: SERVER, SERVICE, PROCESS, JOB.

    Verifica que resolver una alerta mientras la violación sigue activa
    no produce re-notificación en el siguiente ciclo del worker.
    """

    @pytest.mark.asyncio
    async def test_server_silence_while_violating_no_renotify(
        self, db_session: AsyncSession
    ) -> None:
        """SERVER: resolve while violating → no new alert/delivery on re-eval."""
        tenant, server = await _seed_tenant_server(db_session)

        now = datetime.now(UTC)
        window_start = now - timedelta(seconds=60)
        await _add_metrics(
            db_session,
            _MetricSeed(server, tenant, MetricType.CPU_USAGE, [85.0, 87.0, 82.0, 88.0, 90.0], base_ts=window_start),
        )

        rule = await _create_rule(db_session, tenant, EntityType.SERVER, entity_id=server.id)

        created1 = await evaluate_alerts(db_session)
        assert created1 == 1

        alert = await db_session.scalar(select(Alert).where(Alert.rule_id == rule.id))
        assert alert is not None
        original_alert_id = alert.id
        assert alert.status == AlertStatus.OPEN

        # Humano resuelve (simula repo.resolve: status=RESOLVED + silenced_at)
        alert.status = AlertStatus.RESOLVED
        alert.resolved_at = datetime.now(UTC)
        alert.silenced_at = datetime.now(UTC)
        await db_session.flush()

        # Violación sigue activa, worker re-evalúa
        created2 = await evaluate_alerts(db_session)
        assert created2 == 0

        alert2 = await db_session.scalar(select(Alert).where(Alert.rule_id == rule.id))
        assert alert2.id == original_alert_id
        assert alert2.status == AlertStatus.RESOLVED
        assert alert2.silenced_at is not None

        # Sin nuevos deliveries
        deliveries = (await db_session.scalars(
            select(AlertDelivery).where(AlertDelivery.alert_id == original_alert_id)
        )).all()
        assert len(deliveries) == 1

    @pytest.mark.asyncio
    async def test_service_silence_while_violating_no_renotify(
        self, db_session: AsyncSession
    ) -> None:
        """SERVICE: resolve while violating → no new alert/delivery on re-eval."""
        tenant, server = await _seed_tenant_server(db_session)

        svc = await _seed_service(
            db_session, tenant, server,
            desired_state=ServiceState.RUNNING,
            last_status=ServiceState.STOPPED,
            last_checked_at=datetime.now(UTC),
        )

        rule = await _create_rule(db_session, tenant, EntityType.SERVICE, entity_id=svc.id)

        created1 = await evaluate_alerts(db_session)
        assert created1 == 1

        alert = await db_session.scalar(select(Alert).where(Alert.rule_id == rule.id))
        original_alert_id = alert.id

        # Humano resuelve mientras servicio sigue STOPPED
        alert.status = AlertStatus.RESOLVED
        alert.resolved_at = datetime.now(UTC)
        alert.silenced_at = datetime.now(UTC)
        await db_session.flush()

        # Re-evaluar: servicio sigue en violación
        created2 = await evaluate_alerts(db_session)
        assert created2 == 0

        alert2 = await db_session.scalar(select(Alert).where(Alert.rule_id == rule.id))
        assert alert2.id == original_alert_id
        assert alert2.status == AlertStatus.RESOLVED
        assert alert2.silenced_at is not None

        deliveries = (await db_session.scalars(
            select(AlertDelivery).where(AlertDelivery.alert_id == original_alert_id)
        )).all()
        assert len(deliveries) == 1

    @pytest.mark.asyncio
    async def test_process_silence_while_violating_no_renotify(
        self, db_session: AsyncSession
    ) -> None:
        """PROCESS: resolve while violating → no new alert/delivery on re-eval."""
        tenant, server = await _seed_tenant_server(db_session)

        proc = await _seed_process(
            db_session, tenant, server,
            expected_count=2, last_count=1, last_checked_at=datetime.now(UTC),
        )

        rule = await _create_rule(db_session, tenant, EntityType.PROCESS, entity_id=proc.id)

        created1 = await evaluate_alerts(db_session)
        assert created1 == 1

        alert = await db_session.scalar(select(Alert).where(Alert.rule_id == rule.id))
        original_alert_id = alert.id

        alert.status = AlertStatus.RESOLVED
        alert.resolved_at = datetime.now(UTC)
        alert.silenced_at = datetime.now(UTC)
        await db_session.flush()

        created2 = await evaluate_alerts(db_session)
        assert created2 == 0

        alert2 = await db_session.scalar(select(Alert).where(Alert.rule_id == rule.id))
        assert alert2.id == original_alert_id
        assert alert2.silenced_at is not None

        deliveries = (await db_session.scalars(
            select(AlertDelivery).where(AlertDelivery.alert_id == original_alert_id)
        )).all()
        assert len(deliveries) == 1

    @pytest.mark.asyncio
    async def test_job_silence_while_violating_no_renotify(
        self, db_session: AsyncSession
    ) -> None:
        """JOB: resolve while violating → no new alert/delivery on re-eval."""
        tenant, server = await _seed_tenant_server(db_session)

        job = await _seed_job(db_session, tenant, server, name="backup-job")
        await _seed_job_run(
            db_session, job,
            status="failed", exit_code=1,
            started_at=datetime.now(UTC) - timedelta(seconds=30),
        )

        rule = await _create_rule(db_session, tenant, EntityType.JOB, entity_id=job.id, duration_s=120)

        created1 = await evaluate_alerts(db_session)
        assert created1 == 1

        alert = await db_session.scalar(select(Alert).where(Alert.rule_id == rule.id))
        original_alert_id = alert.id

        alert.status = AlertStatus.RESOLVED
        alert.resolved_at = datetime.now(UTC)
        alert.silenced_at = datetime.now(UTC)
        await db_session.flush()

        # Job sigue fallando en la ventana
        created2 = await evaluate_alerts(db_session)
        assert created2 == 0

        alert2 = await db_session.scalar(select(Alert).where(Alert.rule_id == rule.id))
        assert alert2.id == original_alert_id
        assert alert2.silenced_at is not None

        deliveries = (await db_session.scalars(
            select(AlertDelivery).where(AlertDelivery.alert_id == original_alert_id)
        )).all()
        assert len(deliveries) == 1
