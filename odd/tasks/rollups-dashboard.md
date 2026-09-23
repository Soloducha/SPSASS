# Feature — Rollups + Dashboard v0.1

> Feature document ODD. Estado: **completado T1–T6** (autorizado por el usuario: "dale nomás" tras indexar CodeGraph).
>
> Referencia roadmap: `propuesta.md` línea 153 → **Mes 2 = Agente + ingesta**: rollups + dashboard v0.1 (estado general, servidores). Línea 88 (workers): "Ingesta y agregación de métricas (rollups 1m → 5m → 1h → 1d)". Línea 98-99 (frontend): dashboard con estado general, servidores; Recharts + SSE se difieren fuera de v0.1.

---

## Objetivo

Cerrar el mes 2: worker de agregación de métricas (rollups) y dashboard v0.1 que muestra **estado general + servidores** con sus últimas métricas.

## Problema / Por qué

La ingesta ya persiste métricas crudas (`metrics` hypertable). Para el dashboard v0.1 y el futuro histórico (mes 5, reportes) se necesitan agregaciones por período (1m/5m/1h/1d) que reduzcan el volumen y aceleren lecturas. Hoy `workers/main.py` está vacío (`functions = []`, `cron_jobs = []`) y la web es un placeholder.

## Alcance (in/out)

**In (este feature):**
- Migración `0005` + modelo `MetricRollup` (tabla normal de agregación, PK compuesta)
- Servicio de agregación idempotente (bucket por período: count/avg/min/max/last)
- Worker arq: cron jobs 1m/5m/1h/1d registrados en `WorkerSettings` + fix del entrypoint `main()`
- Endpoint `GET /api/v1/dashboard/overview` (JWT, tenant-scoped): totals por estado + servidores con últimas métricas
- Dashboard web v0.1 en `web/src/app/page.tsx` (SSR server component, totals + tabla de servidores)
- Tests: rollups (servicio) + dashboard (HTTP, con cross-tenant)

**Out (slices futuros):**
- Cadena de rollups real (5m desde 1m, 1h desde 5m...) — este slice agrega cada período directo de raw; la cascada es optimización futura
- Recharts / gráficos históricos — mes 5 (reportes), línea 98-99 propuesta
- SSE realtime — mes 5+
- Login web — el dashboard SSR usa token de servicio via env `SPSAAS_DASHBOARD_TOKEN` como bridge temporal hasta que exista login (mes 3+)
- Alertas, servicios/procesos/jobs en dashboard (mes 3-4)

## Decisiones registradas

1. **RLS en `metric_rollups`: NO** — igual que `metrics` (excluida en 0003 por hypertable; rollups se excluye porque el worker agrega MULTI-tenante y las políticas `TO app_user` + FORCE lo romperían sin contexto de tenant). El aislamiento de LECTURA queda en capa de aplicación (`TenantScopedRepository` / queries con `tenant_id` forzado). Documentado en la migración.
2. **Tabla normal, no hypertable** — para v0.1 no justifica Timescale (pocas filas por run); si el volumen lo pide, migración futura `create_hypertable`. La PK compuesta ya está diseñada para upsert idempotente.
3. **Agregación en Python, no SQL** — portable entre SQLite (tests) y Postgres (prod): se leen las raw del window y se agrupan en memoria. Volumen v0.1 bajo. El floor de bucket se computa con epoch floor en Python.
4. **Upsert con `session.merge()`** — portable SQLite/Postgres; `on_conflict_do_update` es dialect-specific.
5. **Periodo se agrega directo de raw `metrics`** (no en cascada) — correcto y simple; window por run: 1m→15 min, 5m→2 h, 1h→48 h, 1d→14 días (cubre restarts sin backfill gigante).
6. **Dashboard lee últimas métricas de RAW, no de rollups** — siempre fresco aunque el worker no haya corrido; los rollups quedan para histórico. Query: `MAX(ts)` group by (server_id, type) + join.
7. **Auth dashboard: JWT (CurrentUser), nunca API key** — es UI humana. Los agentes no ven el dashboard.
8. **Dashboard web v0.1 = SSR server component** — server-side fetch al API con token de servicio `SPSAAS_DASHBOARD_TOKEN` (env), bridge temporal hasta login web. Sin client components, sin Recharts.
9. **TDD**: sin cache `sdd-init` → ODD sin TDD estricto; checks ordinarios (mypy/ruff/pytest, web lint/build).
10. **Delivery**: forecast ~620 líneas → supera ~400 → sliced PRs (stacked-to-main, como mes 2). Slices: A = API completa (rollups + worker + dashboard endpoint + tests), B = web dashboard. NO se pushea ni crean PRs sin decisión del usuario.

## Checklist (tasks)

