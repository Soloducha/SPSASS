# TODO — mes 2: Agente Go v1 + Ingesta (agenda de mañana)

> **No es implementación hoy.** Es el plan/TODO anotado para arrancar mañana. Hoy no se toca código de agente ni de ingesta — solo se deja registrado el alcance, tal como pidió el usuario.
>
> Referencia roadmap: `propuesta.md` (línea 153, roadmap 6 meses) → **Mes 2 = Agente + ingesta**: agente Go v1 (CPU/mem/disco/load), heartbeat, API de ingesta, rollups, dashboard v0.1 (estado general + servidores).
>
> Detalle del plan: `agent/README.md` (sección "Mes 2 — Agente v1 + Ingesta").

---

## Mes 2 — Agente v1 + Ingesta

**Objetivo del mes**: mostrar **servidores monitoreados** (demostrable al cliente). Iteración clave: cada mes termina con algo demostrable.

### Agente Go
- [ ] Estructura base: `cmd/agent`, `internal/collector`, `internal/sender`
- [ ] Recolección: CPU, memoria, disco, load average (cada 30s)
- [ ] Heartbeat + registro automático contra API
- [ ] Push HTTPS con API key + retry/backoff
- [ ] Binario estático: `CGO_ENABLED=0 go build -ldflags="-s -w"`

### API — ingesta
- [ ] Endpoint ingesta: `POST /api/v1/ingest/metrics` (API key en header `X-API-Key`)
- [ ] Payload: JSON con `server_id`, `ts`, `metrics[]` (type, value, tags)
- [ ] Heartbeat: `POST /api/v1/servers/{id}/heartbeat`
- [ ] Registro: `POST /api/v1/servers/register` (primer contacto → crea server + devuelve API key)
- [ ] Rollups (agregación de métricas)
- [ ] Dashboard v0.1: estado general + servidores

### Integración
- [ ] Endpoint de ingesta + heartbeat + registro conectados entre agente Go y API
- [ ] CI gate aplicado al agente Go (si aplica: `go vet`, `go test`)

---

## Dependencias previstas del agente
- `github.com/shirou/gopsutil/v3` — métricas de sistema (CPU, mem, disco, load)
- `github.com/robfig/cron/v3` — parser cron (para jobs, mes 3+)
- `gopkg.in/yaml.v3` — configuración YAML
- `github.com/spf13/cobra` — CLI flags
- `github.com/spf13/viper` — configuración unificada

---

## Enlaces
- Roadmap: `propuesta.md` línea 153 (mes 2) y línea 93 (roadmap)
- Plan detallado agente: `agent/README.md`
- Hallazgos severos pendientes del quality-gate (también TODO de mañana): `odd/tasks/review-followups.md`
