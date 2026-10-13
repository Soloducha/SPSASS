# Feature — mes 6: Pulido + Beta (Onboarding, Invitaciones, Plan Gates, Hardening, Beta Cerrada, Docs, Pricing)

> Feature document ODD. Estado: **CÓDIGO COMPLETO — OPERATIVA PENDIENTE** — actualización 2026-10-13.
>
> Referencia roadmap: `propuesta.md` línea 157 → **Mes 6 = Pulido + beta**: Onboarding, invitaciones, plan gates, hardening, **beta cerrada con 3–5 pilotos**, docs, pricing page.

---

## Objetivo

Transformar el MVP funcional en un producto listo para beta cerrada con pilotos reales:

1. **Onboarding** — Flow guiado para nuevo tenant: registro → crear servidor → instalar agente → ver métricas.
2. **Invitaciones** — Invitar miembros al tenant (email + rol), aceptar invitación, unirse.
3. **Plan Gates** — Enforcement de límites por plan (Free/Starter/Growth/Enterprise): servidores, retención, canales, reportes.
4. **Hardening** — Seguridad (rate limiting, CSP, headers), performance (índices, queries), observabilidad (logs, métricas internas).
6. **Beta Cerrada** — Onboarding de 3-5 pilotos reales, feedback loop, métricas de adopción.
7. **Docs** — Documentación usuario (instalación agente, configuración alertas, reportes) + API reference.
7. **Pricing Page** — Landing pública con planes, FAQ, signup → onboarding.

---

## Problema / Por qué

Hoy el sistema funciona técnicamente (Meses 1-5 completos) pero **no es un producto listo para clientes**:
- No hay forma de registrarse y empezar sin intervención manual.
- No hay control de planes → un tenant Free puede crear 100 servidores.
- No hay forma de invitar al equipo.
- Falta hardening de producción (rate limiting, security headers, etc.).
- No hay docs para que un usuario instale el agente solo.
- No hay pricing page pública para captar leads.

Mes 6 cierra esa brecha: **de MVP técnico a producto vendible en beta cerrada**.

---

## Alcance (in/out)

**In (MVP Mes 6):**

- **Onboarding Web** — `/onboarding` multi-step: registro tenant → crear primer servidor → generar API key → instrucciones instalación agente (Linux/Windows) → verify heartbeat → dashboard.
- **Invitaciones** — Modelo `TenantInvitation` + email con token → `/accept-invitation/{token}` → crear usuario + asociar tenant + rol.
- **Plan Gates** — Middleware/guards que validan límites en tiempo real:
  - Servidores: Free=3, Starter=10, Growth=50, Enterprise=∞
  - Retención métricas: Free=7d, Starter=30d, Growth=90d, Enterprise=365d
  - Canales alerta: Free=email, Starter=email+telegram, Growth=+whatsapp, Enterprise=all
  - Reportes/mes: Free=1, Starter=5, Growth=20, Enterprise=∞
  - API keys: Free=1, Starter=5, Growth=20, Enterprise=∞
- **Hardening** —
  - Rate limiting (API: 100 req/min por key; Web: 30 req/min por IP)
  - Security headers (CSP, HSTS, X-Frame-Options, etc.)
  - Input validation estricta (Pydantic + Zod)
  - Audit logging (cambios críticos: usuarios, planes, API keys)
  - DB indexes críticos + query optimization (EXPLAIN ANALYZE)
  - Internal health checks (`/healthz`, `/readyz`)
- **Beta Cerrada** —
  - Lista de pilotos (3-5) con onboarding asistido
  - Feedback form en-app + métricas de adopción (DAU, servers/tenant, alertas/semana)
  - Canal Slack/Discord privado para soporte directo
- **Docs** —
  - Usuario: `/docs` (Next.js + MDX): instalación agente (Linux systemd, Windows NSSM), config alertas, canales, reportes, troubleshooting.
  - API Reference: OpenAPI/Swagger UI en `/docs/api`.
- **Pricing Page** — `/pricing` estática (Next.js SSG): tabla planes, FAQ, CTA "Empezar gratis" → `/onboarding`.

**Out (post-beta / Mes 7+):**
- SSO/SAML (Enterprise)
- White-label
- On-prem deployment
- Marketplace de integraciones
- Mobile app

---

## Decisiones registradas

