'use client';

/** Dialog para crear invitación con Server Action. */

import { useState, FormEvent } from 'react';
import { XMarkIcon } from '@heroicons/react/24/outline';
import { createInvitationAction } from './actions';
import { MemberRole } from '@/lib/api/invitations';
import type { InvitationResponse } from '@/lib/api/invitations';

const ROLE_LABELS: Record<MemberRole, string> = {
  owner: 'Propietario',
  admin: 'Administrador',
  member: 'Miembro',
  viewer: 'Visor',
};

interface CreateInvitationDialogProps {
  onSuccess?: () => void;
}

export function CreateInvitationDialog({ onSuccess }: CreateInvitationDialogProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [createdInvitation, setCreatedInvitation] = useState<InvitationResponse | null>(null);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setLoading(true);

    const formData = new FormData(event.currentTarget);
    const email = formData.get('email') as string;
    const role = formData.get('role') as MemberRole;

    const result = await createInvitationAction(email, role);
    setLoading(false);

    if (result.error) {
      setError(result.error);
      return;
    }

    setCreatedInvitation(result.invitation!);
  };

  const handleCopyToken = async () => {
    if (!createdInvitation) return;
    await navigator.clipboard.writeText(createdInvitation.token);
    alert('Token copiado al portapapeles');
  };

  if (createdInvitation) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50" role="dialog" aria-modal="true" aria-labelledby="invitation-created-title">
        <div className="w-full max-w-md bg-white rounded-lg shadow-xl p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 id="invitation-created-title" className="text-lg font-semibold text-gray-900">Invitación creada</h2>
            <button onClick={() => { setCreatedInvitation(null); setIsOpen(false); onSuccess?.(); }} className="text-gray-400 hover:text-gray-600" aria-label="Cerrar">
              <XMarkIcon className="h-5 w-5" />
            </button>
          </div>

          <div className="space-y-4">
            <div>
              <p className="text-sm text-gray-500">Email</p>
              <p className="font-medium text-gray-900">{createdInvitation.email}</p>
            </div>
            <div>
              <p className="text-sm text-gray-500">Rol</p>
              <p className="font-medium text-gray-900">{ROLE_LABELS[createdInvitation.role]}</p>
            </div>
            <div>
              <p className="text-sm text-gray-500">Expira</p>
              <p className="font-medium text-gray-900">{new Date(createdInvitation.expires_at).toLocaleString()}</p>
            </div>
            <div className="rounded-lg border border-gray-200 bg-gray-50 p-4">
              <p className="text-sm text-gray-500 mb-2">Token de invitación (compartir manualmente si falla el email)</p>
              <div className="flex gap-2">
                <code className="flex-1 text-xs font-mono break-all bg-white border border-gray-300 rounded p-2">{createdInvitation.token}</code>
                <button onClick={handleCopyToken} className="px-3 py-2 bg-indigo-600 text-white text-sm font-medium rounded-md hover:bg-indigo-700 min-h-[44px] whitespace-nowrap">
                  Copiar
                </button>
              </div>
              <p className="mt-2 text-xs text-gray-500">El link de aceptación es: <code className="text-indigo-600">{window.location.origin}/accept-invitation/{createdInvitation.token}</code></p>
            </div>
          </div>

          <button onClick={() => { setCreatedInvitation(null); setIsOpen(false); onSuccess?.(); }} className="mt-4 w-full px-4 py-2 bg-indigo-600 text-white rounded-md text-sm font-medium hover:bg-indigo-700">
            Entendido
          </button>
        </div>
      </div>
    );
  }

  return (
    <>
      <button
        onClick={() => setIsOpen(true)}
        className="px-4 py-2 bg-indigo-600 text-white rounded-md text-sm font-medium hover:bg-indigo-700 transition-colors min-h-[44px]"
      >
        Nueva invitación
      </button>

      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50" role="dialog" aria-modal="true" aria-labelledby="create-invitation-title">
          <div className="w-full max-w-md bg-white rounded-lg shadow-xl p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 id="create-invitation-title" className="text-lg font-semibold text-gray-900">Nueva invitación</h2>
              <button onClick={() => setIsOpen(false)} className="text-gray-400 hover:text-gray-600" aria-label="Cerrar">
                <XMarkIcon className="h-5 w-5" />
              </button>
            </div>

            <form onSubmit={handleSubmit} className="space-y-4">
              {error && (
                <div className="p-3 bg-red-50 border border-red-200 rounded-md text-red-700 text-sm" role="alert">
                  {error}
                </div>
              )}

              <div>
                <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-1">
                  Email <span className="text-red-500">*</span>
                </label>
                <input
                  type="email"
                  id="email"
                  name="email"
                  required
                  className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus-opacity-20 min-h-[44px]"
                  placeholder="usuario@ejemplo.com"
                />
              </div>

              <div>
                <label htmlFor="role" className="block text-sm font-medium text-gray-700 mb-1">
                  Rol <span className="text-red-500">*</span>
                </label>
                <select
                  id="role"
                  name="role"
                  required
                  className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus-opacity-20 min-h-[44px]"
                >
                  <option value="member">Miembro</option>
                  <option value="admin">Administrador</option>
                  <option value="viewer">Visor</option>
                </select>
              </div>

              <div className="flex gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setIsOpen(false)}
                  className="flex-1 px-4 py-2 border border-gray-300 text-gray-700 rounded-md text-sm font-medium hover:bg-gray-50 min-h-[44px]"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={loading}
                  className="flex-1 px-4 py-2 bg-indigo-600 text-white rounded-md text-sm font-medium hover:bg-indigo-700 disabled:opacity-60 min-h-[44px]"
                >
                  {loading ? 'Creando…' : 'Crear invitación'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}