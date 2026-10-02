# Feature — Auto-restart de Servicios y Procesos

> Feature document ODD. Estado: **PLANIFICADO** — Prioridad 1 del Mes 4 (tras V1 monitorear+alertar).

Referencia roadmap: `propuesta.md` línea 155 → **Mes 4 = Procesos + jobs**: auto-restart de servicios/procesos.

---

## Objetivo

Cuando una alerta **SERVICE** o **PROCESS** se dispara y la entidad tiene `auto_restart=true`, el sistema debe:
1. Intentar reiniciar la entidad localmente en el agente
2. Registrar el intento (éxito/fallo) para auditoría
3. Respetar backoff y política configurable (max retries, cooldown)

---

## Problema / Por qué

Hoy `Service.auto_restart` y `Process.auto_restart` existen en el modelo (Migración 1) pero **nadie los usa**. El operador recibe la alerta pero debe hacer SSH al server y reiniciar a mano. El auto-restart cierra ese gap: el agente ejecuta el restart automáticamente.

---

## Alcance (in/out)

**In (V1 auto-restart):**
- **Nueva tabla** `agent_commands` (o usar `server.config` + polling) para comandos pendientes por server
- **Endpoint API** `POST /api/v1/servers/{server_id}/restart` (auth: JWT user, tenant-scoped) → encola comando
- **Agente**: polling periódico (cada 30s junto a métricas) → `GET /api/v1/servers/{server_id}/commands` → ejecuta restart
- **Ejecución real**:
  - Service: `systemctl restart <name>` (Linux) / `sc stop + sc start` (Windows best-effort)
  - Process: `pkill -f <pattern>` + esperar + verificar (no hay "start" estándar; se delega a systemd/process manager externo)
- **Worker alerts**: al crear alerta SERVICE/PROCESS con `auto_restart=true` → llama endpoint RESTART
- **Idempotencia**: no reintentar restart mientras hay uno `pending`/`running` para misma entidad
- **Backoff**: configurable por entidad (`config.restart_backoff_s`, `config.max_restart_attempts`)

**Out (futuro):**
- Restart de jobs (distinto: el runner ya re-ejecuta jobs fallidos vía `auto_restart` en el job model)
- Web UI para ver historial de restarts
- Notificación de restart (canal delivery)

---

## Decisiones de diseño

1. **Polling, no push**: El agente ya hace polling cada 30s (métricas + entidades). Añadir un GET a `/commands` es trivial y no requiere HTTP server en el agente.
2. **Comando en API, ejecución en agente**: La API solo encola; el agente ejecuta con privilegios locales. Así el agente no necesita credenciales de API para actuar.
3. **Tabla `agent_commands`** (nueva migración):
   ```sql
   CREATE TABLE agent_commands (
       id UUID PRIMARY KEY,
       tenant_id UUID NOT NULL,
       server_id UUID NOT NULL REFERENCES servers(id),
       entity_type VARCHAR(20) NOT NULL,  -- 'service' | 'process'
       entity_name VARCHAR(255) NOT NULL,
       command VARCHAR(500),              -- override opcional; si null, default por tipo
       status VARCHAR(20) NOT NULL DEFAULT 'pending', -- pending, running, success, failed
       attempts INT NOT NULL DEFAULT 0,
       max_attempts INT NOT NULL DEFAULT 3,
       backoff_s INT NOT NULL DEFAULT 60,
       scheduled_at TIMESTAMPTZ NOT NULL DEFAULT now(),
       started_at TIMESTAMPTZ,
       finished_at TIMESTAMPTZ,
       exit_code INT,
       output_tail TEXT,
       created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
       updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
   );
   CREATE INDEX ON agent_commands (server_id, status);
   ```
4. **Worker trigger**: En `_create_alert_and_deliveries` (o post-commit), si `rule.auto_restart` (nuevo campo en AlertRule para SERVICE/PROCESS) → encolar comando.
   - **Alternativa**: Leer `auto_restart` del modelo Service/Process directamente en el worker (evita duplicar en AlertRule). Es más limpio.

---

## Tasks

