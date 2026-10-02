'use server';

/**
 * Server Actions para mutaciones de reglas de alerta (crear, actualizar, toggle, eliminar).
 * Cada acción valida independientemente el token antes de llamar al backend.
 */

import { revalidatePath } from 'next/cache';
import {
  createAlertRule,
  deleteAlertRule,
  toggleRuleEnabled,
  updateAlertRule,
  type AlertRuleCreate,
  type AlertRuleResponse,
  type AlertRuleUpdate,
  type FetchResult,
} from '@/lib/api/rules';
import { getDashboardToken } from '@/lib/config';
import {
  validateCreateRuleData,
  validateEntityId,
  validateRuleId,
  validateUpdateRuleData,
} from '@/lib/rule-validation';
import { mapApiError } from './utils';

interface CreateRuleResult {
  rule: AlertRuleResponse | null;
  error?: string;
}

interface UpdateRuleResult {
  rule: AlertRuleResponse | null;
  error?: string;
}

interface ToggleRuleResult {
  rule: AlertRuleResponse | null;
  error?: string;
}

interface DeleteRuleResult {
  success: boolean;
  error?: string;
}

async function validateToken(): Promise<string | null> {
  const token = getDashboardToken();
  if (!token) {
    return 'Token de dashboard no configurado (SPSAAS_DASHBOARD_TOKEN)';
  }
  return null;
}

/**
 * Server Action para crear una regla de alerta.
 * Valida el token y los datos de entrada antes de llamar al backend.
 */
export async function createAlertRuleAction(
  _prevState: CreateRuleResult,
  formData: FormData
): Promise<CreateRuleResult> {
  const tokenError = await validateToken();
  if (tokenError) {
    return { rule: null, error: tokenError };
  }

  // Parse form data
  const entityType = formData.get('entity_type') as string;
  const entityId = formData.get('entity_id') as string;
  const metric = formData.get('metric') as string;
  const operator = formData.get('operator') as string;
  const threshold = parseFloat(formData.get('threshold') as string);
  const duration_s = formData.get('duration_s') ? parseInt(formData.get('duration_s') as string, 10) : 60;
  const severity = (formData.get('severity') as string) || 'warning';
  const isActive = formData.get('is_active') === 'true';

  // Parse channels
  const emailToRaw = formData.get('email_to') as string;
  const webhookUrl = formData.get('webhook_url') as string;
  const webhookHeadersRaw = formData.get('webhook_headers') as string;
  const telegramChatIdRaw = formData.get('telegram_chat_id') as string;
  const telegramThreadIdRaw = formData.get('telegram_thread_id') as string;
  const telegramSilentRaw = formData.get('telegram_silent') as string;

  const channels: AlertRuleCreate['channels'] = {};

  if (emailToRaw && emailToRaw.trim().length > 0) {
    const emails = emailToRaw.split(',').map(e => e.trim()).filter(e => e.length > 0);
    if (emails.length > 0) {
      channels.email = { to: emails };
    }
  }

  if (webhookUrl && webhookUrl.trim().length > 0) {
    let headers: Record<string, string> = {};
    if (webhookHeadersRaw && webhookHeadersRaw.trim().length > 0) {
      try {
        headers = JSON.parse(webhookHeadersRaw);
      } catch {
        return { rule: null, error: 'Headers de webhook deben ser JSON válido' };
      }
    }
    channels.webhook = { url: webhookUrl.trim(), headers };
  }

  if (telegramChatIdRaw && telegramChatIdRaw.trim().length > 0) {
    const chatId = telegramChatIdRaw.trim();
    const telegramConfig: AlertRuleCreate['channels']['telegram'] = { chat_id: chatId };
    if (telegramThreadIdRaw && telegramThreadIdRaw.trim().length > 0) {
      const threadId = parseInt(telegramThreadIdRaw.trim(), 10);
      if (!isNaN(threadId) && threadId > 0) {
        telegramConfig.thread_id = threadId;
      }
    }
    if (telegramSilentRaw === 'true') {
      telegramConfig.silent = true;
    }
    channels.telegram = telegramConfig;
  }

  const ruleData: AlertRuleCreate = {
    entity_type: entityType as AlertRuleCreate['entity_type'],
    entity_id: entityId && entityId.trim().length > 0 ? entityId.trim() : undefined,
    metric: metric.trim(),
    operator: operator as AlertRuleCreate['operator'],
    threshold,
    duration_s,
    severity: severity as AlertRuleCreate['severity'],
    channels,
    is_active: isActive,
  };

  // Validate (including entity_id UUID guard)
  const validationError = validateCreateRuleData(ruleData);
  if (validationError) {
    return { rule: null, error: validationError };
  }
  const entityIdError = validateEntityId(ruleData.entity_id);
  if (entityIdError) {
    return { rule: null, error: entityIdError };
  }

  try {
    const result: FetchResult<AlertRuleResponse> = await createAlertRule(ruleData);

    if (result.error) {
      const message = mapApiError(result.status, result.error);
      return { rule: null, error: message };
    }

    revalidatePath('/alertas/reglas');
    return { rule: result.data!, error: undefined };
  } catch (err) {
    return {
      rule: null,
      error: err instanceof Error ? err.message : 'Error inesperado al crear la regla',
    };
  }
}

