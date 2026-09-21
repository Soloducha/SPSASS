# SPSAAS — Plan de Producto y Arquitectura v1.0

**Monitoreo SaaS para entornos legacy y Linux, orientado a administradores de sistemas, equipos de operaciones, middleware y mainframe.**

Propuesta de producto para el lanzamiento del primer producto: monitoreo centralizado de servidores, jobs, procesos y servicios críticos, con alertas automáticas (Telegram, WhatsApp, Email) y reportes de disponibilidad y SLA.

---

## 1. Propuesta de valor

**"Monitoreo que funciona en 15 minutos, no en 15 días."**

Los equipos de ops en empresas con infraestructura legacy viven con un dolor concreto: necesitan visibilidad de servidores, jobs y procesos críticos, pero las herramientas tradicionales (Zabbix, Nagios) son tan caras de operar como la infraestructura que monitorean. SPSAAS ofrece:

- **Instalación inmediata**: un comando en el servidor y ya está reportando métricas. Sin servidor de monitoreo propio, sin templates, sin mantenimiento.
- **Alertas donde ya vive el equipo**: Telegram, WhatsApp y Email. Nada de dashboards que nadie mira.
- **Reportes automáticos de SLA**: la evidencia que el equipo de ops necesita para demostrar valor, sin armarla a mano todos los meses.
- **Costo predecible**: SaaS con pricing por servidor, pensado para VPS económicos — no para presupuestos enterprise.

El producto no compite en *riqueza de features* (ahí Zabbix gana), compite en **time-to-value y costo total de operación**.

## 2. Público objetivo

| Segmento | Descripción | Dolor principal |
|---|---|---|
| **Empresas medianas (50–500 empleados)** | Equipos de ops de 1–5 personas, infraestructura mixta legacy + Linux | No tienen presupuesto ni gente para operar Nagios/Zabbix |
| **MSPs y consultoras** | Gestionan infraestructura de múltiples clientes | Necesitan multi-tenant de verdad para reportar por cliente |
| **Sectores regulados** (banca, salud, logística, gobierno) | Mainframe + cron jobs críticos que no pueden caerse | La disponibilidad se audita: necesitan reportes, no solo dashboards |
| **Empresas con mainframe/legacy** | COBOL, AS/400, jobs batch nocturnos | Los jobs se caen a las 3 AM y nadie se entera hasta la mañana |

**ICP primario**: CTO/Head of Ops en empresa de 100–1000 empleados con infraestructura Linux+legacy crítica, equipo pequeño, y presupuesto para SaaS (no para contratar un SRE).

## 3. Diferenciadores frente a los gigantes

| | Zabbix / Nagios | Prometheus / Grafana | **SPSAAS** |
|---|---|---|---|
| **Instalación** | Servidor propio, agentes, templates, curva de meses | Stack que tú operas (server, retención, alerting) | **Un comando por servidor, SaaS listo** |
| **Costo operativo** | Alto (el monitoreo se vuelve un proyecto) | Alto (infraestructura propia de observabilidad) | **Bajo, fijo, predecible** |
| **Alertas** | Email/SMS configurados a mano | Alertmanager, config compleja | **Telegram/WhatsApp/Email nativos, en minutos** |
| **Jobs & procesos** | Scripts y templates manuales | No es su foco | **Monitoreo + auto-restart configurable** |
| **Reportes SLA** | Manuales o plugins | Dashboard manual, tú armas el reporte | **Automáticos, listos para auditoría** |
| **Multi-tenant** | Instancia por cliente | Instancia por cliente | **Nativo desde el día 1** |

La honestidad de CTO: **no vamos a ganar a Zabbix en features**. Ganamos en el 80% de casos de uso que necesitan el 20% del esfuerzo. Ese es el posicionamiento.

## 4. Arquitectura técnica completa

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

**Componentes:**

1. **Agente** (Go, binario estático ~10 MB, sin runtime en el server monitoreado):
   - Recolecta CPU, memoria, disco, load average, servicios (systemd), procesos, jobs cron.
   - Push HTTPS cada 30s con token de autenticación + heartbeat.
   - Auto-restart local de procesos/servicios con backoff y política configurable.
   - Puede correr en mainframe-adjacent hosts vía proxies ligeros (futuro).

2. **API Core** (FastAPI async):
   - Rutas: `auth`, `agents/ingest`, `servers`, `services`, `processes`, `jobs`, `alerts`, `reports`.
   - Auth JWT (usuarios) + API keys (agentes). RBAC por tenant.
   - Pydantic v2 para validación estricta de payloads de agentes.

