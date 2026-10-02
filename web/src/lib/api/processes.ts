/** Server-only typed fetch wrappers for `/api/v1/processes` endpoints. */

import { getDashboardToken, getSpsaasApiUrl } from '@/lib/config';

export interface ProcessCreate {
  server_id: string;
  name: string;
  pattern: string;
  expected_count?: number;
  auto_restart?: boolean;
  config?: Record<string, unknown>;
}

export interface ProcessUpdate {
  name?: string;
  pattern?: string;
  expected_count?: number;
  auto_restart?: boolean;
  config?: Record<string, unknown> | null;
}

export interface ProcessResponse {
  id: string;
  tenant_id: string;
  server_id: string;
  name: string;
  pattern: string;
  expected_count: number;
  auto_restart: boolean;
  config: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ProcessListParams {
  server_id?: string;
  offset?: number;
  limit?: number;
}

export interface FetchResult<T> {
  data: T | null;
  error: string | null;
  status: number | null;
}

function buildProcessesUrl(path: string, params?: URLSearchParams): string {
  const base = getSpsaasApiUrl();
  const url = new URL(`${base}/api/v1/processes${path}`);
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
 * Lista procesos con paginación bounded (offset/limit).
 * El backend no devuelve total count; hasNext se deduce si la página viene llena (length === limit).
 */
export async function listProcesses(params: ProcessListParams = {}): Promise<{
  processes: ProcessResponse[];
  hasNext: boolean;
  error: string | null;
}> {
  const { server_id, offset = 0, limit = 50 } = params;

  const searchParams = new URLSearchParams();
  if (server_id) searchParams.set('server_id', server_id);
  searchParams.set('offset', String(Math.max(0, offset)));
  searchParams.set('limit', String(Math.min(500, Math.max(1, limit))));

  const url = buildProcessesUrl('', searchParams);
  const result = await fetchWithAuth<ProcessResponse[]>(url);

  if (result.error) {
    return { processes: [], hasNext: false, error: result.error };
  }

  const processes = result.data ?? [];
  const hasNext = processes.length === Number(searchParams.get('limit'));
  return { processes, hasNext, error: null };
}

/**
 * Crea un nuevo proceso.
 */
export async function createProcess(data: ProcessCreate): Promise<FetchResult<ProcessResponse>> {
  const url = buildProcessesUrl('');
  return fetchWithAuth<ProcessResponse>(url, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

/**
 * Obtiene un proceso por ID.
 */
export async function getProcess(processId: string): Promise<FetchResult<ProcessResponse>> {
  const url = buildProcessesUrl(`/${processId}`);
  return fetchWithAuth<ProcessResponse>(url);
}

/**
 * Actualiza un proceso (campos parciales).
 */
export async function updateProcess(processId: string, data: ProcessUpdate): Promise<FetchResult<ProcessResponse>> {
  const url = buildProcessesUrl(`/${processId}`);
  return fetchWithAuth<ProcessResponse>(url, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

/**
 * Elimina un proceso.
 */
export async function deleteProcess(processId: string): Promise<FetchResult<null>> {
  const url = buildProcessesUrl(`/${processId}`);
  return fetchWithAuth<null>(url, {
    method: 'DELETE',
  });
}