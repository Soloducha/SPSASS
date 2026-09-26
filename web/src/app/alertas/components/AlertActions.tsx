'use client';

/**
 * Componente de acciones por fila de alerta (Reconocer / Resolver).
 * Un solo <form> por fila con dos botones submit distinguidos por name="intent".
 * useFormStatus deshabilita ambos durante el envío y previene doble envío.
 * El estado de pending intent se trackea localmente para mostrar "Procesando…"
 * solo en el botón que fue enviado.
 */

import { useActionState } from 'react';
import { useFormStatus } from 'react-dom';
import { useState, useEffect, FormEvent } from 'react';
import { alertAction } from '../actions';
import type { AlertResponse, ActionResult } from '@/lib/api/alerts';

interface AlertActionsProps {
  alert: AlertResponse;
}

function SubmitButtons({
  alert,
  intent,
  pendingIntent,
}: { alert: AlertResponse; intent: 'ack' | 'resolve'; pendingIntent: 'ack' | 'resolve' | null }) {
  const { pending } = useFormStatus();

  const isAck = intent === 'ack';
  const label = isAck ? 'Reconocer' : 'Resolver';
  const ariaBusy = pending ? 'true' : 'false';
  const isThisButtonPending = pending && pendingIntent === intent;

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
      {isThisButtonPending ? 'Procesando…' : label}
    </button>
  );
}

function AlertActionsForm({ alert }: { alert: AlertResponse }) {
  const initialState: ActionResult = { status: 'error', message: '' };
  const [state, formAction] = useActionState(alertAction, initialState);
  const [pendingIntent, setPendingIntent] = useState<'ack' | 'resolve' | null>(null);

  const handleFormSubmit = (event: FormEvent<HTMLFormElement>) => {
    // The actual submission is handled by useActionState via formAction
    // We just track which intent was submitted
    // Fix 4: Read intent from native submitter (FormData doesn't include the submit button)
    const submitter = (event.nativeEvent as SubmitEvent).submitter as HTMLButtonElement | null;
    const intent = submitter?.value as 'ack' | 'resolve' | undefined;
    if (intent === 'ack' || intent === 'resolve') {
      setPendingIntent(intent);
    }
  };

  // Reset pendingIntent when the action completes (state changes)
  useEffect(() => {
    if (!state.status || state.status === 'success' || state.status === 'error') {
      // Small delay to let the UI update before clearing
      const timer = setTimeout(() => setPendingIntent(null), 0);
      return () => clearTimeout(timer);
    }
  }, [state.status, state.message]);

  return (
    <form action={formAction} onSubmit={handleFormSubmit} className="flex items-center gap-2">
      <input type="hidden" name="alertId" value={alert.id} />
      <SubmitButtons alert={alert} intent="ack" pendingIntent={pendingIntent} />
      <SubmitButtons alert={alert} intent="resolve" pendingIntent={pendingIntent} />
      <div
        className={`text-xs min-h-[20px] ${
          state.status === 'success' ? 'text-emerald-700' : 'text-red-700'
        }`}
        aria-live="polite"
        aria-atomic="true"
      >
        {typeof state.message === 'string' ? state.message : ''}
      </div>
    </form>
  );
}

export function AlertActions({ alert }: AlertActionsProps) {
  return <AlertActionsForm alert={alert} />;
}