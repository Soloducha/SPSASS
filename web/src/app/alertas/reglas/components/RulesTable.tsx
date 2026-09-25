'use client';

/**
 * Tabla interactiva de reglas de alerta con paginación bounded.
 * Componente cliente para manejar estado de paginación sin recargar el servidor.
 * Acciones: toggle enabled/disabled, editar, eliminar con confirmación accesible.
 * Responsive: tabla con scroll horizontal en desktop, tarjetas apiladas <768px.
 */

import { useState, useRef, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
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

// WCAG AA compliant contrast for severity chips
const SEVERITY_STYLES: Record<AlertSeverity, string> = {
  info: 'bg-blue-100 text-blue-800',
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

/**
 * Accessible confirmation dialog component.
 * - Labelled, keyboard reachable, dismissible with Escape
 * - Focus moved into dialog on open, restored on close
 * - Background not silently interactive (inert via aria-modal)
 * - Full-screen on mobile
 */
function ConfirmDialog({
  isOpen,
  onClose,
  onConfirm,
  title,
  message,
  confirmText = 'Eliminar',
  isLoading = false,
  triggerElement,
}: {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  message: string;
  confirmText?: string;
  isLoading?: boolean;
  triggerElement: HTMLButtonElement | null;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    if (isOpen) {
      dialogRef.current?.showModal();
      // Focus the confirm button for keyboard users
      setTimeout(() => {
        const confirmBtn = dialogRef.current?.querySelector('[data-confirm]') as HTMLElement;
        confirmBtn?.focus();
      }, 0);
    } else {
      dialogRef.current?.close();
      // Restore focus to trigger button
      triggerElement?.focus();
    }

    const handleKeyDown = (e: KeyboardEvent) => {
      if (!isOpen) return;
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose, triggerElement]);

  const handleBackdropClick = (e: React.MouseEvent<HTMLDialogElement>) => {
    // Only close if clicking directly on the backdrop, not the dialog content
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  if (!isOpen) return null;

  return (
    <dialog
      ref={dialogRef}
      className="dialog-container"
      onClick={handleBackdropClick}
      aria-modal="true"
      aria-labelledby="dialog-title"
      aria-describedby="dialog-message"
    >
      <div className="dialog-content" role="document">
        <h2 id="dialog-title" className="text-lg font-semibold text-gray-900 mb-2">
          {title}
        </h2>
        <p id="dialog-message" className="text-sm text-gray-600 mb-6">
          {message}
        </p>
        <div className="flex justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            disabled={isLoading}
            className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-opacity-20 disabled:opacity-50 disabled:cursor-not-allowed min-h-[44px] min-w-[44px]"
          >
            Cancelar
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={isLoading}
            data-confirm
            className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-opacity-20 disabled:opacity-50 disabled:cursor-not-allowed min-h-[44px] min-w-[44px]"
          >
            {isLoading ? 'Eliminando…' : confirmText}
          </button>
        </div>
      </div>
      <style jsx>{`
        .dialog-container {
          border: none;
          border-radius: 0.75rem;
          box-shadow: 0 25px 50px -12px rgb(0 0 0 / 0.25);
          padding: 0;
          max-width: 90vw;
          width: 400px;
        }
        .dialog-container::backdrop {
          background-color: rgb(0 0 0 / 0.5);
          backdrop-filter: blur(2px);
        }
        .dialog-content {
          padding: 1.5rem;
          background: white;
          border-radius: 0.75rem;
        }
        @media (max-width: 640px) {
          .dialog-container {
            max-width: 100vw;
            width: 100vw;
            height: 100vh;
            max-height: 100vh;
            border-radius: 0;
            margin: 0;
            padding: 0;
          }
          .dialog-container::backdrop {
            background-color: rgb(0 0 0 / 0.7);
          }
          .dialog-content {
            border-radius: 0;
            height: 100%;
            display: flex;
            flex-direction: column;
            justify-content: center;
            padding: 1.5rem;
          }
        }
      `}</style>
    </dialog>
  );
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

  // Delete confirmation dialog state
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [ruleToDelete, setRuleToDelete] = useState<AlertRuleResponse | null>(null);
  const [triggerElement, setTriggerElement] = useState<HTMLButtonElement | null>(null);
  // Use separate refs for mobile and desktop
  const deleteTriggerRefMobile = useRef<HTMLButtonElement>(null);
  const deleteTriggerRefDesktop = useRef<HTMLButtonElement>(null);

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

  const openDeleteDialog = (rule: AlertRuleResponse, triggerRef: React.RefObject<HTMLButtonElement | null>) => {
    setRuleToDelete(rule);
    setTriggerElement(triggerRef.current);
    setDeleteDialogOpen(true);
  };

  const closeDeleteDialog = () => {
    setDeleteDialogOpen(false);
    setRuleToDelete(null);
  };

  const handleDeleteConfirm = async () => {
    if (!ruleToDelete) return;

    setIsLoading(true);
    const formData = new FormData();
    formData.append('ruleId', ruleToDelete.id);

    try {
      const result = await deleteAlertRuleAction({ success: false, error: undefined }, formData);
      if (result.error) {
        setActionFeedback(result.error);
        setActionStatus('error');
      } else {
        setRules(rules.filter(r => r.id !== ruleToDelete.id));
        setActionFeedback('Regla eliminada');
        setActionStatus('success');
      }
    } catch (err) {
      setActionFeedback(err instanceof Error ? err.message : 'Error al eliminar la regla');
      setActionStatus('error');
    } finally {
      setIsLoading(false);
      closeDeleteDialog();
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

  // Render rule as a card for mobile stacked layout
  const renderRuleCard = (rule: AlertRuleResponse) => (
    <article key={rule.id} className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm sm:hidden">
      <div className="flex items-start justify-between gap-4 mb-3">
        <div>
          <h3 className="font-medium text-gray-900">
            {ENTITY_TYPE_LABELS[rule.entity_type] ?? rule.entity_type}
            {rule.entity_id && (
              <span className="ml-2 font-mono text-xs text-gray-500">
                {rule.entity_id.slice(0, 8)}…
              </span>
            )}
          </h3>
          <p className="text-sm font-mono text-gray-700 mt-0.5">{rule.metric}</p>
        </div>
        <span
          className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${SEVERITY_STYLES[rule.severity]} shrink-0`}
        >
          {SEVERITY_LABELS[rule.severity]}
        </span>
      </div>

      <dl className="space-y-2 text-sm text-gray-600 mb-4">
        <div className="grid grid-cols-2 gap-2">
          <dt className="text-gray-500">Operador</dt>
          <dd className="font-mono">{OPERATOR_LABELS[rule.operator] ?? rule.operator}</dd>
          <dt className="text-gray-500">Umbral</dt>
          <dd className="font-mono tabular-nums">{rule.threshold.toFixed(2)}</dd>
          <dt className="text-gray-500">Duración (s)</dt>
          <dd className="tabular-nums">{rule.duration_s}</dd>
          <dt className="text-gray-500">Estado</dt>
          <dd>
            <span
              className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                rule.is_active ? 'bg-emerald-100 text-emerald-800' : 'bg-gray-100 text-gray-700'
              }`}
            >
              {rule.is_active ? 'Activa' : 'Inactiva'}
            </span>
          </dd>
        </div>
      </dl>

      <div className="text-xs text-gray-500 mb-3" title={formatChannels(rule.channels)}>
        <span className="font-medium">Canales:</span> {formatChannels(rule.channels)}
      </div>

      <div className="flex items-center gap-2 pt-3 border-t border-gray-100">
        <Link
          href={`/alertas/reglas/${rule.id}/editar`}
          className="flex-1 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700 text-center hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-opacity-20 min-h-[44px] min-w-[44px]"
        >
          Editar
        </Link>
        <button
          type="button"
          ref={deleteTriggerRefMobile}
          onClick={() => openDeleteDialog(rule, deleteTriggerRefMobile)}
          disabled={isLoading}
          className="flex-1 rounded-md bg-red-600 px-3 py-2 text-sm font-medium text-white hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-opacity-20 disabled:opacity-50 disabled:cursor-not-allowed min-h-[44px] min-w-[44px]"
          aria-label={`Eliminar regla ${ENTITY_TYPE_LABELS[rule.entity_type] ?? rule.entity_type} - ${rule.metric}`}
        >
          Eliminar
        </button>
      </div>
    </article>
  );

  // Render rule as a table row for desktop
  const renderRuleRow = (rule: AlertRuleResponse) => (
    <tr key={rule.id} className="hover:bg-gray-50">
      <td className="px-4 py-3 text-gray-900 hidden sm:table-cell">
        {ENTITY_TYPE_LABELS[rule.entity_type] ?? rule.entity_type}
      </td>
      <td className="px-4 py-3 font-mono text-xs text-gray-500 hidden sm:table-cell">
        {rule.entity_id ? `${rule.entity_id.slice(0, 8)}…` : '— (todas)'}
      </td>
      <td className="px-4 py-3 font-mono text-sm text-gray-900 max-w-xs truncate" title={rule.metric}>
        {rule.metric}
      </td>
      <td className="px-4 py-3 text-center font-mono text-sm text-gray-700 hidden sm:table-cell">
        {OPERATOR_LABELS[rule.operator] ?? rule.operator}
      </td>
      <td className="px-4 py-3 text-right tabular-nums text-gray-900 hidden sm:table-cell">
        {rule.threshold.toFixed(2)}
      </td>
      <td className="px-4 py-3 text-center tabular-nums text-gray-900 hidden sm:table-cell">
        {rule.duration_s}
      </td>
      <td className="px-4 py-3 hidden sm:table-cell">
        <span
          className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${SEVERITY_STYLES[rule.severity]}`}
        >
          {SEVERITY_LABELS[rule.severity]}
        </span>
      </td>
      <td className="px-4 py-3 text-xs text-gray-600 max-w-xs truncate hidden sm:table-cell" title={formatChannels(rule.channels)}>
        {formatChannels(rule.channels)}
      </td>
      <td className="px-4 py-3 hidden sm:table-cell">
        <span
          className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${
            rule.is_active ? 'bg-emerald-100 text-emerald-800' : 'bg-gray-100 text-gray-700'
          }`}
        >
          {rule.is_active ? 'Activa' : 'Inactiva'}
        </span>
      </td>
<td className="px-4 py-3">
          <div className="flex items-center gap-2">
            <Link
              href={`/alertas/reglas/${rule.id}/editar`}
              className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-opacity-20 disabled:opacity-50 disabled:cursor-not-allowed min-h-[44px] min-w-[44px] hidden sm:inline-flex"
              aria-label={`Editar regla ${ENTITY_TYPE_LABELS[rule.entity_type] ?? rule.entity_type} - ${rule.metric}`}
            >
              Editar
            </Link>
            <button
              type="button"
              onClick={() => handleToggle(rule.id, !rule.is_active)}
              disabled={isLoading}
              className={`rounded-md px-3 py-1.5 text-sm font-medium min-h-[44px] min-w-[44px] focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-opacity-20 disabled:opacity-50 disabled:cursor-not-allowed transition-colors ${
                rule.is_active
                  ? 'bg-amber-600 text-white hover:bg-amber-700'
                  : 'bg-emerald-600 text-white hover:bg-emerald-700'
              } hidden sm:inline-flex`}
              aria-label={rule.is_active ? 'Desactivar regla' : 'Activar regla'}
            >
              {rule.is_active ? 'Desactivar' : 'Activar'}
            </button>
<button
            type="button"
            ref={deleteTriggerRefDesktop}
            onClick={() => openDeleteDialog(rule, deleteTriggerRefDesktop)}
            disabled={isLoading}
            className="rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-opacity-20 disabled:opacity-50 disabled:cursor-not-allowed min-h-[44px] min-w-[44px]"
            aria-label={`Eliminar regla ${ENTITY_TYPE_LABELS[rule.entity_type] ?? rule.entity_type} - ${rule.metric}`}
          >
            Eliminar
          </button>
          </div>
        </td>
    </tr>
  );

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

      {/* Tabla de reglas (desktop) + Tarjetas apiladas (mobile) */}
      <div className="rounded-lg border border-gray-200 bg-white shadow-sm">
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
          <>
            {/* Desktop table */}
            <div className="overflow-x-auto hidden sm:block">
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
                  {rules.map(renderRuleRow)}
                </tbody>
              </table>
            </div>

            {/* Mobile stacked cards */}
            <div className="block sm:hidden divide-y divide-gray-100 p-4">
              {rules.map(renderRuleCard)}
            </div>
          </>
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

      {/* Accessible Delete Confirmation Dialog */}
      <ConfirmDialog
        isOpen={deleteDialogOpen}
        onClose={closeDeleteDialog}
        onConfirm={handleDeleteConfirm}
        title="Eliminar regla de alerta"
        message={
          ruleToDelete
            ? `¿Eliminar la regla "${ENTITY_TYPE_LABELS[ruleToDelete.entity_type] ?? ruleToDelete.entity_type} - ${ruleToDelete.metric}"? Esta acción no se puede deshacer.`
            : '¿Eliminar esta regla de alerta? Esta acción no se puede deshacer.'
        }
        confirmText="Eliminar"
        isLoading={isLoading}
        triggerElement={triggerElement}
      />
    </section>
  );
}