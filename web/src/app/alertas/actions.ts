'use server';

/**
 * Server Actions para mutaciones de alertas (acknowledge/resolve).
 * Cada acción valida independientemente el token antes de llamar al backend.
 */

import { revalidatePath } from 'next/cache';
import { acknowledgeAlert, resolveAlert } from '@/lib/api/alerts';

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

function mapApiError(status: number, detail: string): string {
  if (status === 404) {
    return 'La alerta ya no existe o no pertenece a este tenant';
  }
  if (status === 401) {
    return 'El token de API configurado es inválido o ha expirado';
  }
  return detail;
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

  // Get token (each action independently validates)
  const token = process.env.SPSAAS_DASHBOARD_TOKEN;
  if (!token) {
    return {
      status: 'error',
      message: 'Token de dashboard no configurado (SPSAAS_DASHBOARD_TOKEN)',
    };
  }

  try {
    let result:
      | { data: { status: string } | null; error: string | null }
      | undefined;

    if (intent === 'ack') {
      result = await acknowledgeAlert(alertId);
    } else {
      result = await resolveAlert(alertId);
    }

    if (result.error) {
      // Try to extract HTTP status from error message
      const statusMatch = result.error.match(/^HTTP (\d+)/);
      const status = statusMatch ? parseInt(statusMatch[1], 10) : 0;
      const message = mapApiError(status, result.error);
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
 * Server Action para reconocer una alerta.
 * Se usa directamente desde el formulario en AlertActions.
 */
export async function acknowledgeAlertAction(
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

/**
 * Server Action para resolver una alerta.
 * Se usa directamente desde el formulario en AlertActions.
 */
export async function resolveAlertAction(
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