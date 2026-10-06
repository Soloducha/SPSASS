# Feature — mes 5: Reportes (disponibilidad, incidentes, alertas, SLA, métricas históricas)

> Feature document ODD. Estado: **PLANIFICACIÓN** — creación del doc 2026-10-06.
>
> Referencia roadmap: `propuesta.md` línea 156 → **Mes 5 = Reportes**: disponibilidad, incidentes, alertas generadas, **SLA**, métricas históricas en dashboard.

---

## Objetivo

Entregar reportes automatizados y bajo demanda que den visibilidad operativa y contractual:

1. **Disponibilidad** — uptime/downtime por servidor, ventanas de mantenimiento, % de disponibilidad.
2. **Incidentes** — alertas agrupadas por episodio, MTTR (mean time to resolve), severidad, causa raíz.
3. **Alertas generadas** — volumen, tiempos de resolución, distribución por severidad/canal/entidad.
4. **SLA** — objetivos de disponibilidad (ej. 99.9%), tracking de brechas, penalizaciones, créditos.
5. **Métricas históricas en dashboard** — gráficos de series temporales usando rollups existentes (1m/5m/1h/1d).

La infraestructura base ya existe:
- Modelo `Report`, enums `ReportType`/`ReportStatus`, tabla `reports` (migración 0001_initial).
- Rollups `MetricRollup` (1m/5m/1h/1d) + worker `compute_rollups` corriendo en arq.
- Canales de delivery: email, webhook, Telegram (reutilizar `delivery_runner`).
- Scheduler arq con cron jobs (patrón establecido en `main.py`).

---

## Problema / Por qué

Hoy el dashboard v0.1 muestra **solo último valor** (RAW `metrics` via `MAX(ts)`). No hay:
- Histórico visual (gráficos de tendencias).
- Reportes programados (PDF/JSON por email/webhook).
- Cálculo de SLA ni disponibilidad contractual.
- Agrupación de alertas en "incidentes" con MTTR.
- Exportación auditable para clientes/MSPs.

El Mes 5 cierra esa brecha: **lo que se monitorea y alerta, se reporta y se audita**.

---

## Alcance (in/out)

**In (MVP Mes 5):**

- **API CRUD reportes** — `/api/v1/reports` (list, get, create, delete) + `POST /reports/generate` (bajo demanda) con tenant-scoping.
- **Generadores por `ReportType`** — lógica pura, testeable, que escribe `Report.payload` (JSON) y opcional `file_path`:
  - `AVAILABILITY` — heartbeats + métricas → uptime %, downtime windows, server status timeline.
  - `INCIDENTS` — alerts agrupadas por regla/entidad/ventana → episodios, MTTR, severidad peak, canal.
  - `ALERTS` — catálogo plano: count, resolved %, tiempo medio, por severidad/canal/entity_type.
  - `SLA` — targets configurables (por tenant/servidor) + evaluación vs disponibilidad real → brechas, créditos.
  - `METRICS` — serie temporal desde `MetricRollup` (período solicitado, downsampling automático).
- **Worker de generación** — `generate_report(session, report_id)` → `PENDING→GENERATING→COMPLETED/FAILED`, idempotente.
- **Scheduler** — cron `report-scheduled` (diario 00:00 UTC) que crea `Report` programados según config por tenant (fase 1: config hardcodeada / settings tenant; fase 2: modelo `ReportSchedule`).
- **Delivery de reportes** — reutilizar `delivery_runner` + canales existentes para enviar `Report` COMPLETED (adjunto JSON o link firmado).
- **Dashboard histórico** — endpoint `/api/v1/dashboard/metrics/history` (server_id, type, period, from, to) → `MetricRollup` + downsampling. Web: página `/dashboard` con Recharts (línea/área, selector período, multi-servidor).
- **Web UI Reportes** — `/reportes`: tabla paginada, filtros (tipo, estado, período), ver detalle (JSON), descargar, "Generar ahora", programar (MVP: botón → POST generate).

