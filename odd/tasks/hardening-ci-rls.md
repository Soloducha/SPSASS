# Feature: hardening-ci-rls — Dockerfiles unificados + RLS real contra Postgres

> Slice de cierre del mes 2: `Dockerfile.worker`/targets web pendientes (TODO #3) + RLS hardening postgres documentado en `mes2-agente-ingesta.md` y `rollups-dashboard.md`.
> Estado base: `main` `b614fcf` (demo bajado, working tree limpio).

## Objetivo

1. **Unificar Dockerfiles de API/worker**: hoy `api/Dockerfile` y `api/Dockerfile.worker` son duplicados casi idénticos que difieren solo en CMD. Alinearlos con el patrón multi-stage de `web/Dockerfile`: un solo `api/Dockerfile` con stages `base`/`api`/`worker` y targets, actualizar `docker-compose.yml` y eliminar `api/Dockerfile.worker`.
2. **Activar RLS de verdad contra Postgres**: hoy la app se conecta como `spsaas` (superuser), y los superusers bypass RLS aunque exista `FORCE ROW LEVEL SECURITY` → la capa RLS de la migración 0003 es decorativa. Hardening: cuando una sesión tiene contexto de tenant (PostgreSQL), ejecutar `SET LOCAL ROLE app_user` + el ya existente `SET LOCAL app.tenant_id`, y agregar los grants faltantes para `app_user` (tablas `metrics` y `metric_rollups` no los tienen, y no hay default privileges).

## Problema / por qué

- `Dockerfile.worker` duplica 27 líneas del `Dockerfile` de API; cualquier cambio de deps/build tiene que hacerse dos veces (ya causó divergencia en el pasado).
- RLS "habilitada" pero inerte: el rol de conexión es superuser → `USING (tenant_id = current_tenant_id())` jamás filtra. La única defensa multi-tenant real hoy es el scoping por código (`TenantScopedRepository` + queries con `tenant_id` forzado). El objetivo es que RLS sea la red de seguridad real que respalde esa capa.
- `SET LOCAL ROLE` duración = transacción actual → revierte solo en commit/rollback; sin fuga entre requests del pool (a diferencia de `SET ROLE` global).
- `login`/`register` NO tienen contexto de tenant (buscan user por email global) → NO deben cambiar de rol; quedan como superuser de bootstrap, como hoy.

## Scope

- **SÍ**: unificar `api/Dockerfile` (stages/targets), actualizar `docker-compose.yml` (api → target api, worker → target worker), borrar `api/Dockerfile.worker`.
- **SÍ**: migración nueva `0006` con grants de `app_user` sobre `metrics` + `metric_rollups` + `ALTER DEFAULT PRIVILEGES` para tablas futuras.
- **SÍ**: `session.py`: en `get_db_session`, cuando hay tenant context y dialect no-sqlite → `SET LOCAL ROLE app_user` además del `SET LOCAL app.tenant_id`.
- **SÍ**: test RLS contra Postgres real (skip si SQLite) que demuestre que `app_user` sin tenant no ve filas.
- **SÍ**: verificación end-to-end con el stack docker real (migraciones + register/login/dashboard/ingest + rollups worker).
- **NO**: cambiar auth pública (login/register) a rol no-superuser.
- **NO**: RLS en `metrics`/`metric_rollups` (limitación TimescaleDB documentada en 0003/0005 — RLS en columna no soportada por hypertable comprimida).
- **NO**: CI: el job `docker-build` ya corre `docker compose build --parallel` y valida los targets; pytest sigue en SQLite (el test RLS queda skipif, ejecutable local/CI futuro con Postgres).

## Restricciones y decisiones

1. **`SET LOCAL ROLE app_user`** (no `SET ROLE`): scope transacción, sin necesidad de reset manual en pool. Requiere superuser conectado (spsaas) pueda asumir el rol → sí, superuser puede `SET ROLE` a cualquier rol; y el rol `app_user` ya existe (0003).
2. **Grants**: `metrics` insert (ingesta agentes) y select (dashboard); `metric_rollups` (worker escribe multi-tenant como superuser via `get_db_session_without_tenant`, pero app puede leer vía repos futuro). `ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user` para que migraciones futuras no rompan la app.
3. **No tocar `get_db_session_without_tenant`** (worker/seed) → sigue superuser multi-tenant.
4. **Patrón Dockerfile**: `base` (sistema + deps + usuario) → `api` (CMD uvicorn) y `worker` (CMD python -m app.workers.main) como targets finales que copian el código desde un stage intermedio (cache eficiente).
5. Forecast líneas ≈ 200-250 → 1 PR único (bajo 400 sin excepción). Delivery: política ordinaria del repo (RDD off por decisión del usuario; commits de trabajo + PR).

## Checklist de tareas

- [x] **T1 — Unificar Dockerfiles** — `api/Dockerfile` multi-stage (base → api/worker targets), compose `target: api` / `target: worker`, borrado `api/Dockerfile.worker` (commit `72d55dd` + `9d0b1ff`). `docker compose build api worker` OK; `docker compose config` resuelve targets.
- [x] **T2 — Migración 0006 grants app_user** — `20260923_2000_0006_rls_app_user_grants.py`: GRANT SELECT/INSERT/UPDATE/DELETE sobre `metrics` + `metric_rollups`, ALTER DEFAULT PRIVILEGES (tablas `arwd`, secuencias `USAGE/SELECT`); downgrade revoca. Aplicada contra Postgres real (`alembic upgrade head` → `20260923_2000_0006 (head)`); verificado `\dp`: grants presentes en metrics/metric_rollups/servers + default ACL `app_user=arwd/spsaas`.
- [x] **T3 — session.py SET LOCAL ROLE app_user** — En `get_db_session` con tenant context y Postgres: `SET LOCAL ROLE app_user` + `SELECT set_config('app.tenant_id', :tid, true)`. **Fix latente destapado**: la forma anterior `SET LOCAL app.tenant_id = :tid` jamás funcionó — Postgres rechaza bind params en SET (syntax error $1). `set_config(..., true)` es equivalente a SET LOCAL y acepta binds. `get_db_session_without_tenant` sigue superuser multi-tenant (worker/seed). Commit `d6e2a00`.
- [x] **T4 — Test RLS Postgres** — `api/tests/test_rls.py`: ve rige que app_user sin tenant no ve filas, con tenant B no ve las de A, con tenant A ve las propias; skip si dialect != postgresql o migración 0003 ausente. Verde contra Postgres real; skippeado en SQLite (CI). Commit `d6e2a00`.
- [x] **T5 — E2E stack real** — `docker compose up -d api worker web` con migraciones aplicadas (head 0006). Script E2E: healthz 200 → register (bootstrap superuser) → login (búsqueda email global) → me (tenant ctx + rol app_user) → API key → server register (X-API-Key → tenant ctx → app_user) → **ingest 2 métricas inserted=2 (INSERT en metrics como app_user, grant 0006)** → dashboard overview (SELECT servers+metrics). Logs API: 0 errores permission/unhandled. Worker rollups 1m corriendo sin fallos.
- [x] **T6 — Docs + cierre** — Feature doc con evidencia; commits work-unit: `72d55dd` (Dockerfile), `9d0b1ff` (borrado worker), `d6e2a00` (RLS activo). Pendiente: PR único + mem_save + este doc.

## Progreso y evidencia

- **2026-09-23**: T1-T5 completados contra Postgres real. Gates: `mypy app` 0 (46 files), `ruff check app tests/` 0, `pytest` 51 passed / 1 xfailed / 2 xpass (Postgres real; SQLite equivalente en CI por skipif del test RLS). Hallazgo: el SET LOCAL con bind param de session.py nunca había funcionado en producción (latente desde 0003); el hardening lo destapó y se corrigió con set_config.
- **Delivery**: RDD off (decisión previa usuario) → política ordinaria del repo. Forecast líneas ≈ 250 → 1 PR único sin excepción de tamaño.

## Criterios de aceptación

- [x] `docker compose build api worker web` OK; `api/Dockerfile.worker` ya no existe en tree.
- [x] Migración 0006 aplicada idempotente (head); grants verificados en information_schema + pg_default_acl.
- [x] `pytest` completo verde contra Postgres real (51 passed / 1 xfailed / 2 xpass) + test RLS demuestra aislamiento real.
- [x] E2E: register/login/me/api-key/server/ingest/dashboard funcionan como app_user superuser bootstrap; 0 errores de permisos; worker rollups OK.
- [ ] PR único abierto (sigue policy ordinaria: decisión del usuario).