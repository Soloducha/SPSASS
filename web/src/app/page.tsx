import type { ReactElement } from 'react';

import { getDashboardToken, getSpsaasApiUrl } from '@/lib/config';

// SSR en vivo: el dashboard siempre se genera por request con el token de
// runtime; nunca se prerenderiza en build time.
export const dynamic = 'force-dynamic';

// ──────────────────────────────────────────────
// Tipos del API (espejo de app/api/v1/dashboard.py)
// ──────────────────────────────────────────────
type ServerStatus = 'online' | 'offline' | 'degraded' | 'unknown';

interface DashboardTotals {
  total: number;
  online: number;
  offline: number;
  degraded: number;
  unknown: number;
}

interface ServerOverviewItem {
  id: string;
  hostname: string;
  ip: string | null;
  os: string | null;
  status: ServerStatus;
  last_heartbeat_at: string | null;
  latest_metrics: Record<string, number>;
}

interface DashboardOverview {
  totals: DashboardTotals;
  servers: ServerOverviewItem[];
}

// ──────────────────────────────────────────────
// Fetch server-side (SSR). El token de servicio es un
// bridge temporal: cuando exista login web (mes 3+),
// esto pasa a autenticación del usuario.
// ──────────────────────────────────────────────
async function getOverview(): Promise<DashboardOverview> {
  const token = getDashboardToken();
  if (!token) {
    throw new Error('SPSAAS_DASHBOARD_TOKEN no está configurado');
  }
  const res = await fetch(`${getSpsaasApiUrl()}/api/v1/dashboard/overview`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: 'no-store',
  });
  if (!res.ok) {
    throw new Error(`API respondió ${res.status}`);
  }
  return res.json() as Promise<DashboardOverview>;
}

// ──────────────────────────────────────────────
// Presentación
// ──────────────────────────────────────────────
const STATUS_LABELS: Record<ServerStatus, string> = {
  online: 'En línea',
  offline: 'Desconectado',
  degraded: 'Degradado',
  unknown: 'Desconocido',
};

const STATUS_STYLES: Record<ServerStatus, string> = {
  online: 'bg-emerald-100 text-emerald-800',
  offline: 'bg-red-100 text-red-800',
  degraded: 'bg-amber-100 text-amber-800',
  unknown: 'bg-gray-100 text-gray-700',
};

const METRIC_LABELS: Record<string, string> = {
  cpu_usage: 'CPU',
  mem_usage: 'Memoria',
  disk_usage: 'Disco',
  load_avg1: 'Carga 1m',
  load_avg5: 'Carga 5m',
  load_avg15: 'Carga 15m',
};

function MetricBar({ label, value }: { label: string; value: number }) {
  const pct = Math.min(Math.max(value, 0), 100);
  return (
    <div className="flex items-center gap-2">
      <span className="w-20 shrink-0 text-xs text-gray-500">{label}</span>
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-gray-200">
        <div
          className="h-full rounded-full bg-indigo-500"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="w-10 shrink-0 text-right text-xs tabular-nums text-gray-600">
        {value.toFixed(1)}
      </span>
    </div>
  );
}

function TotalsCards({ totals }: { totals: DashboardTotals }): ReactElement {
  const cards = [
    { label: 'Servidores', value: totals.total, style: 'text-gray-900' },
    { label: 'En línea', value: totals.online, style: 'text-emerald-600' },
    { label: 'Desconectados', value: totals.offline, style: 'text-red-600' },
    { label: 'Degradados', value: totals.degraded, style: 'text-amber-600' },
  ];
  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
      {cards.map((card) => (
        <div
          key={card.label}
          className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm"
        >
          <p className="text-sm text-gray-500">{card.label}</p>
          <p className={`mt-1 text-3xl font-bold tabular-nums ${card.style}`}>
            {card.value}
          </p>
        </div>
      ))}
    </div>
  );
}

function ServerTable({ servers }: { servers: ServerOverviewItem[] }): ReactElement {
  if (servers.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-gray-300 bg-white p-8 text-center text-gray-500">
        Sin servidores registrados todavía.
      </div>
    );
  }
  return (
    <div className="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
      <table className="min-w-full divide-y divide-gray-200 text-sm">
        <thead className="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
          <tr>
            <th className="px-4 py-3">Servidor</th>
            <th className="px-4 py-3">Estado</th>
            <th className="px-4 py-3">Últimas métricas</th>
            <th className="px-4 py-3">Último heartbeat</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {servers.map((server) => {
            const metrics = Object.entries(server.latest_metrics).filter(
              ([key]) => METRIC_LABELS[key] !== undefined,
            );
            return (
              <tr key={server.id}>
                <td className="px-4 py-3">
                  <p className="font-medium text-gray-900">{server.hostname}</p>
                  <p className="text-xs text-gray-500">
                    {server.ip ?? '—'} {server.os ? `· ${server.os}` : ''}
                  </p>
                </td>
                <td className="px-4 py-3">
                  <span
                    className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_STYLES[server.status]}`}
                  >
                    {STATUS_LABELS[server.status]}
                  </span>
                </td>
                <td className="px-4 py-3">
                  {metrics.length === 0 ? (
                    <span className="text-xs text-gray-400">Sin métricas</span>
                  ) : (
                    <div className="w-56 space-y-1.5">
                      {metrics.map(([key, value]) => (
                        <MetricBar
                          key={key}
                          label={METRIC_LABELS[key]}
                          value={value}
                        />
                      ))}
                    </div>
                  )}
                </td>
                <td className="px-4 py-3 text-xs text-gray-500">
                  {server.last_heartbeat_at
                    ? new Date(server.last_heartbeat_at).toLocaleString('es-AR')
                    : '—'}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default async function HomePage() {
  let overview: DashboardOverview;
  let error: string | null = null;

  try {
    overview = await getOverview();
  } catch (e) {
    error = e instanceof Error ? e.message : 'Error desconocido';
    overview = { totals: { total: 0, online: 0, offline: 0, degraded: 0, unknown: 0 }, servers: [] };
  }

  return (
    <main className="mx-auto max-w-6xl px-4 py-10">
      <header className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">SPSAAS</h1>
        <p className="mt-1 text-sm text-gray-500">
          Monitoreo para entornos legacy y Linux
        </p>
      </header>

      {error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          No se pudo cargar el dashboard: {error}
        </div>
      ) : (
        <div className="space-y-8">
          <TotalsCards totals={overview.totals} />
          <section>
            <h2 className="mb-3 text-lg font-semibold text-gray-900">Servidores</h2>
            <ServerTable servers={overview.servers} />
          </section>
        </div>
      )}
    </main>
  );
}