/**
 * Server Action para actualizar una regla de alerta.
 * Valida el token, el ID de regla, el ID de entidad (UUID) y los datos antes de llamar al backend.
 */
export async function updateAlertRuleAction(
  _prevState: UpdateRuleResult,
  formData: FormData
): Promise<UpdateRuleResult> {
  const tokenError = await validateToken();
  if (tokenError) {
    return { rule: null, error: tokenError };
  }

  const ruleId = formData.get('ruleId') as string;
  const idError = validateRuleId(ruleId);
  if (idError) {
    return { rule: null, error: idError };
  }

  // Parse form data (all optional for PATCH)
  const entityType = formData.get('entity_type') as string | null;
  const entityId = formData.get('entity_id') as string | null;
  const metric = formData.get('metric') as string | null;
  const operator = formData.get('operator') as string | null;
  const thresholdStr = formData.get('threshold') as string | null;
  const durationStr = formData.get('duration_s') as string | null;
  const severity = formData.get('severity') as string | null;
  const isActiveStr = formData.get('is_active') as string | null;

  // Parse channels (optional, but if present must be valid)
  const emailToRaw = formData.get('email_to') as string | null;
  const webhookUrl = formData.get('webhook_url') as string | null;
  const webhookHeadersRaw = formData.get('webhook_headers') as string | null;
  const telegramChatIdRaw = formData.get('telegram_chat_id') as string | null;
  const telegramThreadIdRaw = formData.get('telegram_thread_id') as string | null;
  const telegramSilentRaw = formData.get('telegram_silent') as string | null;

  const channels: AlertRuleUpdate['channels'] = {};

  if (emailToRaw !== null && emailToRaw.trim().length > 0) {
    const emails = emailToRaw.split(',').map(e => e.trim()).filter(e => e.length > 0);
    if (emails.length > 0) {
      channels.email = { to: emails };
    }
  } else if (emailToRaw === '') {
    // Explicitly clear email channel
    channels.email = undefined;
  }

  if (webhookUrl !== null && webhookUrl.trim().length > 0) {
    let headers: Record<string, string> = {};
    if (webhookHeadersRaw !== null && webhookHeadersRaw.trim().length > 0) {
      try {
        headers = JSON.parse(webhookHeadersRaw);
      } catch {
        return { rule: null, error: 'Headers de webhook deben ser JSON válido' };
      }
    }
    channels.webhook = { url: webhookUrl.trim(), headers };
  } else if (webhookUrl === '') {
    // Explicitly clear webhook channel
    channels.webhook = undefined;
  }

  if (telegramChatIdRaw !== null && telegramChatIdRaw.trim().length > 0) {
    const chatId = telegramChatIdRaw.trim();
    const telegramConfig: NonNullable<AlertRuleUpdate['channels']>['telegram'] = { chat_id: chatId };
    if (telegramThreadIdRaw !== null && telegramThreadIdRaw.trim().length > 0) {
      const threadId = parseInt(telegramThreadIdRaw.trim(), 10);
      if (!isNaN(threadId) && threadId > 0) {
        telegramConfig.thread_id = threadId;
      }
    }
    if (telegramSilentRaw === 'true') {
      telegramConfig.silent = true;
    }
    channels.telegram = telegramConfig;
  } else if (telegramChatIdRaw === '') {
    // Explicitly clear telegram channel
    channels.telegram = undefined;
  }

  const ruleData: AlertRuleUpdate = {};

  if (entityType !== null) ruleData.entity_type = entityType as AlertRuleUpdate['entity_type'];
  if (entityId !== null) ruleData.entity_id = entityId.trim().length > 0 ? entityId.trim() : null;
  if (metric !== null) ruleData.metric = metric.trim();
  if (operator !== null) ruleData.operator = operator as AlertRuleUpdate['operator'];
  if (thresholdStr !== null) ruleData.threshold = parseFloat(thresholdStr);
  if (durationStr !== null) ruleData.duration_s = parseInt(durationStr, 10);
  if (severity !== null) ruleData.severity = severity as AlertRuleUpdate['severity'];
  if (isActiveStr !== null) ruleData.is_active = isActiveStr === 'true';
  if (Object.keys(channels).length > 0) ruleData.channels = channels;

  // Validate (including entity_id UUID guard)
  const validationError = validateUpdateRuleData(ruleData);
  if (validationError) {
    return { rule: null, error: validationError };
  }
  const entityIdError = validateEntityId(ruleData.entity_id ?? undefined);
  if (entityIdError) {
    return { rule: null, error: entityIdError };
  }

  try {
    const result: FetchResult<AlertRuleResponse> = await updateAlertRule(ruleId, ruleData);

    if (result.error) {
      const message = mapApiError(result.status, result.error);
      return { rule: null, error: message };
    }

    revalidatePath('/alertas/reglas');
    revalidatePath(`/alertas/reglas/${ruleId}/editar`);
    return { rule: result.data!, error: undefined };
  } catch (err) {
    return {
      rule: null,
      error: err instanceof Error ? err.message : 'Error inesperado al actualizar la regla',
    };
  }
}

