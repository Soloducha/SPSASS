'use client';

/**
 * Tabla interactiva de alertas con filtros y paginación bounded.
 * Componente cliente que navega vía URL (Next.js App Router) para refrescar datos del servidor.
 */

import { useState, useEffect, FormEvent, ChangeEvent } from 'react';
import { useRouter, usePathname, useSearchParams } from 'next/navigation';
import { AlertActions } from './AlertActions';
import type { AlertResponse, AlertStatus, AlertSeverity } from '@/lib/api/alerts';

interface AlertsTableProps {
  initialAlerts: AlertResponse[];
  initialHasNext: boolean;
  initialParams: {
    status?: AlertStatus;
    severity?: AlertSeverity;
    rule_id?: string;
    offset: number;
    limit: number;
  };
}

const STATUS_LABELS: Record<AlertStatus, string> = {
  open: 'Abierta',
  acknowledged: 'Reconocida',
  resolved: 'Resuelta',
};

const STATUS_STYLES: Record<AlertStatus, string> = {
  open: 'bg-blue-100 text-blue-800',
  acknowledged: 'bg-amber-100 text-amber-800',
  resolved: 'bg-emerald-100 text-emerald-800',
};

const SEVERITY_STYLES: Record<AlertSeverity, string> = {
  info: 'bg-gray-100 text-gray-800',
  warning: 'bg-amber-100 text-amber-800',
  critical: 'bg-red-100 text-red-800',
};

const SEVERITY_LABELS: Record<AlertSeverity, string> = {
  info: 'Informativa',
  warning: 'Advertencia',
  critical: 'Crítica',
};

