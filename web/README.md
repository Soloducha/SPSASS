# SPSAAS Web — Next.js 14 Placeholder

Frontend placeholder para SPSAAS. Next.js 14 (App Router) + TypeScript + Tailwind CSS.

## Desarrollo local

```bash
cd web
npm install        # o pnpm install
npm run dev        # http://localhost:3000
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
│       ├── globals.css      # Tailwind imports
│       ├── layout.tsx       # Root layout + metadata
│       └── page.tsx         # Landing placeholder
├── Dockerfile               # Multi-stage (base → deps → builder → runner)
├── next.config.mjs          # output: 'standalone'
├── package.json
├── postcss.config.mjs
├── tailwind.config.ts
└── tsconfig.json
```

## Notas

- **No hay dashboards ni llamadas a API** — esto es un placeholder mínimo (mes 1).
- Los dashboards y la integración real con la API llegarán en meses 2+.
- `output: 'standalone'` en `next.config.mjs` genera una imagen de producción mínima.
- El `Dockerfile` usa `pnpm` vía `corepack` (incluido en Node 20).