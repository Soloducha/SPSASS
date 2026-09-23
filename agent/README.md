# SPSAAS Agent — Agente de monitoreo en Go

Agente de monitoreo liviano en Go (binario estático) que recolecta métricas del host y las envía por HTTPS a la API de SPSAAS con una API key de tenant.

## Estado actual

**Mes 2 — Entregado:** agente v1 funcional — recolección (CPU, memoria, disco, load average), registro automático del servidor, heartbeat periódico, push HTTPS con retry/backoff y logging estructurado.

**Pendiente (meses 3-4):** monitoreo de servicios (systemd), procesos y auto-restart local; jobs cron/batch.

## Uso

Configuración por flags, con fallback a variables de entorno:

| Flag | Env | Default | Descripción |
|------|-----|---------|-------------|
| `--api-url` | `SPSAAS_API_URL` | `http://localhost:8000` | URL base de la API |
| `--api-key` | `SPSAAS_API_KEY` | — (requerido) | API key del tenant |
| `--hostname` | `SPSAAS_HOSTNAME` | `os.Hostname()` | Hostname del servidor |
| `--interval` | `SPSAAS_INTERVAL` | `30s` | Intervalo de recolección |
| `--agent-version` | `SPSAAS_AGENT_VERSION` | `0.1.0` | Versión reportada del agente |
| `--ip` | `SPSAAS_IP` | (opcional) | IP del servidor |

```bash
# Desarrollo
go run ./cmd/agent --api-key spsk_xxx --api-url http://localhost:8000

# Release (binario estático)
CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -ldflags="-s -w" -o dist/agent-linux-amd64 ./cmd/agent
CGO_ENABLED=0 GOOS=linux GOARCH=arm64 go build -ldflags="-s -w" -o dist/agent-linux-arm64 ./cmd/agent
```

La API key se crea desde un usuario admin del tenant vía `POST /auth/api-keys` (la UI aún no existe, se usa la API).

## Comportamiento

- **Arranque**: registra el servidor en `POST /api/v1/servers/register` (upsert por `tenant_id + hostname`); si falla tras los reintentos, sale con error.
- **Métricas** cada `interval` (30s por defecto): `cpu_usage` (%), `mem_usage` (%), `disk_usage` (%) del mount `/`, `load_avg1`, `load_avg5`, `load_avg15`. Valores redondeados a 2 decimales, `ts` en UTC.
- **Push**: `POST /api/v1/ingest/metrics` con header `X-Api-Key`.
- **Heartbeat**: `POST /api/v1/servers/{id}/heartbeat` cada `interval × 5` (~150s), después del primer envío exitoso de métricas.
- **Retry/backoff**: exponencial (base 500ms, máx 8s, 5 intentos, jitter ±20%) sobre errores de red, 5xx, 429 y 408.
- **Logging**: estructurado JSON (`slog`); shutdown graceful en SIGINT/SIGTERM.

## Integración con API

| Endpoint | Método | Auth |
|----------|--------|------|
| `/api/v1/servers/register` | POST | `X-Api-Key` |
| `/api/v1/servers/{id}/heartbeat` | POST | `X-Api-Key` |
| `/api/v1/ingest/metrics` | POST | `X-Api-Key` |

## Tests y checks

```bash
go vet ./...
go test ./...
```

## Limitaciones conocidas

- Disco hardcodeado al mount `/` (no configurable aún).
- Servicios/procesos, auto-restart y jobs: meses 3-4 del roadmap (`propuesta.md` §7).