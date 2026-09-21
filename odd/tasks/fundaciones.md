# Feature: fundaciones — Bootstrap del monorepo SPSAAS (Mes 1)

## Objetivo
Inicializar el monorepo del SaaS SPSAAS con la base técnica del mes 1 del roadmap: estructura, Docker Compose, API FastAPI base, auth JWT, multi-tenant con RLS, modelos + migraciones, y CI.

## Problema / Por qué
El directorio está vacío (solo `propuesta.md`). Sin repositorio, estructura ni infra base no se puede construir nada del roadmap. El mes 1 entrega los cimientos: todo lo que sigue (agente, alertas, jobs, reportes) depende de esto.

## Alcance autorizado
- Bootstrap del monorepo según `propuesta.md` v1.0 (mes 1 del roadmap).
- Stack: FastAPI async + Pydantic v2 + SQLAlchemy 2.0 + Alembic; PostgreSQL 16 + TimescaleDB; Redis 7; arq (estructura de workers); Next.js 14 (placeholder); Docker obligatorio.
- Branch `feature/fundaciones` con commits por unidad de trabajo. Sin push, sin PR aún.

## Fuera de alcance
- Lógica del agente (mes 2), alertas (mes 3), jobs (mes 4), reportes (mes 5), onboarding/beta (mes 6).

## TDD efectivo
- **Modo**: OFF (proyecto nuevo, sin configuración previa ni elección del usuario).
- **Runner**: n/a — se usan **checks funcionales**: pytest, build de imágenes, migraciones Alembic, smoke test de health/auth.

## Tareas

| ID | Tarea | Estado | Commit |
|----|-------|--------|--------|
| T1 | Inicializar repo: estructura monorepo, .gitignore, README raíz, docs/ | ✅ | `aad4100` |
| T2 | Docker Compose dev: postgres 16 + timescale, redis, api, workers, web | ✅ | `1e07b54` |
| T2b | Placeholder web/ Next.js 14 (vacío rompía compose) | ✅ | `b75dc96` |
| T3 | API FastAPI base: estructura app/, settings, logging, /healthz | ✅ | `de46283` |
| T4 | Modelos SQLAlchemy 2.0 async + migraciones Alembic (modelo de datos v1) + seed admin | ✅ | `2373028` (+ `d97254e` soporte Alembic) |
| T5 | Auth JWT: register/login/refresh + API keys para agentes + RBAC por tenant | ✅ | `906c33c` (+ `f1a274a` tenant-bound refresh) |
| T6 | Multi-tenant: RLS Postgres + middleware de tenant + scoping de queries | ✅ | `bbbccd4` |
| T7 | Tests básicos: health, auth flow, aislamiento entre tenants | ✅ | `09a6188` |
| T8 | CI GitHub Actions: lint + test | ✅ | `cd7ffa9` |
| T9 | Verificación integral contra Postgres real: compose build ✅, migraciones 0001-0004 aplicadas ✅, pytest 28 passed / 3 xfailed ✅ | ✅ | `9dd17ae` ˑ `9f8186c` ˑ `02e0743` ˑ `e81a5b4` ˑ `0998257` ˑ `7c023af` ˑ `323ecb8` |

## Ruta elegida
- **Delegada** (writer trigger: 2+ archivos no triviales — bootstrap completo). Un solo writer `general`, con skills de commits por unidad de trabajo.
- El writer cortó su reporte dos veces (tareas grandes) → se dividió en **slices pequeños** por tarea. T1-T4 hechos (con corrección de soporte Alembic por el orquestador: `d97254e`).
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