/** Server-only typed fetch wrapper for `/api/v1/dashboard/overview` endpoint. */

import { getDashboardToken, getSpsaasApiUrl } from '@/lib/config';

export type ServerStatus = 'online' | 'offline' | 'degraded' | 'unknown';

export interface DashboardTotals {
  total: number;
  online: number;
  offline: number;
  degraded: number;
  unknown: number;
}

export interface ServerOverviewItem {
  id: string;
  hostname: string;
  ip: string | null;
  os: string | null;
  status: ServerStatus;
  last_heartbeat_at: string | null;
  latest_metrics: Record<string, number>;
}

export interface DashboardOverview {
  totals: DashboardTotals;
  servers: ServerOverviewItem[];
}

export interface FetchResult<T> {
  data: T | null;
  error: string | null;
  status: number | null;
}

async function fetchWithAuth<T>(url: string): Promise<FetchResult<T>> {
  const token = getDashboardToken();
  if (!token) {
    return { data: null, error: 'Token de dashboard no configurado (SPSAAS_DASHBOARD_TOKEN)', status: null };
  }

  try {
    const response = await fetch(url, {
      headers: {
        Authorization: `Bearer ${token}`,
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
 * Obtiene la vista general del dashboard con la lista de servidores.
 * Usado para poblar el selector de servidor en el formulario de reglas.
 */
export async function getDashboardOverview(): Promise<FetchResult<DashboardOverview>> {
  const url = `${getSpsaasApiUrl()}/api/v1/dashboard/overview`;
  return fetchWithAuth<DashboardOverview>(url);
}