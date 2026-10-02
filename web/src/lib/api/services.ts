/** Server-only typed fetch wrappers for `/api/v1/services` endpoints. */

import { getDashboardToken, getSpsaasApiUrl } from '@/lib/config';

export type ServiceState = 'running' | 'stopped' | 'failed' | 'unknown';

export interface ServiceCreate {
  server_id: string;
  name: string;
  desired_state?: ServiceState;
  auto_restart?: boolean;
  config?: Record<string, unknown>;
}

export interface ServiceUpdate {
  name?: string;
  desired_state?: ServiceState;
  auto_restart?: boolean;
  config?: Record<string, unknown> | null;
}

export interface ServiceResponse {
  id: string;
  tenant_id: string;
  server_id: string;
  name: string;
  desired_state: ServiceState;
  auto_restart: boolean;
  last_status: ServiceState;
  last_checked_at: string | null;
  config: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ServiceListParams {
  server_id?: string;
  offset?: number;
  limit?: number;
}

export interface FetchResult<T> {
  data: T | null;
  error: string | null;
  status: number | null;
}

function buildServicesUrl(path: string, params?: URLSearchParams): string {
  const base = getSpsaasApiUrl();
  const url = new URL(`${base}/api/v1/services${path}`);
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
 * Lista servicios con paginación bounded (offset/limit).
 * El backend no devuelve total count; hasNext se deduce si la página viene llena (length === limit).
 */
export async function listServices(params: ServiceListParams = {}): Promise<{
  services: ServiceResponse[];
  hasNext: boolean;
  error: string | null;
}> {
  const { server_id, offset = 0, limit = 50 } = params;

  const searchParams = new URLSearchParams();
  if (server_id) searchParams.set('server_id', server_id);
  searchParams.set('offset', String(Math.max(0, offset)));
  searchParams.set('limit', String(Math.min(500, Math.max(1, limit))));

  const url = buildServicesUrl('', searchParams);
  const result = await fetchWithAuth<ServiceResponse[]>(url);

  if (result.error) {
    return { services: [], hasNext: false, error: result.error };
  }

  const services = result.data ?? [];
  const hasNext = services.length === Number(searchParams.get('limit'));
  return { services, hasNext, error: null };
}

/**
 * Crea un nuevo servicio.
 */
export async function createService(data: ServiceCreate): Promise<FetchResult<ServiceResponse>> {
  const url = buildServicesUrl('');
  return fetchWithAuth<ServiceResponse>(url, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

/**
 * Obtiene un servicio por ID.
 */
export async function getService(serviceId: string): Promise<FetchResult<ServiceResponse>> {
  const url = buildServicesUrl(`/${serviceId}`);
  return fetchWithAuth<ServiceResponse>(url);
}

/**
 * Actualiza un servicio (campos parciales).
 */
export async function updateService(serviceId: string, data: ServiceUpdate): Promise<FetchResult<ServiceResponse>> {
  const url = buildServicesUrl(`/${serviceId}`);
  return fetchWithAuth<ServiceResponse>(url, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

/**
 * Elimina un servicio.
 */
export async function deleteService(serviceId: string): Promise<FetchResult<null>> {
  const url = buildServicesUrl(`/${serviceId}`);
  return fetchWithAuth<null>(url, {
    method: 'DELETE',
  });
}