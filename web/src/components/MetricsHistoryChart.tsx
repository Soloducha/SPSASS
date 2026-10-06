"use client";

import type { ReactElement } from 'react';
import { useState, useEffect, useCallback } from 'react';
import {
  Line,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import { format } from 'date-fns';
import { es } from 'date-fns/locale';

import { getDashboardToken, getSpsaasApiUrl } from '@/lib/config';

export interface MetricHistoryPoint {
  bucket_start: string;
  avg: number;
  min: number;
  max: number;
  last: number;
  count: number;
}

interface MetricHistoryResponse {
  server_id: string;
  type: string;
  period: string;
  points: MetricHistoryPoint[];
}

interface ServerOption {
  value: string;
  label: string;
}

const METRIC_OPTIONS = [
  { value: 'cpu_usage', label: 'CPU' },
  { value: 'mem_usage', label: 'Memoria' },
  { value: 'disk_usage', label: 'Disco' },
  { value: 'load_avg1', label: 'Carga 1m' },
  { value: 'load_avg5', label: 'Carga 5m' },
  { value: 'load_avg15', label: 'Carga 15m' },
] as const;

const PERIOD_OPTIONS = [
  { value: '1m', label: '1 minuto' },
  { value: '5m', label: '5 minutos' },
  { value: '1h', label: '1 hora' },
  { value: '1d', label: '1 día' },
] as const;

const TIME_RANGE_OPTIONS = [
  { value: '1h', label: 'Última hora', hours: 1 },
  { value: '6h', label: 'Últimas 6 horas', hours: 6 },
  { value: '24h', label: 'Últimas 24 horas', hours: 24 },
  { value: '7d', label: 'Últimos 7 días', hours: 168 },
  { value: '30d', label: 'Últimos 30 días', hours: 720 },
] as const;

interface MetricsHistoryChartProps {
  servers: ServerOption[];
}

interface ServerOption {
  value: string;
  label: string;
}

export function MetricsHistoryChart({ servers }: MetricsHistoryChartProps): ReactElement {
  const [selectedServer, setSelectedServer] = useState<string>(() => {
    // Initialize with first server if available
    // Note: servers prop may not be available yet during initial render
    // This will be '' initially and updated via useEffect
    return '';
  });
  const [selectedMetric, setSelectedMetric] = useState('cpu_usage');
  const [selectedPeriod, setSelectedPeriod] = useState('5m');
  const [selectedTimeRange, setSelectedTimeRange] = useState('24h');
  const [data, setData] = useState<{ bucket_start: string; avg: number; min: number; max: number; last: number }[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Initialize selectedServer from servers prop
  /* eslint-disable react-hooks/exhaustive-deps, react-hooks/set-state-in-effect */
  useEffect(() => {
    if (servers.length > 0 && !selectedServer) {
      setSelectedServer(servers[0].value);
    }
  }, [servers, selectedServer]);
  /* eslint-enable react-hooks/exhaustive-deps, react-hooks/set-state-in-effect */

  const fetchData = useCallback(async () => {
    if (!selectedServer) return;

    setLoading(true);
    setError(null);

    try {
      const token = getDashboardToken();
      if (!token) throw new Error('Token no configurado');

      const now = new Date();
      const timeRange = TIME_RANGE_OPTIONS.find(t => t.value === selectedTimeRange);
      const from = new Date(now.getTime() - (timeRange?.hours ?? 24) * 60 * 60 * 1000);
      const to = now;

      const params = new URLSearchParams({
        server_id: selectedServer,
        type: selectedMetric,
        period: selectedPeriod,
        from_ts: from.toISOString(),
        to_ts: to.toISOString(),
        max_points: '500',
      });

      const res = await fetch(`${getSpsaasApiUrl()}/api/v1/dashboard/metrics/history?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
        cache: 'no-store',
      });

      if (!res.ok) throw new Error(`API respondió ${res.status}`);

      const json = await res.json();
      setData(json.points ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error desconocido');
      setData([]);
    } finally {
      setLoading(false);
    }
  }, [selectedServer, selectedMetric, selectedPeriod, selectedTimeRange]);

  // Trigger fetch when selectedServer changes
  /* eslint-disable react-hooks/exhaustive-deps, react-hooks/set-state-in-effect */
  useEffect(() => {
    if (selectedServer) {
      fetchData();
    }
  }, [selectedServer, fetchData]);
  /* eslint-enable react-hooks/exhaustive-deps, react-hooks/set-state-in-effect */

  const metricLabel = METRIC_OPTIONS.find(m => m.value === selectedMetric)?.label ?? selectedMetric;
  const periodLabel = PERIOD_OPTIONS.find(p => p.value === selectedPeriod)?.label ?? selectedPeriod;
  const timeRangeLabel = TIME_RANGE_OPTIONS.find(t => t.value === selectedTimeRange)?.label ?? selectedTimeRange;

  return (
    <section className="space-y-6">
      {/* Controles */}
      <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
        <div className="grid gap-4 sm:grid-cols-4">
          <div>
            <label htmlFor="server-select" className="block text-sm font-medium text-gray-700 mb-1">
              Servidor
            </label>
            <select
              id="server-select"
              value={selectedServer}
              onChange={e => setSelectedServer(e.target.value)}
              className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-opacity-20 min-h-[44px]"
            >
              {servers.map(s => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="metric-select" className="block text-sm font-medium text-gray-700 mb-1">
              Métrica
            </label>
            <select
              id="metric-select"
              value={selectedMetric}
              onChange={e => setSelectedMetric(e.target.value)}
              className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-opacity-20 min-h-[44px]"
            >
              {METRIC_OPTIONS.map(m => (
                <option key={m.value} value={m.value}>
                  {m.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="period-select" className="block text-sm font-medium text-gray-700 mb-1">
              Período (rollup)
            </label>
            <select
              id="period-select"
              value={selectedPeriod}
              onChange={e => setSelectedPeriod(e.target.value)}
              className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-opacity-20 min-h-[44px]"
            >
              {PERIOD_OPTIONS.map(p => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="timerange-select" className="block text-sm font-medium text-gray-700 mb-1">
              Rango temporal
            </label>
            <select
              id="timerange-select"
              value={selectedTimeRange}
              onChange={e => setSelectedTimeRange(e.target.value)}
              className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-opacity-20 min-h-[44px]"
            >
              {TIME_RANGE_OPTIONS.map(t => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="mt-3 flex flex-wrap gap-2 text-sm text-gray-500">
          <span>Métrica: <strong>{METRIC_OPTIONS.find(m => m.value === selectedMetric)?.label}</strong></span>
          <span>Período: <strong>{PERIOD_OPTIONS.find(p => p.value === selectedPeriod)?.label}</strong></span>
          <span>Rango: <strong>{TIME_RANGE_OPTIONS.find(t => t.value === selectedTimeRange)?.label}</strong></span>
        </div>
      </div>

      {/* Gráfico */}
      <div className="rounded-lg border border-gray-200 bg-white shadow-sm">
        {error ? (
          <div className="p-4 text-red-600">
            Error al cargar datos: {error}
          </div>
        ) : loading ? (
          <div className="h-80 flex items-center justify-center text-gray-500">
            Cargando métricas históricas...
          </div>
        ) : data.length === 0 ? (
          <div className="h-80 flex items-center justify-center text-gray-400">
            Sin datos disponibles para el período seleccionado
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={400}>
            <AreaChart data={data} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="colorAvg" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis
                dataKey="bucket_start"
                tickFormatter={value => format(new Date(value), 'HH:mm', { locale: es })}
                tick={{ fontSize: 11, fill: '#6b7280' }}
                interval="preserveStartEnd"
              />
              <YAxis
                tick={{ fontSize: 11, fill: '#6b7280' }}
                label={{ value: metricLabel, angle: -90, position: 'insideLeft', offset: 10, fill: '#6b7280', fontSize: 11 }}
              />
              <Tooltip
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                formatter={(value: any) => [typeof value === 'number' ? value.toFixed(1) : '', '']}
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                labelFormatter={(value: any) => format(new Date(value), 'dd/MM/yyyy HH:mm', { locale: es })}
                contentStyle={{
                  backgroundColor: '#fff',
                  border: '1px solid #e5e7eb',
                  borderRadius: '8px',
                  boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)',
                }}
              />
              <Legend />
              <Area
                type="monotone"
                dataKey="avg"
                name="Promedio"
                stroke="#3b82f6"
                fillOpacity={1}
                fill="url(#colorAvg)"
              />
              <Line
                type="monotone"
                dataKey="min"
                name="Mínimo"
                stroke="#10b981"
                strokeDasharray="5 5"
                dot={false}
              />
              <Line
                type="monotone"
                dataKey="max"
                name="Máximo"
                stroke="#ef4444"
                strokeDasharray="5 5"
                dot={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}

        <div className="mt-4 flex flex-wrap gap-4 text-xs text-gray-500">
          <span>🔵 Promedio (área)</span>
          <span>🟢 Mínimo (línea discontinua)</span>
          <span>🔴 Máximo (línea discontinua)</span>
          <span>Puntos: {data.length}</span>
        </div>
      </div>
    </section>
  );
}