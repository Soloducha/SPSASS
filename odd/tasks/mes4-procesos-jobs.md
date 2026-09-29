# Feature — mes 4: Procesos + Servicios + Jobs v1 (monitorear + alertar + runner)

> Feature document ODD. Estado: **EN IMPLEMENTACIÓN** — T1–T5 cerradas y verificadas (2026-09-28); T6 (E2E real) pendiente. El branch `feat/mes4-01-crud` acumula 5.964 líneas autoradas y **todavía no fue pusheado ni entregado**.
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
3. **Alertas de job vía `alert_on_fail`** del modelo: el runner crea la alerta directamente cuando un run falla/timeouts, sin requerir una `AlertRule` adicional. **Implica migración**: `Alert.rule_id` pasa a `nullable=True` (migration `0007`), porque `Alert.rule_id` hoy es NOT NULL FK y una alerta de job no proviene de una regla configurable. `value_at_trigger` se setea con `exit_code` (0.0 en timeout). Verificar que `deliver_alerts`/`delivery_runner` no asume `rule` al despachar.
4. **Detección de procesos por observación, no por métrica numérica**: los estados se persisten como observaciones (columna/tabla o metric tags — decide writer T4), no forzando enum→float. **Decisión T4 (orquestador)**: el agente reporta inventario (name/cmdline/state) y el matching contra configs es **server-side**. Migración `0008`: `processes.last_count INT NOT NULL DEFAULT 0` + `processes.last_checked_at`; `services` ya tiene `last_status`/`last_checked_at`. El endpoint `/ingest/entities` matchea el inventario contra las configs del tenant+server y actualiza esos campos; NO persiste el inventario completo (slice futuro si hace falta).
5. **TDD**: no hay cache `sdd-init` para el proyecto → modo ODD sin TDD estricto (convención de features previas); checks ordinarios por task: API `python -m mypy app` + `python -m ruff check app` + `python -m pytest -q` en `api/`; Go `go vet ./...` + `go test ./...` en `agent/`.
6. **Delivery**: forecast supera ~400 líneas autoradas → `ask-on-risk` por defecto; **chain strategy del proyecto: `stacked-to-main`** (confirmada en features previas). Si el forecast pide split, se acumula en PRs apilados.

## Checklist (tasks)

