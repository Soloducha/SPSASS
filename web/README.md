# SPSAAS Web — Next.js 16 (scaffold)

Frontend de SPSAAS. Next.js 16 (App Router) + TypeScript + Tailwind CSS 4. Hoy es un scaffold mínimo: landing placeholder, sin dashboards ni llamadas a la API.

## Stack

- Next.js 16.3.5, React 19.3.0, TypeScript 5.7
- Tailwind CSS 4 (vía PostCSS, sin `tailwind.config.ts`)
- pnpm (vía corepack) + Node 24

## Desarrollo local

```bash
cd web
pnpm install
pnpm dev        # http://localhost:3000
```

## Docker

```bash
# Desde la raíz del monorepo
docker compose build web
docker compose up web
```

El servicio expone el puerto **3000** y monta `./web:/app` con volúmenes para `node_modules` y `.next` (hot reload en desarrollo).

## Estructura

```
web/
├── src/
│   └── app/
│       ├── globals.css        # Tailwind imports
│       ├── layout.tsx         # Root layout + metadata
│       └── page.tsx           # Landing placeholder
├── Dockerfile                 # Multi-stage (base → deps → builder → runner → dev)
├── next.config.mjs            # output: 'standalone'
├── package.json
├── pnpm-lock.yaml
├── pnpm-workspace.yaml
├── postcss.config.mjs
└── tsconfig.json
```

## Notas

- **Sin dashboards ni llamadas a API** — scaffold mínimo. El dashboard v0.1 (estado general + servidores) es el próximo slice del roadmap (mes 2).
- `output: 'standalone'` en `next.config.mjs` genera una imagen de producción mínima.
- El `Dockerfile` usa `pnpm` vía `corepack` sobre **Node 24**; el target por defecto en compose es `dev`, y `runner` es la imagen de producción.