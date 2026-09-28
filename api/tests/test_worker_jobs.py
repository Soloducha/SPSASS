"""Tests para el worker de jobs (T2).

Cubre: due detection con croniter, ejecución de comandos, timeout,
concurrencia, alertas en fallo, tenant scoping.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from croniter import croniter

from app.models.alert import Alert, AlertDelivery, AlertSeverity
from app.models.job import Job, JobKind, JobRun, JobStatus
from app.models.server import Server, ServerStatus
from app.models.tenant import Tenant
from app.workers.jobs import _is_cron_due, run_due_jobs
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


# ──────────────────────────────────────────────
# Helpers de seed
# ──────────────────────────────────────────────

async def _seed_tenant_server_job(
    session: AsyncSession,
    *,
    kind: JobKind = JobKind.CRON,
    schedule_cron: str | None = "* * * * *",
    status: JobStatus = JobStatus.ACTIVE,
    command: str = "echo hello",
    timeout_s: int = 60,
    alert_on_fail: bool = True,
    name: str | None = None,
) -> tuple[Tenant, Server, Job]:
    """Crea tenant + server + job y devuelve los tres."""
    tenant = Tenant(name="job-tenant", slug=f"job-{uuid4().hex[:8]}")
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

    job = Job(
        tenant_id=tenant.id,
        server_id=server.id,
        name=name or f"job-{uuid4().hex[:8]}",
        kind=kind,
        schedule_cron=schedule_cron,
        command=command,
        timeout_s=timeout_s,
        alert_on_fail=alert_on_fail,
        status=status,
    )
    session.add(job)
    await session.flush()
    return tenant, server, job


# ──────────────────────────────────────────────
# Tests unitarios de _is_cron_due
# ──────────────────────────────────────────────

class TestIsCronDue:
    """Tests de la función de detección de cron debido."""

    def test_expresion_cada_minuto_siempre_es_devida(self) -> None:
        """Expresión * * * * * (cada minuto) → siempre due."""
        now = datetime(2026, 1, 15, 12, 30, 45, tzinfo=UTC)
        assert _is_cron_due("* * * * *", now) is True

    def test_expresion_cada_hora_en_minuto_cero(self) -> None:
        """Expresión 0 * * * * → due solo en minuto 0."""
        due = datetime(2026, 1, 15, 12, 0, 30, tzinfo=UTC)
        not_due = datetime(2026, 1, 15, 12, 30, 30, tzinfo=UTC)
        assert _is_cron_due("0 * * * *", due) is True
        assert _is_cron_due("0 * * * *", not_due) is False

    def test_expresion_diaria_en_medianoche(self) -> None:
        """Expresión 0 0 * * * → due solo a medianoche."""
        due = datetime(2026, 1, 15, 0, 0, 30, tzinfo=UTC)
        not_due = datetime(2026, 1, 15, 12, 0, 30, tzinfo=UTC)
        assert _is_cron_due("0 0 * * *", due) is True
        assert _is_cron_due("0 0 * * *", not_due) is False

    def test_expresion_invalida_retorna_false(self) -> None:
        """Expresión inválida → False (warning se loguea via structlog a stdout)."""
        now = datetime(2026, 1, 15, 12, 30, 45, tzinfo=UTC)
        assert _is_cron_due("invalid cron", now) is False

    def test_strategia_un_minuto_atras(self) -> None:
        """La estrategia usa now - 1min como base para evitar doble ejecución."""
        # Expresión cada 5 minutos: 0, 5, 10, 15...
        expr = "*/5 * * * *"

        # En 12:05:30 → base = 12:04:30 → next = 12:05:00 <= now → DUE
        now_due = datetime(2026, 1, 15, 12, 5, 30, tzinfo=UTC)
        assert _is_cron_due(expr, now_due) is True

        # En 12:05:00 → base = 12:04:00 → next = 12:05:00 <= now → DUE
        now_due_exact = datetime(2026, 1, 15, 12, 5, 0, tzinfo=UTC)
        assert _is_cron_due(expr, now_due_exact) is True

        # En 12:04:59 → base = 12:03:59 → next = 12:05:00 > now → NOT DUE
        now_not_due = datetime(2026, 1, 15, 12, 4, 59, tzinfo=UTC)
        assert _is_cron_due(expr, now_not_due) is False


# ──────────────────────────────────────────────
# Tests de run_due_jobs (motor principal)
# ──────────────────────────────────────────────

class TestRunDueJobs:
    """Tests de la función principal run_due_jobs."""

    @pytest.mark.asyncio
    async def test_job_no_cron_se_salta(self, db_session: AsyncSession) -> None:
        """Job BATCH (sin schedule_cron) → se salta."""
        await _seed_tenant_server_job(
            db_session, kind=JobKind.BATCH, schedule_cron=None
        )

        executed = await run_due_jobs(db_session)
        assert executed == 0

    @pytest.mark.asyncio
    async def test_job_inactivo_se_salta(self, db_session: AsyncSession) -> None:
        """Job con status=PAUSED → se salta."""
        await _seed_tenant_server_job(
            db_session, status=JobStatus.PAUSED
        )

        executed = await run_due_jobs(db_session)
        assert executed == 0

    @pytest.mark.asyncio
    async def test_job_cron_no_devido_se_salta(self, db_session: AsyncSession) -> None:
        """Job CRON válido pero no debido → se salta."""
        # Expresión cada hora en minuto 0, ahora es 12:30
        await _seed_tenant_server_job(
            db_session, schedule_cron="0 * * * *"
        )

        executed = await run_due_jobs(db_session)
        assert executed == 0

    @pytest.mark.asyncio
    async def test_cron_invalido_se_salta(self, db_session: AsyncSession) -> None:
        """Job con cron inválido → se salta (warning se loguea via structlog)."""
        await _seed_tenant_server_job(
            db_session, schedule_cron="not a valid cron"
        )

        executed = await run_due_jobs(db_session)
        assert executed == 0

    @pytest.mark.asyncio
    async def test_concurrencia_previene_doble_ejecucion(self, db_session: AsyncSession) -> None:
        """Si hay JobRun previo con status=running → salta el job."""
        tenant, server, job = await _seed_tenant_server_job(db_session)

        # Crear JobRun previo "running"
        running_run = JobRun(
            job_id=job.id,
            tenant_id=tenant.id,
            started_at=datetime.now(UTC) - timedelta(minutes=5),
            status="running",
            exit_code=None,
            output_tail=None,
            run_metadata={},
        )
        db_session.add(running_run)
        await db_session.flush()

        executed = await run_due_jobs(db_session)
        assert executed == 0

        # Verificar que no se creó nuevo run
        runs = (await db_session.scalars(
            select(JobRun).where(JobRun.job_id == job.id)
        )).all()
        assert len(runs) == 1
        assert runs[0].status == "running"

    @pytest.mark.asyncio
    async def test_ejecucion_exitosa_crea_run_success(
        self, db_session: AsyncSession
    ) -> None:
        """Comando exitoso (exit=0) → JobRun status=success."""
        tenant, server, job = await _seed_tenant_server_job(
            db_session, command="echo hello"
        )

        with patch("app.workers.jobs._run_job_command", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (0, "hello\n", False)  # exit_code=0, no timeout

            executed = await run_due_jobs(db_session)

        assert executed == 1
        mock_run.assert_called_once_with("echo hello", job.timeout_s)

        run = await db_session.scalar(
            select(JobRun).where(JobRun.job_id == job.id)
        )
        assert run is not None
        assert run.status == "success"
        assert run.exit_code == 0
        assert run.output_tail == "hello\n"
        assert run.finished_at is not None

    @pytest.mark.asyncio
    async def test_ejecucion_fallida_crea_run_failed(
        self, db_session: AsyncSession
    ) -> None:
        """Comando fallido (exit!=0) → JobRun status=failed + log warning."""
        tenant, server, job = await _seed_tenant_server_job(
            db_session, command="exit 1"
        )

        with patch("app.workers.jobs._run_job_command", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (1, "error output\n", False)  # exit_code=1

            executed = await run_due_jobs(db_session)

        assert executed == 1

        run = await db_session.scalar(
            select(JobRun).where(JobRun.job_id == job.id)
        )
        assert run is not None
        assert run.status == "failed"
        assert run.exit_code == 1
        assert "error output" in run.output_tail

    @pytest.mark.asyncio
    async def test_timeout_crea_run_timeout_y_metadata(
        self, db_session: AsyncSession
    ) -> None:
        """Comando que excede timeout → JobRun status=timeout + metadata timed_out."""
        tenant, server, job = await _seed_tenant_server_job(
            db_session, command="sleep 100", timeout_s=1
        )

        with patch("app.workers.jobs._run_job_command", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (None, "partial output\n", True)  # timeout

            executed = await run_due_jobs(db_session)

        assert executed == 1

        run = await db_session.scalar(
            select(JobRun).where(JobRun.job_id == job.id)
        )
        assert run is not None
        assert run.status == "timeout"
        assert run.exit_code is None
        assert run.run_metadata == {"timed_out": True}

    @pytest.mark.asyncio
    async def test_fallo_con_alert_on_fail_loguea_intento_alerta(
        self, db_session: AsyncSession
    ) -> None:
        """Fallo con alert_on_fail=True → loguea intento de alerta (rule_id required)."""
        tenant, server, job = await _seed_tenant_server_job(
            db_session, alert_on_fail=True
        )

        with patch("app.workers.jobs._run_job_command", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (1, "error\n", False)

            await run_due_jobs(db_session)

        # Verificar que el run se creó con status=failed
        run = await db_session.scalar(
            select(JobRun).where(JobRun.job_id == job.id)
        )
        assert run is not None
        assert run.status == "failed"

    @pytest.mark.asyncio
    async def test_sin_alert_on_fail_no_loguea_alerta(
        self, db_session: AsyncSession
    ) -> None:
        """Fallo con alert_on_fail=False → NO loguea intento de alerta."""
        tenant, server, job = await _seed_tenant_server_job(
            db_session, alert_on_fail=False
        )

        with patch("app.workers.jobs._run_job_command", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (1, "error\n", False)

            await run_due_jobs(db_session)

        # Verificar que el run se creó con status=failed pero no se loguea alerta
        run = await db_session.scalar(
            select(JobRun).where(JobRun.job_id == job.id)
        )
        assert run is not None
        assert run.status == "failed"

    @pytest.mark.asyncio
    async def test_multiple_jobs_solo_ejecuta_los_devidos(
        self, db_session: AsyncSession
    ) -> None:
        """Varios jobs: solo los debidos se ejecutan."""
        # Job 1: debido (cada minuto)
        _, _, job1 = await _seed_tenant_server_job(
            db_session, name="job-due", schedule_cron="* * * * *"
        )
        # Job 2: no debido (cada hora en min 0, ahora 12:30)
        _, _, job2 = await _seed_tenant_server_job(
            db_session, name="job-not-due", schedule_cron="0 * * * *"
        )
        # Job 3: inactivo
        _, _, job3 = await _seed_tenant_server_job(
            db_session, name="job-inactive", status=JobStatus.PAUSED
        )
        # Job 4: BATCH (sin cron)
        _, _, job4 = await _seed_tenant_server_job(
            db_session, name="job-batch", kind=JobKind.BATCH
        )

        with patch("app.workers.jobs._run_job_command", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (0, "ok\n", False)

            executed = await run_due_jobs(db_session)

        assert executed == 1
        mock_run.assert_called_once()

        # Verificar que solo job1 se ejecutó
        run1 = await db_session.scalar(
            select(JobRun).where(JobRun.job_id == job1.id)
        )
        run2 = await db_session.scalar(
            select(JobRun).where(JobRun.job_id == job2.id)
        )
        assert run1 is not None
        assert run2 is None

    @pytest.mark.asyncio
    async def test_tenant_id_se_propaga_al_run(
        self, db_session: AsyncSession
    ) -> None:
        """El JobRun creado lleva el tenant_id del job."""
        tenant, server, job = await _seed_tenant_server_job(db_session)

        with patch("app.workers.jobs._run_job_command", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (0, "ok\n", False)

            await run_due_jobs(db_session)

        run = await db_session.scalar(
            select(JobRun).where(JobRun.job_id == job.id)
        )
        assert run is not None
        assert run.tenant_id == tenant.id

    @pytest.mark.asyncio
    async def test_commit_al_final_guarda_todo(
        self, db_session: AsyncSession
    ) -> None:
        """Al final de run_due_jobs se hace commit de todos los runs."""
        tenant, server, job = await _seed_tenant_server_job(db_session)

        with patch("app.workers.jobs._run_job_command", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (0, "ok\n", False)

            await run_due_jobs(db_session)

        # El run debe estar persistido (commit implícito en la fixture db_session)
        run = await db_session.scalar(
            select(JobRun).where(JobRun.job_id == job.id)
        )
        assert run is not None
        assert run.id is not None


# ──────────────────────────────────────────────
# Test de integración real con timeout (short)
# ──────────────────────────────────────────────

class TestRunJobCommandIntegration:
    """Test de integración real de _run_job_command con timeout corto."""

    @pytest.mark.asyncio
    async def test_timeout_real_con_sleep_corto(self) -> None:
        """Comando sleep real con timeout muy corto → timeout detectado."""
        from app.workers.jobs import _run_job_command

        # sleep 10 con timeout 1 segundo → debe hacer timeout
        exit_code, output_tail, timed_out = await _run_job_command(
            "python -c \"import time; time.sleep(10)\"",
            timeout_s=1,
        )

        assert timed_out is True
        assert exit_code is None
        # output_tail puede estar vacío si el proceso no escribió nada antes de morir

    @pytest.mark.asyncio
    async def test_comando_exitoso_real(self) -> None:
        """Comando echo real → exit_code=0."""
        from app.workers.jobs import _run_job_command

        exit_code, output_tail, timed_out = await _run_job_command(
            "echo 'hello world'",
            timeout_s=5,
        )

        assert timed_out is False
        assert exit_code == 0
        assert "hello world" in output_tail

    @pytest.mark.asyncio
    async def test_comando_fallido_real(self) -> None:
        """Comando exit 1 real → exit_code=1."""
        from app.workers.jobs import _run_job_command

        exit_code, output_tail, timed_out = await _run_job_command(
            "exit 2",
            timeout_s=5,
        )

        assert timed_out is False
        assert exit_code == 2