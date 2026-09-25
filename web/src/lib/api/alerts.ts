/** Server-only typed fetch wrappers for `/api/v1/alerts` endpoints. */

import { getDashboardToken, getSpsaasApiUrl } from '@/lib/config';

export type AlertSeverity = 'info' | 'warning' | 'critical';
export type AlertStatus = 'open' | 'acknowledged' | 'resolved';

export interface AlertResponse {
  id: string;
  tenant_id: string;
  rule_id: string;
  server_id: string | null;
  severity: AlertSeverity;
  status: AlertStatus;
  message: string;
  triggered_at: string;
  resolved_at: string | null;
  acknowledged_at: string | null;
  acknowledged_by: string | null;
  value_at_trigger: number;
  created_at: string;
  updated_at: string;
}

export interface AlertListParams {
  status?: AlertStatus;
  severity?: AlertSeverity;
  rule_id?: string;
  offset?: number;
  limit?: number;
}

export interface AlertAckResponse {
  id: string;
  status: AlertStatus;
  acknowledged_at: string | null;
  resolved_at: string | null;
  acknowledged_by: string | null;
}

/** Result of an authenticated fetch, including the HTTP status for error mapping. */
export interface FetchResult<T> {
  data: T | null;
  error: string | null;
  status: number | null;
}

function buildAlertsUrl(path: string, params?: URLSearchParams): string {
  const base = getSpsaasApiUrl();
  const url = new URL(`${base}/api/v1/alerts${path}`);
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
 * Lista alertas con filtros opcionales y paginación bounded (offset/limit).
 * El backend no devuelve total count; hasNext se deduce si la página viene llena (length === limit).
 */
export async function listAlerts(params: AlertListParams = {}): Promise<{
  alerts: AlertResponse[];
  hasNext: boolean;
  error: string | null;
}> {
  const { status, severity, rule_id, offset = 0, limit = 50 } = params;

  const searchParams = new URLSearchParams();
  if (status) searchParams.set('status', status);
  if (severity) searchParams.set('severity', severity);
  if (rule_id) searchParams.set('rule_id', rule_id);
  searchParams.set('offset', String(Math.max(0, offset)));
  searchParams.set('limit', String(Math.min(50, Math.max(1, limit)))); // bounded to 50 max per task

  const url = buildAlertsUrl('', searchParams);
  const result = await fetchWithAuth<AlertResponse[]>(url);

  if (result.error) {
    return { alerts: [], hasNext: false, error: result.error };
  }

  const alerts = result.data ?? [];
  const hasNext = alerts.length === Number(searchParams.get('limit'));
  return { alerts, hasNext, error: null };
}

/**
 * Reconoce (acknowledge) una alerta.
 * El backend deriva el actor del usuario autenticado (JWT sub) e ignora cualquier valor en el body.
 * Se envía un body JSON vacío válido porque el endpoint requiere AlertAckRequest.
 */
export async function acknowledgeAlert(alertId: string): Promise<FetchResult<AlertAckResponse>> {
  const url = buildAlertsUrl(`/${alertId}/ack`);
  // Body vacío válido: AlertAckRequest.acknowledged_by es opcional y deprecated
  return fetchWithAuth<AlertAckResponse>(url, {
    method: 'POST',
    body: JSON.stringify({}),
  });
}

/**
 * Resuelve una alerta.
 * Sin body.
 */
export async function resolveAlert(alertId: string): Promise<FetchResult<AlertAckResponse>> {
  const url = buildAlertsUrl(`/${alertId}/resolve`);
  return fetchWithAuth<AlertAckResponse>(url, {
    method: 'POST',
  });
}

