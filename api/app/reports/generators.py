"""Generadores de reportes por tipo.

Cada generador recibe (session, tenant_id, period_start, period_end, params)
y retorna un dict serializable como JSON para almacenar en Report.payload.
"""

from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from app.models.alert import Alert, AlertRule, AlertSeverity, AlertStatus, EntityType
from app.models.metric import Metric, MetricType
from app.models.metric_rollup import MetricRollup, RollupPeriod
from app.models.server import Server
from app.models.tenant import Tenant
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# ──────────────────────────────────────────────
# Helpers comunes
# ──────────────────────────────────────────────

HEARTBEAT_THRESHOLD = timedelta(minutes=5)  # server "online" si heartbeat < 5 min


def _iso(dt: datetime | None) -> str | None:
    """Serializa datetime a ISO con Z (UTC)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat().replace("+00:00", "Z")


def _ensure_utc(dt: datetime) -> datetime:
    """Asegura que datetime sea timezone-aware UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


async def _get_servers_in_period(
    session: AsyncSession,
    tenant_id: UUID,
    period_start: datetime,
    period_end: datetime,
    server_id: UUID | None = None,
) -> Sequence[Server]:
    """Obtiene servers del tenant, opcionalmente filtrado por server_id."""
    stmt = select(Server).where(
        Server.tenant_id == tenant_id,
    )
    if server_id is not None:
        stmt = stmt.where(Server.id == server_id)
    result = await session.execute(stmt)
    return result.scalars().all()


async def _get_alerts_in_period(  # noqa: PLR0913, PLR0917
    session: AsyncSession,
    tenant_id: UUID,
    period_start: datetime,
    period_end: datetime,
    severity: AlertSeverity | None = None,
    entity_type: EntityType | None = None,
    rule_id: UUID | None = None,
) -> Sequence[Alert]:
    """Obtiene alertas del tenant en el período, con filtros opcionales."""
    stmt = select(Alert).where(
        Alert.tenant_id == tenant_id,
        Alert.triggered_at >= period_start,
        Alert.triggered_at <= period_end,
    )
    if severity is not None:
        stmt = stmt.where(Alert.severity == severity)
    if entity_type is not None:
        stmt = stmt.where(AlertRule.entity_type == entity_type).join(AlertRule)
    if rule_id is not None:
        stmt = stmt.where(Alert.rule_id == rule_id)
    stmt = stmt.order_by(Alert.triggered_at)
    result = await session.execute(stmt)
    return result.scalars().all()


async def _get_tenant_sla_target(session: AsyncSession, tenant_id: UUID) -> float:
    """Lee target SLA de tenant.settings.sla.default_target_pct (default 99.9)."""
    stmt = select(Tenant.settings).where(Tenant.id == tenant_id)
    result = await session.execute(stmt)
    settings = result.scalar_one_or_none() or {}
    sla = settings.get("sla", {})
    return float(sla.get("default_target_pct", 99.9))


