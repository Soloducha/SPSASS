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
import { mapApiError } from './utils';

const UUID_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const ALLOWED_ENTITY_TYPES = ['server', 'service', 'process', 'job', 'metric'] as const;
const ALLOWED_OPERATORS = ['gt', 'gte', 'lt', 'lte', 'eq', 'neq'] as const;
const ALLOWED_SEVERITIES = ['info', 'warning', 'critical'] as const;

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

function validateRuleId(ruleId: string): string | null {
  if (!ruleId || !UUID_REGEX.test(ruleId)) {
    return 'ID de regla inválido';
  }
  return null;
}

function validateEntityId(entityId: string | undefined): string | null {
  if (entityId && entityId.trim().length > 0) {
    const trimmed = entityId.trim();
    if (!UUID_REGEX.test(trimmed)) {
      return 'ID de entidad debe ser un UUID válido';
    }
  }
  return null;
}

function validateCreateRuleData(data: AlertRuleCreate): string | null {
  if (!data.entity_type || !ALLOWED_ENTITY_TYPES.includes(data.entity_type)) {
    return 'Tipo de entidad no válido';
  }
  if (!data.metric || data.metric.trim().length === 0 || data.metric.length > 100) {
    return 'La métrica es obligatoria (máximo 100 caracteres)';
  }
  if (!data.operator || !ALLOWED_OPERATORS.includes(data.operator)) {
    return 'Operador no válido';
  }
  if (typeof data.threshold !== 'number' || !Number.isFinite(data.threshold)) {
    return 'El umbral debe ser un número válido';
  }
  if (data.duration_s !== undefined && (data.duration_s < 1 || !Number.isInteger(data.duration_s))) {
    return 'La duración debe ser un entero positivo (segundos)';
  }
  if (data.severity && !ALLOWED_SEVERITIES.includes(data.severity)) {
    return 'Severidad no válida';
  }
  if (!data.channels || Object.keys(data.channels).length === 0) {
    return 'Se requiere al menos un canal (email, webhook o telegram)';
  }
  if (data.channels.email) {
    if (!Array.isArray(data.channels.email.to) || data.channels.email.to.length === 0) {
      return 'El canal email requiere al menos un destinatario';
    }
    for (const email of data.channels.email.to) {
      if (typeof email !== 'string' || email.trim().length === 0) {
        return 'Todos los destinatarios email deben ser cadenas no vacías';
      }
      // Basic email format validation
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
        return 'Formato de email inválido en destinatarios';
      }
    }
  }
  if (data.channels.webhook) {
    if (typeof data.channels.webhook.url !== 'string' || data.channels.webhook.url.trim().length === 0) {
      return 'El canal webhook requiere una URL';
    }
    try {
      new URL(data.channels.webhook.url);
    } catch {
      return 'URL de webhook inválida';
    }
  }
  if (data.channels.telegram) {
    if (typeof data.channels.telegram.chat_id !== 'string' || data.channels.telegram.chat_id.trim().length === 0) {
      return 'El canal telegram requiere un chat_id';
    }
    // Client-side shape validation: numeric ID (^-?\d+$) or @username (^@[A-Za-z0-9_]{5,32}$)
    const chatId = data.channels.telegram.chat_id.trim();
    const isNumericId = /^-?\d+$/.test(chatId);
    const isUsername = /^@[A-Za-z0-9_]{5,32}$/.test(chatId);
    if (!isNumericId && !isUsername) {
      return 'chat_id de telegram debe ser un ID numérico (ej: -1001234567890) o un username (ej: @canal_bot)';
    }
    if (data.channels.telegram.thread_id !== undefined) {
      if (typeof data.channels.telegram.thread_id !== 'number' || !Number.isInteger(data.channels.telegram.thread_id) || data.channels.telegram.thread_id < 1) {
        return 'thread_id de telegram debe ser un entero positivo';
      }
    }
    if (data.channels.telegram.silent !== undefined && typeof data.channels.telegram.silent !== 'boolean') {
      return 'silent de telegram debe ser booleano';
    }
  }
  return null;
}

function validateUpdateRuleData(data: AlertRuleUpdate): string | null {
  if (data.entity_type !== undefined && !ALLOWED_ENTITY_TYPES.includes(data.entity_type)) {
    return 'Tipo de entidad no válido';
  }
  if (data.metric !== undefined && (data.metric.trim().length === 0 || data.metric.length > 100)) {
    return 'La métrica es obligatoria (máximo 100 caracteres)';
  }
  if (data.operator !== undefined && !ALLOWED_OPERATORS.includes(data.operator)) {
    return 'Operador no válido';
  }
  if (data.threshold !== undefined && (typeof data.threshold !== 'number' || !Number.isFinite(data.threshold))) {
    return 'El umbral debe ser un número válido';
  }
  if (data.duration_s !== undefined && (data.duration_s < 1 || !Number.isInteger(data.duration_s))) {
    return 'La duración debe ser un entero positivo (segundos)';
  }
  if (data.severity !== undefined && !ALLOWED_SEVERITIES.includes(data.severity)) {
    return 'Severidad no válida';
  }
  if (data.channels !== undefined) {
    if (!data.channels || Object.keys(data.channels).length === 0) {
      return 'Se requiere al menos un canal (email, webhook o telegram)';
    }
    if (data.channels.email) {
      if (!Array.isArray(data.channels.email.to) || data.channels.email.to.length === 0) {
        return 'El canal email requiere al menos un destinatario';
      }
      for (const email of data.channels.email.to) {
        if (typeof email !== 'string' || email.trim().length === 0) {
          return 'Todos los destinatarios email deben ser cadenas no vacías';
        }
        if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
          return 'Formato de email inválido en destinatarios';
        }
      }
    }
    if (data.channels.webhook) {
      if (typeof data.channels.webhook.url !== 'string' || data.channels.webhook.url.trim().length === 0) {
        return 'El canal webhook requiere una URL';
      }
      try {
        new URL(data.channels.webhook.url);
      } catch {
        return 'URL de webhook inválida';
      }
    }
    if (data.channels.telegram) {
      if (typeof data.channels.telegram.chat_id !== 'string' || data.channels.telegram.chat_id.trim().length === 0) {
        return 'El canal telegram requiere un chat_id';
      }
      // Client-side shape validation: numeric ID (^-?\d+$) or @username (^@[A-Za-z0-9_]{5,32}$)
      const chatId = data.channels.telegram.chat_id.trim();
      const isNumericId = /^-?\d+$/.test(chatId);
      const isUsername = /^@[A-Za-z0-9_]{5,32}$/.test(chatId);
      if (!isNumericId && !isUsername) {
        return 'chat_id de telegram debe ser un ID numérico (ej: -1001234567890) o un username (ej: @canal_bot)';
      }
      if (data.channels.telegram.thread_id !== undefined) {
        if (typeof data.channels.telegram.thread_id !== 'number' || !Number.isInteger(data.channels.telegram.thread_id) || data.channels.telegram.thread_id < 1) {
          return 'thread_id de telegram debe ser un entero positivo';
        }
      }
      if (data.channels.telegram.silent !== undefined && typeof data.channels.telegram.silent !== 'boolean') {
        return 'silent de telegram debe ser booleano';
      }
    }
  }
  return null;
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