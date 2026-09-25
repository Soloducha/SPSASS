/** Server-only typed fetch wrappers for `/api/v1/alerts/rules` endpoints. */

import { getDashboardToken, getSpsaasApiUrl } from '@/lib/config';

export type EntityType = 'server' | 'service' | 'process' | 'job' | 'metric';
export type AlertOperator = 'gt' | 'gte' | 'lt' | 'lte' | 'eq' | 'neq';
export type AlertSeverity = 'info' | 'warning' | 'critical';

export interface WebhookChannelConfig {
  url: string;
  headers: Record<string, string>;
}

export interface EmailChannelConfig {
  to: string[];
}

export interface AlertRuleChannels {
  webhook?: WebhookChannelConfig;
  email?: EmailChannelConfig;
}

export interface AlertRuleCreate {
  entity_type: EntityType;
  entity_id?: string;
  metric: string;
  operator: AlertOperator;
  threshold: number;
  duration_s?: number;
  severity?: AlertSeverity;
  channels: AlertRuleChannels;
  is_active?: boolean;
}

export interface AlertRuleUpdate {
  entity_type?: EntityType;
  entity_id?: string | null;
  metric?: string;
  operator?: AlertOperator;
  threshold?: number;
  duration_s?: number;
  severity?: AlertSeverity;
  channels?: AlertRuleChannels;
  is_active?: boolean;
}

export interface AlertRuleResponse {
  id: string;
  tenant_id: string;
  entity_type: EntityType;
  entity_id: string | null;
  metric: string;
  operator: AlertOperator;
  threshold: number;
  duration_s: number;
  severity: AlertSeverity;
  channels: AlertRuleChannels;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface AlertRuleListParams {
  offset?: number;
  limit?: number;
}

export interface FetchResult<T> {
  data: T | null;
  error: string | null;
  status: number | null;
}

function buildRulesUrl(path: string, params?: URLSearchParams): string {
  const base = getSpsaasApiUrl();
  const url = new URL(`${base}/api/v1/alerts/rules${path}`);
  if (params) {
    url.search = params.toString();
  }
  return url.toString();
}

async function fetchWithAuth<T>(
  url: string,
  init?: RequestInit
): Promise<FetchResult<T>> {
  const token = getDashboardToken();
  if (!token) {
    return { data: null, error: 'Token de dashboard no configurado (SPSAAS_DASHBOARD_TOKEN)', status: null };
  }

  try {
    const response = await fetch(url, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
        ...init?.headers,
      },
      cache: 'no-store',
    });

    if (!response.ok) {
      let detail = `HTTP ${response.status}`;
      try {
        const err = await response.json();
        detail = err.detail ?? detail;
      } catch {
        // ignore parse error
      }
      return { data: null, error: detail, status: response.status };
    }

    const data = (await response.json()) as T;
    return { data, error: null, status: response.status };
  } catch (err) {
    return { data: null, error: err instanceof Error ? err.message : 'Error de red desconocido', status: null };
  }
}

/**
 * Lista reglas de alerta con paginación bounded (offset/limit).
 * El backend no devuelve total count; hasNext se deduce si la página viene llena (length === limit).
 */
export async function listAlertRules(params: AlertRuleListParams = {}): Promise<{
  rules: AlertRuleResponse[];
  hasNext: boolean;
  error: string | null;
}> {
  const { offset = 0, limit = 50 } = params;

  const searchParams = new URLSearchParams();
  searchParams.set('offset', String(Math.max(0, offset)));
  searchParams.set('limit', String(Math.min(500, Math.max(1, limit))));

  const url = buildRulesUrl('', searchParams);
  const result = await fetchWithAuth<AlertRuleResponse[]>(url);

  if (result.error) {
    return { rules: [], hasNext: false, error: result.error };
  }

  const rules = result.data ?? [];
  const hasNext = rules.length === Number(searchParams.get('limit'));
  return { rules, hasNext, error: null };
}

/**
 * Crea una nueva regla de alerta.
 */
export async function createAlertRule(data: AlertRuleCreate): Promise<FetchResult<AlertRuleResponse>> {
  const url = buildRulesUrl('');
  return fetchWithAuth<AlertRuleResponse>(url, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

/**
 * Obtiene una regla de alerta por ID.
 */
export async function getAlertRule(ruleId: string): Promise<FetchResult<AlertRuleResponse>> {
  const url = buildRulesUrl(`/${ruleId}`);
  return fetchWithAuth<AlertRuleResponse>(url);
}

/**
 * Actualiza una regla de alerta (campos parciales).
 */
export async function updateAlertRule(ruleId: string, data: AlertRuleUpdate): Promise<FetchResult<AlertRuleResponse>> {
  const url = buildRulesUrl(`/${ruleId}`);
  return fetchWithAuth<AlertRuleResponse>(url, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

/**
 * Elimina una regla de alerta.
 */
export async function deleteAlertRule(ruleId: string): Promise<FetchResult<null>> {
  const url = buildRulesUrl(`/${ruleId}`);
  return fetchWithAuth<null>(url, {
    method: 'DELETE',
  });
}

/**
 * Alterna el estado activo/inactivo de una regla.
 */
export async function toggleRuleEnabled(ruleId: string, isActive: boolean): Promise<FetchResult<AlertRuleResponse>> {
  return updateAlertRule(ruleId, { is_active: isActive });
}