- [x] **T1 — Repos + CRUD API** — `ProcessRepository`, `ServiceRepository`, `JobRepository`, `JobRunRepository` (read list) sobre `TenantScopedRepository`; schemas Pydantic; router `/api/v1/services`, `/api/v1/processes`, `/api/v1/jobs` (+ `/api/v1/jobs/{id}/runs`); registro en `main.py`; tests HTTP tenant-scoped (404 cross-tenant). **DONE** en `ae5c66e` (branch `feat/mes4-01-crud`): 7 archivos nuevos + 5 modificados; mypy 0 errores, ruff limpio, 132 passed (14 tests nuevos). Gotchas para fases siguientes: JobRun NO tiene TimestampMixin (solo started/finished); cascade jobs→job_runs; `status` de JobRun es string libre (`running|success|failed|timeout`); schema valida `schedule_cron` requerido para kind=cron.
- [x] **T2 — Job runner (worker)** — `api/app/workers/jobs.py`: carga jobs `kind=cron` `status=active`, parsea `schedule_cron` (croniter — decidido), ejecuta `command` con `asyncio.create_subprocess_shell` + `timeout_s`, registra `JobRun` (`running→success/failed/timeout`, `exit_code`, `output_tail` capado ~4KB), `alert_on_fail` → crea `Alert` + deliveries pending. Cron `job-run-1m` en `WorkerSettings`. **DONE** en `a86f048` + fix alertas `b6464e2`: módulo `workers/jobs.py` (due-detection `croniter(expr, now-1min).get_next <= now`, salta si hay JobRun `running` previo, timeout con kill, alerta directa con `rule_id=None` tras migración `0007_alert_rule_id_nullable` que hace `alerts.rule_id` nullable, `value_at_trigger=float(exit_code or 0.0)`, deliveries desde `job.config.channels` con idempotencia `run_metadata["alerted"]`); dep `croniter==6.2.4`; mypy 0, ruff limpio, 153 passed. Migración validada offline (`alembic upgrade head --sql`) — **pendiente de aplicar en DB real**.
- [x] **T3 — Agent collectors de proceso/servicio** — Go: nuevo collector que lista procesos (`gopsutil process.Processes()`, campos name+cmdline+state) y servicios (linux systemd vía gopsutil/host o exec `systemctl`, windows best-effort WMI/svc — documentar límites reales); nuevo tipo de payload en `internal/sender`; config para habilitar; `go vet` + `go test` limpios. **DONE** en `6a324cc` + fix `264ac20`: `agent/internal/collector/entities.go` + `gopsutil_entities.go` (procesos vía gopsutil; servicios systemd real vía `systemctl` en linux, best-effort WMI `sc` en windows); payload `EntityStatePayload` en `internal/sender`; go vet/build/test verdes. **Nota**: el agente reporta inventario (name/cmdline/state), NO matchea configs — el matching es server-side (T4).
- [x] **T4 — Ingest de estado de procesos/servicios (API)** — endpoint dedicado `POST /api/v1/ingest/entities` (decidido: no extender `MetricIngestPayload` porque el shape difiere). Schemas `EntityProcessItem`/`EntityServiceItem`/`EntityIngestPayload`/`EntitiesIngestResponse`; auth ApiKeyAuth + tenant-scoped. Services: match por nombre case-insensitive contra configs del tenant+server → `last_status` (estado inválido → `UNKNOWN`) + `last_checked_at`. Processes: regex `pattern` contra name/cmdline del inventario → `last_count` + `last_checked_at`; regex inválido → warning + skip sin crash. `matched_*` = configs actualizadas (no procesos reportados). Migración `0008` (proceses.`last_count` NOT NULL DEFAULT 0 + `last_checked_at`). **DONE** en `46b5bd1` (branch `feat/mes4-01-crud`): 5 archivos (ingest.py +162, schemas.py +38, process.py +4, migración 0008, tests nuevos); mypy 0, ruff limpio, 163 passed (10 tests T4 nuevos). **Gotchas**: (1) `expire_on_commit=False` en `api/app/db/session.py` → re-verificar BD desde la misma sesión da objetos stale del identity map; usar `db_session.expire_all()` antes de verificar. (2) structlog con `PrintLoggerFactory` escribe a stdout, NO al módulo logging → `caplog` nunca captura warnings; asertar comportamiento, no el log. (3) **Fix aplicado**: `down_revision` de migración `0008` usaba el nombre de archivo completo (`20260928_0000_0007_alert_rule_id_nullable`) pero Alembic resuelve por revision id (`20260928_0000_0007`) → `KeyError` en `alembic upgrade head --sql`; corregido y validado offline.
- [x] **T5 — Alert engine multi-entidad** — `evaluate_alerts`: evaluar `SERVICE` (desired_state vs estado reportado), `PROCESS` (pattern/expected_count vs observado), `JOB` (JobRun fallido/timeout reciente, si no ya alertado por runner); resolución OPEN→RESOLVED coherente. Tests por entidad + regresión SERVER intacta (suite completa verde). **DONE** en `2ae0689` (branch `feat/mes4-01-crud`): `api/app/workers/alerts.py` extendido con `_evaluate_service_rules`/`_evaluate_process_rules`/`_evaluate_job_rules` (SERVICE: `last_status != desired_state`, ignora never-ingested/UNKNOWN; PROCESS: `last_count < expected_count`, ignora never-ingested; JOB: último JobRun fallido/timeout dentro de `duration_s` del rule, salta runs ya alertados por runner vía `run_metadata["alerted"]`); `entity_id=None` → todas las entidades del tenant; cross-tenant safe. **Decisión de diseño**: columna `Alert.target_entity_id` nullable (migración `0009_alert_target_entity`) para idempotencia/resolución unambiguous por target dentro de un rule (server_id+message colisiona con servicios del mismo nombre en distintos servers). Resolución: SERVICE/PROCESS al volver sano; JOB al run success o al fallo ya runner-alertado. `metric`/`operator`/`threshold` se aceptan pero NO se usan para no-SERVER (decisión usuario: **solo estado derivado**). 23 tests nuevos en `api/tests/test_alerts_entities.py`; mypy 0, ruff limpio, 186 passed (2 SMTP ambientales conocidos); migración `0009` validada offline (`alembic upgrade head --sql`). **Pendiente de aplicar en DB real** junto con `0007`+`0008` (T6).
- [ ] **T6 — E2E real (stack Docker)** — levantar stack; crear service/process/job + JobRun simulado o job real que falle; verificar: alerta creada, delivery `pending→sent` (webhook local o email), resolución al volver a estado sano; runner ejecutando un job cron simple. Documentar evidencia y cerrar.

