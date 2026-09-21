# Feature: Deps refresh round 1 — low risk updates

- **Estado**: en progreso
- **Rama**: `feature/deps-refresh` (basada en feature/next16-web, sin main aún)
- **Última actualización**: 2026-09-21

## Objetivo

Actualizar dependencias de bajo riesgo en todo el monorepo (web/api/agent), verificando que nada se rompe. Ronda 1 = los que tienen menor probabilidad de romper; ronda 2 (futura) = los cambios mayores (tailwind 4, redis 8, pytest 9, pytest-asyncio 1.x, httpx 0.28, typescript NO se toca).

## Alcance Ronda 1

### web (npm)
- `postcss`: 8.4.49 → 8.5.28
- `@types/node`: 20.17.0 → 24.x (matchea Node 24 runtime)
- NO tocar: typescript (5.7.2 → 7.0.2 es rewrite en Go, muy fresco), tailwind (ronda 2), next/react/react-dom ya al día, eslint queda 9.x (eslint-config-next 16 acepta >=9)

### api (PyPI)
- `sqlalchemy==2.0.*` → 2.0.54
- `alembic==1.13.*` → 1.20.0
- `pydantic==2.9.*` → 2.13.5
- `pydantic-settings==2.5.*` → 2.15.0
- `asyncpg==0.29.*` → 0.31.0
- `uvicorn[standard]==0.32.*` → 0.53.0
- `arq==0.23.*` → 0.28.0
- `structlog==24.1.*` → 26.1.0
- `ruff==0.6.*` → 0.16.8 (dev)
- patches chicos: python-multipart→0.0.32, python-dotenv→1.2.3, email-validator→2.3.0, passlib[bcrypt]→1.7.4, python-jose[cryptography]→3.5.0
- NO tocar en ronda 1: httpx (0.27→0.28 breaking), redis (5→8 mayor), pytest (8→9 mayor), pytest-asyncio (0.23→1.x mayor), mypy (1.11→2 mayor), pytest-cov (5→7 mayor), fastapi (0.115→0.141 salto grande de 26 minors — evaluar en ronda 2 con cuidado)

### agent (Go)
- `go 1.23` → `go 1.27.1` (go.mod, sin dependencias reales aún)

## Fuera de alcance

- Ronda 2: tailwind 4, redis 8, pytest 9 + plugins, httpx 0.28, mypy 2, fastapi 0.141, typescript 7
- No crear PR/main aún

## Tareas

- [x] T1: Web — actualizar postcss + @types/node en web/package.json, regenerar pnpm-lock.yaml (commit: ac2a7f4)
- [x] T2: API — actualizar rangos en api/pyproject.toml (commit: b6f2654)
- [x] T3: Agent — go 1.23 → 1.27.1 en agent/go.mod (commit: ee156a7)
- [x] T4: Verificación: web build+lint, api pytest (28 passed / 3 xfailed contra Postgres), agent build (verificado)

## Progreso

- 2026-09-21: auditoría de versiones (npm view / PyPI / go.dev) → clasificación por riesgo; rama `feature/deps-refresh` creada.
- 2026-09-21: T1 web completado — postcss 8.5.28, @types/node 24.13.6, pnpm-lock.yaml regenerado, lint OK (1 warning conocido), build OK
- 2026-09-21: T2 api completado — 13 deps actualizadas, ruff 0.16.8, pytest 28 passed / 3 xfailed, docker build OK
- 2026-09-21: T3 agent completado — go 1.27.1, go build ./... OK (warning: no packages, esperado)
- 2026-09-21: T4 verificación final — git status limpio (4 archivos modificados + task doc), next build OK, pytest baseline OK

## Checks

- web: `pnpm lint` exitoso, `next build` exitoso (node:24)
- api: `pytest` → 28 passed / 3 xfailed contra Postgres real
- agent: `go build ./...` exitoso
- `git log` con commits work-unit convencionales