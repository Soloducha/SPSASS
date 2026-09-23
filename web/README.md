# SPSAAS Web — Next.js 16

Frontend de SPSAAS. Next.js 16 (App Router) + TypeScript + Tailwind CSS 4. Incluye el dashboard v0.1 (estado general + servidores con últimas métricas) como server component que consume la API.

## Stack

- Next.js 16.3.5, React 19.3.0, TypeScript 5.7
- Tailwind CSS 4 (vía PostCSS, sin `tailwind.config.ts`)
- pnpm (vía corepack) + Node 24

## Variables de entorno (dashboard v0.1)

El dashboard se renderiza en el server (SSR, `dynamic = "force-dynamic"`) y necesita:

- `SPSAAS_API_URL` — base URL de la API. En Docker se resuelve por nombre de servicio: `http://api:8000`. En dev local: `http://localhost:8000`.
- `SPSAAS_DASHBOARD_TOKEN` — JWT de acceso con el que la web fetchea el endpoint. Es un puente temporal hasta el login web: hoy se genera con `POST /auth/login` (credenciales de un usuario del tenant) y se inyecta vía entorno. Sin él, la web muestra "SPSAAS_DASHBOARD_TOKEN no está configurado".

En `docker compose` se pasa así (el token no tiene default por ser secreto):

```bash
export SPSAAS_DASHBOARD_TOKEN=<jwt>
docker compose up -d web
```

## Desarrollo local

```bash
cd web
pnpm install
SPSAAS_API_URL=http://localhost:8000 SPSAAS_DASHBOARD_TOKEN=<jwt> pnpm dev   # http://localhost:3000
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
│   ├── app/
│   │   ├── globals.css        # Tailwind imports
│   │   ├── layout.tsx         # Root layout + metadata
│   │   └── page.tsx           # Dashboard v0.1 (SSR)
│   └── lib/
│       └── config.ts          # Getters de env en request time (SPSAAS_API_URL, SPSAAS_DASHBOARD_TOKEN)
├── Dockerfile                 # Multi-stage (base → deps → builder → runner → dev)
├── next.config.mjs            # output: 'standalone'
├── package.json
├── pnpm-lock.yaml
├── pnpm-workspace.yaml
├── postcss.config.mjs
└── tsconfig.json
```

## Notas

- `output: 'standalone'` en `next.config.mjs` genera una imagen de producción mínima.
- El `Dockerfile` usa `pnpm` vía `corepack` sobre **Node 24**; el target por defecto en compose es `dev`, y `runner` es la imagen de producción.
- El login web (auth real en el frontend) reemplazará el token de servicio en un slice futuro.