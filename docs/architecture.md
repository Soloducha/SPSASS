# Arquitectura Técnica — SPSAAS v1.0

> **Fuente de verdad**: [`propuesta.md`](../propuesta.md) — Secciones 4 (Arquitectura), 5 (Modelo de datos), 8 (Módulos), 10 (Decisiones tecnológicas).

---

## Resumen

SPSAAS sigue una arquitectura **monolítica modular** desplegada via Docker Compose, con separación clara de responsabilidades:

```
┌─────────────────┐      ┌──────────────────────────────┐      ┌─────────────────┐
│   Agente Linux  │      │         API Core             │      │   Frontend      │
│  (Go, ~10 MB)   │─────▶│   FastAPI (async)            │◀─────│   Next.js 14    │
│  push HTTPS     │      │   Auth · Ingesta · Admin     │      │   SSR + SSE     │
└─────────────────┘      └──────────────┬───────────────┘      └─────────────────┘
                                         │
                                         ▼
                               ┌─────────────────────┐
                               │        Redis        │    ← broker + cache
                               └──────────┬──────────┘
                                          ▼
                     ┌─────────────────────────────────────┐
                     │         Workers (arq)               │
                     │  ┌───────────┐ ┌─────────────────┐  │
                     │  │ Métricas  │ │ Alert Engine    │  │
                     │  └───────────┘ └─────────────────┘  │
                     └──────────┬──────────────────┬───────┘
                                ▼                  ▼
                     ┌──────────────────┐   ┌──────────────┐
                     │  PostgreSQL 16   │   │ Telegram /   │
                     │  + TimescaleDB   │   │ WhatsApp /   │
                     │  (hypertables)   │   │ Email        │
                     └──────────────────┘   └──────────────┘
```

---

## Componentes

### 1. API Core (`api/`)
- **Framework**: FastAPI async + Pydantic v2
- **ORM**: SQLAlchemy 2.0 (async) + Alembic
- **Auth**: JWT (usuarios) + API keys (agentes) + RBAC por tenant
- **Módulos**: `auth`, `ingest`, `servers`, `jobs`, `alerts`, `reports`

### 2. Workers (`api/workers/`)
- **Framework**: arq sobre Redis (async nativo, liviano)
- **Jobs**: ingesta/rollups métricas, alert engine, job monitor
- **Escalado**: horizontal vía réplicas de worker

### 3. Base de Datos
- **PostgreSQL 16** + **TimescaleDB** (extensión nativa)
- **Hypertables**: métricas (`metrics`) con retención/compresión automática
- **Tablas relacionales**: resto del modelo (ver `propuesta.md` §5)
- **Multi-tenant**: shared schema + `tenant_id` + **RLS** (Row Level Security)

### 4. Frontend (`web/`)
- **Framework**: Next.js 14 App Router + TypeScript
- **UI**: Tailwind + shadcn/ui + Recharts
- **Realtime**: SSE (Server-Sent Events)
- **Estado**: TanStack Query

### 5. Agente (`agent/`)
- **Lenguaje**: Go (binario estático ~10 MB)
- **Push**: HTTPS cada 30s con token + heartbeat
- **Capacidad**: auto-restart local con backoff

---

## Modelo de Datos (v1)

Todas las tablas de negocio llevan `tenant_id`. Ver `propuesta.md` §5 para DDL completo.

| Tabla | Propósito | Tipo |
|-------|-----------|------|
| `tenants` | Organizaciones | Relacional |
| `users` | Usuarios del sistema | Relacional |
| `tenant_members` | MSP: usuario en múltiples tenants | Relacional |
| `servers` | Servidores monitoreados | Relacional |
| `metrics` | Series temporales (CPU, RAM, disco, load) | **Hypertable Timescale** |
| `services` | Servicios systemd | Relacional |
| `processes` | Procesos por patrón | Relacional |
| `jobs` | Jobs cron/batch/scheduled | Relacional |
| `job_runs` | Ejecuciones de jobs | Relacional |
| `alert_rules` | Reglas de alerta | Relacional |
| `alerts` | Alertas disparadas | Relacional |
| `alert_deliveries` | Entregas por canal | Relacional |
| `reports` | Reportes generados (JSONB) | Relacional |

---

## Multi-Tenant: Shared Schema + RLS

```sql
-- Ejemplo de política RLS en tenants
ALTER TABLE servers ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON servers
  USING (tenant_id = current_setting('app.current_tenant_id')::uuid);
```

- Cada request setea `app.current_tenant_id` via middleware
- RLS actúa como **red de seguridad**: aunque el código olvide filtrar, Postgres bloquea
- Subdominio por tenant: `acme.spsaas.app` → resuelve a `tenant_id` via middleware

---

## Decisiones Clave (Inmutables en MVP)

| Decisión | Justificación |
|----------|---------------|
| TimescaleDB sobre PostgreSQL | Una sola DB, un backup, un costo; escala >> MVP |
| Agente en Go | Binario estático 10 MB sin runtime en server del cliente |
| arq (no Celery) | Async nativo, liviano, perfecto para VPS |
| SSE (no WebSockets) | Funciona detrás de proxies, suficiente para dashboards |
| Shared schema + RLS | Multi-tenant real desde día 1, sin complejidad de schema-per-tenant |

---

## Variables de Entorno Críticas

| Variable | Descripción | Ejemplo |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL + Timescale | `postgresql+asyncpg://user:pass@db:5432/spsaas` |
| `REDIS_URL` | Redis broker/cache | `redis://redis:6379/0` |
| `JWT_SECRET` | Firma de tokens (32+ chars) | `super-secret-change-in-production` |
| `JWT_ALGORITHM` | Algoritmo JWT | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Expiración access token | `15` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Expiración refresh token | `7` |
| `API_KEY_PREFIX` | Prefijo API keys agentes | `spsk_` |

---

## Referencias

- [`propuesta.md`](../propuesta.md) — Documento completo de producto y arquitectura
- [`odd/tasks/fundaciones.md`](../odd/tasks/fundaciones.md) — Tareas del mes 1