3. **Workers** (arq sobre Redis — liviano, async nativo, perfecto para VPS):
   - Ingesta y agregación de métricas (rollups 1m → 5m → 1h → 1d).
   - Alert Engine: evalúa reglas, deduplica, escala (alertas recurrentes cada X, no cada 30s).
   - Job Monitor: detecta jobs caídos, dispara alertas y ejecuta auto-restart.

4. **Datos** (PostgreSQL 16 + TimescaleDB):
   - Hypertables para métricas con retención y compresión automática.
   - Todo el resto en tablas relacionales clásicas.
   - Migraciones con Alembic.

5. **Frontend** (Next.js 14 App Router):
   - Dashboard con estado general, servidores, jobs, alertas, gráficos históricos (Recharts).
   - Realtime con **SSE** (Server-Sent Events) — más simple que WebSockets, funciona detrás de proxies, suficiente para dashboards.
   - SSR para el dashboard principal (métricas en server components) + client components interactivos.

6. **Infra** (Docker obligatorio):
   - Dev: `docker-compose up` con todo.
   - Prod inicial: **un VPS económico (2 vCPU / 4 GB RAM)** con compose: nginx → api+frontend+workers+redis+postgres. Escala a multi-VPS cuando la load lo pida.
   - CI/CD con GitHub Actions: build → test → push registry → deploy.

## 5. Modelo de datos inicial

```
tenants(id, name, slug, plan, settings, created_at)
users(id, tenant_id FK, email, password_hash, role, ...)
tenant_members(user_id, tenant_id, role)          -- user puede estar en varios tenants (MSP)

servers(id, tenant_id FK, hostname, ip, os, agent_version, status,
        last_heartbeat_at, alert_channels JSONB)

metrics(ts, server_id FK, type, value, tags JSONB)  -- HYPERTABLE Timescale
  · cpu_usage, mem_usage, disk_usage, load_avg1/5/15

services(id, tenant_id, server_id, name, desired_state, auto_restart, last_status, ...)
processes(id, tenant_id, server_id, name, pattern, expected_count, auto_restart, ...)

jobs(id, tenant_id, server_id, name, kind ENUM(cron, batch, scheduled),
     schedule_cron, command, timeout_s, alert_on_fail, auto_restart, ...)
job_runs(id, job_id, started_at, finished_at, exit_code, status, output_tail, ...)

alert_rules(id, tenant_id, entity_type, entity_id, metric, operator, threshold,
            duration_s, severity, channels JSONB)
alerts(id, tenant_id, rule_id, server_id, severity, status ENUM(open, ack, resolved),
       message, triggered_at, resolved_at, value_at_trigger)
alert_deliveries(id, alert_id, channel, status, external_ref, delivered_at)

reports(id, tenant_id, period_start, period_end, type, payload JSONB, generated_at)
```

**Regla de oro**: toda tabla de negocio lleva `tenant_id`; todos los queries multi-tenant pasan por RLS.

## 6. Diseño multi-tenant

**Modelo: shared database + shared schema + RLS de PostgreSQL.**

- Cada fila tiene `tenant_id`; cada request lleva el tenant en el JWT.
- **Row Level Security** en Postgres como red de seguridad: aunque un query "olvide" filtrar por tenant, la política lo bloquea. Esto es la diferencia entre un multi-tenant "que funciona" y uno "que filtra datos de clientes".
- Subdominio por tenant: `acme.spsaas.app`, `msp1.spsaas.app`.
- **Cuotas por tenant**: servidores máx, usuarios, alertas/mes, retención de métricas.
- Aislamiento por schema por tenant: **solo si** un enterprise lo exige (banca/regulados) — v2, como feature premium.

## 7. Roadmap de 6 meses

| Mes | Foco | Entregables |
|---|---|---|
| **1** | Fundaciones | Repo monorepo, CI/CD, Docker compose, auth JWT, multi-tenant base, modelos + migraciones, bootstrap admin |
| **2** | Agente + ingesta | Agente Go v1 (CPU/mem/disco/load), heartbeat, API de ingesta, rollups, dashboard v0.1 (estado general, servidores) |
| **3** | Alertas | Alert Engine, reglas, dedupe/escalado, canal **Telegram + Email** |
| **4** | Procesos + jobs | Servicios/procesos con auto-restart, job monitor cron/batch, detección de errores, canal **WhatsApp** |
| **5** | Reportes | Disponibilidad, incidentes, alertas generadas, **SLA**, métricas históricas en dashboard |
| **6** | Pulido + beta | Onboarding, invitaciones, plan gates, hardening, **beta cerrada con 3–5 pilotos**, docs, pricing page |

