# Feature — mes 4: Procesos + Servicios + Jobs v1 (monitorear + alertar + runner)

> Feature document ODD. Estado: **EN PLANIFICACIÓN** (exploración completada 2026-09-28).
>
> Referencia roadmap: `propuesta.md` línea 155 → **Mes 4 = Procesos + jobs**: servicios/procesos con auto-restart, job monitor cron/batch, detección de errores, canal WhatsApp.
>
> **Decisión de alcance del usuario (2026-09-28)**: V1 = **monitorear + alertar** (repos + CRUD + agent collectors de proceso/servicio + runner de jobs en el worker + extender alert engine a SERVICE/PROCESS/JOB). **Sin** auto-restart, **sin** WhatsApp, **sin** UI/dashboard (slices futuros).

---

## Objetivo

Que las entidades `Service`, `Process`, `Job`/`JobRun` — cuyas tablas existen desde la migración inicial del Mes 1 pero **no las usa nadie** — se monitoreen de verdad:

1. **API CRUD** para services/processes/jobs (+ lectura de job_runs) con scoping tenant.
2. **Job runner** en el worker arq: ejecuta los jobs definidos en DB según `schedule_cron`, registra `JobRun` (exit_code, output_tail, timeout) y **alerta si un job falla** (`alert_on_fail`).
3. **Agent collectors** de procesos y servicios: el agente reporta el estado real del host (sin ejecutar comandos — eso es el slice de auto-restart).
4. **Alert engine multi-entidad**: `evaluate_alerts` deja de saltear `EntityType.SERVICE/PROCESS/JOB` y evalúa contra lo reportado + `JobRun`; los deliveries reutilizan los canales ya verificados (email/webhook).

## Problema / Por qué

El schema del Mes 1 creó `processes`, `services`, `jobs`, `job_runs` **con RLS ya aplicada** y `EntityType` ya incluye `SERVICE|PROCESS|JOB|METRIC`, pero:
- No existen `ProcessRepository`/`ServiceRepository`/`JobRepository` ni routers.
- El worker de alertas **saltea todo lo que no es SERVER** (`workers/alerts.py:182-184`).
- No hay scheduler/runner: `schedule_cron`/`command`/`timeout_s` son columnas dormidas.
- El agente Go solo recolecta CPU/mem/disco/load; no toca procesos ni servicios.

El Mes 3 probó que un job cron caído a las 3 AM nadie lo ve hasta la mañana (propuesta línea 29). Este feature cierra esa brecha para el V1.

## Alcance (in/out)

**In (V1):**
- Repos + schemas + routers CRUD de `services`/`processes`/`jobs` (+ `job_runs` list) bajo `/api/v1/`.
- Runner de jobs: worker arq cron `job-run-1m` que ejecuta jobs `kind=cron` activos según `schedule_cron`, con `timeout_s`, registra `JobRun` (`running/success/failed/timeout`, `exit_code`, `output_tail` capado) y con `alert_on_fail` crea `Alert` + deliveries pending (mismo patrón que `evaluate_alerts`).
- Agente: collectors de procesos (gopsutil `process.Processes` + cmdline) y servicios (linux systemd / windows best-effort), que reportan estado al API vía ingest.
- API de ingest de estado de procesos/servicios (extender `MetricIngestPayload` o endpoint dedicado — decide el writer T4 con boundary explícito).
- Evaluación multi-entidad: `evaluate_alerts` evalúa `EntityType.SERVICE` (desired_state vs last_status/estado reportado), `PROCESS` (pattern regex + expected_count vs reportado), `JOB` (JobRun fallido/timeout reciente). La resolución de alertas (OPEN→RESOLVED) sigue la semántica actual.
- Tests API (HTTP, tenant-scoping) + tests Go (collectors) + gates existentes.

**Out (slices futuros):**
- **Auto-restart** de procesos/servicios/jobs (requiere ejecución en el host — privilegios, sudo/RunAs; el modelo `auto_restart` ya existe pero nadie lo usa; slice aparte).
- **Canal WhatsApp** (misma abstracción que email/webhook; requiere cuenta Business de Meta). Vision: fuera.
- **UI**: página `/servers/[id]` con pestañas de servicios/procesos/jobs, Recharts (fuera; el dashboard v0.1 queda como está).
- Ejecución remota de `command` de jobs sobre el server monitoreado (el runner V1 corre en el worker central; el `server_id` del job es referencia de contexto, no target de ejecución remota).

## Decisiones registradas

1. **Runner central, no agente-side** (usuario aprobó "incluir runner de jobs (Recomendado)"): el worker arq ejecuta los jobs definidos en DB. El agente NO ejecuta comandos en V1 — solo reporta estado. Ejecución side-effect local al worker contenedor, como un cron de la plataforma.
2. **Monitoreo de procesos/servicios por comparación contra config**: el agente no conoce las configs; reporta estado del host y el worker/API matchea contra `processes.pattern`+`expected_count` y `services.desired_state`.
3. **Alertas de job vía `alert_on_fail`** del modelo: el runner crea la alerta directamente cuando un run falla/timeouts, sin requerir una `AlertRule` adicional.
4. **Detección de procesos por observación, no por métrica numérica**: los estados se persisten como observaciones (columna/tabla o metric tags — decide writer T4), no forzando enum→float.
5. **TDD**: no hay cache `sdd-init` para el proyecto → modo ODD sin TDD estricto (convención de features previas); checks ordinarios por task: API `python -m mypy app` + `python -m ruff check app` + `python -m pytest -q` en `api/`; Go `go vet ./...` + `go test ./...` en `agent/`.
6. **Delivery**: forecast supera ~400 líneas autoradas → `ask-on-risk` por defecto; **chain strategy del proyecto: `stacked-to-main`** (confirmada en features previas). Si el forecast pide split, se acumula en PRs apilados.

