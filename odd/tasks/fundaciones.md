# Feature: fundaciones — Bootstrap del monorepo SPSAAS (Mes 1)

## Objetivo
Inicializar el monorepo del SaaS SPSAAS con la base técnica del mes 1 del roadmap: estructura, Docker Compose, API FastAPI base, auth JWT, multi-tenant con RLS, modelos + migraciones, y CI.

## Problema / Por qué
El directorio está vacío (solo `propuesta.md`). Sin repositorio, estructura ni infra base no se puede construir nada del roadmap. El mes 1 entrega los cimientos: todo lo que sigue (agente, alertas, jobs, reportes) depende de esto.

## Alcance autorizado
- Bootstrap del monorepo según `propuesta.md` v1.0 (mes 1 del roadmap).
- Stack: FastAPI async + Pydantic v2 + SQLAlchemy 2.0 + Alembic; PostgreSQL 16 + TimescaleDB; Redis 7; arq (estructura de workers); Next.js 14 (placeholder); Docker obligatorio.
- **Entregado en `main`**: el bootstrap inicial fue rebaseado y sus commits viven en la historia de `main` (ver tabla de tareas con commits vivos). La branch `feature/fundaciones` original fue eliminada tras rebase.

## Fuera de alcance
- Lógica del agente (mes 2), alertas (mes 3), jobs (mes 4), reportes (mes 5), onboarding/beta (mes 6).

## TDD efectivo
- **Modo**: OFF (proyecto nuevo, sin configuración previa ni elección del usuario).
- **Runner**: n/a — se usan **checks funcionales**: pytest, build de imágenes, migraciones Alembic, smoke test de health/auth.

## Tareas

| ID | Tarea | Estado | Commit (vivo en `main`) |
|----|-------|--------|-------------------------|
| T1 | Inicializar repo: estructura monorepo, .gitignore, README raíz, docs/ | ✅ | `3114109` (antes `aad4100`, reescrito por rebase) |
| T2 | Docker Compose dev: postgres 16 + timescale, redis, api, workers, web | ✅ | `88dc827` (antes `1e07b54`, reescrito por rebase) |
| T2b | Placeholder web/ Next.js 14 (vacío rompía compose) | ✅ | `10eca33` (antes `b75dc96`, reescrito por rebase) |
| T3 | API FastAPI base: estructura app/, settings, logging, /healthz | ✅ | `a31b2da` (antes `de46283`, reescrito por rebase) |
| T4 | Modelos SQLAlchemy 2.0 async + migraciones Alembic (modelo de datos v1) + seed admin | ✅ | `8122027` + `a180dac` (antes `2373028` + `d97254e`, reescritos por rebase) |
| T5 | Auth JWT: register/login/refresh + API keys para agentes + RBAC por tenant | ✅ | `f761971` + `8b17b94` (antes `906c33c` + `f1a274a`, reescritos por rebase) |
| T6 | Multi-tenant: RLS Postgres + middleware de tenant + scoping de queries | ✅ | `f8555a5` (antes `bbbccd4`, reescrito por rebase) |
| T7 | Tests básicos: health, auth flow, aislamiento entre tenants | ✅ | `b93f7ed` (antes `09a6188`, reescrito por rebase) |
| T8 | CI GitHub Actions: lint + test | ✅ | `ac8a4bc` (antes `cd7ffa9`, reescrito por rebase) |
| T9 | Verificación integral contra Postgres real: compose build ✅, migraciones 0001-0004 aplicadas ✅, pytest 28 passed / 3 xfailed ✅ | ✅ | `9c607aa` + `c3d5f83` + fixes `62bc6cb`, `2e8e4fd`, `a88c9ac`, `df0529a`, `88fae5f`, `664baaf` (antes `9dd17ae`..`323ecb8`, reescritos por rebase) |

## Ruta elegida
- **Delegada** (writer trigger: 2+ archivos no triviales — bootstrap completo). Un solo writer `general`, con skills de commits por unidad de trabajo.
- El writer cortó su reporte dos veces (tareas grandes) → se dividió en **slices pequeños** por tarea. T1-T4 hechos (con corrección de soporte Alembic por el orquestador, commit `a180dac` en `main`, antes `d97254e` reescrito por rebase).
- Post-delegación: gate audit del orquestador + spot check por tarea.

## Criterios de aceptación
- `docker compose up` levanta postgres+redis+api (frontend/workers placeholder ok).
- Migraciones Alembic aplican sin error.
- `pytest` verde (health, auth, aislamiento tenant).
- README quickstart funcional.

## Decisiones vinculantes (de propuesta.md)
- Multi-tenant: shared schema + `tenant_id` + RLS (no schema-per-tenant en MVP).
- Métricas: hypertable Timescale (estructura lista; ingesta real en mes 2).
- Agente: Go, repo aparte dentro del monorepo (placeholder este mes).
- Workers: arq sobre Redis (estructura lista; lógica en meses 2-4).

## Progreso / Verificación
- **Verificado (real, contra Postgres)**: Docker instalado + compose build ✅ (api, worker, web). Migraciones Alembic 0001→0004 aplicadas contra Postgres real (`spsaas` y `spsaas_test`), head `20260921_0000_0004`. RLS + FORCE activo en 12 tablas de negocio + política SELECT en `tenants`; rol `app_user` NOINHERIT; `metrics` SIN RLS (limitación TimescaleDB 2.30: columnstore no soporta RLS; aislamiento cubierto por `TenantScopedRepository` en app). `pytest` 28 passed / 3 xfailed contra Postgres real.
- **Bugs reales destapados por Postgres (invisibles en SQLite)**:
  1. ENUMs: SQLAlchemy autogeneraba `name='plantype'` + valores UPPERCASE desde la clase Python; la migración creó `plan_type` con valores lowercase → todo INSERT fallaba con DatatypeMismatch. Fix: `SAEnum(Clase, name="...", values_callable=lambda e: [m.value for m in e])` en los 9 modelos con enums.
  2. Datetimes: `last_login_at` (users) y `last_used_at` (api_keys) se escribían con `datetime.now(UTC)` pero los modelos no declaraban `DateTime(timezone=True)` → asyncpg `DataError` en login. Fix: modelos + migración 0004 (alter `api_keys.last_used_at` varchar→timestamptz).
  3. `api/app/repositories/base.py`: método `list` sombreaba el builtin y rompía `list[dict]` en anotaciones → `from __future__ import annotations`.
  4. Tests: conftest ahora limpiar TRUNCATE condicional por test (solo Postgres) porque SQLite in-memory daba DB limpia gratis.
- **Riesgo mes 2**: los 3 xfailed son tests deliberados de `TenantScopedRepository` con SQLite in-memory propio (no usan la DB de test); quedan fuera del alcance. `next@14.2.16` vulnerable (todo #8, decidir bump). CI `docker-build` no migra: no habría detectado estos bugs — considerar paso de migración en CI.