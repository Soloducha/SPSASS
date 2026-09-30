'use client';

/**
 * Formulario controlado para crear una regla de alerta.
 * Valida en cliente (espejo del backend) y usa Server Action para crear.
 */

import { useState, FormEvent, ChangeEvent } from 'react';
import { createAlertRuleAction } from '../../actions';
import type { ServerOverviewItem } from '@/lib/api/dashboard';

const ENTITY_TYPES = ['server', 'service', 'process', 'job', 'metric'] as const;
const OPERATORS = ['gt', 'gte', 'lt', 'lte', 'eq', 'neq'] as const;
const SEVERITIES = ['info', 'warning', 'critical'] as const;

const ENTITY_TYPE_LABELS: Record<(typeof ENTITY_TYPES)[number], string> = {
  server: 'Servidor',
  service: 'Servicio',
  process: 'Proceso',
  job: 'Tarea',
  metric: 'Métrica',
};

const OPERATOR_LABELS: Record<(typeof OPERATORS)[number], string> = {
  gt: 'Mayor que (>)',
  gte: 'Mayor o igual (≥)',
  lt: 'Menor que (<)',
  lte: 'Menor o igual (≤)',
  eq: 'Igual (=)',
  neq: 'Distinto (≠)',
};

const SEVERITY_LABELS: Record<(typeof SEVERITIES)[number], string> = {
  info: 'Informativa',
  warning: 'Advertencia',
  critical: 'Crítica',
};

interface CreateRuleFormProps {
  servers: ServerOverviewItem[];
}