export function AlertsTable({
  initialAlerts,
  initialHasNext,
  initialParams,
}: AlertsTableProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const [isLoading, setIsLoading] = useState(false);

  // Filters and pagination state derived from URL (initialParams as fallback for first render)
  const [filters, setFilters] = useState({
    status: initialParams.status ?? '',
    severity: initialParams.severity ?? '',
    rule_id: initialParams.rule_id ?? '',
  });
  const [offset, setOffset] = useState(initialParams.offset);
  const [limit] = useState(initialParams.limit);
  // Use initialHasNext from props (server-rendered) — updated on each navigation
  const hasNext = initialHasNext;

  // Fix 2: Reset isLoading when navigation settles (pathname or searchParams change)
  useEffect(() => {
    const timer = setTimeout(() => setIsLoading(false), 0);
    return () => clearTimeout(timer);
  }, [pathname, searchParams]);

  // Fix 6: Keep filters and offset in sync with the URL after mount
  useEffect(() => {
    const timer = setTimeout(() => {
      setFilters({
        status: searchParams.get('status') ?? '',
        severity: searchParams.get('severity') ?? '',
        rule_id: searchParams.get('rule_id') ?? '',
      });
      setOffset(Number(searchParams.get('offset') ?? 0));
    }, 0);
    return () => clearTimeout(timer);
  }, [searchParams]);

  const buildUrl = (params: {
    status?: string;
    severity?: string;
    rule_id?: string;
    offset: number;
    limit: number;
  }) => {
    const newParams = new URLSearchParams(searchParams.toString());
    if (params.status) newParams.set('status', params.status);
    else newParams.delete('status');
    if (params.severity) newParams.set('severity', params.severity);
    else newParams.delete('severity');
    if (params.rule_id) newParams.set('rule_id', params.rule_id);
    else newParams.delete('rule_id');
    newParams.set('offset', String(params.offset));
    newParams.set('limit', String(params.limit));
    return `${pathname}?${newParams.toString()}`;
  };

  const navigate = (targetOffset: number, opts?: { resetOffset?: boolean; filters?: typeof filters }) => {
    const nextFilters = opts?.filters ?? filters;
    const finalOffset = opts?.resetOffset ? 0 : targetOffset;
    const nextUrl = buildUrl({
      status: nextFilters.status || undefined,
      severity: nextFilters.severity || undefined,
      rule_id: nextFilters.rule_id || undefined,
      offset: finalOffset,
      limit,
    });
    // Fix 2: Guard no-op navigation — if URL unchanged, don't latch isLoading and don't push
    if (nextUrl === `${pathname}?${searchParams.toString()}`) {
      return;
    }
    setIsLoading(true);
    if (opts?.resetOffset) setOffset(0);
    else setOffset(finalOffset);
    router.push(nextUrl);
  };

  const handleFilterChange = (e: ChangeEvent<HTMLSelectElement | HTMLInputElement>) => {
    const { name, value } = e.target;
    // Fix 3: Compute next filters synchronously and pass to navigate to avoid stale closure
    const nextFilters = { ...filters, [name]: value };
    setFilters(nextFilters);
    // Reset offset to 0 when filters change
    navigate(0, { resetOffset: true, filters: nextFilters });
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    navigate(0, { resetOffset: true });
  };

  const handlePrev = () => {
    if (offset > 0) {
      navigate(Math.max(0, offset - limit));
    }
  };

  const handleNext = () => {
    if (hasNext) {
      navigate(offset + limit);
    }
  };

  const formatDate = (dateStr: string) => {
    try {
      return new Date(dateStr).toLocaleString('es', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        timeZone: 'UTC',
        hourCycle: 'h23',
      });
    } catch {
      return dateStr;
    }
  };

  const formatMessage = (message: string) => {
    if (message.length <= 80) return message;
    return `${message.slice(0, 80)}…`;
  };

  // Use initialAlerts from props (server-rendered data) — updated on each navigation
  const alerts = initialAlerts;

  return (
    <section aria-labelledby="alerts-table-heading">
      {/* Filtros */}
      <form onSubmit={handleSubmit} className="mb-6 flex flex-col sm:flex-row gap-4 items-start">
        <div className="flex-1 min-w-[200px]">
          <label htmlFor="filter-status" className="block text-sm font-medium text-gray-700 mb-1">
            Estado
          </label>
          <select
            id="filter-status"
            name="status"
            value={filters.status}
            onChange={handleFilterChange}
            className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-opacity-20 min-h-[44px]"
          >
            <option value="">Todos los estados</option>
            <option value="open">Abierta</option>
            <option value="acknowledged">Reconocida</option>
            <option value="resolved">Resuelta</option>
          </select>
        </div>

        <div className="flex-1 min-w-[200px]">
          <label htmlFor="filter-severity" className="block text-sm font-medium text-gray-700 mb-1">
            Severidad
          </label>
          <select
            id="filter-severity"
            name="severity"
            value={filters.severity}
            onChange={handleFilterChange}
            className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-opacity-20 min-h-[44px]"
          >
            <option value="">Todas las severidades</option>
            <option value="info">Informativa</option>
            <option value="warning">Advertencia</option>
            <option value="critical">Crítica</option>
          </select>
        </div>

        <div className="flex-1 min-w-[200px]">
          <label htmlFor="filter-rule-id" className="block text-sm font-medium text-gray-700 mb-1">
            ID de regla
          </label>
          <input
            type="text"
            id="filter-rule-id"
            name="rule_id"
            value={filters.rule_id}
            onChange={handleFilterChange}
            placeholder="Filtrar por UUID de regla"
            className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-opacity-20 min-h-[44px] font-mono text-xs"
          />
        </div>

        <div className="flex items-end sm:ml-auto">
          <button
            type="submit"
            disabled={isLoading}
            className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-opacity-20 disabled:opacity-50 disabled:cursor-not-allowed min-h-[44px] min-w-[44px]"
          >
            {isLoading ? 'Cargando…' : 'Filtrar'}
          </button>
        </div>
      </form>

      {/* Tabla de alertas */}
      <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white shadow-sm">
        {alerts.length === 0 ? (
          <div className="p-8 text-center text-gray-500">
            {isLoading ? (
              'Cargando alertas…'
            ) : (
              <>
                <p className="font-medium text-gray-900 mb-1">Sin alertas</p>
                <p className="text-sm">No se encontraron alertas con los filtros actuales.</p>
              </>
            )}
          </div>
        ) : (
          <table className="min-w-full divide-y divide-gray-200 text-sm" role="table">
            <thead className="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
              <tr>
                <th className="px-4 py-3" scope="col">ID</th>
                <th className="px-4 py-3" scope="col">Severidad</th>
                <th className="px-4 py-3" scope="col">Estado</th>
                <th className="px-4 py-3" scope="col">Regla</th>
                <th className="px-4 py-3" scope="col">Servidor</th>
                <th className="px-4 py-3" scope="col">Mensaje</th>
                <th className="px-4 py-3" scope="col">Disparada (UTC)</th>
                <th className="px-4 py-3" scope="col">Valor</th>
                <th className="px-4 py-3" scope="col">Acciones</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {alerts.map((alert) => (
                <tr key={alert.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-mono text-xs text-gray-500">
                    {alert.id.slice(0, 8)}…
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${
                        SEVERITY_STYLES[alert.severity]
                      }`}
                    >
                      {SEVERITY_LABELS[alert.severity]}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${
                        STATUS_STYLES[alert.status]
                      }`}
                    >
                      {STATUS_LABELS[alert.status]}
                    </span>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-gray-500">
                    {alert.rule_id.slice(0, 8)}…
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-gray-500">
                    {alert.server_id ? `${alert.server_id.slice(0, 8)}…` : '—'}
                  </td>
                  <td className="px-4 py-3 text-gray-900 max-w-xs truncate" title={alert.message}>
                    {formatMessage(alert.message)}
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-500 whitespace-nowrap">
                    {formatDate(alert.triggered_at)}
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-500 tabular-nums">
                    {alert.value_at_trigger.toFixed(2)}
                  </td>
                  <td className="px-4 py-3">
                    <AlertActions alert={alert} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Paginación */}
      {alerts.length > 0 && (
        <nav
          className="mt-4 flex items-center justify-between"
          aria-label="Paginación de alertas"
        >
          <div className="text-sm text-gray-500" aria-live="polite">
            Mostrando {offset + 1}–{offset + alerts.length}{' '}
            {hasNext ? '+' : ''} (límite: {limit})
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handlePrev}
              disabled={offset === 0 || isLoading}
              className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-opacity-20 disabled:opacity-50 disabled:cursor-not-allowed min-h-[44px] min-w-[44px]"
              aria-label="Página anterior"
            >
              Anterior
            </button>
            <button
              type="button"
              onClick={handleNext}
              disabled={!hasNext || isLoading}
              className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-opacity-20 disabled:opacity-50 disabled:cursor-not-allowed min-h-[44px] min-w-[44px]"
              aria-label="Página siguiente"
            >
              Siguiente
            </button>
          </div>
        </nav>
      )}
    </section>
  );
}