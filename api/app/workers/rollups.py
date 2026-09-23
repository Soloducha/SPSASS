"""Cálculo de rollups de métricas (agregaciones por período).

El worker arq ejecuta ``compute_rollups`` para 1m/5m/1h/1d. Cada período se
agrega DIRECTAMENTE desde las métricas crudas (fuente única de verdad); la
cadena 5m→desde 1m, 1h→desde 5m, etc. queda como optimización futura cuando
el volumen lo pida.

Idempotencia: la PK compuesta (period, bucket_start, server_id, type) permite
upsert vía ``session.merge``; re-ejecutar recalcula los mismos buckets sin
duplicar filas.

Solo se escriben buckets COMPLETOS (el bucket en curso se excluye).
"""

from collections import defaultdict
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.metric import Metric, MetricType
from app.models.metric_rollup import MetricRollup, RollupPeriod

# Ventana de lectura hacia atrás por período en cada run.
# Cubre restarts / cron perdidos sin backfill gigante.
WINDOW: dict[RollupPeriod, timedelta] = {
    RollupPeriod.MIN_1: timedelta(minutes=15),
    RollupPeriod.MIN_5: timedelta(hours=2),
    RollupPeriod.HOUR_1: timedelta(hours=48),
    RollupPeriod.DAY_1: timedelta(days=14),
}

PERIOD_SECONDS: dict[RollupPeriod, int] = {
    RollupPeriod.MIN_1: 60,
    RollupPeriod.MIN_5: 300,
    RollupPeriod.HOUR_1: 3600,
    RollupPeriod.DAY_1: 86400,
}


def bucketize(ts: datetime, period_s: int, *, tz: timezone = UTC) -> datetime:
    """Devuelve el inicio del bucket al que pertenece ``ts`` (epoch floor)."""
    epoch_bucket = int(as_utc(ts).timestamp() // period_s) * period_s
    return datetime.fromtimestamp(epoch_bucket, tz=tz)


def as_utc(dt: datetime) -> datetime:
    """Normaliza a UTC aware. SQLite devuelve datetimes NAIVE al leer; asumimos
    UTC porque la API y el worker siempre escriben UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


async def compute_rollups(session: AsyncSession, period: RollupPeriod) -> int:
    """Agrega métricas crudas del window en buckets de ``period``.

    Idempotente: upsert por PK compuesta (merge) — re-ejecutar recalcula los
    mismos buckets. Solo escriben buckets COMPLETOS (el bucket en curso se
    excluye).

    Devuelve la cantidad de buckets escritos.
    """
    period_s = PERIOD_SECONDS[period]
    now = datetime.now(UTC)
    window_start = now - WINDOW[period]

    rows = (await session.scalars(select(Metric).where(Metric.ts >= window_start))).all()

    groups: dict[tuple[datetime, UUID, UUID, MetricType], list[Metric]] = defaultdict(list)
    for m in rows:
        bucket = bucketize(m.ts, period_s)
        groups[(bucket, m.tenant_id, m.server_id, m.type)].append(m)

    written = 0
    for (bucket, tenant_id, server_id, mtype), items in groups.items():
        # Solo buckets completos (el siguiente bucket aún no empezó)
        if bucket + timedelta(seconds=period_s) > now:
            continue

        values = [m.value for m in items]
        last_item = max(items, key=lambda m: as_utc(m.ts))
        rollup = MetricRollup(
            period=period,
            bucket_start=bucket,
            tenant_id=tenant_id,
            server_id=server_id,
            type=mtype,
            count=len(items),
            avg=sum(values) / len(values),
            min=min(values),
            max=max(values),
            last=last_item.value,
        )
        await session.merge(rollup)
        written += 1

    await session.commit()
    return written