### T1 — Migración + Modelo + Repo `agent_commands`
- Migración Alembic `0011_agent_commands.py`
- Modelo `AgentCommand` en `api/app/models/agent_command.py`
- Repo `AgentCommandRepository` en `api/app/repositories/agent_command.py`
- Tests unitarios de repo

### T2 — API Endpoints (servers.py)
- `POST /api/v1/servers/{server_id}/restart` (user JWT, tenant-scoped)
  - Body: `{entity_type: "service|process", entity_name: string, command?: string}`
  - Valida que entidad existe y pertenece al tenant+server
  - Crea `AgentCommand` con status=pending
- `GET /api/v1/servers/{server_id}/commands` (API key auth, para agente)
  - Devuelve comandos `pending` para ese server, ordenados por `scheduled_at`
  - Marca los devueltos como `running` + `started_at=now`
- `PATCH /api/v1/agent-commands/{command_id}/result` (API key auth, para agente)
  - Body: `{status: "success|failed", exit_code?: int, output_tail?: string}`
  - Actualiza comando con resultado

### T3 — Agente: Polling + Ejecución
- `agent/internal/sender`: `GetCommands(serverID)` + `ReportCommandResult(commandID, result)`
- `agent/internal/collector`: `ExecuteRestart(command)` → `systemctl restart` / `pkill` + verificación
- `agent/cmd/agent/main.go`: en loop de métricas, cada 30s llamar `GetCommands` y ejecutar
- Tests Go: mock de comandos, verificación de ejecución

### T4 — Worker Alerts: Trigger Auto-restart
- En `evaluate_alerts` / `_create_alert_and_deliveries`: tras crear alerta SERVICE/PROCESS, si entidad tiene `auto_restart=true` → llamar `POST /servers/{id}/restart`
- Evitar duplicados: chequear `agent_commands` pendientes para misma entidad antes de encolar
- Log estructurado: `auto_restart_triggered`, `auto_restart_skipped_duplicate`

### T5 — Tests Integración + E2E
- Test API: encolar → agente poll → ejecutar → reportar → verificar status
- Test Worker: alerta SERVICE con `auto_restart=true` → comando encolado
- E2E real: stack Docker, service nginx `auto_restart=true`, matar proceso → alerta → restart → service running

---

## Acceptance Criteria

1. **API**: `POST /restart` encola comando; `GET /commands` devuelve pendientes; `PATCH /result` actualiza. Tenant-scoped (404 cross-tenant).
2. **Agente**: Cada 30s pide comandos; ejecuta `systemctl restart nginx` (service) o `pkill -f pattern` (process); reporta resultado.
3. **Worker**: Alerta SERVICE/PROCESS con `auto_restart=true` → comando encolado automáticamente.
4. **Idempotencia**: No se encolan comandos duplicados para misma entidad mientras hay uno `pending`/`running`.
5. **Checks**: `mypy app` = 0; `ruff check` = 0; `pytest` verde; `go vet ./...` + `go test ./...` verdes.

---

## Checks aplicables

- API (workdir `api/`): `python -m mypy app`; `python -m ruff check`; `python -m pytest -q`.
- Go (workdir `agent/`): `go vet ./...`; `go test ./...`.
- E2E: compose stack en ejecución.

---

## Route Declaration

| Task | Route | Trigger Evidence |
|------|-------|------------------|
| T1 | Delegated direct (writer) | Migración + modelo + repo + tests (3+ archivos) |
| T2 | Delegated direct (writer) | API endpoints + auth + validación (2+ archivos) |
| T3 | Delegated direct (writer) | Agente Go: polling + ejecución + tests (2+ archivos) |
| T4 | Delegated direct (writer) | Worker alerts integración + tests |
| T5 | Delegated direct (verifier) | Tests integración + E2E Docker |

---

## Delivery Strategy

Forecast: ~2000 líneas autoradas (tests incluidos). Supera presupuesto 400 → `ask-on-risk` + chain `stacked-to-main`.
Slice boundaries: T1+T2 (API+DB) → PR 1; T3 (Agente) → PR 2; T4 (Worker) → PR 3; T5 (Tests/E2E) → PR 4.