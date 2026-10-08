/** Server-only typed fetch wrappers for `/api/v1/servers` endpoints. */

import { getDashboardToken, getSpsaasApiUrl } from '@/lib/config';

export type ServerStatus = 'online' | 'offline' | 'degraded' | 'unknown';

export interface ServerRegisterRequest {
  hostname: string;
  ip?: string;
  os?: string;
  agent_version?: string;
}

export interface ServerRegisterResponse {
  id: string;
  hostname: string;
  status: string;
  agent_version: string | null;
  last_heartbeat_at: string | null;
}

export interface ServerResponse {
  id: string;
  tenant_id: string;
  hostname: string;
  ip: string | null;
  os: string | null;
  agent_version: string | null;
  status: ServerStatus;
  last_heartbeat_at: string | null;
  alert_channels: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ServerListParams {
  offset?: number;
  limit?: number;
}

export interface ServerListResponse {
  items: ServerResponse[];
  hasNext: boolean;
  error: string | null;
}

export interface ApiKeyCreatedResponse {
  id: string;
  name: string;
  prefix: string;
  /** Clave en claro. Solo se devuelve en la creación: en BD queda el hash. */
  key: string;
  created_at: string;
}

export interface FetchResult<T> {
  data: T | null;
  error: string | null;
  status: number | null;
}

function buildServersUrl(path: string, params?: URLSearchParams): string {
  const base = getSpsaasApiUrl();
  const url = new URL(`${base}/api/v1/servers${path}`);
  if (params) {
    url.search = params.toString();
  }
  return url.toString();
}

async function fetchWithAuth<T>(
  url: string,
  init?: RequestInit
): Promise<{ data: T | null; error: string | null; status: number | null }> {
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
 * Registra un nuevo servidor o actualiza uno existente (upsert por tenant+hostname).
 */
export async function registerServer(data: {
  hostname: string;
  ip?: string;
  os?: string;
  agent_version?: string;
}): Promise<{ serverId: string } | { error: string }> {
  const token = getDashboardToken();
  if (!token) {
    return { error: 'Token de dashboard no configurado (SPSAAS_DASHBOARD_TOKEN)' };
  }

  const baseUrl = getSpsaasApiUrl();
  const url = `${baseUrl}/api/v1/servers/register`;

  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        hostname: data.hostname,
        ip: data.ip,
        os: data.os,
        agent_version: data.agent_version,
      }),
      cache: 'no-store',
    });

    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try {
        const err = await res.json();
        detail = err.detail ?? detail;
      } catch { /* ignore */ }
      return { error: detail };
    }

    const body = (await res.json()) as ServerRegisterResponse;
    return { serverId: body.id };
  } catch (err) {
    return { error: err instanceof Error ? err.message : 'Error de red al registrar servidor' };
  }
}

/**
 * Crea una API Key para el tenant del usuario autenticado.
 *
 * La respuesta incluye `key` con la clave en claro: la API solo la devuelve
 * en este momento, en BD queda únicamente el hash.
 */
export async function createApiKey(data: {
  name: string;
  description?: string;
}): Promise<{ apiKey: string } | { error: string }> {
  const token = getDashboardToken();
  if (!token) {
    return { error: 'Token de dashboard no configurado (SPSAAS_DASHBOARD_TOKEN)' };
  }

  const url = `${getSpsaasApiUrl()}/api/v1/api-keys`;

  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ name: data.name, description: data.description }),
      cache: 'no-store',
    });

    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try {
        const err = await res.json();
        detail = err.detail ?? detail;
      } catch { /* ignore */ }
      return { error: detail };
    }

    const body = (await res.json()) as ApiKeyCreatedResponse;
    return { apiKey: body.key };
  } catch (err) {
    return { error: err instanceof Error ? err.message : 'Error de red al crear la API Key' };
  }
}