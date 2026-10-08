/** Server-only typed fetch wrappers for `/api/v1/invitations` endpoints. */

import { getDashboardToken, getSpsaasApiUrl } from '@/lib/config';

export type MemberRole = 'owner' | 'admin' | 'member' | 'viewer';

export interface InvitationCreateRequest {
  email: string;
  role: MemberRole;
}

export interface InvitationResponse {
  id: string;
  email: string;
  role: MemberRole;
  /** JWT de invitación. Solo se devuelve al crear, para compartir el link a mano. */
  token: string;
  expires_at: string;
  created_at: string;
  accepted_at: string | null;
}

export interface InvitationListResponse {
  id: string;
  email: string;
  role: MemberRole;
  expires_at: string;
  created_at: string;
  accepted_at: string | null;
}

export interface AcceptInvitationRequest {
  password: string;
  full_name?: string;
}

export interface AcceptInvitationUser {
  id: string;
  email: string;
  full_name: string | null;
  role: string;
  tenant_id: string;
}

export interface AcceptInvitationTenant {
  id: string;
  name: string;
  slug: string;
  plan: string;
}

export interface AcceptInvitationResponse {
  access_token: string;
  refresh_token: string;
  user: AcceptInvitationUser;
  tenant: AcceptInvitationTenant;
}

async function readErrorDetail(res: Response, fallback: string): Promise<string> {
  try {
    const err = await res.json();
    return err.detail ?? fallback;
  } catch {
    return fallback;
  }
}

/**
 * Crea una invitación para el tenant del dashboard.
 *
 * El `token` viene siempre en la respuesta: si el envío por email falla
 * (SMTP sin configurar, por ejemplo) el admin puede compartir el link a mano.
 */
export async function createInvitation(
  data: InvitationCreateRequest
): Promise<{ invitation: InvitationResponse } | { error: string }> {
  const token = getDashboardToken();
  if (!token) {
    return { error: 'Token de dashboard no configurado (SPSAAS_DASHBOARD_TOKEN)' };
  }

  const url = `${getSpsaasApiUrl()}/api/v1/invitations`;

  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(data),
      cache: 'no-store',
    });

    if (!res.ok) {
      return { error: await readErrorDetail(res, `HTTP ${res.status}`) };
    }

    const body = (await res.json()) as InvitationResponse;
    return { invitation: body };
  } catch (err) {
    return { error: err instanceof Error ? err.message : 'Error de red al crear la invitación' };
  }
}

/** Lista las invitaciones del tenant del dashboard. */
export async function listInvitations(): Promise<
  { invitations: InvitationListResponse[] } | { error: string }
> {
  const token = getDashboardToken();
  if (!token) {
    return { error: 'Token de dashboard no configurado (SPSAAS_DASHBOARD_TOKEN)' };
  }

  const url = `${getSpsaasApiUrl()}/api/v1/invitations`;

  try {
    const res = await fetch(url, {
      headers: { Authorization: `Bearer ${token}` },
      cache: 'no-store',
    });

    if (!res.ok) {
      return { error: await readErrorDetail(res, `HTTP ${res.status}`) };
    }

    const body = (await res.json()) as InvitationListResponse[];
    return { invitations: body };
  } catch (err) {
    return {
      error: err instanceof Error ? err.message : 'Error de red al listar las invitaciones',
    };
  }
}

/**
 * Acepta una invitación y devuelve la sesión del usuario invitado.
 *
 * Es pública: no lleva `Authorization`. El token viaja en el path porque forma
 * parte del link del email.
 */
export async function acceptInvitation(
  token: string,
  data: AcceptInvitationRequest
): Promise<{ session: AcceptInvitationResponse } | { error: string }> {
  const url = `${getSpsaasApiUrl()}/api/v1/invitations/accept/${encodeURIComponent(token)}`;

  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
      cache: 'no-store',
    });

    if (!res.ok) {
      return { error: await readErrorDetail(res, `HTTP ${res.status}`) };
    }

    const body = (await res.json()) as AcceptInvitationResponse;
    return { session: body };
  } catch (err) {
    return { error: err instanceof Error ? err.message : 'Error de red al aceptar la invitación' };
  }
}