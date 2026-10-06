"""Worker de entrega de reportes completados.

Procesa Reports con status=COMPLETED que no tienen delivered_at,
los envía por los canales configurados en tenant.settings.report_channels
(email, webhook, telegram), y marca delivered_at + run_metadata.

Utiliza las clases de canal existentes (EmailChannel, WebhookChannel, TelegramChannel)
adaptando los datos del reporte al formato que esperan.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.session import get_db_session_without_tenant
from app.models.report import Report, ReportStatus
from app.models.tenant import Tenant
from app.workers.delivery.email import EmailChannel
from app.workers.delivery.telegram import TelegramChannel
from app.workers.delivery.webhook import WebhookChannel

logger = get_logger(__name__)


# ──────────────────────────────────────────────
# Adapters: hacer que Report parezca Alert para los canales
# ──────────────────────────────────────────────

class ReportAlertAdapter:
    """Adapta un Report para que parezca un Alert a los canales de delivery."""

    def __init__(self, report: Report, payload: dict) -> None:
        self.report = report
        self.payload = payload

    @property
    def severity(self) -> str:
        return "info"

    @property
    def message(self) -> str:
        summary = self.payload.get("summary", {})
        return f"Reporte {self.report.type.value} generado: {summary}"

    @property
    def triggered_at(self) -> datetime:
        return self.report.generated_at or datetime.now(UTC)

    @property
    def id(self) -> UUID:
        return self.report.id

    @property
    def tenant_id(self) -> UUID:
        return self.report.tenant_id


class ReportRuleAdapter:
    """Adapta un Report para que parezca un AlertRule a los canales."""

    def __init__(self, report: Report) -> None:
        self.report = report

    @property
    def id(self) -> UUID:
        return self.report.id

    @property
    def tenant_id(self) -> UUID:
        return self.report.tenant_id

    @property
    def channels(self) -> dict:
        return {}


class ReportServerAdapter:
    """Adapta un Report para que parezca un Server a los canales."""

    def __init__(self, report: Report) -> None:
        self.report = report

    @property
    def id(self) -> UUID:
        return self.report.id

    @property
    def tenant_id(self) -> UUID:
        return self.report.tenant_id


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

async def _get_pending_deliveries(session: AsyncSession) -> list[Report]:
    """Obtiene reports COMPLETED sin delivered_at, límite 50 por corrida."""
    stmt = select(Report).where(
        Report.status == ReportStatus.COMPLETED,
        Report.delivered_at.is_(None),
    ).limit(50)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def _get_tenant_report_channels(session: AsyncSession, tenant_id: UUID) -> dict[str, Any]:
    """Lee tenant.settings.report_channels."""
    stmt = select(Tenant.settings).where(Tenant.id == tenant_id)
    result = await session.execute(stmt)
    settings: dict[str, Any] = result.scalar_one_or_none() or {}
    channels = settings.get("report_channels")
    return channels if isinstance(channels, dict) else {}


def _build_report_payload(report: Report) -> dict[str, Any]:
    """Construye payload de entrega para el reporte."""
    return {
        "report_id": str(report.id),
        "type": report.type.value,
        "period_start": report.period_start.isoformat() if report.period_start else None,
        "period_end": report.period_end.isoformat() if report.period_end else None,
        "generated_at": report.generated_at.isoformat() if report.generated_at else None,
        "payload": report.payload,
        "file_path": report.file_path,
    }


# ──────────────────────────────────────────────
# Envío por canal
# ──────────────────────────────────────────────

async def _send_via_email(
    session: AsyncSession,
    report: Report,
    channel_config: dict[str, Any],
    payload: dict[str, Any],
) -> bool:
    """Envía reporte por email usando EmailChannel."""
    to = channel_config.get("to")
    if not to:
        logger.warning("email_channel_missing_to", report_id=str(report.id))
        return False

    channel = EmailChannel()
    alert_adapter = ReportAlertAdapter(report, payload)
    rule_adapter = ReportRuleAdapter(report)
    server_adapter = ReportServerAdapter(report)

    try:
        ext_ref = await channel.send(
            alert=alert_adapter,  # type: ignore[arg-type]
            rule=rule_adapter,  # type: ignore[arg-type]
            server=server_adapter,  # type: ignore[arg-type]
            channel_config=channel_config,
        )
        logger.info("report_email_sent", report_id=str(report.id), external_ref=ext_ref)
        return True
    except Exception:
        logger.exception("email_delivery_failed", report_id=str(report.id))
        return False


async def _send_via_webhook(
    session: AsyncSession,
    report: Report,
    channel_config: dict[str, Any],
    payload: dict[str, Any],
) -> bool:
    """Envía reporte por webhook usando WebhookChannel."""
    url = channel_config.get("url")
    if not url:
        logger.warning("webhook_channel_missing_url", report_id=str(report.id))
        return False

    channel = WebhookChannel()
    alert_adapter = ReportAlertAdapter(report, payload)
    rule_adapter = ReportRuleAdapter(report)
    server_adapter = ReportServerAdapter(report)

    try:
        ext_ref = await channel.send(
            alert=alert_adapter,  # type: ignore[arg-type]
            rule=rule_adapter,  # type: ignore[arg-type]
            server=server_adapter,  # type: ignore[arg-type]
            channel_config={"url": url, "headers": channel_config.get("headers", {})},
        )
        logger.info("report_webhook_sent", report_id=str(report.id), external_ref=ext_ref)
        return True
    except Exception:
        logger.exception("webhook_delivery_failed", report_id=str(report.id))
        return False


async def _send_via_telegram(
    session: AsyncSession,
    report: Report,
    channel_config: dict[str, Any],
    payload: dict[str, Any],
) -> bool:
    """Envía reporte por Telegram usando TelegramChannel."""
    chat_id = channel_config.get("chat_id")
    if not chat_id:
        logger.warning("telegram_channel_missing_chat_id", report_id=str(report.id))
        return False

    thread_id = channel_config.get("thread_id")
    silent = channel_config.get("silent", False)

    channel = TelegramChannel()
    alert_adapter = ReportAlertAdapter(report, payload)
    rule_adapter = ReportRuleAdapter(report)
    server_adapter = ReportServerAdapter(report)

    try:
        ext_ref = await channel.send(
            alert=alert_adapter,  # type: ignore[arg-type]
            rule=rule_adapter,  # type: ignore[arg-type]
            server=server_adapter,  # type: ignore[arg-type]
            channel_config={
                "chat_id": chat_id,
                "thread_id": thread_id,
                "silent": silent,
                "message": _format_report_for_telegram(report, payload),
            },
        )
        logger.info("report_telegram_sent", report_id=str(report.id), external_ref=ext_ref)
        return True
    except Exception:
        logger.exception("telegram_delivery_failed", report_id=str(report.id))
        return False


# ──────────────────────────────────────────────
# Formateo de mensajes
# ──────────────────────────────────────────────

def _format_report_for_email(report: Report, payload: dict[str, Any]) -> str:
    """Formatea reporte para email HTML."""
    summary = payload.get("summary", {})
    servers = payload.get("servers", [])
    incidents = payload.get("incidents", [])

    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6;">
        <h2>📊 Reporte SPSAAS: {report.type.value.title()}</h2>
        <p><strong>Período:</strong> {report.period_start} - {report.period_end}</p>
        <p><strong>Generado:</strong> {report.generated_at}</p>
        <hr>
    """

    if report.type.value == "availability":
        html += f"""
        <h3>Resumen de Disponibilidad</h3>
        <ul>
            <li>Total servidores: {summary.get('total_servers', 0)}</li>
            <li>Uptime general: {summary.get('overall_uptime_pct', 0)}%</li>
        </ul>
        <table border="1" cellpadding="5" style="border-collapse: collapse;">
            <tr><th>Servidor</th><th>Uptime</th><th>Downtime (s)</th></tr>
        """
        for s in servers:
            html += f"<tr><td>{s['hostname']}</td><td>{s['uptime_pct']}%</td><td>{s['downtime_seconds']}</td></tr>"
        html += "</table>"

    elif report.type.value == "incidents":
        html += f"""
        <h3>Resumen de Incidentes</h3>
        <ul>
            <li>Total incidentes: {summary.get('total_incidents', 0)}</li>
            <li>MTTR: {summary.get('mttr_seconds', 0)}s</li>
        </ul>
        <table border="1" cellpadding="5" style="border-collapse: collapse;">
            <tr><th>ID</th><th>Severidad</th><th>Inicio</th><th>Fin</th><th>Duración (s)</th></tr>
        """
        for inc in incidents:
            html += f"<tr><td>{inc['incident_id'][:8]}</td><td>{inc['severity']}</td><td>{inc['started_at']}</td><td>{inc['resolved_at'] or '—'}</td><td>{inc['duration_seconds']}</td></tr>"
        html += "</table>"

    elif report.type.value == "alerts":
        html += f"""
        <h3>Resumen de Alertas</h3>
        <ul>
            <li>Total: {summary.get('total', 0)}</li>
            <li>Resueltas: {summary.get('resolved', 0)}</li>
            <li>Abiertas: {summary.get('open', 0)}</li>
        </ul>
        """

    elif report.type.value == "sla":
        html += f"""
        <h3>Reporte SLA</h3>
        <ul>
            <li>Target: {summary.get('target_pct', 0)}%</li>
            <li>Logrado: {summary.get('achieved_pct', 0)}%</li>
            <li>Breach: {'Sí' if summary.get('breach') else 'No'}</li>
            <li>Crédito: {summary.get('credit_due_pct', 0)}%</li>
        </ul>
        """

    elif report.type.value == "metrics":
        html += f"""
        <h3>Métricas: {payload.get('type', '')} ({payload.get('period', '')})</h3>
        <p>Puntos: {len(payload.get('points', []))}</p>
        """

    html += """
        <hr>
        <p style="color: #666; font-size: 0.9em;">
            Este es un reporte automático de SPSAAS.
        </p>
    </body>
    </html>
    """
    return html


