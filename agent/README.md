# SPSAAS Agent — Placeholder (Mes 1)

Este directorio contendrá el agente de monitoreo en Go (binario estático ~10 MB).

## Estado actual: Placeholder

**Mes 1**: Solo estructura de carpetas y planificación.
**Mes 2+**: Implementación completa.

---

## Plan de implementación (Meses 2-4)

### Mes 2 — Agente v1 + Ingesta
- [ ] Estructura base: `cmd/agent`, `internal/collector`, `internal/sender`
- [ ] Recolección: CPU, memoria, disco, load average (cada 30s)
- [ ] Heartbeat + registro automático contra API
- [ ] Push HTTPS con API key + retry/backoff
- [ ] Binario estático: `CGO_ENABLED=0 go build -ldflags="-s -w"`

### Mes 3 — Alertas + Auto-restart
- [ ] Recolección de servicios (systemd) y procesos
- [ ] Auto-restart local con backoff y política configurable
- [ ] Integración con Alert Engine (recibe comandos de restart)

### Mes 4 — Jobs + Mainframe-adjacent
- [ ] Monitoreo de jobs cron/batch
- [ ] Detección de fallos y reporte de output_tail
- [ ] Proxies ligeros para mainframe-adjacent hosts

---

## Estructura de carpetas objetivo

```
agent/
├── cmd/
│   └── agent/
│       └── main.go           # Entry point
├── internal/
│   ├── collector/            # Recolectores de métricas
│   │   ├── cpu.go
│   │   ├── memory.go
│   │   ├── disk.go
│   │   ├── load.go
│   │   ├── services.go       # systemd
│   │   ├── processes.go      # por patrón
│   │   └── jobs.go           # cron/batch
│   ├── sender/               # Push HTTPS a API
│   │   ├── client.go
│   │   ├── payload.go        # Pydantic-compatible JSON
│   │   └── retry.go
│   ├── config/               # Configuración (env/file/flags)
│   └── autostart/            # Lógica de auto-restart local
├── pkg/                      # Código reutilizable
├── go.mod
├── go.sum
├── Makefile
├── Dockerfile                # Multi-stage: builder → scratch/distroless
└── README.md                 # Este archivo
```

---

## Dependencias clave (previstas)

| Paquete | Propósito |
|---------|-----------|
| `github.com/shirou/gopsutil/v3` | Métricas de sistema (CPU, mem, disco, load) |
| `github.com/robfig/cron/v3` | Parser de cron expressions para jobs |
| `gopkg.in/yaml.v3` | Configuración YAML |
| `github.com/spf13/cobra` | CLI flags |
| `github.com/spf13/viper` | Configuración unificada |

---

## Build y distribución

```bash
# Desarrollo
go run ./cmd/agent

# Release (binario estático)
CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -ldflags="-s -w" -o dist/agent-linux-amd64 ./cmd/agent
CGO_ENABLED=0 GOOS=linux GOARCH=arm64 go build -ldflags="-s -w" -o dist/agent-linux-arm64 ./cmd/agent

# Docker (multi-stage → scratch)
docker build -t spsaas/agent:v1.0.0 .
```

---

## Integración con API

- **Endpoint ingesta**: `POST /api/v1/ingest/metrics` (API key en header `X-API-Key`)
- **Payload**: JSON con `server_id`, `ts`, `metrics[]` (type, value, tags)
- **Heartbeat**: `POST /api/v1/servers/{id}/heartbeat`
- **Registro**: `POST /api/v1/servers/register` (primer contacto → crea server + devuelve API key)

Ver `propuesta.md` sección 4 y 8 para detalles de arquitectura.