- [x] **T1 — Modelo `MetricRollup` + migración 0005** — tabla `metric_rollups` (period String, bucket_start tz, tenant_id, server_id, type, count, avg, min, max, last; PK (period, bucket_start, server_id, type)); índices (tenant_id, period, bucket_start) y (server_id, bucket_start). Sin RLS (ver Decisión 1). Commit `b266eab`.
- [x] **T2 — Servicio de rollups** — `app/workers/rollups.py` (ruta real: no existe `app/services/`): `compute_rollups(session, period)` + helpers `bucketize(ts, period_s)` y `as_utc(dt)`; lee raw del window, agrupa por (bucket, tenant, server, type), calcula count/avg/min/max/last, `session.merge()` idempotente. Solo buckets COMPLETOS. Windows: 1m→15min, 5m→2h, 1h→48h, 1d→14d. 12 tests unit en `tests/test_rollups.py` (bucketize + agregación, idempotencia, re-run actualiza, por tipo, aislamiento tenant/server, bucket en curso excluido, ventana por período). Commit `11d206a`.
- [x] **T3 — Worker arq** — `app/workers/main.py`: 4 `CronJob` con `cron()` (1m cada minuto, 5m cada 5 min, 1h cada hora, 1d medianoche) + wrappers por período (arq 0.28 sin kwargs en cron) + `main()` arranca `Worker` real vía `create_worker`. `WorkerSettings` tipado contra `WorkerSettingsBase`. Commit `2d07d17`.
- [x] **T4 — Endpoint dashboard overview** — `app/api/v1/dashboard.py`: `GET /api/v1/dashboard/overview` (CurrentUser JWT): totals por ServerStatus + servers con latest_metrics vía MAX(ts) group-by + join (portable). Schemas Pydantic `DashboardOverview`/`ServerOverviewItem`. Router registrado en app. 4 tests HTTP (401, empty, última observación gana, cross-tenant) en `tests/test_dashboard.py`. Commit `9a59df4`.
- [x] **T5 — Dashboard web v0.1** — reemplazar placeholder de `web/src/app/page.tsx`: server component que fetchea el endpoint con `SPSAAS_DASHBOARD_TOKEN`, renderiza totals + tabla de servidores (status badge, hostname, ip, últimas métricas). Estados: loading/error/empty. `next.config` ya tiene standalone. Commits `d21f76e` (page SSR, `dynamic = force-dynamic`, barras por métrica, UI español) + `c5077f6` (config module `web/src/lib/config.ts`, fix .gitignore `lib/` Python → negación `!web/src/lib/`; env leídos en request time). lint + build verdes, ruta `ƒ` dinámica.
- [x] **T6 — Tests** — absorbido en T1–T5 (modo ODD: tests junto al código). `tests/test_rollups.py`: unit del bucketize + agregación (count/avg/min/max/last), idempotencia (2 runs → 1 fila), re-run actualiza valores, por tipo, multi-tenant separado, bucket incompleto excluido, ventana por período (12 tests). `tests/test_dashboard.py`: HTTP 401 sin token, empty tenant, última observación gana, cross-tenant server de A no aparece en B (4 tests). Total suite: 50 passed / 1 xfailed / 2 xpass. Commits `11d206a`, `9a59df4`.

## Acceptance Criteria

- [x] `mypy app` = 0 errores; `ruff check app` = 0; `pytest` verde (baseline 34 passed / 1 xfailed / 2 xpass sin cambios) en `api/`.
- [x] `web`: `pnpm lint` y `pnpm build` verdes (evidencia local).
- [x] `GET /api/v1/dashboard/overview` devuelve totals + servidores con últimas métricas, scoped al tenant del JWT; cross-tenant sin fuga.
- [x] Correr rollups dos veces no duplica filas (idempotente).
- [x] Worker registra 4 cron jobs y arranca (evidencia de import/config, no se exige Redis corriendo).

## Checks aplicables

- API (workdir `api/`): `python -m mypy app`; `python -m ruff check app`; `python -m pytest -q` (baseline: 34 passed, 1 xfailed, 2 xpass pre-existentes — no tocarlos).
- Web (workdir `web/`): `pnpm lint`; `pnpm build`.

## Progreso y evidencia

- **2026-09-23**: Feature iniciado. CódigoGraph indexado (73 files, 800 nodos) por pedido del usuario. Mapeo completado con codegraph_explore: modelos `Metric`/`Server`/`Base` (PK compuesta, mixins), `TenantScopedRepository` (scoping obligatorio), `get_db_session`/`get_db_session_without_tenant`, workers/main.py vacío, migración RLS 0003 (metrics excluida), migración 0001 (hypertable), compose (worker service presente), dependencias arq 0.28.0. Branch `feat/rollups-dashboard` creada desde `main` (PR #5 housekeeping queda OUT de este slice).
- **2026-09-23**: T1–T5 completados (ver checklist). Gates API: `mypy app` 0 (46 files), `ruff check app` 0, `pytest` 50 passed / 1 xfailed / 2 xpass. Gates web: `pnpm lint` 0, `pnpm build` OK (ruta `/` dinámica `ƒ`).
- **2026-09-23**: RDD assess del rango (base `c5f89aa`, 16 paths, 1187 líneas): risk **medium** (`executable_change` .gitignore), `review_due: true` (`slice_budget_reached`) → preflight STATUS devolvió `stop(run rdd_disabled)`. RDD está off clone-local (decisión explícita previa del usuario, ver `odd/tasks/quality-gate.md`); sin review nativo, delivery por política ordinaria (regla user-owned: no reactivar por mi cuenta).
- Siguiente: decisión del usuario sobre delivery (PR A = API `b266eab..9a59df4`, PR B = Web `d21f76e+c5077f6`, stacked-to-main). Todo el código ya está commiteado y verificado.

## Rutas por task

| Task | Ruta | Trigger |
|------|------|---------|
| T1 | direct inline | 2 archivos (modelo + migración), ya entendidos |
| T2 | direct inline | 1 archivo nuevo + tests, diseño resuelto |
| T3 | direct inline | 1 archivo, mecánico |
| T4 | direct inline | endpoint + schemas + repo query |
| T5 | delegated/writer direct | web page nueva no trivial (node_modules local disponible? verificar) |
| T6 | direct inline | tests con patrones existentes |

## Enlaces

- Roadmap: `propuesta.md` líneas 88, 98-99, 153-159
- Feature previo cerrado: `odd/tasks/mes2-agente-ingesta.md` (rollups + dashboard declarados "slice aparte")
- PR #5 housekeeping (abierto, OUT): https://github.com/Soloducha/SPSASS/pull/5