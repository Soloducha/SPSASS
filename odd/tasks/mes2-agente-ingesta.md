# Feature — mes 2: Agente Go v1 + Ingesta

> Feature document ODD. Estado: **en progreso** (autorizado por el usuario: "si esta tarea termino ok y necesitas el ok para avanzar con el mes 2, dale nomas!")
>
> Referencia roadmap: `propuesta.md` línea 153 → **Mes 2 = Agente + ingesta**: agente Go v1 (CPU/mem/disco/load), heartbeat, API de ingesta, rollups, dashboard v0.1.
> Plan detallado original: `agent/README.md` ("Mes 2 — Agente v1 + Ingesta").

---

## Objetivo

Mostrar **servidores monitoreados** (demostrable al cliente): agente Go que recolecta CPU/memoria/disco/load cada 30s y los sube por HTTPS a la API con API key; la API los persiste con scoping de tenant.

## Problema / Por qué

No existe telemetría todavía. El mes 1 dejó auth + multi-tenant + models (`Server`, `Metric`). El mes 2 conecta el primer productor de datos (agente) con la API, y deja la base para alertas y dashboard.

## Alcance (in/out)

**In (este feature):**
- Fix de inyección de tenant por dependencias (bloqueante, ver T1)
- API: `POST /api/v1/servers/register`, `POST /api/v1/servers/{id}/heartbeat`, `POST /api/v1/ingest/metrics`
- Agente Go: `cmd/agent`, `internal/collector`, `internal/sender`; recolección 30s; heartbeat; registro automático; push HTTPS con API key + retry/backoff; binario estático
- Tests de la API (HTTP) + tests del agente (Go) + gates CI

**Out (slices futuros del mes 2 o mes 3):**
- Rollups (agregación) — slice aparte
- Dashboard v0.1 (estado general + servidores) — slice aparte (web/)
- Alertas, servicios/procesos, jobs (mes 3+)

## Decisiones registradas

1. **Fix de tenant context (T1)**: el `TenantMiddleware` actual lee `request.state.tenant_id` en `dispatch()` ANTES de que las dependencias de auth corran (ellas corren dentro de `call_next`) → el contexto NUNCA se setea vía HTTP. Hoy no explota porque ningún endpoint HTTP usa `TenantScopedRepository` (que llama `require_tenant_context()` en `__init__`). Los endpoints nuevos SÍ lo van a usar → fix dependency-based: `set_tenant_context()` dentro de `get_current_user` y `get_tenant_from_api_key`. El middleware queda como fallback de `X-Tenant-ID` (testing/admin).
2. **Auth del agente (T2-T4)**: API key por tenant existente (`X-Api-Key: spsk_...` con `ApiKeyAuth`) — Opción A del mapeo (admin crea key vía UI; el agente la usa para registrarse y reportar). **NO** se crea key por servidor en este slice (requeriría modelo `server_id` en `ApiKey` — future).
3. **Registro de servidor (T2)**: upsert por `(tenant_id, hostname)`; si existe, actualiza `ip/os/agent_version` y marca `ONLINE`; si no, crea.
4. **TDD**: no hay cache `sdd-init` para el proyecto → modo ODD sin TDD estricto; checks ordinarios por slice (API: mypy/ruff/pytest; Go: go vet/go test).
5. **Delivery**: forecast supera ~400 líneas autoradas → `ask-on-risk` por defecto; el usuario pre-autorizó avanzar, así que se mantienen work-unit commits por task en la feature branch y al final del feature se propone el split de PRs. NO se pushea ni se crean PRs sin decisión del usuario.

## Checklist (tasks)