## Acceptance Criteria

> Marcado contra la suite automatizada de cada task. El **E2E real contra el stack Docker (delivery `pending→sent`, runner en vivo, migraciones aplicadas) NO está cubierto por estos checks** — es T6.

- [x] API: CRUD de services/processes/jobs funciona con tenant-scoping; key de tenant A NO ve/edita entidades de tenant B (404). — `api/tests/test_processes_services_jobs.py`, 14 tests (T1 `ae5c66e`).
- [x] Un job cron fallido genera `JobRun(failed/timeout)` + alerta + delivery pending. — `api/tests/test_worker_jobs.py`, 21 tests (T2 `a86f048` + fix `b6464e2`); delivery *pending* verificado en test, el envío real es T6.
- [x] Un proceso cuyo pattern deja de matchear (o cae bajo `expected_count`) genera alerta. — `api/tests/test_alerts_entities.py` (T5 `2ae0689`).
- [x] Un servicio cuyo estado reportado difiere de `desired_state` genera alerta. — `api/tests/test_alerts_entities.py` (T5 `2ae0689`).
- [x] Las alertas SERVICE/PROCESS/JOB se resuelven cuando el estado vuelve a lo esperado. — `api/tests/test_alerts_entities.py`, incluye resolución JOB por fallo ya runner-alertado (T5 `2ae0689`).
- [x] `mypy app` = 0; `ruff check app` = 0; `pytest` verde (sin xpass nuevos) en `api/`. — última corrida observada en T5 `2ae0689`: mypy 0, ruff limpio, **186 passed** + 2 fallos SMTP ambientales conocidos (`.env`).
- [x] `go vet ./...` + `go test ./...` verdes en `agent/`. — última corrida observada en T3 `264ac20`.
- [ ] **E2E real**: migraciones `0007`+`0008`+`0009` aplicadas en DB real; alerta + delivery `pending→sent`; resolución en vivo; runner ejecutando un job cron. → **T6**.

## Checks aplicables

- API (workdir `api/`): `python -m mypy app`; `python -m ruff check app`; `python -m pytest -q`.
- Go (workdir `agent/`): `go vet ./...`; `go test ./...`.
- E2E: compose stack en ejecución (api/db/redis/web/worker); psql como `spsaas` (bypass RLS); tenant demo `1f350381-dea0-4f2f-8a29-7daab42225bf`.

## Progreso y evidencia

- **2026-09-28** — T1 `ae5c66e`, T2 `a86f048`+`b6464e2`, T3 `6a324cc`+`264ac20`, T4 `46b5bd1` (branch `feat/mes4-01-crud`).
- **T4 — nota de verificación**: 10 tests nuevos en `api/tests/test_ingest_entities.py`; 163 passed (2 SMTP ambientales conocidos por `.env`). Migración `0008` validada offline tras corregir `down_revision`. Pendiente aplicar `0007`+`0008` en DB real (T6).
- **2026-09-28** — T5 `2ae0689` (branch `feat/mes4-01-crud`): alert engine multi-entidad SERVICE/PROCESS/JOB + migración `0009` (`Alert.target_entity_id`). 23 tests nuevos en `api/tests/test_alerts_entities.py`; 186 passed, 2 SMTP ambientales conocidos; mypy 0, ruff limpio; migraciones `0007`+`0008`+`0009` validadas offline, pendientes de aplicar en DB real (T6).
- **Siguiente**: T6 — E2E real (stack Docker): aplicar migraciones, verificar alertas SERVICE/PROCESS/JOB + delivery + resolución de punta a punta.
- **2026-09-29** — Merge de `main` al branch (`9e3e2e3`). `main` estaba **más adelantado que el branch** en este doc (`0735d58` cerró T3+T4 y `13964a2` cerró T5 directo en `main`, mientras el branch seguía con la copia de `ccfbe77`); conflicto resuelto tomando la versión de `main`, que subsume el `cff789b` del branch. Sin ese merge, "sincronizar el doc" habría duplicado trabajo ya hecho y generado conflicto en el PR.