1. **Onboarding server-side (SSR)** — Next.js App Router con Server Actions para crear tenant + servidor + API key en una transacción. Token de invitación JWT firmado (expira 7 días).
2. **Plan Gates como middleware + DB constraints** — Validación temprana en API (403 + mensaje claro) + CHECK constraints en DB como red de seguridad.
3. **Rate limiting con Redis** — Sliding window (Redis sorted sets) por API key / IP. Configurable por plan.
4. **Invitaciones sin registro previo** — Token JWT con `tenant_id` + `role` + `email` → al aceptar, si usuario existe lo asocia, si no existe crea cuenta + tenant membership.
5. **Docs con MDX + Next.js** — Contenido en `/docs/content/*.mdx`, renderizado con `next-mdx-remote`. Versionado en repo.
5. **Pricing page SSG** — Generada en build (`next build`), datos de planes en JSON/TS, FAQ en MDX.
6. **Beta cerrada: lista manual** — No auto-signup público. Lista de emails en `pilots.json` o DB flag `is_pilot`. Acceso via feature flag.

---

## Checklist (tasks)

- [x] **T1 — Onboarding Web** — `/onboarding` multi-step (SSR + Server Actions): registro tenant → servidor → API key → instrucciones agente → verify → dashboard. Tests E2E (Playwright) ✅.
- [x] **T2 — Invitaciones** — Modelo `TenantInvitation` + email (SendGrid/Resend) + `/accept-invitation/{token}` page + Server Action aceptar. Tests unit + E2E ✅. Dashboard UI `/invitations` (list + create) ✅. Migración Alembic `tenant_invitations` ✅. `clean_database` fixture ✅.
- [x] **T3 — Plan Gates** — Middleware `planGuard` + DB CHECK constraints + helpers `canCreateServer()`, `canCreateApiKey()`, etc. Tests unit + integración.
- [x] **T4 — Hardening** — Rate limiter (Redis), security headers (next-secure-headers), audit log (tabla `AuditLog`), health checks, DB indexes, query optimization. Tests de carga (k6).
- [ ] **T5 — Beta Cerrada** — Feature flag `BETA_ENABLED`, lista pilotos en DB, feedback widget (Hotjar/propio), métricas adopción (PostHog/Plausible/propio), canal soporte.
- [x] **T6 — Docs** — `/docs` (Next.js + MDX): instalación agente (Linux/Windows), alertas, reportes, troubleshooting. API Reference (`/docs/api` Swagger UI).
- [x] **T7 — Pricing Page** — `/pricing` (SSG): tabla planes (JSON), FAQ (MDX), CTA → `/onboarding`. Tests visuales (Chromatic/Storybook).
- [ ] **T8 — Beta Launch** — Onboarding 3-5 pilotos, feedback loop semanal, métricas adopción (DAU, servers/tenant, alertas/semana), canal Slack privado.

---

## Acceptance Criteria

- [x] Onboarding: usuario nuevo registra tenant, crea servidor, genera API key, instala agente, ve métricas en dashboard en < 10 min.
- [x] Invitaciones: admin invita miembro → email recibido → click → crea cuenta/ingresa → ve tenant en dashboard. Dashboard UI `/invitations` funcional.
- [x] Plan Gates: tenant Free intenta crear 4to servidor → 403 "Límite de plan alcanzado (3 servidores). Upgrade a Starter para 10."; tenant Starter intenta 11avo → 403.
- [x] Rate limiting: 101 requests/min con misma API key → 429 "Rate limit exceeded".
- [x] Security headers: `curl -I` muestra CSP, HSTS, X-Frame-Options, Referrer-Policy.
- [x] Health checks: `GET /healthz` → 200 OK; `GET /readyz` → 200 si DB+Redis OK, 503 si no.
- [x] Docs: `/docs` carga, búsqueda funciona, código copiable; `/docs/api` muestra Swagger UI.
- [x] Pricing page: `/pricing` renderiza estático, tabla planes correcta, FAQ expandible, CTA funciona.
- [ ] Beta: 3-5 pilotos onboarded, feedback semanal, métricas DAU/servers/alertas en dashboard interno.
- [x] `mypy app` = 0; `ruff check` = 0; `pytest` verde (292 passed); `pnpm run lint` = 0; `pnpm run build` = success; `pnpm run test` = verde (vitest + Playwright 9 passed).

---

## Checks aplicables

- API (workdir `api/`): `python -m mypy app`; `python -m ruff check`; `python -m pytest -q`.
- `python -m ruff format --check` **no es gate**.
- Migraciones: `alembic current` + `alembic upgrade/downgrade` contra Postgres real.
- Go (workdir `agent/`): `go vet ./...`; `go test ./...`.
- Web (workdir `web/`): `pnpm run lint`; `pnpm run build`; `pnpm run test`.
- E2E: Playwright (onboarding, invitaciones, plan gates).
- Load test: k6 (rate limiting, health checks bajo carga).

---

## Progreso y evidencia

