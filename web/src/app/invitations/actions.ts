'use server';

/**
 * Server Actions para el flujo de invitaciones (T2 - Mes 6).
 *
 * `createInvitationAction` requiere el token de dashboard (solo admins).
 * `acceptInvitationAction` es público: el token de invitación viaja en el link
 * del email, no en una sesión.
 */

import {
  acceptInvitation,
  createInvitation,
  listInvitations,
  type AcceptInvitationResponse,
  type InvitationListResponse,
  type InvitationResponse,
  type MemberRole,
} from '@/lib/api/invitations';

export interface CreateInvitationActionResult {
  invitation?: InvitationResponse;
  error?: string;
}

export interface ListInvitationsActionResult {
  invitations: InvitationListResponse[];
  error?: string;
}

export interface AcceptInvitationActionResult {
  session?: AcceptInvitationResponse;
  error?: string;
}

/** Crea una invitación para el tenant del dashboard. */
export async function createInvitationAction(
  email: string,
  role: MemberRole
): Promise<CreateInvitationActionResult> {
  if (!email.trim()) {
    return { error: 'El email es obligatorio' };
  }

  const result = await createInvitation({ email: email.trim(), role });
  if ('error' in result) return { error: result.error };
  return { invitation: result.invitation };
}

/** Lista las invitaciones del tenant del dashboard. */
export async function listInvitationsAction(): Promise<ListInvitationsActionResult> {
  const result = await listInvitations();
  if ('error' in result) return { invitations: [], error: result.error };
  return { invitations: result.invitations };
}

/**
 * Acepta una invitación y devuelve la sesión del invitado.
 *
 * La web todavía no tiene login con cookies (el dashboard se autentica con
 * `SPSAAS_DASHBOARD_TOKEN`), así que por ahora esta action solo devuelve los
 * tokens: conectarlos a una sesión web es trabajo del flujo de login.
 */
export async function acceptInvitationAction(
  token: string,
  password: string,
  fullName?: string
): Promise<AcceptInvitationActionResult> {
  if (!token) {
    return { error: 'Enlace de invitación inválido' };
  }
  if (!password || password.length < 8) {
    return { error: 'La contraseña debe tener al menos 8 caracteres' };
  }

  const result = await acceptInvitation(token, {
    password,
    full_name: fullName?.trim() || undefined,
  });
  if ('error' in result) return { error: result.error };
  return { session: result.session };
}