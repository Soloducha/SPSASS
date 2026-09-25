'use client';

/**
 * Componente de acciones por fila de alerta (Reconocer / Resolver).
 * Un solo <form> por fila con dos botones submit distinguidos por name="intent".
 * useFormStatus deshabilita ambos durante el envío y previene doble envío.
 */

import { useActionState } from 'react';
import { useFormStatus } from 'react-dom';
import {
  acknowledgeAlertAction,
  resolveAlertAction,
} from '../actions';
import type { AlertResponse, AlertStatus } from '@/lib/api/alerts';

interface AlertActionsProps {
  alert: AlertResponse;
}

function SubmitButtons({ alert, intent }: { alert: AlertResponse; intent: 'ack' | 'resolve' }) {
  const { pending } = useFormStatus();

  const isAck = intent === 'ack';
  const label = isAck ? 'Reconocer' : 'Resolver';
  const ariaBusy = pending ? 'true' : 'false';

  // Reconocer solo si status === 'open'
  // Resolver solo si status !== 'resolved'
  const showAck = alert.status === 'open';
  const showResolve = alert.status !== 'resolved';

  if (isAck && !showAck) return null;
  if (!isAck && !showResolve) return null;

  return (
    <button
      type="submit"
      name="intent"
      value={intent}
      disabled={pending}
      aria-busy={ariaBusy}
      className={`rounded-md px-3 py-1.5 text-sm font-medium min-h-[44px] min-w-[44px] focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-opacity-20 disabled:opacity-50 disabled:cursor-not-allowed transition-colors ${
        isAck
          ? 'bg-indigo-600 text-white hover:bg-indigo-700'
          : 'bg-emerald-600 text-white hover:bg-emerald-700'
      }`}
    >
      {pending ? 'Procesando…' : label}
    </button>
  );
}

function AlertActionsForm({ alert }: { alert: AlertResponse }) {
  const [state, formAction] = useActionState(
    async (_prev: { status: 'success' | 'error'; message: string }, formData: FormData) => {
      const intent = formData.get('intent') as 'ack' | 'resolve';
      if (intent === 'ack') {
        return acknowledgeAlertAction({ status: 'error', message: '' }, formData);
      }
      return resolveAlertAction({ status: 'error', message: '' }, formData);
    },
    { status: 'error', message: '' }
  );

  return (
    <form action={formAction} className="flex items-center gap-2">
      <input type="hidden" name="alertId" value={alert.id} />
      <SubmitButtons alert={alert} intent="ack" />
      <SubmitButtons alert={alert} intent="resolve" />
      {state.message && (
        <div
          className={`text-xs min-h-[20px] ${
            state.status === 'success' ? 'text-emerald-700' : 'text-red-700'
          }`}
          aria-live="polite"
          aria-atomic="true"
        >
          {state.message}
        </div>
      )}
    </form>
  );
}

export function AlertActions({ alert }: AlertActionsProps) {
  return <AlertActionsForm alert={alert} />;
}