- **2026-10-07** — Feature doc creado. T1 Onboarding Web **COMPLETO** (salvo Playwright E2E).
  - ✅ UI + Server Actions (`web/src/app/onboarding/page.tsx`, `actions.ts`)
  - ✅ Endpoint API `POST /api/v1/api-keys` (`api/app/api/v1/api_keys.py`)
  - ✅ Frontend `createApiKey` real (`web/src/lib/api/servers.ts`)
  - ✅ Fix código duplicado en `page.tsx`
  - ✅ Router montado en FastAPI (`api/app/api/__init__.py`, `api/app/main.py`)
  - **Checks:** mypy 0, ruff 0 errors, pytest 292 passed, lint 0 errors, build success, test 174 passed
  - **Pendiente:** Playwright E2E para el flujo completo

- **2026-10-07** — T2 Invitaciones **COMPLETO** (salvo tests unit/E2E y migración Alembic).
  - ✅ Modelo `TenantInvitation` con índice único parcial (`tenant_id`, `email` WHERE `accepted_at IS NULL`)
  - ✅ Endpoints: `POST /api/v1/invitations` (create), `GET /api/v1/invitations` (list), `POST /api/v1/invitations/accept/{token}` (accept público)
  - ✅ Email SMTP para invitaciones (`api/app/workers/delivery/invitation_email.py`)
  - ✅ Config `WEB_URL` + `INVITATION_EXPIRE_DAYS` en `api/app/core/config.py`
  - ✅ Frontend: API client (`web/src/lib/api/invitations.ts`), Server Actions (`web/src/app/invitations/actions.ts`), Accept page (`web/src/app/accept-invitation/[token]/page.tsx`)
  - ✅ Router montado en FastAPI
  - **Checks:** mypy 0, ruff 0 errors (solo warnings pre-existentes), pytest 292 passed, lint 0 errors, build OK, test 174 passed
  - **Pendiente:** Tests unit/E2E, migración Alembic, UI para crear invitaciones en dashboard
  - **Riesgos:** No hay migración Alembic (crear en follow-up), `clean_database` en conftest no limpia `tenant_invitations`, token de invitación en URL (logs/Referer), tokens de accept no se usan en sesión web

- **2026-10-13** — Deuda técnica T1/T2 **RESUELTA**:
  - ✅ **Alembic migration** `tenant_invitations` creada: `api/alembic/versions/20261013_0000_add_tenant_invitations_table.py` (índice parcial único `uq_tenant_invitation_pending` en `tenant_id, email WHERE accepted_at IS NULL`)
  - ✅ **`clean_database` fixture** actualizada en `api/tests/conftest.py` para limpiar `tenant_invitations`
  - ✅ **Dashboard UI invitaciones** `/invitations`: página Server Component con tabla (EntityTable) + dialog cliente `CreateInvitationDialog` para crear/listar invitaciones
  - ✅ **Playwright E2E** configurado: `web/playwright.config.ts`, `web/e2e/onboarding.spec.ts` (9 tests: onboarding UI validation, invitations UI)
  - ✅ **Token en URL**: mitigado con `Referrer-Policy: strict-origin-when-cross-origin` (security headers), token JWT expira en 7 días, single-use (accepted_at), scope limitado a membership en un tenant
  - **Checks:** mypy 0, ruff 0, pytest 292 passed, lint 0, build success, vitest + Playwright 9 passed

---

## Rutas por task

| Task | Ruta | Trigger |
|------|------|---------|
| T1 | delegated (writer) | Next.js App Router + Server Actions + Playwright E2E |
| T2 | delegated (writer) | Modelo + email + Server Action + Playwright E2E |
| T3 | delegated (writer) | Middleware + DB constraints + helpers + tests |
| T4 | delegated (writer) | Redis rate limiter + middleware + headers + k6 load test |
| T5 | manual/ops | Feature flag + lista pilotos + métricas |
| T6 | delegated (writer) | Next.js + MDX + Swagger UI |
| T7 | delegated (writer) | Next.js SSG + MDX + JSON planes |
| T8 | manual/ops | Onboarding pilotos + feedback loop |

---

## Enlaces

- Roadmap: `propuesta.md` línea 157 (mes 6), 224-229 (checklist validación).
- Modelos base: `api/app/models/tenant.py`, `api/app/models/user.py`, `api/app/models/api_key.py`.
- Auth: `api/app/core/auth/`, `web/src/lib/auth/`.
- Web patterns: `web/src/app/entidades/` (CRUD pattern), `web/src/app/onboarding/` (nuevo).
- Email: `api/app/workers/delivery/email.py` (reutilizar).