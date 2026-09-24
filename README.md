# SPSAAS — Monitoreo SaaS para entornos legacy y Linux

**Monitoreo que funciona en 15 minutos, no en 15 días.**

SaaS de monitoreo centralizado de servidores, jobs, procesos y servicios críticos, con alertas automáticas — entrega v1 por **Webhook y Email (SMTP)** — y reportes de disponibilidad y SLA. Telegram/WhatsApp: en roadmap.

---

## 🚀 Quickstart (Desarrollo)

### Prerrequisitos
- Docker y Docker Compose
- Git

### Levantar todo el stack

```bash
# Clonar y entrar
git clone <repo-url>
cd SPSAAS

# Levantar servicios (postgres+timescale, redis, api, worker, web)
docker compose up --build -d

# Ver logs
docker compose logs -f api

# Verificar health
curl http://localhost:8000/healthz
```

### Servicios y puertos

| Servicio | Puerto | Descripción |
|----------|--------|-------------|
| API (FastAPI) | 8000 | Backend principal + docs en `/docs` |
| Web (Next.js 16) | 3000 | Dashboard v0.1 (SSR); consola de alertas pendiente |
| PostgreSQL + TimescaleDB | 5432 | Base de datos principal |
| Redis | 6379 | Broker + cache |
| Worker (arq) | — | Background: rollups, evaluación y entrega de alertas (crons de 1 minuto) |

> El **agente Go no corre en compose**: se compila como binario estático y se ejecuta
> en cada host monitoreado (ver [`agent/README.md`](agent/README.md)).

### Comandos útiles

```bash
# Ver estado de contenedores
docker compose ps

# Ejecutar migraciones (la API las corre al inicio, pero manualmente):
docker compose exec api alembic upgrade head

# Bootstrap del primer tenant + admin (requiere variables de entorno)
docker compose exec \
  -e SPSAAS_ADMIN_EMAIL=admin@example.com \
  -e SPSAAS_ADMIN_PASSWORD=securepass123 \
  api python -m scripts.seed_admin

# Shell en la API
docker compose exec api bash

# Detener todo
docker compose down

# Detener y limpiar volúmenes (¡borra datos!)
docker compose down -v
```

---

## 🌐 API — Endpoints principales

| Método | Ruta | Auth |
|--------|------|------|
| `POST` | `/auth/register`, `/auth/login`, `/auth/refresh` | — |
| `GET` | `/auth/me` | JWT |
| `POST`/`GET`/`DELETE` | `/auth/api-keys` | JWT |
| `POST` | `/api/v1/servers/register` | API key (`X-Api-Key`) |
| `POST` | `/api/v1/servers/{id}/heartbeat` | API key (`X-Api-Key`) |
| `POST` | `/api/v1/ingest/metrics` | API key (`X-Api-Key`) — 202, batch ≤ 1000 |
| `GET` | `/api/v1/dashboard/overview` | JWT — estado agregado y métricas recientes |
| `GET`/`POST` | `/api/v1/alerts/rules` | JWT — reglas de alerta (CRUD) |
| `PATCH`/`DELETE` | `/api/v1/alerts/rules/{rule_id}` | JWT — editar / eliminar regla |
| `GET` | `/api/v1/alerts` | JWT — alertas recientes/activas |
| `POST` | `/api/v1/alerts/{alert_id}/ack`, `/resolve` | JWT — acuse / resolución |
| `GET` | `/healthz`, `/readyz` | — |

Swagger UI: `http://localhost:8000/docs` (solo dev).

---

## 🔔 Alertas

- **Motor**: `evaluate_alerts()` corre cada minuto (cron `alert-eval-1m`) y compara las últimas métricas contra las reglas del tenant. Al disparar, crea una `AlertDelivery` **por canal configurado** en estado `pending` (dedupe: no re-dispara mientras la alerta esté activa sin resolver).
- **Reglas** (`/api/v1/alerts/rules`): condiciones sobre métricas (CPU, memoria, disco…), entidad objetivo, severidad y `channels` — **≥1 canal obligatorio**: `{"webhook": {"url", "headers"?}}` y/o `{"email": {"to": [...]}}`.
- **Entrega**: el runner `deliver_alerts()` (cron `alert-delivery-1m`) procesa los `pending` cross-tenant y deja `sent` (con `external_ref`) o `failed` (con motivo tipado). Un intento por ciclo en v1 — sin reintentos con backoff aún.
- **Canales v1**: Webhook HTTP POST (timeout 10s, headers custom) y Email vía SMTP (stdlib, `STARTTLS` opcional). Cómo agregar un canal nuevo: `api/app/workers/delivery/README.md`.
- **SMTP** — el canal email está activo solo si hay host y remitente (`smtp_enabled`):

| Variable | Uso |
|----------|-----|
| `SMTP_HOST` | Host del servidor SMTP (vacío = email deshabilitado) |
| `SMTP_PORT` | Puerto (default `587`) |
| `SMTP_USER` / `SMTP_PASSWORD` | Credenciales opcionales (login solo si hay usuario) |
| `SMTP_FROM` | Remitente (vacío = email deshabilitado) |
| `SMTP_STARTTLS` | `true`/`false` (default `true`) |

Consulta de alertas: `GET /api/v1/alerts` + acuse (`ack`) y resolución (`resolve`) según severidad. UI web de alertas: pendiente (próximo feature).

---

## 🏗 Estructura del monorepo