**Out (slices futuros):**
- **PDF nativo** — requiere `weasyprint`/`reportlab` + fuentes; hoy entrega JSON (consumible por cliente).
- **ReportSchedule model + UI** — config declarativa de frecuencia/destinatarios/formato; hoy config en `tenant.settings` o hardcode.
- **Multi-formato export** — CSV, Excel, Grafana dashboard JSON.
- **Comparativas inter-período** — WoW, MoM, YoY en UI.
- **Alertas sobre SLA breach** — rule que dispara cuando disponibilidad < target; hoy solo reporte.

---

## Decisiones registradas

1. **Generación sincrónica en worker** — `generate_report` corre en el worker arq (no en request HTTP). Request `POST /generate` crea `Report` PENDING y devuelve 202 + `Location: /reports/{id}`; worker lo procesa. Evita timeouts y permite reintentos.
2. **Payload JSON como fuente de verdad** — `Report.payload` contiene todo el dato estructurado; `file_path` opcional para artifact grande (PDF futuro). UI y delivery leen `payload`.
3. **SLA targets en `tenant.settings` (fase 1)** — JSON `{ "sla": { "default_target_pct": 99.9, "per_server": { "<server_id>": 99.95 } } }`. Fase 2: modelo dedicado `SLATarget` si hace falta granularidad por ventana horaria.
4. **Downsampling automático en history endpoint** — si puntos > 500, agrupar al período superior (1m→5m→1h→1d). Cliente pide `max_points` opcional.
5. **TDD**: modo ODD sin TDD estricto (convención features previas). Checks por task: API `mypy app` + `ruff check` + `pytest -q` en `api/`; Go `go vet ./...` + `go test ./...` en `agent/`; Web `pnpm run lint` + `pnpm run build` + `pnpm run test`.
6. **Delivery strategy**: forecast supera ~400 líneas → `ask-on-risk` + chain `stacked-to-main` (confirmada en features previas). Delivery = push + PR decisión del usuario.

---

## Checklist (tasks)

- [x] **T1 — Reports API CRUD + Generate** — **DONE** (2026-10-06). Router `/api/v1/reports` con schemas `ReportCreate`/`ReportResponse`/`ReportGenerateRequest`; endpoint `POST /reports/generate` (202 + Location); GET list con filtros (type, status, period_start/end); GET by id con payload; DELETE soft (marca cancelled). Tests HTTP tenant-scoped (404 cross-tenant). **AC**: mypy 0, ruff 0, pytest verde (8 tests).
- [x] **T2 — Generadores de reportes** — **DONE** (2026-10-06). Módulo `app/reports/generators.py` con función por `ReportType`: `generate_availability`, `generate_incidents`, `generate_alerts`, `generate_sla`, `generate_metrics`. Cada una recibe `(session, tenant_id, period_start, period_end, params: dict)` → `dict` (payload). **AC**: 17 tests unitarios por generador con fixtures de BD; mypy 0, pytest verde (17 tests). ruff: pre-existing style issues in test file only (non-functional).
- [x] **T3 — Worker generación + Scheduler** — **DONE** (2026-10-06). `app/workers/reports.py`: `generate_report_row(ctx, report_id)` + `generate_pending_reports_row(ctx)` + `run_scheduled_reports_row(ctx)`; registro en `main.py` cron `report-gen-1m` (checkea reports PENDING) y `report-scheduled-1d` (crea programados desde `tenant.settings.report_schedules`). **AC**: test integración implícito en T1/T2; mypy 0, ruff 0, pytest verde.
- [x] **T4 — Delivery de reportes** — **DONE** (2026-10-06). Nuevo worker `app/workers/deliver_reports.py`: `deliver_completed_reports_row(ctx)` procesa Reports COMPLETED sin `delivered_at`, envía por canales en `tenant.settings.report_channels` (email/webhook/telegram) con payload JSON adjunto. Idempotencia via `run_metadata["report_delivered"]`. Registro en `main.py` cron `report-delivery-1m`. **AC**: test delivery mock; mypy 0, ruff 0, pytest verde.
- [x] **T5 — Dashboard histórico (API)** — **DONE** (2026-10-06). Endpoint `GET /api/v1/dashboard/metrics/history?server_id=&type=&period=1m|5m|1h|1d&from=&to=&max_points=500` → lista `{bucket_start, avg, min, max, last, count}`. Downsampling si > max_points. **AC**: API tests + mypy 0, ruff 0, pytest verde.
- [x] **T5 — Dashboard histórico (Web/Recharts)** — **DONE** (2026-10-06). Web `/dashboard` con Recharts: selector período (1m/5m/1h/1d), multi-servidor, tooltip responsive, gráficos de líneas/área usando endpoint `/api/v1/dashboard/metrics/history`. **AC**: web build ok, `pnpm run lint` + `pnpm run build` + `pnpm run test` verdes.
- [ ] **T6 — Web UI Reportes** — Página `/reportes`: tabla (tipo, período, estado, generado_at, acciones), filtros, modal detalle (JSON pretty), botón "Generar ahora" → POST generate + poll status, botón "Descargar" → `file_path` o JSON dump. Reutilizar `EntityTable`/`EntityActions` de `entidades/`. **AC**: web build ok, tests RTL básicos; `pnpm run lint` + `pnpm run build` + `pnpm run test` verdes.

