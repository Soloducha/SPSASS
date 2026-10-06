"""Worker de generación de reportes programados y bajo demanda.

Dos jobs:
- generate_report_row: procesa Reports con status=PENDING → GENERATING → COMPLETED/FAILED
- run_scheduled_reports_row: crea Reports programados según tenant.settings.report_schedules
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select, update

from app.core.logging import get_logger
from app.db.session import get_db_session_without_tenant
from app.models.report import Report, ReportStatus, ReportType
from app.models.tenant import Tenant
from app.reports.generators import GENERATORS, generate_report

logger = get_logger(__name__)


# ──────────────────────────────────────────────
# Job: procesar reports pendientes (bajo demanda)
# ──────────────────────────────────────────────

async def generate_report_row(ctx: dict[str, Any], report_id: UUID) -> int:
    """Procesa un Report específico por ID.

    Transición: PENDING → GENERATING → COMPLETED | FAILED
    Retorna 1 si procesó, 0 si no encontrado o ya procesado.
    """
    async with get_db_session_without_tenant() as session:
        # Obtener reporte con lock para evitar doble procesamiento
        stmt = select(Report).where(
            Report.id == report_id,
            Report.status == ReportStatus.PENDING,
        ).with_for_update(skip_locked=True)
        result = await session.execute(stmt)
        report = result.scalar_one_or_none()

        if not report:
            logger.debug("report_not_found_or_not_pending", report_id=str(report_id))
            return 0

        # Marcar GENERATING
        await session.execute(
            update(Report)
            .where(Report.id == report_id)
            .values(status=ReportStatus.GENERATING)
        )
        await session.flush()

        try:
            # Generar payload
            params = report.payload if isinstance(report.payload, dict) else {}
            payload = await generate_report(
                session=session,
                tenant_id=report.tenant_id,
                report_type=report.type.value,
                period_start=report.period_start,
                period_end=report.period_end,
                params=params,
            )
        except Exception:
            # Marcar FAILED con error
            await session.execute(
                update(Report)
                .where(Report.id == report_id)
                .values(
                    status=ReportStatus.FAILED,
                    error="generation error",
                    generated_at=datetime.now(UTC),
                )
            )
            logger.exception("report_failed", report_id=str(report_id))
            return 1  # Contamos como procesado (para no reintentar indefinido)

        # Guardar resultado
        await session.execute(
            update(Report)
            .where(Report.id == report_id)
            .values(
                status=ReportStatus.COMPLETED,
                payload=payload,
                generated_at=datetime.now(UTC),
                error=None,
            )
        )
        logger.info("report_completed", report_id=str(report_id), tenant_id=str(report.tenant_id))
        return 1


async def generate_pending_reports_row(ctx: dict[str, Any]) -> int:
    """Procesa TODOS los reports PENDING (corre cada minuto).

    Retorna cantidad de reports procesados.
    """
    async with get_db_session_without_tenant() as session:
        stmt = select(Report.id).where(Report.status == ReportStatus.PENDING).limit(100)
        result = await session.execute(stmt)
        report_ids = [row[0] for row in result.all()]

    processed = 0
    for report_id in report_ids:
        processed += await generate_report_row(ctx, report_id)

    if processed:
        logger.info("batch_reports_processed", count=processed)
    return processed


# ──────────────────────────────────────────────
# Job: crear reports programados (diario)
# ──────────────────────────────────────────────

async def run_scheduled_reports_row(ctx: dict[str, Any]) -> int:
    """Crea Reports programados según tenant.settings.report_schedules.

    Formato esperado en tenant.settings:
    {
        "report_schedules": [
            {"type": "availability", "period": "daily", "params": {}},
            {"type": "sla", "period": "weekly", "params": {"target_pct": 99.95}},
            {"type": "metrics", "period": "daily", "params": {"server_id": "uuid", "type": "cpu_usage", "period": "1h"}}
        ]
    }

    Solo crea si no existe ya un reporte del mismo tipo+período para ese tenant hoy.
    """
    created = 0
    now = datetime.now(UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)

    async with get_db_session_without_tenant() as session:
        # Obtener todos los tenants con report_schedules
        stmt = select(Tenant.id, Tenant.settings).where(Tenant.settings.op("->")("report_schedules").is_not(None))
        result = await session.execute(stmt)

        for tenant_id, settings in result.all():
            schedules = settings.get("report_schedules", [])
            if not schedules:
                continue

            for sched in schedules:
                rtype_str = sched.get("type")
                period_str = sched.get("period", "daily")
                params = sched.get("params", {})

                # Validar tipo
                if rtype_str not in GENERATORS:
                    logger.warning("invalid_report_type_in_schedule", tenant_id=str(tenant_id), type=rtype_str)
                    continue

                # Calcular período según period_str
                if period_str == "daily":
                    period_start = today_start
                    period_end = today_end
                elif period_str == "weekly":
                    # Semana actual (lunes a domingo)
                    days_since_monday = now.weekday()
                    period_start = today_start - timedelta(days=days_since_monday)
                    period_end = period_start + timedelta(days=6, hours=23, minutes=59, seconds=59)
                elif period_str == "monthly":
                    # Mes actual
                    period_start = today_start.replace(day=1)
                    # Primer día del mes siguiente - 1 segundo
                    next_month = period_start.replace(day=28) + timedelta(days=4)
                    period_end = next_month.replace(day=1) - timedelta(seconds=1)
                else:
                    logger.warning("invalid_period_in_schedule", tenant_id=str(tenant_id), period=period_str)
                    continue

                # Verificar si ya existe reporte para este tenant+tipo+período
                exists_stmt = select(Report.id).where(
                    Report.tenant_id == tenant_id,
                    Report.type == ReportType(rtype_str),
                    Report.period_start == period_start,
                    Report.period_end == period_end,
                    Report.status.in_([ReportStatus.PENDING, ReportStatus.GENERATING, ReportStatus.COMPLETED]),
                )
                exists_result = await session.execute(exists_stmt)
                if exists_result.scalar_one_or_none():
                    logger.debug("scheduled_report_already_exists", tenant_id=str(tenant_id), type=rtype_str)
                    continue

                # Crear reporte PENDING
                report = Report(
                    tenant_id=tenant_id,
                    type=ReportType(rtype_str),
                    period_start=period_start,
                    period_end=period_end,
                    payload=params,
                    status=ReportStatus.PENDING,
                )
                session.add(report)
                created += 1
                logger.info("scheduled_report_created", tenant_id=str(tenant_id), type=rtype_str, period=period_str)

        await session.commit()

    if created:
        logger.info("scheduled_reports_created", count=created)
    return created


# ──────────────────────────────────────────────
# Helper para compatibilidad: procesar por report_id
# ──────────────────────────────────────────────

async def process_report_by_id(report_id: UUID) -> bool:
    """Helper standalone para tests/scripts: procesa un reporte por ID.

    Retorna True si procesó, False si no encontrado.
    """
    async with get_db_session_without_tenant() as session:
        stmt = select(Report).where(Report.id == report_id)
        result = await session.execute(stmt)
        report = result.scalar_one_or_none()

        if not report:
            return False

        if report.status != ReportStatus.PENDING:
            return False

        await session.execute(
            update(Report).where(Report.id == report_id).values(status=ReportStatus.GENERATING)
        )
        await session.flush()

        try:
            params = report.payload if isinstance(report.payload, dict) else {}
            payload = await generate_report(
                session=session,
                tenant_id=report.tenant_id,
                report_type=report.type.value,
                period_start=report.period_start,
                period_end=report.period_end,
                params=params,
            )
        except Exception:
            await session.execute(
                update(Report)
                .where(Report.id == report_id)
                .values(
                    status=ReportStatus.FAILED,
                    error="generation error",
                    generated_at=datetime.now(UTC),
                )
            )
            return True

        await session.execute(
            update(Report)
            .where(Report.id == report_id)
            .values(
                status=ReportStatus.COMPLETED,
                payload=payload,
                generated_at=datetime.now(UTC),
                error=None,
            )
        )
        return True
