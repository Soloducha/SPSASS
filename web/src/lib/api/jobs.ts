/** Server-only typed fetch wrappers for `/api/v1/jobs` endpoints. */

import { getDashboardToken, getSpsaasApiUrl } from '@/lib/config';

export type JobKind = 'cron' | 'batch' | 'scheduled';
export type JobStatus = 'active' | 'paused' | 'disabled';

export interface JobCreate {
  server_id: string;
  name: string;
  kind: JobKind;
  schedule_cron?: string;
  command: string;
  timeout_s?: number;
  alert_on_fail?: boolean;
  auto_restart?: boolean;
  status?: JobStatus;
  config?: Record<string, unknown>;
}

export interface JobUpdate {
  name?: string;
  kind?: JobKind;
  schedule_cron?: string | null;
  command?: string;
  timeout_s?: number;
  alert_on_fail?: boolean;
  auto_restart?: boolean;
  status?: JobStatus;
  config?: Record<string, unknown> | null;
}

export interface JobResponse {
  id: string;
  tenant_id: string;
  server_id: string;
  name: string;
  kind: JobKind;
  schedule_cron: string | null;
  command: string;
  timeout_s: number;
  alert_on_fail: boolean;
  auto_restart: boolean;
  status: JobStatus;
  config: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface JobListParams {
  server_id?: string;
  status?: JobStatus;
  offset?: number;
  limit?: number;
}

export interface JobRunResponse {
  id: string;
  tenant_id: string;
  job_id: string;
  started_at: string;
  finished_at: string | null;
  exit_code: number | null;
  status: string; // running | success | failed | timeout
  output_tail: string | null;
  run_metadata: Record<string, unknown>;
}

export interface JobRunListParams {
  limit?: number;
  offset?: number;
}

export interface FetchResult<T> {
  data: T | null;
  error: string | null;
  status: number | null;
}

function buildJobsUrl(path: string, params?: URLSearchParams): string {
  const base = getSpsaasApiUrl();
  const url = new URL(`${base}/api/v1/jobs${path}`);
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
 * Lista jobs con paginación bounded (offset/limit).
 * El backend no devuelve total count; hasNext se deduce si la página viene llena (length === limit).
 */
export async function listJobs(params: JobListParams = {}): Promise<{
  jobs: JobResponse[];
  hasNext: boolean;
  error: string | null;
}> {
  const { server_id, status, offset = 0, limit = 50 } = params;

  const searchParams = new URLSearchParams();
  if (server_id) searchParams.set('server_id', server_id);
  if (status) searchParams.set('status', status);
  searchParams.set('offset', String(Math.max(0, offset)));
  searchParams.set('limit', String(Math.min(500, Math.max(1, limit))));

  const url = buildJobsUrl('', searchParams);
  const result = await fetchWithAuth<JobResponse[]>(url);

  if (result.error) {
    return { jobs: [], hasNext: false, error: result.error };
  }

  const jobs = result.data ?? [];
  const hasNext = jobs.length === Number(searchParams.get('limit'));
  return { jobs, hasNext, error: null };
}

/**
 * Crea un nuevo job.
 */
export async function createJob(data: JobCreate): Promise<FetchResult<JobResponse>> {
  const url = buildJobsUrl('');
  return fetchWithAuth<JobResponse>(url, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

/**
 * Obtiene un job por ID.
 */
export async function getJob(jobId: string): Promise<FetchResult<JobResponse>> {
  const url = buildJobsUrl(`/${jobId}`);
  return fetchWithAuth<JobResponse>(url);
}

/**
 * Actualiza un job (campos parciales).
 */
export async function updateJob(jobId: string, data: JobUpdate): Promise<FetchResult<JobResponse>> {
  const url = buildJobsUrl(`/${jobId}`);
  return fetchWithAuth<JobResponse>(url, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

/**
 * Elimina un job.
 */
export async function deleteJob(jobId: string): Promise<FetchResult<null>> {
  const url = buildJobsUrl(`/${jobId}`);
  return fetchWithAuth<null>(url, {
    method: 'DELETE',
  });
}

/**
 * Lista ejecuciones de un job (JobRuns).
 */
export async function listJobRuns(jobId: string, params: JobRunListParams = {}): Promise<{
  runs: JobRunResponse[];
  hasNext: boolean;
  error: string | null;
}> {
  const { offset = 0, limit = 50 } = params;

  const searchParams = new URLSearchParams();
  searchParams.set('offset', String(Math.max(0, offset)));
  searchParams.set('limit', String(Math.min(500, Math.max(1, limit))));

  const url = buildJobsUrl(`/${jobId}/runs`, searchParams);
  const result = await fetchWithAuth<JobRunResponse[]>(url);

  if (result.error) {
    return { runs: [], hasNext: false, error: result.error };
  }

  const runs = result.data ?? [];
  const hasNext = runs.length === Number(searchParams.get('limit'));
  return { runs, hasNext, error: null };
}