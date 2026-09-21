# Feature: Bump web a Next.js 16 + React 19

- **Estado**: en progreso
- **Rama**: `feature/next16-web` (basada en feature/fundaciones, sin main aún)
- **Última actualización**: 2026-09-21

## Objetivo

Migrar `web/` de Next 14.2.16 (placeholder vulnerable) a **Next 16.3.5 + React 19.3.0 + ESLint flat config**, cerrando todos los advisories de seguridad conocidos (CVE-2025-29927, CVE-2025-57822, CVE-2025-55183/55184 y la clase 2026 que solo se parcha en 15.5+/16.2+).

## Problema

- `next@14.2.16` tiene múltiples CVEs conocidos y la línea 14.x ya no recibe fixes de seguridad (los fixes 2026 son solo para 15.5.16+/16.2.5+).
- La línea 14.2.35 (máximo del 14.x) NO cierra la clase 2026.
- El web es un placeholder (~3 archivos de app) → coste de migración mínimo AHORA.

## Alcance

- `web/package.json`: next 16.3.5, react/react-dom 19.3.0, @types/react 19.3.0, eslint ^9 + eslint-config-next 16.3.5
- `web/pnpm-lock.yaml`: regenerar (frozen-lockfile en Dockerfile)
- Nuevo `web/eslint.config.mjs` (flat config, porque Next 16 elimina `next lint`)
- `web/package.json` script `lint`: `next lint` → `eslint .`
- `web/Dockerfile`: comentario de encabezado Next.js 14 → 16 (no requiere cambios de runtime: node:20-alpine ≥20.9 ok; `output: 'standalone'` sigue soportado)
- `docker-compose.yml`: comentario del servicio web

## Fuera de alcance

- No migrar a Tailwind 4 (se queda en 3.4.15, compatible)
- No migrar la API ni el worker
- No crear PR/main aún (decisión del usuario pendiente)

## Tareas

- [x] T1: Actualizar `web/package.json` con Next 16.3.5 + React 19.3.0 + devDeps eslint flat
- [x] T2: Crear `web/eslint.config.mjs` flat config + cambiar script lint
- [x] T3: Regenerar `pnpm-lock.yaml` y verificar `pnpm install --frozen-lockfile`
- [x] T4: Actualizar comentarios Dockerfile + docker-compose.yml
- [x] T5: Verificación: `pnpm lint`, `pnpm build`, `docker compose build web`

## Progreso

- 2026-09-21: investigación (Snyk, NCSC, advisories Next.js, registry npm) → decisión Next 16; rama `feature/next16-web` creada.

## Checks

- `corepack pnpm install --frozen-lockfile` (en web/) exitoso
- `pnpm lint` exitoso
- `pnpm build` exitoso
- `docker compose build web` en root repo exitoso
- `git log` con commits work-unit convencionales