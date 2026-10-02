/**
 * Validación compartida para los formularios de reglas de alerta.
 * Funciones puras: sin 'use server', sin React.
 */

const ENTITY_TYPES = ['server', 'service', 'process', 'job', 'metric'] as const;
const OPERATORS = ['gt', 'gte', 'lt', 'lte', 'eq', 'neq'] as const;
const SEVERITIES = ['info', 'warning', 'critical'] as const;

export function validateField(name: string, value: string): string | null {
  switch (name) {
    case 'entity_type':
      if (!value || !ENTITY_TYPES.includes(value as typeof ENTITY_TYPES[number])) {
        return 'Tipo de entidad no válido';
      }
      return null;
    case 'entity_id':
      if (value && value.trim().length > 0) {
        const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
        if (!uuidRegex.test(value.trim())) {
          return 'ID de entidad debe ser un UUID válido';
        }
      }
      return null;
    case 'metric':
      if (!value || value.trim().length === 0) {
        return 'La métrica es obligatoria';
      }
      if (value.length > 100) {
        return 'La métrica no puede exceder 100 caracteres';
      }
      return null;
    case 'operator':
      if (!value || !OPERATORS.includes(value as typeof OPERATORS[number])) {
        return 'Operador no válido';
      }
      return null;
    case 'threshold':
      const num = parseFloat(value);
      if (isNaN(num) || !Number.isFinite(num)) {
        return 'El umbral debe ser un número válido';
      }
      return null;
    case 'duration_s':
      if (value) {
        const num = parseInt(value, 10);
        if (isNaN(num) || num < 1 || !Number.isInteger(num)) {
          return 'La duración debe ser un entero positivo (segundos)';
        }
      }
      return null;
    case 'severity':
      if (!value || !SEVERITIES.includes(value as typeof SEVERITIES[number])) {
        return 'Severidad no válida';
      }
      return null;
    case 'email_to':
      if (value && value.trim().length > 0) {
        const emails = value.split(',').map(e => e.trim()).filter(e => e.length > 0);
        for (const email of emails) {
          if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
            return 'Formato de email inválido';
          }
        }
      }
      return null;
    case 'webhook_url':
      if (value && value.trim().length > 0) {
        try {
          new URL(value.trim());
        } catch {
          return 'URL de webhook inválida';
        }
      }
      return null;
    case 'webhook_headers':
      if (value && value.trim().length > 0) {
        try {
          JSON.parse(value);
        } catch {
          return 'Headers de webhook deben ser JSON válido';
        }
      }
      return null;
    case 'telegram_chat_id':
      if (value && value.trim().length > 0) {
        const chatId = value.trim();
        const isNumericId = /^-?\d+$/.test(chatId);
        const isUsername = /^@[A-Za-z0-9_]{5,32}$/.test(chatId);
        if (!isNumericId && !isUsername) {
          return 'chat_id debe ser un ID numérico (ej: -1001234567890) o un username (ej: @canal_bot)';
        }
      }
      return null;
    case 'telegram_thread_id':
      if (value && value.trim().length > 0) {
        const num = parseInt(value, 10);
        if (isNaN(num) || num < 1 || !Number.isInteger(num)) {
          return 'thread_id debe ser un entero positivo';
        }
      }
      return null;
    default:
      return null;
  }
}

export function validateChannels(emailTo: string, webhookUrl: string, telegramChatId: string): string | null {
  const hasEmail = emailTo.trim().length > 0;
  const hasWebhook = webhookUrl.trim().length > 0;
  const hasTelegram = telegramChatId.trim().length > 0;
  if (!hasEmail && !hasWebhook && !hasTelegram) {
    return 'Se requiere al menos un canal (email, webhook o telegram)';
  }
  return null;
}