## Delivery, slices y RDD

**Estrategia**: `ask-on-risk` + chain `stacked-to-main` (decisión 6, confirmada en features previas). Delivery sigue política ordinaria del repo: push y PR son decisiones del usuario.

**Forecast por work-unit (inserciones + borrados, generado excluido)** — medido sobre `main..feat/mes4-01-crud`:

| Slice | Commits | Líneas | vs. presupuesto 400 |
|-------|---------|--------|--------------------|
| T1 CRUD | `ae5c66e` | 1.742 | excede ×4.4 |
| T2 job runner | `a86f048`, `b6464e2` | 881 | excede ×2.2 |
| T3 collectors | `6a324cc`, `264ac20` | 956 | excede ×2.4 |
| T4 ingest | `46b5bd1` | 806 | excede ×2.0 |
| T5 alert engine | `2ae0689` | 1.571 | excede ×3.9 |
| T6 E2E | pendiente | — | — |
| (docs) | `cff789b` | 8 | ok |

**Hallazgo honesto**: con esta granularidad **ningún slice entra en el presupuesto de 400 líneas**. El grueso son tests legítimos (`test_processes_services_jobs.py` = 982 líneas, `test_alerts_entities.py` = 942). Opciones reales, sin recortes cosméticos: (a) `size:exception` por slice, (b) sub-slicing de los tests, o (c) un PR único con excepción. **Decisión pendiente del usuario** — el documento no la define.

### Registro RDD (receipt-driven development)

- Estado: **on** (decidido por `global`; el off previo estaba en `clone_local` y se limpió el 2026-09-29 con `review mode enable --scope clone`).
- `gentle-ai review assess` mide el rango **base → HEAD**, no un commit suelto. Con HEAD en el merge, cada base devuelve la cola restante (5.899 → 4.157 → … → 1.586). Por lo tanto **la assessment de un slice solo es válida cuando el tip de ese slice ES el HEAD**; no se puede evaluar retroactivamente el branch acumulado.
- Ningún work-unit de esta feature fue revisado nativamente todavía: se antecedentieron a la activación de RDD.
- T6 agregará un work-unit más; ese sí va por el flujo normal assess → review nativo.
- El branch acumulado **no es candidato válido** (el candidato es un work-unit commit o un PR slice, nunca el branch entero), aunque `assess --base-ref main` devuelva `high_risk`.


| Task | Ruta | Trigger |
|------|------|---------|
| T1 | delegated (writer) | 2+ archivos no-triviales (repos+schemas+routers+tests) |
| T2 | delegated (writer) | worker nuevo + tests, runner con diseño de boundary. **Decisión: croniter** (dependencia nueva — no existe cron lib hoy) |
| T3 | delegated (writer) | feature nuevo en Go |
| T4 | delegated (writer) | pipeline ingest + tests |
| T5 | delegated (writer) | worker alerts + tests multi-entidad |
| T6 | delegated según unidad E2E | escritura de evidencia + posible fix menor |

## Enlaces

- Roadmap: `propuesta.md` líneas 155 (mes 4), 77/79 (agente recolecta procesos/servicios/jobs cron, auto-restart local), 90 (job monitor).
- Feature delivery verificada: `odd/tasks/alert-delivery.md`, `odd/tasks/alert-web-ui.md` (canales email/webhook ya probados de punta a punta).
- Modelos existentes: `api/app/models/process.py`, `service.py`, `job.py`; worker actual `api/app/workers/alerts.py:162-224`.