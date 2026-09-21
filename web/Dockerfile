# Multi-stage Dockerfile for Next.js 16
# Usage:
#   Development (hot reload): docker compose up web
#   Production build:        docker build --target runner -t spsaas-web ./web

# ──────────────────────────────────────────────
# Stage 1: Base — shared dependencies
# Node 24 (Krypton) — Active LTS until 2028-04-30 (Node 20 reached EOL 2026-04-30)
# ──────────────────────────────────────────────
FROM node:24-alpine AS base
WORKDIR /app
ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"
ENV NEXT_TELEMETRY_DISABLED=1
RUN corepack enable && corepack prepare pnpm@latest --activate

# ──────────────────────────────────────────────
# Stage 2: Dependencies — install all deps
# ──────────────────────────────────────────────
FROM base AS deps
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

# ──────────────────────────────────────────────
# Stage 3: Builder — build the Next.js app
# ──────────────────────────────────────────────
FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN pnpm run build

# ──────────────────────────────────────────────
# Stage 4: Runner — minimal production image
# ──────────────────────────────────────────────
FROM node:24-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Create non-root user
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# Copy built assets
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["node", "server.js"]

# ──────────────────────────────────────────────
# Stage 5: Dev — development image (DEFAULT target)
# ──────────────────────────────────────────────
FROM base AS dev
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
EXPOSE 3000
CMD ["pnpm", "dev", "-H", "0.0.0.0"]