/**
 * Server Action para alternar el estado activo/inactivo de una regla.
 */
export async function toggleRuleEnabledAction(
  _prevState: ToggleRuleResult,
  formData: FormData
): Promise<ToggleRuleResult> {
  const tokenError = await validateToken();
  if (tokenError) {
    return { rule: null, error: tokenError };
  }

  const ruleId = formData.get('ruleId') as string;
  const isActive = formData.get('is_active') === 'true';

  const idError = validateRuleId(ruleId);
  if (idError) {
    return { rule: null, error: idError };
  }

  try {
    const result: FetchResult<AlertRuleResponse> = await toggleRuleEnabled(ruleId, isActive);

    if (result.error) {
      const message = mapApiError(result.status, result.error);
      return { rule: null, error: message };
    }

    revalidatePath('/alertas/reglas');
    return { rule: result.data!, error: undefined };
  } catch (err) {
    return {
      rule: null,
      error: err instanceof Error ? err.message : 'Error inesperado al cambiar el estado',
    };
  }
}

/**
 * Server Action para eliminar una regla de alerta.
 */
export async function deleteAlertRuleAction(
  _prevState: DeleteRuleResult,
  formData: FormData
): Promise<DeleteRuleResult> {
  const tokenError = await validateToken();
  if (tokenError) {
    return { success: false, error: tokenError };
  }

  const ruleId = formData.get('ruleId') as string;

  const idError = validateRuleId(ruleId);
  if (idError) {
    return { success: false, error: idError };
  }

  try {
    const result: FetchResult<null> = await deleteAlertRule(ruleId);

    if (result.error) {
      const message = mapApiError(result.status, result.error);
      return { success: false, error: message };
    }

    revalidatePath('/alertas/reglas');
    return { success: true, error: undefined };
  } catch (err) {
    return {
      success: false,
      error: err instanceof Error ? err.message : 'Error inesperado al eliminar la regla',
    };
  }
}