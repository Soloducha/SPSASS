'use server';

/**
 * Server Actions para mutaciones de alertas (acknowledge/resolve).
 * Cada acción valida independientemente el token antes de llamar al backend.
 */

import { revalidatePath } from 'next/cache';
import { acknowledgeAlert, resolveAlert, type FetchResult } from '@/lib/api/alerts';
import { getDashboardToken } from '@/lib/config';

const UUID_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

type ActionIntent = 'ack' | 'resolve';

interface ActionResult {
  status: 'success' | 'error';
  message: string;
}

function validateAlertId(alertId: string): string | null {
  if (!alertId || !UUID_REGEX.test(alertId)) {
    return 'ID de alerta inválido';
  }
  return null;
}

function validateIntent(intent: string): intent is ActionIntent {
  return intent === 'ack' || intent === 'resolve';
}

function mapApiError(status: number | null, detail: string): string {
  if (status === 404) {
    return 'La alerta ya no existe o no pertenece a este tenant';
  }
  if (status === 401) {
    return 'El token de API configurado es inválido o ha expirado';
  }
  if (status === 422) {
    return 'Datos de entrada inválidos para la acción solicitada';
  }
  if (typeof detail === 'string' && detail.trim().length > 0) {
    return detail;
  }
  return status ? `Error del servidor (${status})` : 'Error inesperado al procesar la acción';
}

async function performAlertAction(
  alertId: string,
  intent: ActionIntent
): Promise<ActionResult> {
  // Validate alertId
  const idError = validateAlertId(alertId);
  if (idError) {
    return { status: 'error', message: idError };
  }

  // Get token via shared helper (each action independently validates)
  const token = getDashboardToken();
  if (!token) {
    return {
      status: 'error',
      message: 'Token de dashboard no configurado (SPSAAS_DASHBOARD_TOKEN)',
    };
  }

  try {
    let result: FetchResult<{ status: string } | null>;

    if (intent === 'ack') {
      result = await acknowledgeAlert(alertId);
    } else {
      result = await resolveAlert(alertId);
    }

    if (result.error) {
      // Use the HTTP status directly from the typed fetch result
      const message = mapApiError(result.status, result.error);
      return { status: 'error', message };
    }

    // Success - revalidate the alerts list
    revalidatePath('/alertas');
    const actionLabel = intent === 'ack' ? 'reconocida' : 'resuelta';
    return {
      status: 'success',
      message: `Alerta ${actionLabel} correctamente`,
    };
  } catch (err) {
    return {
      status: 'error',
      message: err instanceof Error ? err.message : 'Error inesperado al procesar la acción',
    };
  }
}

/**
 * Server Action unificada para reconocer o resolver una alerta.
 * Lee y valida `intent` y `alertId` desde formData del lado del servidor.
 */
export async function alertAction(
  _prevState: ActionResult,
  formData: FormData
): Promise<ActionResult> {
  const alertId = formData.get('alertId') as string;
  const intent = formData.get('intent') as string;

  if (!validateIntent(intent)) {
    return { status: 'error', message: 'Acción no válida' };
  }

  return performAlertAction(alertId, intent);
}