async def generate_availability(
    session: AsyncSession,
    tenant_id: UUID,
    period_start: datetime,
    period_end: datetime,
    params: dict,
) -> dict:
    """Reporte de disponibilidad: uptime/downtime por servidor.

    params:
        - server_id (str|UUID): opcional, filtrar un server específico
    """
    # Normalizar a UTC
    period_start = _ensure_utc(period_start)
    period_end = _ensure_utc(period_end)

    server_id_str = params.get("server_id")
    server_id = UUID(server_id_str) if server_id_str and server_id_str != "all" else None

    servers = await _get_servers_in_period(session, tenant_id, period_start, period_end, server_id)

    servers_data = []
    total_uptime_seconds = 0
    total_possible_seconds = 0

    for server in servers:
        # Obtener métricas RAW del server en el período para detectar heartbeats
        metrics_stmt = select(Metric.ts).where(
            Metric.tenant_id == tenant_id,
            Metric.server_id == server.id,
            Metric.ts >= period_start,
            Metric.ts <= period_end,
        ).order_by(Metric.ts)
        metrics_result = await session.execute(metrics_stmt)
        metric_timestamps = [_ensure_utc(row[0]) for row in metrics_result.all()]

        # Calcular uptime basado en gaps entre métricas
        # Si no hay métricas → 0% uptime
        downtime_windows: list[dict[str, Any]] = []
        status_changes: list[dict[str, Any]] = []

        if not metric_timestamps:
            uptime_pct = 0.0
            downtime_seconds = int((period_end - period_start).total_seconds())
            downtime_windows = [{"start": _iso(period_start), "end": _iso(period_end), "duration_s": downtime_seconds}]
            status_changes = []
        else:
            # Detectar gaps > HEARTBEAT_THRESHOLD
            prev_ts = period_start

            for ts in metric_timestamps:
                gap = (ts - prev_ts).total_seconds()
                if gap > HEARTBEAT_THRESHOLD.total_seconds():
                    # Downtime detectado
                    downtime_windows.append({
                        "start": _iso(prev_ts),
                        "end": _iso(ts),
                        "duration_s": int(gap),
                    })
                    status_changes.append({"at": _iso(prev_ts), "from": "online", "to": "offline"})
                    status_changes.append({"at": _iso(ts), "from": "offline", "to": "online"})
                prev_ts = ts

            # Gap final hasta period_end
            final_gap = (period_end - prev_ts).total_seconds()
            if final_gap > HEARTBEAT_THRESHOLD.total_seconds():
                downtime_windows.append({
                    "start": _iso(prev_ts),
                    "end": _iso(period_end),
                    "duration_s": int(final_gap),
                })
                status_changes.append({"at": _iso(prev_ts), "from": "online", "to": "offline"})

            downtime_seconds = sum(w["duration_s"] for w in downtime_windows)
            total_period_seconds = int((period_end - period_start).total_seconds())
            uptime_seconds = max(0, total_period_seconds - downtime_seconds)
            uptime_pct = round((uptime_seconds / total_period_seconds) * 100, 2) if total_period_seconds > 0 else 0.0

        total_uptime_seconds += max(0, int((period_end - period_start).total_seconds()) - downtime_seconds)
        total_possible_seconds += int((period_end - period_start).total_seconds())

        servers_data.append({
            "server_id": str(server.id),
            "hostname": server.hostname,
            "uptime_pct": uptime_pct,
            "downtime_seconds": downtime_seconds,
            "downtime_windows": downtime_windows,
            "status_changes": status_changes,
        })

    overall_uptime_pct = round((total_uptime_seconds / total_possible_seconds) * 100, 2) if total_possible_seconds > 0 else 0.0

    return {
        "summary": {
            "total_servers": len(servers),
            "overall_uptime_pct": overall_uptime_pct,
        },
        "servers": servers_data,
    }


async def generate_incidents(
    session: AsyncSession,
    tenant_id: UUID,
    period_start: datetime,
    period_end: datetime,
    params: dict,
) -> dict:
    """Reporte de incidentes: alertas agrupadas por episodio + MTTR.

    params:
        - severity (str): opcional, filtrar por severidad (info/warning/critical)
        - entity_type (str): opcional, filtrar por tipo (server/service/process/job/metric)
    """
    period_start = _ensure_utc(period_start)
    period_end = _ensure_utc(period_end)
    severity = AlertSeverity(params["severity"]) if params.get("severity") else None
    entity_type = EntityType(params["entity_type"]) if params.get("entity_type") else None

    alerts = await _get_alerts_in_period(
        session, tenant_id, period_start, period_end,
        severity=severity, entity_type=entity_type,
    )

    # Agrupar alertas en incidentes por rule_id + ventana temporal contigua
    incident_gap_threshold = timedelta(minutes=5)  # gap < 5 min = mismo incidente

    incidents_by_rule: dict[UUID, list[Alert]] = defaultdict(list)
    for alert in alerts:
        if alert.rule_id:
            incidents_by_rule[alert.rule_id].append(alert)

    incidents = []
    severity_counts: dict[str, int] = defaultdict(int)

    for rule_id, rule_alerts in incidents_by_rule.items():
        if not rule_alerts:
            continue

        # Agrupar en episodios contiguos
        episodes = []
        current_episode = [rule_alerts[0]]

        for alert in rule_alerts[1:]:
            gap = (alert.triggered_at - current_episode[-1].triggered_at).total_seconds()
            if gap <= incident_gap_threshold.total_seconds():
                current_episode.append(alert)
            else:
                episodes.append(current_episode)
                current_episode = [alert]
        episodes.append(current_episode)

        # Obtener regla para metadatos
        rule_stmt = select(AlertRule).where(AlertRule.id == rule_id)
        rule_result = await session.execute(rule_stmt)
        rule = rule_result.scalar_one_or_none()

        for episode in episodes:
            if not episode:
                continue

            first = episode[0]
            last = episode[-1]
            severity_counts[first.severity.value] += 1

            # Duración del incidente
            duration_s = int((last.triggered_at - first.triggered_at).total_seconds())

            # Resuelto si el último está RESOLVED
            resolved_at = last.resolved_at if last.status == AlertStatus.RESOLVED else None

            # Canales únicos usados
            channels: set[str] = set()
            for a in episode:
                if a.rule and a.rule.channels:
                    channels.update(a.rule.channels.keys())

            incidents.append({
                "incident_id": str(UUID(bytes=rule_id.bytes[:16]) if hasattr(rule_id, 'bytes') else rule_id),
                "rule_id": str(rule_id),
                "entity_type": rule.entity_type.value if rule else "unknown",
                "entity_name": _get_entity_name(rule, first) if rule else "unknown",
                "severity": first.severity.value,
                "started_at": _iso(first.triggered_at),
                "resolved_at": _iso(resolved_at),
                "duration_seconds": duration_s,
                "alert_count": len(episode),
                "channels": sorted(channels),
                "root_cause": first.message,
            })

    total_incidents = len(incidents)
    resolved_incidents = [i for i in incidents if i["resolved_at"]]
    mttr_seconds = 0
    if resolved_incidents:
        mttr_seconds = int(sum(
            (
                datetime.fromisoformat(str(i["resolved_at"]).replace("Z", "+00:00")) -
                datetime.fromisoformat(str(i["started_at"]).replace("Z", "+00:00"))
            ).total_seconds()
            for i in resolved_incidents
        ) / len(resolved_incidents))

    return {
        "summary": {
            "total_incidents": total_incidents,
            "mttr_seconds": mttr_seconds,
            "by_severity": dict(severity_counts),
        },
        "incidents": incidents,
    }


