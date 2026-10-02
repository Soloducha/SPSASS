# Feature — Web UI: Servicios, Procesos, Jobs (Mes 4 V1)

> Feature document ODD. Estado: **PLANIFICADO** — Prioridad 2 del Mes 4 (tras auto-restart).

Referencia roadmap: `propuesta.md` línea 155 → **Mes 4 = Procesos + jobs**: UI web para gestión de servicios/procesos/jobs.

---

## Objetivo

Añadir páginas al dashboard Next.js para **CRUD y visualización** de:
- **Servicios** (`/servers/[serverId]/services` o `/services`)
- **Procesos** (`/servers/[serverId]/processes` o `/processes`)
- **Jobs** (`/servers/[serverId]/jobs` o `/jobs`) + historial de ejecuciones (`JobRun`)

Las APIs ya existen en el backend (`/api/v1/services`, `/api/v1/processes`, `/api/v1/jobs`, `/api/v1/jobs/{id}/runs`). El trabajo es **solo frontend**.

---

## Alcance (in/out)

**In (V1 Web UI):**
- **API clients tipados** en `web/src/lib/api/`: `services.ts`, `processes.ts`, `jobs.ts`
- **Páginas Server Components** (SSR) para listado con paginación
- **Páginas Client Components** para crear/editar (forms + Server Actions)
- **Tabla reutilizable** (extender `RulesTable.tsx` o crear componente genérico)
- **Navegación**: enlaces desde `/alertas/reglas` o nueva sección `/entidades` en sidebar
- **Job Runs**: vista de historial de ejecuciones por job (tabla con status, exit_code, output_tail)
- **Auto-restart badge**: mostrar si la entidad tiene `auto_restart=true`

**Out (futuro):**
- Ejecución manual de restart desde UI (botón "Restart now" → POST `/servers/{id}/restart`)
- Gráficos de métricas por entidad (Recharts)
- Filtros avanzados, búsqueda, export CSV
- WebSocket/SSE para updates en tiempo real

---

## Estructura de URLs propuesta

```
/entidades
  /servicios
    page.tsx                    # Lista paginada (SSR)
    nueva/page.tsx              # Crear (Client + Server Action)
    [id]/editar/page.tsx        # Editar (Client + Server Action)
  /procesos
    page.tsx
    nueva/page.tsx
    [id]/editar/page.tsx
  /jobs
    page.tsx
    nueva/page.tsx
    [id]/editar/page.tsx
    [id]/runs/page.tsx          # Historial JobRuns
```

Alternativa: agrupar por servidor (`/servers/[serverId]/services`) pero el backend soporta listado global tenant-scoped.

---

## Tasks

### T1 — API Clients (`web/src/lib/api/`)
- `services.ts`: types + list/create/get/update/delete + `ServiceState` enum
- `processes.ts`: types + list/create/get/update/delete
- `jobs.ts`: types + list/create/get/update/delete + `listJobRuns(jobId)`
- Reutilizar patrón `rules.ts`: `FetchResult<T>`, `fetchWithAuth`, `buildUrl`, paginación bounded

### T2 — Componentes base reutilizables
- `EntityTable.tsx` (genérico): columnas configurables, paginación, actions (edit/delete), loading/error states
- `EntityForm.tsx` (genérico): campos dinámicos según schema, validación client-side (zod o reuse `validation.ts`)
- `EntityActions.tsx`: botones Edit/Delete + confirm dialog (accesible)

### T3 — Servicios (CRUD)
- `services/page.tsx` (Server Component): `listServices` + tabla
- `services/nueva/page.tsx` + `components/CreateServiceForm.tsx`: Server Action `createServiceAction`
- `services/[id]/editar/page.tsx` + `components/EditServiceForm.tsx`: Server Action `updateServiceAction`
- Server Action `deleteServiceAction`

### T4 — Procesos (CRUD)
- Mismo patrón que servicios
- Campo extra: `pattern` (regex), `expected_count`

### T5 — Jobs (CRUD + Runs)
- Mismo patrón CRUD
- Campos extra: `kind` (cron/batch/scheduled), `schedule_cron`, `command`, `timeout_s`, `alert_on_fail`, `auto_restart`
- **Job Runs**: `jobs/[id]/runs/page.tsx` → tabla con `status`, `exit_code`, `started_at`, `finished_at`, `output_tail` (truncado)

### T6 — Navegación + Integración
- Sidebar: nueva sección "Entidades" con sub-items Servicios/Procesos/Jobs
- Breadcrumbs
- Tests: unitarios para API clients + componentes (Vitest + RTL)

---

## Acceptance Criteria

1. **API Clients**: Tipos correctos, mypy/ruff limpio, tests unitarios (list/create/get/update/delete mock)
2. **Listado**: Paginación (offset/limit), loading skeleton, error toast, empty state
3. **Crear/Editar**: Form validado client-side, Server Action llama API, redirect a lista en éxito, error toast en fallo
4. **Eliminar**: Dialog confirmación accesible (role=alertdialog), Server Action, refresh lista
5. **Job Runs**: Tabla con paginación, columnas: status badge, exit_code, timestamps, output_tail (tooltip expandible)
6. **Auto-restart badge**: Chip/badge visible en fila si `auto_restart=true`
7. **Checks**: `pnpm run lint` + `pnpm run build` + `pnpm run test` verdes

---

## Route Declaration

| Task | Route | Trigger Evidence |
|------|-------|------------------|
| T1 | Delegated direct (writer) | 3 nuevos archivos API client tipados (~150 líneas c/u) |
| T2 | Delegated direct (writer) | Componentes base reutilizables (Table, Form, Actions) |
| T3 | Delegated direct (writer) | 4 archivos: page, nueva, editar, components |
| T4 | Delegated direct (writer) | 4 archivos: page, nueva, editar, components |
| T5 | Delegated direct (writer) | 5 archivos: page, nueva, editar, runs, components |
| T6 | Delegated direct (writer) | Sidebar + breadcrumbs + tests |

---

## Delivery Strategy

Forecast: ~3000 líneas (incl. tests). Supera 400 → `ask-on-risk` + chain `stacked-to-main`.
Slices: T1+T2 (API + base) → PR 1; T3 (Servicios) → PR 2; T4 (Procesos) → PR 3; T5 (Jobs) → PR 4; T6 (Nav) → PR 5.