def _format_report_for_telegram(report: Report, payload: dict[str, Any]) -> str:
    """Formatea reporte para Telegram (Markdown, máx 4096 chars)."""
    summary = payload.get("summary", {})

    lines = [
        f"📊 *Reporte SPSAAS: {report.type.value.title()}*",
        f"📅 Período: {report.period_start} - {report.period_end}",
        f"⏰ Generado: {report.generated_at}",
        "—",
    ]

    if report.type.value == "availability":
        lines.extend([
            f"🖥 *{summary.get('total_servers', 0)} servidores* | Uptime: *{summary.get('overall_uptime_pct', 0)}%*",
            "",
            *[f"• {s['hostname']}: {s['uptime_pct']}% ({s['downtime_seconds']}s down)" for s in payload.get("servers", [])[:5]],
        ])

    elif report.type.value == "incidents":
        lines.extend([
            f"🚨 *{summary.get('total_incidents', 0)} incidentes* | MTTR: {summary.get('mttr_seconds', 0)}s",
            "",
            *[f"• {inc['severity'].upper()}: {inc['started_at']} - {inc['resolved_at'] or 'abierto'} ({inc['duration_seconds']}s)" for inc in payload.get("incidents", [])[:5]],
        ])

    elif report.type.value == "alerts":
        lines.extend([
            f"🔔 *{summary.get('total', 0)} alertas* | Resueltas: {summary.get('resolved', 0)} | Abiertas: {summary.get('open', 0)}",
        ])

    elif report.type.value == "sla":
        breach_emoji = "❌" if summary.get("breach") else "✅"
        lines.extend([
            f"📋 *SLA* {breach_emoji}",
            f"Target: {summary.get('target_pct', 0)}% | Logrado: {summary.get('achieved_pct', 0)}%",
            f"Breach: {'Sí' if summary.get('breach') else 'No'} | Crédito: {summary.get('credit_due_pct', 0)}%",
        ])

    elif report.type.value == "metrics":
        pts = payload.get("points", [])
        if pts:
            avg_val = sum(p["avg"] for p in pts) / len(pts)
            lines.extend([
                f"📈 *{payload.get('type', '')} ({payload.get('period', '')})*",
                f"Puntos: {len(pts)} | Promedio: {avg_val:.1f}",
            ])

    lines.append("\n—")
    lines.append("_Reporte automático SPSAAS_")

    return "\n".join(lines)