def _get_entity_name(rule: AlertRule, alert: Alert) -> str:
    """Obtiene nombre legible de la entidad para el incidente."""
    if rule.entity_id:
        return str(rule.entity_id)  # TODO: resolver nombre real via join
    return "all"


async def generate_alerts(
    session: AsyncSession,
    tenant_id: UUID,
    period_start: datetime,
    period_end: datetime,
    params: dict,
) -> dict:
    """Reporte de alertas: catálogo plano volumen/severidad/canal.

    params: filtros opcionales (severity, entity_type, status, rule_id)
    """
    period_start = _ensure_utc(period_start)
    period_end = _ensure_utc(period_end)
    severity = AlertSeverity(params["severity"]) if params.get("severity") else None
    entity_type = EntityType(params["entity_type"]) if params.get("entity_type") else None
    status = AlertStatus(params["status"]) if params.get("status") else None
    rule_id = UUID(params["rule_id"]) if params.get("rule_id") else None

    stmt = select(Alert).where(
        Alert.tenant_id == tenant_id,
        Alert.triggered_at >= period_start,
        Alert.triggered_at <= period_end,
    )
    if severity is not None:
        stmt = stmt.where(Alert.severity == severity)
    if entity_type is not None:
        stmt = stmt.join(AlertRule).where(AlertRule.entity_type == entity_type)
    if status is not None:
        stmt = stmt.where(Alert.status == status)
    if rule_id is not None:
        stmt = stmt.where(Alert.rule_id == rule_id)
    stmt = stmt.order_by(Alert.triggered_at.desc())
    result = await session.execute(stmt)
    alerts = result.scalars().all()

    # Agregaciones
    by_severity: dict[str, int] = defaultdict(int)
    by_status: dict[str, int] = defaultdict(int)
    by_channel: dict[str, int] = defaultdict(int)
    by_entity_type: dict[str, int] = defaultdict(int)

    alerts_data = []
    for alert in alerts:
        by_severity[alert.severity.value] += 1
        by_status[alert.status.value] += 1
        by_entity_type[alert.rule.entity_type.value if alert.rule else "unknown"] += 1

        # Canales del delivery
        for delivery in alert.deliveries:
            by_channel[delivery.channel] += 1

        alerts_data.append({
            "id": str(alert.id),
            "rule_id": str(alert.rule_id) if alert.rule_id else None,
            "type": alert.rule.entity_type.value if alert.rule else "job",
            "severity": alert.severity.value,
            "status": alert.status.value,
            "triggered_at": _iso(alert.triggered_at),
            "resolved_at": _iso(alert.resolved_at),
            "channel": alert.deliveries[0].channel if alert.deliveries else "none",
            "message": alert.message,
        })

    return {
        "summary": {
            "total": len(alerts),
            "resolved": by_status.get("resolved", 0),
            "open": by_status.get("open", 0) + by_status.get("acknowledged", 0),
            "by_severity": dict(by_severity),
            "by_status": dict(by_status),
            "by_channel": dict(by_channel),
            "by_entity_type": dict(by_entity_type),
        },
        "alerts": alerts_data,
    }


