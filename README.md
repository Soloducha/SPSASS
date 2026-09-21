# SPSAAS — Monitoreo SaaS para entornos legacy y Linux

**Monitoreo que funciona en 15 minutos, no en 15 días.**

SaaS de monitoreo centralizado de servidores, jobs, procesos y servicios críticos, con alertas automáticas (Telegram, WhatsApp, Email) y reportes de disponibilidad y SLA.

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
| Web (Next.js) | 3000 | Frontend placeholder |
| PostgreSQL + TimescaleDB | 5432 | Base de datos principal |
| Redis | 6379 | Broker + cache |
| Worker (arq) | — | Procesamiento en background |

### Comandos útiles

```bash
# Ver estado de contenedores
docker compose ps

# Ejecutar migraciones (la API las corre al inicio, pero manualmente):
docker compose exec api alembic upgrade head

# Tests de la API
docker compose exec api pytest -v

# Shell en la API
docker compose exec api bash

# Detener todo
docker compose down

# Detener y limpiar volúmenes (¡borra datos!)
docker compose down -v
```

---

## 🏗 Estructura del monorepo

```
SPSAAS/
├── docker-compose.yml          # Stack completo de desarrollo
├── .gitignore
├── README.md                   # Este archivo
├── docs/
│   └── architecture.md         # Referencia a propuesta.md
├── api/                        # FastAPI + Alembic + tests
│   ├── app/
│   ├── tests/
│   ├── alembic/
│   ├── pyproject.toml
│   └── Dockerfile
├── agent/                      # Placeholder Go (meses 2+)
│   ├── README.md
│   └── go.mod
└── web/                        # Next.js 14 placeholder
    ├── app/
    ├── package.json
    └── Dockerfile
```

---

## 📚 Documentación clave

- [`propuesta.md`](propuesta.md) — Plan de producto y arquitectura v1.0 (fuente de verdad)
- [`docs/architecture.md`](docs/architecture.md) — Resumen técnico de la arquitectura
- [`odd/tasks/fundaciones.md`](odd/tasks/fundaciones.md) — Feature document del mes 1

---

## 🔐 Autenticación y multi-tenant

- **Usuarios**: JWT (access + refresh tokens)
- **Agentes**: API keys
- **Multi-tenant**: Shared schema + `tenant_id` + RLS PostgreSQL
- **Subdominio por tenant**: `acme.spsaas.app`

---

## 🧪 Tests

```bash
# Solo API
docker compose exec api pytest -v

# Con cobertura
docker compose exec api pytest --cov=app --cov-report=term-missing
```

---

## 📦 Deploy (Producción inicial)

Un VPS económico (2 vCPU / 4 GB RAM) con Docker Compose:

```bash
# En el VPS
git clone <repo-url>
cd SPSAAS
cp .env.example .env  # Configurar variables de producción
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

Ver `propuesta.md` sección 4 y 10 para detalles de escalado.

---

## 🗺 Roadmap (6 meses)

| Mes | Foco | Entregables |
|-----|------|-------------|
| **1** | Fundaciones | Repo, CI/CD, Docker, auth, multi-tenant, modelos, bootstrap admin |
| **2** | Agente + ingesta | Agente Go, heartbeat, API ingesta, rollups, dashboard v0.1 |
| **3** | Alertas | Alert Engine, reglas, dedupe, Telegram + Email |
| **4** | Procesos + jobs | Servicios/procesos, job monitor, auto-restart, WhatsApp |
| **5** | Reportes | Disponibilidad, incidentes, SLA, métricas históricas |
| **6** | Pulido + beta | Onboarding, invitaciones, plan gates, beta cerrada 3-5 pilotos |

---

## 📄 Licencia

Proprietary — SPSAAS Team