# ──────────────────────────────────────────────
# Job principal
# ──────────────────────────────────────────────

async def deliver_completed_reports_row(ctx: dict[str, Any]) -> int:
    """Procesa reports COMPLETED pendientes de entrega.

    Para cada reporte:
    1. Lee tenant.settings.report_channels
    2. Envía por cada canal configurado (email/webhook/telegram)
    3. Marca delivered_at + run_metadata["report_delivered"] = true (idempotencia)
    """
    async with get_db_session_without_tenant() as session:
        stmt = select(Report).where(
            Report.status == ReportStatus.COMPLETED,
            Report.delivered_at.is_(None),
        ).limit(50)
        result = await session.execute(stmt)
        reports = list(result.scalars().all())

        delivered = 0

        for report in reports:
            metadata = report.payload.get("run_metadata", {}) if isinstance(report.payload, dict) else {}
            if metadata.get("report_delivered"):
                continue

            channels = await _get_tenant_report_channels(session, report.tenant_id)
            if not channels:
                logger.debug("no_report_channels_configured", tenant_id=str(report.tenant_id), report_id=str(report.id))
                continue

            payload = _build_report_payload(report)
            all_sent = True

            for channel_name, channel_config in channels.items():
                success = False
                if channel_name == "email":
                    success = await _send_via_email(session, report, channel_config, payload)
                elif channel_name == "webhook":
                    success = await _send_via_webhook(session, report, channel_config, payload)
                elif channel_name == "telegram":
                    success = await _send_via_telegram(session, report, channel_config, payload)
                else:
                    logger.warning("unknown_report_channel", channel=channel_name, report_id=str(report.id))

                if not success:
                    all_sent = False
                    logger.warning("report_channel_failed", report_id=str(report.id), channel=channel_name)

            if all_sent:
                metadata = report.payload.get("run_metadata", {}) if isinstance(report.payload, dict) else {}
                await session.execute(
                    update(Report)
                    .where(Report.id == report.id)
                    .values(
                        delivered_at=datetime.now(UTC),
                        payload={
                            **report.payload,
                            "run_metadata": {**metadata, "report_delivered": True},
                        }
                    )
                )
                delivered += 1
                logger.info("report_delivered", report_id=str(report.id), tenant_id=str(report.tenant_id), channels=list(channels.keys()))
            else:
                logger.warning("report_delivery_partial", report_id=str(report.id), tenant_id=str(report.tenant_id))

        await session.commit()

    return delivered


# ──────────────────────────────────────────────
# Wrapper para arq cron
# ──────────────────────────────────────────────

async def deliver_completed_reports_row_wrapper(ctx: dict[str, Any]) -> int:
    """Wrapper para arq cron job."""
    return await deliver_completed_reports_row(ctx)