export function CreateRuleForm({ servers }: CreateRuleFormProps) {
  const [entityType, setEntityType] = useState<'server' | 'service' | 'process' | 'job' | 'metric'>('server');
  const [entityId, setEntityId] = useState('');
  const [metric, setMetric] = useState('');
  const [operator, setOperator] = useState<'gt' | 'gte' | 'lt' | 'lte' | 'eq' | 'neq'>('gt');
  const [threshold, setThreshold] = useState('');
  const [duration_s, setDuration_s] = useState('60');
  const [severity, setSeverity] = useState<'info' | 'warning' | 'critical'>('warning');
  const [isActive, setIsActive] = useState(true);

  const [emailTo, setEmailTo] = useState('');
  const [webhookUrl, setWebhookUrl] = useState('');
  const [webhookHeaders, setWebhookHeaders] = useState('');
  const [telegramChatId, setTelegramChatId] = useState('');
  const [telegramThreadId, setTelegramThreadId] = useState('');
  const [telegramSilent, setTelegramSilent] = useState(false);

  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitStatus, setSubmitStatus] = useState<'idle' | 'submitting' | 'success' | 'error'>('idle');
  const [submitMessage, setSubmitMessage] = useState('');

  const hasEmail = emailTo.trim().length > 0;
  const hasWebhook = webhookUrl.trim().length > 0;
  const hasTelegram = telegramChatId.trim().length > 0;

  const validateField = (name: string, value: string): string | null => {
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
  };

  const handleChange = (e: ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target;

    if (name === 'entity_type') {
      setEntityType(value as 'server' | 'service' | 'process' | 'job' | 'metric');
    } else if (name === 'entity_id') {
      setEntityId(value);
    } else if (name === 'metric') {
      setMetric(value);
    } else if (name === 'operator') {
      setOperator(value as 'gt' | 'gte' | 'lt' | 'lte' | 'eq' | 'neq');
    } else if (name === 'threshold') {
      setThreshold(value);
    } else if (name === 'duration_s') {
      setDuration_s(value);
    } else if (name === 'severity') {
      setSeverity(value as 'info' | 'warning' | 'critical');
    } else if (name === 'is_active') {
      setIsActive(value === 'true');
    } else if (name === 'email_to') {
      setEmailTo(value);
    } else if (name === 'webhook_url') {
      setWebhookUrl(value);
    } else if (name === 'webhook_headers') {
      setWebhookHeaders(value);
    } else if (name === 'telegram_chat_id') {
      setTelegramChatId(value);
    } else if (name === 'telegram_thread_id') {
      setTelegramThreadId(value);
    } else if (name === 'telegram_silent') {
      setTelegramSilent(value === 'true');
    }

    // Validate on change
    const error = validateField(name, value);
    setErrors(prev => ({ ...prev, [name]: error ?? '' }));
  };

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setSubmitStatus('submitting');
    setSubmitMessage('');

    // Validate all fields
    const newErrors: Record<string, string> = {};
    const fieldValues = {
      entity_type: entityType,
      entity_id: entityId,
      metric,
      operator,
      threshold,
      duration_s,
      severity,
      email_to: emailTo,
      webhook_url: webhookUrl,
      webhook_headers: webhookHeaders,
      telegram_chat_id: telegramChatId,
      telegram_thread_id: telegramThreadId,
    };

    for (const [name, value] of Object.entries(fieldValues)) {
      const error = validateField(name, value as string);
      if (error) newErrors[name] = error;
    }

    // Check at least one channel
    if (!hasEmail && !hasWebhook && !hasTelegram) {
      newErrors.channels = 'Se requiere al menos un canal (email, webhook o telegram)';
    }

    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors);
      setSubmitStatus('error');
      setSubmitMessage('Por favor corrija los errores en el formulario');
      return;
    }

    const formData = new FormData();
    formData.append('entity_type', entityType);
    if (entityId.trim()) formData.append('entity_id', entityId.trim());
    formData.append('metric', metric.trim());
    formData.append('operator', operator);
    formData.append('threshold', threshold);
    formData.append('duration_s', duration_s);
    formData.append('severity', severity);
    formData.append('is_active', String(isActive));
    if (hasEmail) formData.append('email_to', emailTo);
    if (hasWebhook) {
      formData.append('webhook_url', webhookUrl.trim());
      if (webhookHeaders.trim()) formData.append('webhook_headers', webhookHeaders.trim());
    }
    if (hasTelegram) {
      formData.append('telegram_chat_id', telegramChatId.trim());
      if (telegramThreadId.trim()) formData.append('telegram_thread_id', telegramThreadId.trim());
      if (telegramSilent) formData.append('telegram_silent', 'true');
    }

    try {
      const result = await createAlertRuleAction({ rule: null, error: undefined }, formData);

      if (result.error) {
        setErrors({ submit: result.error });
        setSubmitStatus('error');
        setSubmitMessage(result.error);
      } else {
        setSubmitStatus('success');
        setSubmitMessage('Regla creada correctamente');
        // Reset form
        setEntityType('server');
        setEntityId('');
        setMetric('');
        setOperator('gt');
        setThreshold('');
        setDuration_s('60');
        setSeverity('warning');
        setIsActive(true);
        setEmailTo('');
        setWebhookUrl('');
        setWebhookHeaders('');
        setTelegramChatId('');
        setTelegramThreadId('');
        setTelegramSilent(false);
        setErrors({});
      }
    } catch (err) {
      setSubmitStatus('error');
      setSubmitMessage(err instanceof Error ? err.message : 'Error inesperado al crear la regla');
    }
  };

  const hasServers = servers.length > 0;
  const serverOptions = servers.map(s => ({ value: s.id, label: s.hostname }));

  return (
    <section aria-labelledby="create-rule-form-heading">
      <h2 id="create-rule-form-heading" className="sr-only">
        Formulario de creación de regla
      </h2>

      <div
        className="mb-4"
        role="status"
        aria-live="polite"
        aria-atomic="true"
      >
        {submitMessage && (
          <div
            className={`rounded-lg p-4 text-sm ${
              submitStatus === 'success'
                ? 'border border-emerald-200 bg-emerald-50 text-emerald-700'
                : 'border border-red-200 bg-red-50 text-red-700'
            }`}
            role="alert"
          >
            {submitMessage}
          </div>
        )}
      </div>

      <form onSubmit={handleSubmit} className="space-y-6" noValidate>
        <fieldset className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
          <legend className="text-lg font-semibold text-gray-900 mb-4">
            Configuración de la regla
          </legend>

          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="entity_type" className="block text-sm font-medium text-gray-700 mb-1">
                Tipo de entidad <span className="text-red-500" aria-hidden="true">*</span>
              </label>
              <select
                id="entity_type"
                name="entity_type"
                value={entityType}
                onChange={handleChange}
                className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-opacity-20 min-h-[44px]"
                aria-invalid={!!errors.entity_type}
                aria-describedby={errors.entity_type ? 'entity_type-error' : undefined}
              >
                {ENTITY_TYPES.map(type => (
                  <option key={type} value={type}>
                    {ENTITY_TYPE_LABELS[type]}
                  </option>
                ))}
              </select>
              {errors.entity_type && (
                <p id="entity_type-error" className="mt-1 text-sm text-red-600" role="alert">
                  {errors.entity_type}
                </p>
              )}
            </div>

            <div>
              <label htmlFor="entity_id" className="block text-sm font-medium text-gray-700 mb-1">
                ID de entidad (opcional)
                {entityType === 'server' && hasServers && (
                  <span className="text-gray-400 ml-1 text-xs">(seleccione un servidor abajo)</span>
                )}
              </label>
              {entityType === 'server' && hasServers ? (
                <select
                  id="entity_id"
                  name="entity_id"
                  value={entityId}
                  onChange={handleChange}
                  className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-opacity-20 min-h-[44px]"
                  aria-invalid={!!errors.entity_id}
                  aria-describedby={errors.entity_id ? 'entity_id-error' : undefined}
                >
                  <option value="">Todas las entidades (sin filtro)</option>
                  {serverOptions.map(opt => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  type="text"
                  id="entity_id"
                  name="entity_id"
                  value={entityId}
                  onChange={handleChange}
                  placeholder="UUID de la entidad (opcional, vacío = todas)"
                  className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm font-mono text-xs focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-opacity-20 min-h-[44px]"
                  aria-invalid={!!errors.entity_id}
                  aria-describedby={errors.entity_id ? 'entity_id-error' : undefined}
                />
              )}
              {errors.entity_id && (
                <p id="entity_id-error" className="mt-1 text-sm text-red-600" role="alert">
                  {errors.entity_id}
                </p>
              )}
              <p className="mt-1 text-xs text-gray-500">
                Deje vacío para aplicar a todas las entidades del tipo seleccionado.
              </p>
            </div>

            <div>
              <label htmlFor="metric" className="block text-sm font-medium text-gray-700 mb-1">
                Métrica <span className="text-red-500" aria-hidden="true">*</span>
              </label>
              <input
                type="text"
                id="metric"
                name="metric"
                value={metric}
                onChange={handleChange}
                placeholder="Ej: cpu_usage, mem_usage, disk_usage"
                maxLength={100}
                className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-opacity-20 min-h-[44px]"
                aria-invalid={!!errors.metric}
                aria-describedby={errors.metric ? 'metric-error' : undefined}
              />
              {errors.metric && (
                <p id="metric-error" className="mt-1 text-sm text-red-600" role="alert">
                  {errors.metric}
                </p>
              )}
            </div>

            <div>
              <label htmlFor="operator" className="block text-sm font-medium text-gray-700 mb-1">
                Operador <span className="text-red-500" aria-hidden="true">*</span>
              </label>
              <select
                id="operator"
                name="operator"
                value={operator}
                onChange={handleChange}
                className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-opacity-20 min-h-[44px]"
                aria-invalid={!!errors.operator}
                aria-describedby={errors.operator ? 'operator-error' : undefined}
              >
                {OPERATORS.map(op => (
                  <option key={op} value={op}>
                    {OPERATOR_LABELS[op]}
                  </option>
                ))}
              </select>
              {errors.operator && (
                <p id="operator-error" className="mt-1 text-sm text-red-600" role="alert">
                  {errors.operator}
                </p>
              )}
            </div>

            <div>
              <label htmlFor="threshold" className="block text-sm font-medium text-gray-700 mb-1">
                Umbral <span className="text-red-500" aria-hidden="true">*</span>
              </label>
              <input
                type="number"
                id="threshold"
                name="threshold"
                value={threshold}
                onChange={handleChange}
                step="any"
                placeholder="Ej: 80.5"
                className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-opacity-20 min-h-[44px]"
                aria-invalid={!!errors.threshold}
                aria-describedby={errors.threshold ? 'threshold-error' : undefined}
              />
              {errors.threshold && (
                <p id="threshold-error" className="mt-1 text-sm text-red-600" role="alert">
                  {errors.threshold}
                </p>
              )}
            </div>

            <div>
              <label htmlFor="duration_s" className="block text-sm font-medium text-gray-700 mb-1">
                Duración (segundos)
              </label>
              <input
                type="number"
                id="duration_s"
                name="duration_s"
                value={duration_s}
                onChange={handleChange}
                min="1"
                step="1"
                className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-opacity-20 min-h-[44px]"
                aria-invalid={!!errors.duration_s}
                aria-describedby={errors.duration_s ? 'duration-error' : undefined}
              />
              {errors.duration_s && (
                <p id="duration-error" className="mt-1 text-sm text-red-600" role="alert">
                  {errors.duration_s}
                </p>
              )}
              <p className="mt-1 text-xs text-gray-500">
                Tiempo que la condición debe mantenerse antes de disparar (mín. 1s, defecto 60s).
              </p>
            </div>

            <div>
              <label htmlFor="severity" className="block text-sm font-medium text-gray-700 mb-1">
                Severidad
              </label>
              <select
                id="severity"
                name="severity"
                value={severity}
                onChange={handleChange}
                className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-opacity-20 min-h-[44px]"
                aria-invalid={!!errors.severity}
                aria-describedby={errors.severity ? 'severity-error' : undefined}
              >
                {SEVERITIES.map(sev => (
                  <option key={sev} value={sev}>
                    {SEVERITY_LABELS[sev]}
                  </option>
                ))}
              </select>
              {errors.severity && (
                <p id="severity-error" className="mt-1 text-sm text-red-600" role="alert">
                  {errors.severity}
                </p>
              )}
            </div>

            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="is_active"
                name="is_active"
                checked={isActive}
                onChange={e => { setIsActive(e.target.checked); handleChange(e); }}
                className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500 focus:ring-2"
              />
              <label htmlFor="is_active" className="text-sm font-medium text-gray-700 cursor-pointer">
                Regla activa
              </label>
            </div>
          </div>
        </fieldset>

        <fieldset className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
          <legend className="text-lg font-semibold text-gray-900 mb-4">
            Canales de notificación
          </legend>
          <p className="mb-4 text-sm text-gray-500">
            Configure al menos un canal. Puede usar email, webhook y telegram simultáneamente.
          </p>

          <div className="space-y-4">
            <div>
              <label htmlFor="email_to" className="block text-sm font-medium text-gray-700 mb-1">
                Email - Destinatarios (separados por coma)
                <span className="text-red-500" aria-hidden="true">{hasWebhook || hasTelegram ? '' : ' *'}</span>
              </label>
              <textarea
                id="email_to"
                name="email_to"
                value={emailTo}
                onChange={handleChange}
                rows={2}
                placeholder="usuario1@ejemplo.com, usuario2@ejemplo.com"
                className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm font-mono text-xs focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-opacity-20 min-h-[44px]"
                aria-invalid={!!errors.email_to}
                aria-describedby={errors.email_to ? 'email_to-error' : undefined}
              />
              {errors.email_to && (
                <p id="email_to-error" className="mt-1 text-sm text-red-600" role="alert">
                  {errors.email_to}
                </p>
              )}
              <p className="mt-1 text-xs text-gray-500">
                Al menos un email válido requerido si usa este canal.
              </p>
            </div>

            <div>
              <label htmlFor="webhook_url" className="block text-sm font-medium text-gray-700 mb-1">
                Webhook - URL
                <span className="text-red-500" aria-hidden="true">{hasEmail || hasTelegram ? '' : ' *'}</span>
              </label>
              <input
                type="url"
                id="webhook_url"
                name="webhook_url"
                value={webhookUrl}
                onChange={handleChange}
                placeholder="https://ejemplo.com/webhook/alertas"
                className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-opacity-20 min-h-[44px]"
                aria-invalid={!!errors.webhook_url}
                aria-describedby={errors.webhook_url ? 'webhook_url-error' : undefined}
              />
              {errors.webhook_url && (
                <p id="webhook_url-error" className="mt-1 text-sm text-red-600" role="alert">
                  {errors.webhook_url}
                </p>
              )}
            </div>

            <div>
              <label htmlFor="webhook_headers" className="block text-sm font-medium text-gray-700 mb-1">
                Webhook - Headers (JSON opcional)
              </label>
              <textarea
                id="webhook_headers"
                name="webhook_headers"
                value={webhookHeaders}
                onChange={handleChange}
                rows={3}
                placeholder='{ "Authorization": "Bearer token", "X-Custom-Header": "valor" }'
                className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm font-mono text-xs focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-opacity-20 min-h-[44px]"
                aria-invalid={!!errors.webhook_headers}
                aria-describedby={errors.webhook_headers ? 'webhook_headers-error' : undefined}
              />
              {errors.webhook_headers && (
                <p id="webhook_headers-error" className="mt-1 text-sm text-red-600" role="alert">
                  {errors.webhook_headers}
                </p>
              )}
              <p className="mt-1 text-xs text-gray-500">
                Objeto JSON con headers adicionales para el webhook.
              </p>
            </div>

            <div>
              <label htmlFor="telegram_chat_id" className="block text-sm font-medium text-gray-700 mb-1">
                Telegram - Chat ID
                <span className="text-red-500" aria-hidden="true">{hasEmail || hasWebhook ? '' : ' *'}</span>
              </label>
              <input
                type="text"
                id="telegram_chat_id"
                name="telegram_chat_id"
                value={telegramChatId}
                onChange={handleChange}
                placeholder="-1001234567890 o @canal_bot"
                className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-opacity-20 min-h-[44px]"
                aria-invalid={!!errors.telegram_chat_id}
                aria-describedby={errors.telegram_chat_id ? 'telegram_chat_id-error' : undefined}
              />
              {errors.telegram_chat_id && (
                <p id="telegram_chat_id-error" className="mt-1 text-sm text-red-600" role="alert">
                  {errors.telegram_chat_id}
                </p>
              )}
              <p className="mt-1 text-xs text-gray-500">
                ID numérico del chat/grupo (ej: -1001234567890) o username del canal/bot (ej: @canal_bot).
              </p>
            </div>

            <div>
              <label htmlFor="telegram_thread_id" className="block text-sm font-medium text-gray-700 mb-1">
                Telegram - Thread ID (opcional)
              </label>
              <input
                type="number"
                id="telegram_thread_id"
                name="telegram_thread_id"
                value={telegramThreadId}
                onChange={handleChange}
                placeholder="42"
                min="1"
                step="1"
                className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-opacity-20 min-h-[44px]"
                aria-invalid={!!errors.telegram_thread_id}
                aria-describedby={errors.telegram_thread_id ? 'telegram_thread_id-error' : undefined}
              />
              {errors.telegram_thread_id && (
                <p id="telegram_thread_id-error" className="mt-1 text-sm text-red-600" role="alert">
                  {errors.telegram_thread_id}
                </p>
              )}
              <p className="mt-1 text-xs text-gray-500">
                ID del tema (topic) en grupos con foros habilitados. Solo aplica si el grupo tiene topics.
              </p>
            </div>

            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="telegram_silent"
                name="telegram_silent"
                checked={telegramSilent}
                onChange={e => { setTelegramSilent(e.target.checked); handleChange(e); }}
                className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500 focus:ring-2"
              />
              <label htmlFor="telegram_silent" className="text-sm font-medium text-gray-700 cursor-pointer">
                Enviar sin notificación (silencioso)
              </label>
            </div>
          </div>

          {errors.channels && (
            <p className="mt-2 text-sm text-red-600" role="alert">
              {errors.channels}
            </p>
          )}
        </fieldset>

        <div className="flex items-center justify-end gap-4 pt-4 border-t border-gray-200">
          <button
            type="button"
            onClick={() => window.history.back()}
            className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-opacity-20 min-h-[44px] min-w-[44px]"
          >
            Cancelar
          </button>
          <button
            type="submit"
            disabled={submitStatus === 'submitting'}
            className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-opacity-20 disabled:opacity-50 disabled:cursor-not-allowed min-h-[44px] min-w-[44px]"
          >
            {submitStatus === 'submitting' ? 'Creando…' : 'Crear regla'}
          </button>
        </div>
      </form>
    </section>
  );
}