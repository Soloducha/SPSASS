'use client';

/**
 * Tabla interactiva de reglas de alerta con paginación bounded.
 * Componente cliente para manejar estado de paginación sin recargar el servidor.
 * Acciones: toggle enabled/disabled, eliminar con confirmación.
 */

import { useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { toggleRuleEnabledAction, deleteAlertRuleAction } from '../actions';
import type { AlertRuleResponse, EntityType, AlertOperator, AlertSeverity } from '@/lib/api/rules';

interface RulesTableProps {
  initialRules: AlertRuleResponse[];
  initialHasNext: boolean;
  initialParams: {
    offset: number;
    limit: number;
  };
}

const ENTITY_TYPE_LABELS: Record<EntityType, string> = {
  server: 'Servidor',
  service: 'Servicio',
  process: 'Proceso',
  job: 'Tarea',
  metric: 'Métrica',
};

const OPERATOR_LABELS: Record<AlertOperator, string> = {
  gt: '>',
  gte: '≥',
  lt: '<',
  lte: '≤',
  eq: '=',
  neq: '≠',
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

function formatChannels(channels: AlertRuleResponse['channels']): string {
  const parts: string[] = [];
  if (channels.email && channels.email.to.length > 0) {
    parts.push(`Email: ${channels.email.to.join(', ')}`);
  }
  if (channels.webhook) {
    parts.push(`Webhook: ${channels.webhook.url}`);
  }
  return parts.length > 0 ? parts.join('; ') : '—';
}

export function RulesTable({
  initialRules,
  initialHasNext,
  initialParams,
}: RulesTableProps) {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [rules, setRules] = useState<AlertRuleResponse[]>(initialRules);
  const [hasNext] = useState(initialHasNext);
  const [isLoading, setIsLoading] = useState(false);
  const [offset, setOffset] = useState(initialParams.offset);
  const [limit] = useState(initialParams.limit);
  const [actionFeedback, setActionFeedback] = useState<string | null>(null);
  const [actionStatus, setActionStatus] = useState<'success' | 'error' | null>(null);

  const buildUrl = (newOffset: number) => {
    const params = new URLSearchParams(searchParams.toString());
    params.set('offset', String(newOffset));
    params.set('limit', String(limit));
    return `/alertas/reglas?${params.toString()}`;
  };

  const handleToggle = async (ruleId: string, newIsActive: boolean) => {
    setActionFeedback(null);
    setActionStatus(null);
    setIsLoading(true);

    const formData = new FormData();
    formData.append('ruleId', ruleId);
    formData.append('is_active', String(newIsActive));

    try {
      const result = await toggleRuleEnabledAction({ rule: null, error: undefined }, formData);
      if (result.error) {
        setActionFeedback(result.error);
        setActionStatus('error');
      } else {
        setRules(rules.map(r => (r.id === ruleId ? { ...r, is_active: newIsActive } : r)));
        setActionFeedback(newIsActive ? 'Regla activada' : 'Regla desactivada');
        setActionStatus('success');
      }
    } catch (err) {
      setActionFeedback(err instanceof Error ? err.message : 'Error al cambiar el estado');
      setActionStatus('error');
    } finally {
      setIsLoading(false);
    }
  };

  const handleDelete = async (ruleId: string) => {
    if (!confirm('¿Eliminar esta regla de alerta? Esta acción no se puede deshacer.')) {
      return;
    }

    setActionFeedback(null);
    setActionStatus(null);
    setIsLoading(true);

    const formData = new FormData();
    formData.append('ruleId', ruleId);

    try {
      const result = await deleteAlertRuleAction({ success: false, error: undefined }, formData);
      if (result.error) {
        setActionFeedback(result.error);
        setActionStatus('error');
      } else {
        setRules(rules.filter(r => r.id !== ruleId));
        setActionFeedback('Regla eliminada');
        setActionStatus('success');
      }
    } catch (err) {
      setActionFeedback(err instanceof Error ? err.message : 'Error al eliminar la regla');
      setActionStatus('error');
    } finally {
      setIsLoading(false);
    }
  };

  const handlePrev = () => {
    if (offset > 0) {
      const newOffset = Math.max(0, offset - limit);
      setOffset(newOffset);
      router.push(buildUrl(newOffset));
    }
  };

  const handleNext = () => {
    if (hasNext) {
      const newOffset = offset + limit;
      setOffset(newOffset);
      router.push(buildUrl(newOffset));
    }
  };

  return (
    <section aria-labelledby="rules-table-heading">
      <div className="mb-4" role="status" aria-live="polite" aria-atomic="true">
        {actionFeedback && (
          <div
            className={`rounded-lg p-4 text-sm ${
              actionStatus === 'success'
                ? 'border border-emerald-200 bg-emerald-50 text-emerald-700'
                : 'border border-red-200 bg-red-50 text-red-700'
            }`}
            role="alert"
            aria-live="polite"
          >
            {actionFeedback}
          </div>
        )}
      </div>

      {/* Tabla de reglas */}
      <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white shadow-sm">
        {rules.length === 0 ? (
          <div className="p-8 text-center text-gray-500">
            {isLoading ? (
              'Cargando reglas…'
            ) : (
              <>
                <p className="font-medium text-gray-900 mb-1">Sin reglas</p>
                <p className="text-sm">No se encontraron reglas de alerta.</p>
              </>
            )}
          </div>
        ) : (
          <table className="min-w-full divide-y divide-gray-200 text-sm" role="table">
            <thead className="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
              <tr>
                <th className="px-4 py-3" scope="col">Entidad</th>
                <th className="px-4 py-3" scope="col">ID Entidad</th>
                <th className="px-4 py-3" scope="col">Métrica</th>
                <th className="px-4 py-3" scope="col">Operador</th>
                <th className="px-4 py-3" scope="col">Umbral</th>
                <th className="px-4 py-3" scope="col">Duración (s)</th>
                <th className="px-4 py-3" scope="col">Severidad</th>
                <th className="px-4 py-3" scope="col">Canales</th>
                <th className="px-4 py-3" scope="col">Estado</th>
                <th className="px-4 py-3" scope="col">Acciones</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {rules.map((rule) => (
                <tr key={rule.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 text-gray-900">
                    {ENTITY_TYPE_LABELS[rule.entity_type] ?? rule.entity_type}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-gray-500">
                    {rule.entity_id ? `${rule.entity_id.slice(0, 8)}…` : '— (todas)'}
                  </td>
                  <td className="px-4 py-3 font-mono text-sm text-gray-900 max-w-xs truncate" title={rule.metric}>
                    {rule.metric}
                  </td>
                  <td className="px-4 py-3 text-center font-mono text-sm text-gray-700">
                    {OPERATOR_LABELS[rule.operator] ?? rule.operator}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-gray-900">
                    {rule.threshold.toFixed(2)}
                  </td>
                  <td className="px-4 py-3 text-center tabular-nums text-gray-900">
                    {rule.duration_s}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${SEVERITY_STYLES[rule.severity]}`}
                    >
                      {SEVERITY_LABELS[rule.severity]}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-600 max-w-xs truncate" title={formatChannels(rule.channels)}>
                    {formatChannels(rule.channels)}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${
                        rule.is_active ? 'bg-emerald-100 text-emerald-800' : 'bg-gray-100 text-gray-800'
                      }`}
                    >
                      {rule.is_active ? 'Activa' : 'Inactiva'}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => handleToggle(rule.id, !rule.is_active)}
                        disabled={isLoading}
                        className={`rounded-md px-3 py-1.5 text-sm font-medium min-h-[44px] min-w-[44px] focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-opacity-20 disabled:opacity-50 disabled:cursor-not-allowed transition-colors ${
                          rule.is_active
                            ? 'bg-amber-600 text-white hover:bg-amber-700'
                            : 'bg-emerald-600 text-white hover:bg-emerald-700'
                        }`}
                        aria-label={rule.is_active ? 'Desactivar regla' : 'Activar regla'}
                      >
                        {rule.is_active ? 'Desactivar' : 'Activar'}
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDelete(rule.id)}
                        disabled={isLoading}
                        className="rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-opacity-20 disabled:opacity-50 disabled:cursor-not-allowed min-h-[44px] min-w-[44px]"
                        aria-label="Eliminar regla"
                      >
                        Eliminar
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Paginación */}
      {rules.length > 0 && (
        <nav
          className="mt-4 flex items-center justify-between"
          aria-label="Paginación de reglas"
        >
          <div className="text-sm text-gray-500" aria-live="polite">
            Mostrando {offset + 1}–{offset + rules.length}{' '}
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