## Checklist (tasks)

- [ ] **T1 — Repos + CRUD API** — `ProcessRepository`, `ServiceRepository`, `JobRepository`, `JobRunRepository` (read list) sobre `TenantScopedRepository`; schemas Pydantic; router `/api/v1/services`, `/api/v1/processes`, `/api/v1/jobs` (+ `/api/v1/jobs/{id}/runs`); registro en `main.py`; tests HTTP tenant-scoped (404 cross-tenant).
- [ ] **T2 — Job runner (worker)** — `api/app/workers/jobs.py`: carga jobs `kind=cron` `status=active`, parsea `schedule_cron` (cron library — elegir con boundary: croniter vs manual; verificar disponibilidad), ejecuta `command` con `asyncio.create_subprocess_shell` + `timeout_s`, registra `JobRun` (`running→success/failed/timeout`, `exit_code`, `output_tail` capado ~4KB), `alert_on_fail` → crea `Alert` + deliveries pending (reutilizando el patrón de `evaluate_alerts:127-135`). Cron `job-run-1m` en `WorkerSettings`. Tests unitarios (subprocess mock) + test de integración de alerta.
- [ ] **T3 — Agent collectors de proceso/servicio** — Go: nuevo collector que lista procesos (`gopsutil process.Processes()`, campos name+cmdline+state) y servicios (linux systemd vía gopsutil/host o exec `systemctl`, windows best-effort WMI/svc — documentar límites reales); nuevo tipo de payload en `internal/sender`; config para habilitar; `go vet` + `go test` limpios.
- [ ] **T4 — Ingest de estado de procesos/servicios (API)** — extender el pipeline de ingest (payload o endpoint dedicado) para recibir el reporte del agente y persistirlo (actualizar `services.last_status`/`last_checked_at` cuando exista config; observar procesos contra `pattern`/`expected_count`). Validación + tests HTTP.
- [ ] **T5 — Alert engine multi-entidad** — `evaluate_alerts`: evaluar `SERVICE` (desired_state vs estado reportado), `PROCESS` (pattern/expected_count vs observado), `JOB` (JobRun fallido/timeout reciente, si no ya alertado por runner); resolución OPEN→RESOLVED coherente. Tests por entidad + regresión SERVER intacta (suite completa verde).
- [ ] **T6 — E2E real (stack Docker)** — levantar stack; crear service/process/job + JobRun simulado o job real que falle; verificar: alerta creada, delivery `pending→sent` (webhook local o email), resolución al volver a estado sano; runner ejecutando un job cron simple. Documentar evidencia y cerrar.

## Acceptance Criteria

- [ ] API: CRUD de services/processes/jobs funciona con tenant-scoping; key de tenant A NO ve/edita entidades de tenant B (404).
- [ ] Un job cron fallido genera `JobRun(failed/timeout)` + alerta + delivery pending.
- [ ] Un proceso cuyo pattern deja de matchear (o cae bajo `expected_count`) genera alerta.
- [ ] Un servicio cuyo estado reportado difiere de `desired_state` genera alerta.
- [ ] Las alertas SERVICE/PROCESS/JOB se resuelven cuando el estado vuelve a lo esperado.
- [ ] `mypy app` = 0; `ruff check app` = 0; `pytest` verde (sin xpass nuevos) en `api/`.
- [ ] `go vet ./...` + `go test ./...` verdes en `agent/`.

## Checks aplicables

- API (workdir `api/`): `python -m mypy app`; `python -m ruff check app`; `python -m pytest -q`.
- Go (workdir `agent/`): `go vet ./...`; `go test ./...`.
- E2E: compose stack en ejecución (api/db/redis/web/worker); psql como `spsaas` (bypass RLS); tenant demo `1f350381-dea0-4f2f-8a29-7daab42225bf`.

## Progreso y evidencia

- (vacío — feature iniciado 2026-09-28 con doc de planificación)

## Rutas por task

| Task | Ruta | Trigger |
|------|------|---------|
| T1 | delegated (writer) | 2+ archivos no-triviales (repos+schemas+routers+tests) |
| T2 | delegated (writer) | worker nuevo + tests, runner con diseño de boundary |
| T3 | delegated (writer) | feature nuevo en Go |
| T4 | delegated (writer) | pipeline ingest + tests |
| T5 | delegated (writer) | worker alerts + tests multi-entidad |
| T6 | delegated según unidad E2E | escritura de evidencia + posible fix menor |

## Enlaces

- Roadmap: `propuesta.md` líneas 155 (mes 4), 77/79 (agente recolecta procesos/servicios/jobs cron, auto-restart local), 90 (job monitor).
- Feature delivery verificada: `odd/tasks/alert-delivery.md`, `odd/tasks/alert-web-ui.md` (canales email/webhook ya probados de punta a punta).
- Modelos existentes: `api/app/models/process.py`, `service.py`, `job.py`; worker actual `api/app/workers/alerts.py:162-224`.