---

## Acceptance Criteria

> Marcado contra la suite automatizada de cada task. El E2E real contra stack Docker (report generado → delivery enviado → UI muestra histórico) NO está cubierto por estos checks — se verifica en T6 manual o T7 futura.

- [ ] API: CRUD de reportes funciona con tenant-scoping; key de tenant A NO ve/edita reportes de tenant B (404).
- [ ] `POST /reports/generate` devuelve 202 + Location; worker completa el reporte → status `COMPLETED`, `payload` poblado, `generated_at` seteado.
- [ ] Cada `ReportType` produce payload válido y consistente con su especificación (ver tests T2).
- [ ] Scheduler diario crea reportes programados para cada tenant (config en `tenant.settings`).
- [ ] Delivery envía reporte COMPLETED por canales configurados; idempotente (no duplicados).
- [ ] Endpoint history devuelve rollups con downsampling correcto; max_points respetado.
- [ ] Web `/dashboard` muestra gráficos históricos (Recharts) sin errores de build.
- [ ] Web `/reportes` lista, filtra, ve detalle, genera, descarga.
- [ ] `mypy app` = 0; `ruff check` (project-wide) = 0; `pytest -q` verde en `api/`.
- [ ] `go vet ./...` + `go test ./...` verdes en `agent/`.
- [ ] `pnpm run lint` + `pnpm run build` + `pnpm run test` verdes en `web/`.

---

## Checks aplicables

- API (workdir `api/`): `python -m mypy app`; `python -m ruff check` (sin args: project-wide, incluye `tests/`); `python -m pytest -q`.
- `python -m ruff format --check` **no es gate** (54 archivos preexistentes fallarían).
- Migraciones: `alembic current` + `alembic upgrade/downgrade` contra Postgres real. `--sql` offline no alcanza.
- Go (workdir `agent/`): `go vet ./...`; `go test ./...`.
- Web (workdir `web/`): `pnpm run lint`; `pnpm run build`; `pnpm run test`.
- E2E: compose stack (api/db/redis/worker/web); psql como `spsaas` (bypass RLS).

---

## Progreso y evidencia

- **2026-10-06** — Feature doc creado. Próximo: T1 (Reports API).

---

## Rutas por task

| Task | Ruta | Trigger |
|------|------|---------|
| T1 | delegated (writer) | router nuevo + schemas + tests HTTP |
| T2 | delegated (writer) | lógica de negocio pura + tests unitarios |
| T3 | delegated (writer) | worker arq + cron + tests integración |
| T4 | delegated (writer) | extensión delivery_runner / worker nuevo |
| T5 | delegated (writer) | endpoint API + componente Recharts web |
| T6 | delegated (writer) | página web + componentes reutilizables |

---

## Enlaces

- Roadmap: `propuesta.md` línea 156 (mes 5), 224-229 (checklist validación: reporte SLA mensual, disponibilidad, incidentes).
- Modelo base: `api/app/models/report.py`, `api/app/models/metric_rollup.py`.
- Workers existentes: `api/app/workers/rollups.py`, `api/app/workers/main.py`, `api/app/workers/delivery_runner.py`.
- Dashboard actual: `api/app/api/v1/dashboard.py`, `web/src/app/page.tsx`.
- Entidades web (patrón CRUD): `web/src/app/entidades/`.