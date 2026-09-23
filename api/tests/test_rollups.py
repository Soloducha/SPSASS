"""Tests unitarios del servicio de rollups (agregación de métricas)."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.models.metric import Metric, MetricType
from app.models.metric_rollup import MetricRollup, RollupPeriod
from app.models.server import Server, ServerStatus
from app.models.tenant import Tenant
from app.workers.rollups import as_utc, bucketize, compute_rollups
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class _MetricSeed:
    """Seed de métrica cruda para helpers de test."""

    ts: datetime
    value: float
    mtype: MetricType


async def _seed_server(session: AsyncSession) -> tuple[Tenant, Server]:
    """Crea un tenant + server de prueba y devuelve ambos."""
    tenant = Tenant(name="rollup-tenant", slug=f"rollup-{uuid4().hex[:8]}")
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


async def _add_metrics(
    session: AsyncSession,
    server: Server,
    tenant: Tenant,
    seeds: list[_MetricSeed],
) -> None:
    """Inserta métricas crudas de un server/tenant."""
    for seed in seeds:
        session.add(
            Metric(
                ts=seed.ts,
                server_id=server.id,
                tenant_id=tenant.id,
                type=seed.mtype,
                value=seed.value,
            )
        )
    await session.flush()


class TestBucketize:
    def test_floor_a_minuto(self) -> None:
        ts = datetime(2026, 9, 23, 12, 34, 56, tzinfo=UTC)
        assert bucketize(ts, 60) == datetime(2026, 9, 23, 12, 34, 0, tzinfo=UTC)

    def test_floor_a_cinco_minutos(self) -> None:
        ts = datetime(2026, 9, 23, 12, 34, 56, tzinfo=UTC)
        assert bucketize(ts, 300) == datetime(2026, 9, 23, 12, 30, 0, tzinfo=UTC)

    def test_floor_a_hora(self) -> None:
        ts = datetime(2026, 9, 23, 12, 34, 56, tzinfo=UTC)
        assert bucketize(ts, 3600) == datetime(2026, 9, 23, 12, 0, 0, tzinfo=UTC)

    def test_floor_a_dia(self) -> None:
        ts = datetime(2026, 9, 23, 12, 34, 56, tzinfo=UTC)
        assert bucketize(ts, 86400) == datetime(2026, 9, 23, 0, 0, 0, tzinfo=UTC)

    def test_naive_se_trata_como_utc(self) -> None:
        ts = datetime(2026, 9, 23, 12, 34, 56)  # naive, como devuelve SQLite
        assert bucketize(ts, 60) == datetime(2026, 9, 23, 12, 34, 0, tzinfo=UTC)


class TestComputeRollups:
    async def _completed_bucket(self) -> datetime:
        """Bucket 1m completo más reciente (dentro del window y ya cerrado)."""
        return bucketize(datetime.now(UTC) - timedelta(seconds=90), 60)

    async def test_agrega_bucket_con_count_avg_min_max_last(
        self, db_session: AsyncSession
    ) -> None:
        tenant, server = await _seed_server(db_session)

        # Valores en un bucket 1m completo: 1.0, 3.0, 5.0, 7.0
        bucket = await self._completed_bucket()
        seeds = [
            _MetricSeed(bucket + timedelta(seconds=i * 10), v, MetricType.CPU_USAGE)
            for i, v in enumerate([1.0, 3.0, 5.0, 7.0])
        ]
        await _add_metrics(db_session, server, tenant, seeds)

        written = await compute_rollups(db_session, RollupPeriod.MIN_1)

        assert written == 1
        rollup = await db_session.scalar(
            select(MetricRollup).where(MetricRollup.server_id == server.id)
        )
        assert rollup is not None
        assert rollup.period == RollupPeriod.MIN_1
        assert rollup.tenant_id == tenant.id
        assert rollup.type == MetricType.CPU_USAGE
        assert rollup.count == 4
        assert rollup.avg == 4.0
        assert rollup.min == 1.0
        assert rollup.max == 7.0
        assert rollup.last == 7.0
        assert as_utc(rollup.bucket_start) == bucket

    async def test_es_idempotente_no_duplica_filas(self, db_session: AsyncSession) -> None:
        tenant, server = await _seed_server(db_session)
        bucket = await self._completed_bucket()
        await _add_metrics(
            db_session, server, tenant, [_MetricSeed(bucket, 2.0, MetricType.CPU_USAGE)]
        )

        await compute_rollups(db_session, RollupPeriod.MIN_1)
        await compute_rollups(db_session, RollupPeriod.MIN_1)

        total = await db_session.scalar(select(func.count()).select_from(MetricRollup))
        assert total == 1

    async def test_reejecucion_actualiza_valores_existentes(
        self, db_session: AsyncSession
    ) -> None:
        tenant, server = await _seed_server(db_session)
        bucket = await self._completed_bucket()
        await _add_metrics(
            db_session, server, tenant, [_MetricSeed(bucket, 2.0, MetricType.CPU_USAGE)]
        )
        await compute_rollups(db_session, RollupPeriod.MIN_1)

        # Llega otra métrica al mismo bucket → re-calcula
        await _add_metrics(
            db_session,
            server,
            tenant,
            [_MetricSeed(bucket + timedelta(seconds=30), 6.0, MetricType.CPU_USAGE)],
        )
        await compute_rollups(db_session, RollupPeriod.MIN_1)

        rollup = await db_session.scalar(
            select(MetricRollup).where(MetricRollup.server_id == server.id)
        )
        assert rollup is not None
        assert rollup.count == 2
        assert rollup.avg == 4.0
        assert rollup.last == 6.0

    async def test_agrupa_por_tipo(self, db_session: AsyncSession) -> None:
        tenant, server = await _seed_server(db_session)
        bucket = await self._completed_bucket()
        await _add_metrics(
            db_session,
            server,
            tenant,
            [
                _MetricSeed(bucket, 1.0, MetricType.CPU_USAGE),
                _MetricSeed(bucket + timedelta(seconds=1), 100.0, MetricType.MEM_USAGE),
            ],
        )

        await compute_rollups(db_session, RollupPeriod.MIN_1)

        rollups = (await db_session.scalars(select(MetricRollup))).all()
        assert len(rollups) == 2
        by_type = {r.type: r for r in rollups}
        assert by_type[MetricType.CPU_USAGE].avg == 1.0
        assert by_type[MetricType.MEM_USAGE].avg == 100.0

    async def test_aisla_por_tenant_y_server(self, db_session: AsyncSession) -> None:
        tenant_a, server_a = await _seed_server(db_session)
        tenant_b, server_b = await _seed_server(db_session)
        bucket = await self._completed_bucket()
        await _add_metrics(
            db_session, server_a, tenant_a, [_MetricSeed(bucket, 1.0, MetricType.CPU_USAGE)]
        )
        await _add_metrics(
            db_session, server_b, tenant_b, [_MetricSeed(bucket, 42.0, MetricType.CPU_USAGE)]
        )

        await compute_rollups(db_session, RollupPeriod.MIN_1)

        rollups = (await db_session.scalars(select(MetricRollup))).all()
        assert len(rollups) == 2
        assert {r.avg for r in rollups} == {1.0, 42.0}

    async def test_excluye_bucket_en_curso(self, db_session: AsyncSession) -> None:
        tenant, server = await _seed_server(db_session)
        # Métrica "ahora" (bucket en curso) → no debe generar rollup
        now = datetime.now(UTC)
        await _add_metrics(
            db_session, server, tenant, [_MetricSeed(now, 1.0, MetricType.CPU_USAGE)]
        )

        written = await compute_rollups(db_session, RollupPeriod.MIN_1)

        assert written == 0
        total = await db_session.scalar(select(func.count()).select_from(MetricRollup))
        assert total == 0

    async def test_respeta_ventana_por_periodo(self, db_session: AsyncSession) -> None:
        tenant, server = await _seed_server(db_session)
        # 20 min atrás: fuera de window 1m (15 min), pero dentro de 5m (2h)
        old = datetime.now(UTC) - timedelta(minutes=20)
        await _add_metrics(
            db_session, server, tenant, [_MetricSeed(old, 1.0, MetricType.CPU_USAGE)]
        )

        await compute_rollups(db_session, RollupPeriod.MIN_1)
        total_1m = await db_session.scalar(select(func.count()).select_from(MetricRollup))
        assert total_1m == 0

        await compute_rollups(db_session, RollupPeriod.MIN_5)
        total_5m = await db_session.scalar(select(func.count()).select_from(MetricRollup))
        assert total_5m == 1