- [x] **T1 — Fix tenant context dependency-based** — `set_tenant_context()` en `get_current_user` y `get_tenant_from_api_key`; `SET LOCAL` solo en PostgreSQL (SQLite-safe). Verificado por tests HTTP + verifier independiente. Commit `3e41660`.
- [x] **T2 — Registro de servidor** — `POST /api/v1/servers/register` con upsert `(tenant_id, hostname)` (201 nuevo / 200 update mismo id). Tests HTTP. Commit `3e41660`.
- [x] **T3 — Heartbeat** — `POST /api/v1/servers/{id}/heartbeat` tenant-scoped (404 cross-tenant). Tests HTTP. Commit `3e41660`.
- [x] **T4 — Ingesta de métricas** — `POST /api/v1/ingest/metrics`, batch cap 1000, PK compuesta con microsecond offsets, `{received, inserted}`. Tests HTTP + persistencia verificada. Commit `3e41660`.
- [x] **T5 — Ruteo y model wiring** — `api/app/api/v1/` con `servers.py`, `ingest.py`, registrados en `main.py`. Commit `3e41660`.
- [ ] **T6 — Agente Go: estructura + collector** — `cmd/agent/main.go`, `internal/collector` con gopsutil v3: CPU %, mem, disco, load avg cada 30s; struct `MetricsBatch` que matchea el payload de la API.
- [ ] **T7 — Agente Go: sender** — `internal/sender`: registro (`/servers/register`), heartbeat periódico (`/servers/{id}/heartbeat`), push HTTPS (`/ingest/metrics`) con header `X-Api-Key`, retry/backoff, timeouts.
- [ ] **T8 — Agente Go: config + main** — configuración por env/flags (API URL, API key, intervalo, server id), logging, shutdown graceful, binario estático (`CGO_ENABLED=0 go build -ldflags="-s -w"`).
- [ ] **T9 — Agente Go: tests** — tests unitarios de collector (mock de gopsutil) y sender (httptest), `go vet` + `go test` limpios.

## Acceptance Criteria

- [ ] Un agente con API key válida puede registrarse, hacer heartbeat y enviar métricas a la API; las métricas se persisten con `tenant_id` del tenant de la key.
- [ ] Un API key de tenant A NO puede registrar/heartbeat/ingestar para un server de tenant B (404 o 403, sin fuga).
- [ ] `mypy app` = 0 errores; `ruff check app` = 0; `pytest` verde (sin xpass nuevos) en `api/`.
- [ ] `go vet ./...` y `go test ./...` verdes en `agent/`.
- [ ] El agente compila estático y reporta métricas contra una API local de desarrollo.

## Checks aplicables

- API (workdir `api/`): `mymy app` → `python -m mypy app`; lint → `python -m ruff check app` (y `ruff check .`); tests → `python -m pytest -q` (baseline: 28 passed, 1 xfailed, **2 xpass pre-existentes por bump pytest 8→9 — no tocarlos**, no son falla).
- Go (workdir `agent/`): `go vet ./...`, `go test ./...`.

## Progreso y evidencia

- **2026-09-22**: Feature iniciado. Mapeo de la API completado (general subagent): confirmado que `ApiKeyAuth` y flujo API key → tenant existen; encontrado y verificado bug de tenant context en middleware (ver Decisiones). Branch `feature/mes2-agent-ingesta` creada desde `main@cd422c1`.
- **2026-09-22**: T1-T5 completados (delegado writer + verifier independiente). Commit `3e41660` (11 files, +578/−4). Checks: mypy 0 (43 files), ruff 0, pytest 34 passed / 1 xfailed / 2 xpass baseline. Assess native: high_risk (hot_path auth) → verifier independiente exit pass, 0 bloqueantes. Findings menores documentados: RLS `SET LOCAL` queda como hardening postgres (la isolation primaria funciona por ContextVar), `get_current_user_optional` no setea tenant (no aplica hoy).
- Siguiente: T6-T9 (agente Go).

## Rutas por task

| Task | Ruta | Trigger |
|------|------|---------|
| T1-T5 | delegated (writer) | 2+ archivos no-triviales |
| T6-T9 | delegated (writer) | feature nuevo en Go |

## Enlaces

- Roadmap: `propuesta.md` línea 153 (mes 2) y línea 93 (roadmap)
- Plan detallado agente: `agent/README.md`
- Feature anterior (cerrado, sin mergear): `odd/tasks/review-followups.md`