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
| T3 | API FastAPI base: estructura app/, settings, logging, /healthz | ✅ | `de46283` |
| T4 | Modelos SQLAlchemy 2.0 async + migraciones Alembic (modelo de datos v1) + seed admin | ✅ | `2373028` (+ `d97254e` soporte Alembic) |
| T5 | Auth JWT: register/login/refresh + API keys para agentes + RBAC por tenant | 🔲 | — |
| T6 | Multi-tenant: RLS Postgres + middleware de tenant + scoping de queries | 🔲 | — |
| T7 | Tests básicos: health, auth flow, aislamiento entre tenants | 🔲 | — |
| T8 | CI GitHub Actions: lint + test | 🔲 | — |
| T9 | Verificación integral: compose build + up, migraciones aplicadas, pytest verde, smoke test | 🔲 | — |

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
- (pendiente de delegación)