async def generate_sla(
    session: AsyncSession,
    tenant_id: UUID,
    period_start: datetime,
    period_end: datetime,
    params: dict,
) -> dict:
    """Reporte SLA: targets vs disponibilidad real → brechas.

    params:
        - target_pct (float): opcional, override del target (default de tenant.settings)
    """
    period_start = _ensure_utc(period_start)
    period_end = _ensure_utc(period_end)
    target_pct = float(params.get("target_pct", 0))
    if target_pct == 0:
        target_pct = await _get_tenant_sla_target(session, tenant_id)

    # Reusar lógica de availability para obtener uptime por server
    availability_payload = await generate_availability(session, tenant_id, period_start, period_end, params)
    servers_avail = availability_payload["servers"]

    servers_data = []
    breach_count = 0
    total_breach_minutes = 0

    for s in servers_avail:
        achieved = s["uptime_pct"]
        breach = achieved < target_pct
        breach_minutes = 0
        if breach:
            breach_count += 1
            # Minutos de breach = downtime en minutos
            breach_minutes = s["downtime_seconds"] // 60
            total_breach_minutes += breach_minutes

        servers_data.append({
            "server_id": s["server_id"],
            "hostname": s["hostname"],
            "target_pct": target_pct,
            "achieved_pct": achieved,
            "breach": breach,
            "breach_minutes": breach_minutes,
        })

    overall_achieved = availability_payload["summary"]["overall_uptime_pct"]
    overall_breach = overall_achieved < target_pct

    # Crédito simple: 10% por cada 0.1% bajo target, máx 100%
    breach_pct = max(0, target_pct - overall_achieved)
    credit_due_pct = min(100, int(breach_pct * 100))  # 0.1% = 10%, 1% = 100%

    return {
        "target_pct": target_pct,
        "achieved_pct": overall_achieved,
        "breach": overall_breach,
        "breach_minutes": total_breach_minutes,
        "servers": servers_data,
        "credit_due_pct": credit_due_pct,
    }


async def generate_metrics(
    session: AsyncSession,
    tenant_id: UUID,
    period_start: datetime,
    period_end: datetime,
    params: dict,
) -> dict:
    """Reporte métricas: serie temporal desde MetricRollup (downsampling).

    params (requeridos):
        - server_id (str|UUID)
        - type (str): cpu_usage, mem_usage, disk_usage, load_avg1, load_avg5, load_avg15
        - period (str): 1m, 5m, 1h, 1d
    params (opcional):
        - max_points (int): default 500
    """
    period_start = _ensure_utc(period_start)
    period_end = _ensure_utc(period_end)
    server_id = UUID(params["server_id"]) if params.get("server_id") else None
    metric_type = MetricType(params["type"]) if params.get("type") else None
    period_str = params.get("period", "5m")
    max_points = int(params.get("max_points", 500))

    if not server_id or not metric_type:
        raise ValueError("server_id and type are required for metrics report")

    period = RollupPeriod(period_str)

    stmt = select(MetricRollup).where(
        MetricRollup.tenant_id == tenant_id,
        MetricRollup.server_id == server_id,
        MetricRollup.type == metric_type,
        MetricRollup.period == period,
        MetricRollup.bucket_start >= period_start,
        MetricRollup.bucket_start <= period_end,
    ).order_by(MetricRollup.bucket_start)
    result = await session.execute(stmt)
    rollups = result.scalars().all()

    points = [
        {
            "bucket_start": _iso(r.bucket_start),
            "avg": r.avg,
            "min": r.min,
            "max": r.max,
            "last": r.last,
            "count": r.count,
        }
        for r in rollups
    ]

    # Downsampling si excede max_points
    if len(points) > max_points:
        # Estrategia simple: tomar cada N-ésimo punto
        step = len(points) // max_points + 1
        points = points[::step]

    return {
        "server_id": str(server_id),
        "type": metric_type.value,
        "period": period.value,
        "points": points,
    }


# Dispatcher


GENERATORS = {
    "availability": generate_availability,
    "incidents": generate_incidents,
    "alerts": generate_alerts,
    "sla": generate_sla,
    "metrics": generate_metrics,
}


async def generate_report(  # noqa: PLR0913, PLR0917
    session: AsyncSession,
    tenant_id: UUID,
    report_type: str,
    period_start: datetime,
    period_end: datetime,
    params: dict,
) -> dict:
    """Dispatch al generador correspondiente."""
    generator = GENERATORS.get(report_type)
    if not generator:
        raise ValueError(f"Unknown report type: {report_type}")
    return await generator(session, tenant_id, period_start, period_end, params)