```
SPSAAS/
├── docker-compose.yml              # Stack completo de desarrollo
├── .github/workflows/ci.yml        # CI: API (lint+tests), agente Go, docker build
├── README.md                       # Este archivo
├── propuesta.md                    # Fuente de verdad: producto + arquitectura
├── docs/
│   └── architecture.md             # Resumen técnico de la arquitectura
├── odd/tasks/                      # Feature documents ODD (uno por slice)
├── api/                            # FastAPI + Alembic + tests
│   ├── app/
│   │   ├── api/v1/                  # Routers: servers, ingest, dashboard, alerts
│   │   ├── workers/                 # rollups, alerts (engine), delivery/ (canales), delivery_runner
│   │   ├── core/                    # config, security, db, tenant (RLS)
│   ├── tests/
│   ├── alembic/
│   ├── scripts/                    # seed_admin.py (bootstrap tenant + admin)
│   ├── pyproject.toml
│   ├── Dockerfile
│   └── Dockerfile.worker
├── agent/                          # Agente Go v1 (collector, sender, config + tests)
│   ├── cmd/agent/
│   ├── internal/
│   ├── go.mod
│   └── README.md
└── web/                            # Next.js 16 (dashboard v0.1 SSR; consola de alertas pendiente)
    ├── src/app/
    ├── package.json
    └── Dockerfile
```

---

## 📚 Documentación clave

- [`propuesta.md`](propuesta.md) — Plan de producto y arquitectura v1.0 (fuente de verdad)
- [`docs/architecture.md`](docs/architecture.md) — Resumen técnico de la arquitectura
- [`odd/tasks/`](odd/tasks/) — Feature documents por slice:
  - [`fundaciones.md`](odd/tasks/fundaciones.md) — Mes 1: base del monorepo
  - [`mes2-agente-ingesta.md`](odd/tasks/mes2-agente-ingesta.md) — Mes 2: agente Go + API de ingesta
  - [`mes3-alertas.md`](odd/tasks/mes3-alertas.md) — Mes 3: alert engine + API de reglas
  - [`alert-delivery.md`](odd/tasks/alert-delivery.md) — Entrega de alertas (canales webhook/email + runner)
  - [`hardening-ci-rls.md`](odd/tasks/hardening-ci-rls.md) — Hardening CI + RLS
  - [`quality-gate.md`](odd/tasks/quality-gate.md) — Gate de calidad (mypy 0 + ruff pragmático)
  - [`review-followups.md`](odd/tasks/review-followups.md) — Follow-ups de la review quality-gate
  - [`next16-web.md`](odd/tasks/next16-web.md), [`deps-refresh.md`](odd/tasks/deps-refresh.md) — Web Next 16 + refresh de dependencias
- Sub-READMEs: [`api/README.md`](api/README.md), [`agent/README.md`](agent/README.md), [`web/README.md`](web/README.md)

---

## 🔐 Autenticación y multi-tenant

- **Usuarios**: JWT (access + refresh tokens)
- **Agentes**: API keys por tenant (header `X-Api-Key`, prefijo `spsk_`)
- **Multi-tenant**: shared schema + `tenant_id` + **RLS en PostgreSQL**
  (migración `0003_enable_rls`; `metrics` se aísla en la app por limitación
  de TimescaleDB con columnstore)
- **Subdominio por tenant** (`acme.spsaas.app`): planeado, aún no implementado
  (hoy el tenant se resuelve por JWT / API key; `X-Tenant-ID` es solo fallback de testing)

---

## 🧪 Tests y quality gate

```bash
# API — tests (SQLite in-memory, sin servicios externos)
cd api
pytest -v

# API — quality gate (idéntico al de CI)
ruff check app/
mypy app

# Agente Go
cd agent
go vet ./...
go test ./...
```

Baseline API: **117 passed, 1 skipped, 1 xfailed, 2 xpass pre-existentes** (no tocar).

---

## 🤖 CI (GitHub Actions)

Workflow: [`.github/workflows/ci.yml`](.github/workflows/ci.yml) — corre en push/PR a `main` y `develop`:

| Job | Qué valida |
|-----|-----------|
| `python-api` | `ruff check app/` + `mypy app` + `pytest` (SQLite in-memory) |
| `go-agent` | `go vet` + `go test` + build estático (`CGO_ENABLED=0`) |
| `docker-build` | `docker compose build --parallel` |

---

## 📦 Deploy (Producción inicial)

Un VPS económico (2 vCPU / 4 GB RAM) con Docker Compose. Todavía **no existe**
`docker-compose.prod.yml` (plan pendiente):

```bash
# En el VPS
git clone <repo-url>
cd SPSAAS
cp api/.env.example api/.env   # Configurar variables de producción
docker compose up -d
```

Ver `propuesta.md` sección 4 y 10 para detalles de escalado.

---

## 🗺 Roadmap (6 meses)

| Mes | Foco | Entregables | Estado |
|-----|------|-------------|--------|
| **1** | Fundaciones | Repo, CI/CD, Docker, auth, multi-tenant, modelos, bootstrap admin | ✅ Entregado |
| **2** | Agente + ingesta | Agente Go v1, heartbeat, API ingesta, rollups, dashboard v0.1 | ✅ Entregado |
| **3** | Alertas | Alert Engine, reglas, dedupe, entrega Webhook + Email (SMTP) | ✅ Entregado (canales v1: webhook + email; Telegram/WhatsApp ⏳) |
| **4** | Procesos + jobs | Servicios/procesos, job monitor, auto-restart, WhatsApp | ⏳ Pendiente |
| **5** | Reportes | Disponibilidad, incidentes, SLA, métricas históricas | ⏳ Pendiente |
| **6** | Pulido + beta | Onboarding, invitaciones, plan gates, beta cerrada 3-5 pilotos | ⏳ Pendiente |

Ver `propuesta.md` §7 para la fuente de verdad del roadmap.

---

## 📄 Licencia

Proprietary — SPSAAS Team
