/** Server-only typed fetch wrappers for `/api/v1/reports` endpoints. */

import { getDashboardToken, getSpsaasApiUrl } from '@/lib/config';

export type ReportType = 'availability' | 'incidents' | 'alerts' | 'sla' | 'metrics';
export type ReportStatus = 'pending' | 'generating' | 'completed' | 'failed' | 'cancelled';

export interface ReportBase {
  type: ReportType;
  period_start: string;
  period_end: string;
  params?: Record<string, unknown>;
}

export type ReportCreate = ReportBase;

export interface ReportGenerateRequest extends ReportBase {
  params?: Record<string, unknown>;
}

export interface ReportResponse {
  id: string;
  tenant_id: string;
  type: ReportType;
  status: ReportStatus;
  period_start: string;
  period_end: string;
  payload: Record<string, unknown>;
  generated_at: string | null;
  file_path: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface ReportListParams {
  type?: ReportType;
  status?: ReportStatus;
  period_start?: string;
  period_end?: string;
  offset?: number;
  limit?: number;
  page?: number;
}

export interface ReportListResponse {
  items: ReportResponse[];
  total: number;
  page: number;
  page_size: number;
}

export interface ReportGenerateResponse {
  id: string;
  location: string;
}

export interface FetchResult<T> {
  data: T | null;
  error: string | null;
  status: number | null;
}

function buildReportsUrl(path: string, params?: URLSearchParams): string {
  const base = getSpsaasApiUrl();
  const url = new URL(`${base}/api/v1/reports${path}`);
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
 * Lista reportes con paginación y filtros.
 */
export async function listReports(params: ReportListParams = {}): Promise<{
  reports: ReportResponse[];
  total: number;
  page: number;
  page_size: number;
  error: string | null;
}> {
  const { type, status, period_start, period_end, offset = 0, limit = 50, page = 1 } = params;

  const searchParams = new URLSearchParams();
  if (type) searchParams.set('type', type);
  if (status) searchParams.set('status', status);
  if (period_start) searchParams.set('period_start', period_start);
  if (period_end) searchParams.set('period_end', period_end);
  searchParams.set('page', String(Math.max(1, page)));
  searchParams.set('page_size', String(Math.min(200, Math.max(1, limit))));

  const url = buildReportsUrl('', searchParams);
  const result = await fetchWithAuth<ReportListResponse>(url);

  if (result.error) {
    return { reports: [], total: 0, page: 1, page_size: limit, error: result.error };
  }

  return {
    reports: result.data?.items ?? [],
    total: result.data?.total ?? 0,
    page: result.data?.page ?? 1,
    page_size: result.data?.page_size ?? limit,
    error: null,
  };
}

/**
 * Crea un reporte manual (POST /reports).
 */
export async function createReport(data: ReportCreate): Promise<FetchResult<ReportResponse>> {
  const url = buildReportsUrl('');
  return fetchWithAuth<ReportResponse>(url, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

/**
 * Genera un reporte asíncrono (POST /reports/generate).
 * Devuelve 202 + Location header con el ID del reporte.
 */
export async function generateReport(data: ReportGenerateRequest): Promise<FetchResult<ReportGenerateResponse>> {
  const url = buildReportsUrl('/generate');
  const result = await fetchWithAuth<{ location?: string }>(url, {
    method: 'POST',
    body: JSON.stringify(data),
  });

  if (result.error) {
    return { data: null, error: result.error, status: result.status };
  }

  const location = result.data?.location;
  const reportId = location?.split('/').pop() ?? '';
  return { data: { id: reportId, location: location ?? '' }, error: null, status: 202 };
}

/**
 * Obtiene un reporte por ID con payload completo.
 */
export async function getReport(reportId: string): Promise<FetchResult<ReportResponse>> {
  const url = buildReportsUrl(`/${reportId}`);
  return fetchWithAuth<ReportResponse>(url);
}

/**
 * Elimina (cancela) un reporte.
 */
export async function deleteReport(reportId: string): Promise<FetchResult<null>> {
  const url = buildReportsUrl(`/${reportId}`);
  return fetchWithAuth<null>(url, {
    method: 'DELETE',
  });
}