**Iteración clave**: cada mes termina con algo demostrable al cliente. Mes 2 ya mostramos servidores monitoreados.

## 8. Módulos del MVP

```
app/
├── agent/          → repo Go separado (binario estático)
├── api/
│   ├── auth/       → JWT, API keys, RBAC
│   ├── ingest/     → endpoint de agentes, validación, enqueue
│   ├── servers/    → CRUD, registro, heartbeats
│   ├── jobs/       → CRUD jobs, job_runs
│   ├── alerts/     → reglas, CRUD alerts
│   └── reports/    → generación y descarga
├── workers/
│   ├── metrics/    → ingest, rollups, retención
│   ├── alerts/     → evaluación, dedupe, escalation
│   └── jobs/       → scheduler, monitoreo, auto-restart
└── web/            → Next.js (app router)
    ├── dashboard/  → overview, servidores, jobs, alertas, métricas
    ├── settings/   → tenants, canales, reglas, usuarios
    └── reports/    → SLA, disponibilidad, incidentes
```

## 9. Estrategia de monetización

| Plan | Precio | Incluye | Objetivo |
|---|---|---|---|
| **Free** | $0 | 3 servidores, alertas Email, 7 días retención | Embudo de adopción |
| **Starter** | **$29/mes** | 10 servidores, Telegram + Email, 30 días retención | SMB |
| **Growth** | **$79/mes** | 50 servidores, + WhatsApp, reportes SLA, 90 días | Empresas medianas |
| **Enterprise** | Custom | Ilimitado, SSO/SAML, white-label, on-prem, soporte | MSPs y regulados |

- **Pricing por servidor** es el estándar del mercado (Datadog cobra ~$15–18/host) — nosotros **por debajo**, coherente con el target de VPS económicos.
- Upsell lógico: retención extendida, más canales, reportes auditables.
- **Upsell oculto clave**: el MSP que monitorea 10 clientes paga Growth por tenant → multi-tenant es un feature de venta directa.

## 10. Recomendación tecnológica moderna

| Capa | Elección | Por qué |
|---|---|---|
| Backend API | **FastAPI + Pydantic v2 + SQLAlchemy 2.0 (async) + Alembic** | Async de base, tipado total, docs OpenAPI gratis |
| Workers | **arq (Redis)** | Async nativo, liviano — Celery es overkill y pesado para VPS |
| Broker/Cache | **Redis 7** | Broker + cache + rate limiting |
| Base de datos | **PostgreSQL 16 + TimescaleDB** | Series temporales SIN agregar otra DB; compresión y retención nativas |
| Frontend | **Next.js 14 (App Router) + TypeScript + Tailwind + shadcn/ui + Recharts + TanStack Query** | SSR para dashboards, UX moderna, realtime con SSE |
| Agente | **Go (binario estático)** | 10 MB sin runtime, cero dependencias en el server del cliente, bajo consumo |
| Deploy | **Docker Compose → VPS único → multi-VPS con Traefik** | Costo inicial mínimo, camino de escalado claro |
| CI/CD | GitHub Actions | Build/test/deploy automático desde día 1 |
| Billing | Stripe (+ Billing Portal) | Estándar, listo para planes y proration |
| Observabilidad propia | Prometheus + Grafana interno | Vos también tenés que estar monitoreado 😉 |

---

## Decisiones clave

**Las 2 decisiones que más impacto tienen** (y donde la mayoría se equivoca):

1. **TimescaleDB sobre PostgreSQL en vez de una DB de series temporal separada** (InfluxDB/Mongo): una sola base, un solo backup, un solo costo. Escala muchísimo más de lo que el MVP necesita.
2. **Agente en Go aunque el backend sea Python**: el agente vive en el servidor del cliente; un binario estático de 10 MB sin Python runtime es un argumento de venta enorme (menos superficie de ataque, menos consumo, instalación trivial).

---

## Checklist de validación

- [ ] Time-to-value real: instalar agente en un servidor de prueba y ver métricas en el dashboard
- [ ] Alerta de Telegram configurada y recibida (verificar latencia y dedupe)
- [ ] Un cron job monitoreado con detección de fallo real
- [ ] Reporte SLA mensual generado automáticamente
- [ ] Aislamiento multi-tenant: verificar que el tenant A no ve datos del tenant B
- [ ] Deploy completo en VPS de 2 vCPU/4 GB con Docker Compose

## Próximo paso

Bootstrap del monorepo (mes 1): estructura, Docker Compose, auth JWT, multi-tenant base, modelos + migraciones.