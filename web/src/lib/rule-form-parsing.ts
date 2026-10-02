import type { AlertRuleCreate, AlertRuleUpdate } from '@/lib/api/rules';

/**
 * Pure FormData → AlertRuleCreate/AlertRuleUpdate parsing.
 * Validation lives separately in `rule-validation.ts`.
 */

export function parseCreateRuleFormData(formData: FormData): {
  ruleData: AlertRuleCreate | null;
  error?: string;
} {
  const entityType = formData.get('entity_type') as string;
  const entityId = formData.get('entity_id') as string;
  const metric = formData.get('metric') as string;
  const operator = formData.get('operator') as string;
  const threshold = parseFloat(formData.get('threshold') as string);
  const duration_s = formData.get('duration_s')
    ? parseInt(formData.get('duration_s') as string, 10)
    : 60;
  const severity = (formData.get('severity') as string) || 'warning';
  const isActive = formData.get('is_active') === 'true';

  const emailToRaw = formData.get('email_to') as string;
  const webhookUrl = formData.get('webhook_url') as string;
  const webhookHeadersRaw = formData.get('webhook_headers') as string;
  const telegramChatIdRaw = formData.get('telegram_chat_id') as string;
  const telegramThreadIdRaw = formData.get('telegram_thread_id') as string;
  const telegramSilentRaw = formData.get('telegram_silent') as string;

  const channels: AlertRuleCreate['channels'] = {};

  if (emailToRaw && emailToRaw.trim().length > 0) {
    const emails = emailToRaw.split(',').map((e) => e.trim()).filter((e) => e.length > 0);
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
        return { ruleData: null, error: 'Headers de webhook deben ser JSON válido' };
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

  return { ruleData };
}

export function parseUpdateRuleFormData(formData: FormData): {
  ruleData: AlertRuleUpdate | null;
  error?: string;
} {
  const entityType = formData.get('entity_type') as string | null;
  const entityId = formData.get('entity_id') as string | null;
  const metric = formData.get('metric') as string | null;
  const operator = formData.get('operator') as string | null;
  const thresholdStr = formData.get('threshold') as string | null;
  const durationStr = formData.get('duration_s') as string | null;
  const severity = formData.get('severity') as string | null;
  const isActiveStr = formData.get('is_active') as string | null;

  const emailToRaw = formData.get('email_to') as string | null;
  const webhookUrl = formData.get('webhook_url') as string | null;
  const webhookHeadersRaw = formData.get('webhook_headers') as string | null;
  const telegramChatIdRaw = formData.get('telegram_chat_id') as string | null;
  const telegramThreadIdRaw = formData.get('telegram_thread_id') as string | null;
  const telegramSilentRaw = formData.get('telegram_silent') as string | null;

  const channels: AlertRuleUpdate['channels'] = {};

  if (emailToRaw !== null && emailToRaw.trim().length > 0) {
    const emails = emailToRaw.split(',').map((e) => e.trim()).filter((e) => e.length > 0);
    if (emails.length > 0) {
      channels.email = { to: emails };
    }
  } else if (emailToRaw === '') {
    channels.email = undefined;
  }

  if (webhookUrl !== null && webhookUrl.trim().length > 0) {
    let headers: Record<string, string> = {};
    if (webhookHeadersRaw !== null && webhookHeadersRaw.trim().length > 0) {
      try {
        headers = JSON.parse(webhookHeadersRaw);
      } catch {
        return { ruleData: null, error: 'Headers de webhook deben ser JSON válido' };
      }
    }
    channels.webhook = { url: webhookUrl.trim(), headers };
  } else if (webhookUrl === '') {
    channels.webhook = undefined;
  }

  if (telegramChatIdRaw !== null && telegramChatIdRaw.trim().length > 0) {
    const chatId = telegramChatIdRaw.trim();
    const telegramConfig: NonNullable<AlertRuleUpdate['channels']>['telegram'] = {
      chat_id: chatId,
    };
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

  return { ruleData };
}
