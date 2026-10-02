/**
 * Validación de datos de reglas de alerta.
 * Funciones puras: sin 'use server', sin React.
 */

import type { AlertRuleCreate, AlertRuleUpdate } from '@/lib/api/rules';

export const UUID_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export const ALLOWED_ENTITY_TYPES = ['server', 'service', 'process', 'job', 'metric'] as const;
export const ALLOWED_OPERATORS = ['gt', 'gte', 'lt', 'lte', 'eq', 'neq'] as const;
export const ALLOWED_SEVERITIES = ['info', 'warning', 'critical'] as const;

export function validateRuleId(ruleId: string): string | null {
  if (!ruleId || !UUID_REGEX.test(ruleId)) {
    return 'ID de regla inválido';
  }
  return null;
}

export function validateEntityId(entityId: string | undefined): string | null {
  if (entityId && entityId.trim().length > 0) {
    const trimmed = entityId.trim();
    if (!UUID_REGEX.test(trimmed)) {
      return 'ID de entidad debe ser un UUID válido';
    }
  }
  return null;
}

export function validateCreateRuleData(data: AlertRuleCreate): string | null {
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

export function validateUpdateRuleData(data: AlertRuleUpdate): string | null {
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
