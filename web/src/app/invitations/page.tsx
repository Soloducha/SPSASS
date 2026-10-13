/** Invitaciones al tenant - Server Component con SSR. */

import { Metadata } from 'next';
import { listInvitationsAction } from './actions';
import { EntityTable, PaginationProps } from '@/components/EntityTable';
import { MemberRole } from '@/lib/api/invitations';
import { CreateInvitationDialog } from './CreateInvitationDialog';
import type { InvitationListResponse } from '@/lib/api/invitations';

export const metadata: Metadata = {
  title: 'Invitaciones - SPSAAS',
  description: 'Gestión de invitaciones al tenant',
};

interface InvitationsPageProps {
  searchParams: Promise<{ offset?: string; limit?: string }>;
}

interface InvitationWithStatus extends InvitationListResponse {
  status: 'pending' | 'accepted' | 'expired';
}

async function getInvitationsPage(searchParams: Promise<{ offset?: string; limit?: string }>) {
  const params = await searchParams;
  const offset = Math.max(0, parseInt(params.offset ?? '0', 10));
  const limit = Math.min(500, Math.max(1, parseInt(params.limit ?? '50', 10)));

  const result = await listInvitationsAction();
  // Paginación en memoria (la API no soporta offset/limit aún)
  const now = new Date().toISOString();
  const invitationsWithStatus: InvitationWithStatus[] = result.invitations.map((inv) => ({
    ...inv,
    status: inv.accepted_at ? 'accepted' : inv.expires_at < now ? 'expired' : 'pending',
  }));
  const paginated = invitationsWithStatus.slice(offset, offset + limit);
  const hasNext = offset + limit < invitationsWithStatus.length;

  return { result: { invitations: paginated, error: result.error, hasNext }, offset, limit };
}

const ROLE_LABELS: Record<MemberRole, string> = {
  owner: 'Propietario',
  admin: 'Administrador',
  member: 'Miembro',
  viewer: 'Visor',
};

const ROLE_BADGE: Record<MemberRole, 'default' | 'success' | 'warning' | 'error' | 'info'> = {
  owner: 'warning',
  admin: 'info',
  member: 'success',
  viewer: 'default',
};

const STATUS_BADGE: Record<'pending' | 'accepted' | 'expired', 'default' | 'success' | 'warning' | 'error' | 'info'> = {
  pending: 'warning',
  accepted: 'success',
  expired: 'error',
};

export default async function InvitationsPage({ searchParams }: InvitationsPageProps) {
  const { result, offset, limit } = await getInvitationsPage(searchParams);

  const columns = [
    {
      key: 'email',
      header: 'Email',
      type: 'text' as const,
    },
    {
      key: 'role',
      header: 'Rol',
      type: 'badge' as const,
      badgeVariantMap: ROLE_BADGE,
    },
    {
      key: 'status',
      header: 'Estado',
      type: 'badge' as const,
      badgeVariantMap: STATUS_BADGE,
    },
    {
      key: 'created_at',
      header: 'Creada',
      type: 'date' as const,
      dateOptions: { year: 'numeric' as const, month: 'short' as const, day: 'numeric' as const, hour: '2-digit' as const, minute: '2-digit' as const },
    },
    {
      key: 'expires_at',
      header: 'Expira',
      type: 'date' as const,
      dateOptions: { year: 'numeric' as const, month: 'short' as const, day: 'numeric' as const, hour: '2-digit' as const, minute: '2-digit' as const },
    },
  ];

  const currentPage = Math.floor(offset / limit);
  const pagination: PaginationProps = {
    currentPage,
    hasNext: result.hasNext,
    onPrevious: () => {
      const newOffset = Math.max(0, offset - limit);
      window.location.href = `/invitaciones?offset=${newOffset}&limit=${limit}`;
    },
    onNext: () => {
      const newOffset = offset + limit;
      window.location.href = `/invitaciones?offset=${newOffset}&limit=${limit}`;
    },
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Invitaciones</h1>
          <p className="text-gray-500 mt-1">Invita a tu equipo al tenant</p>
        </div>
        <CreateInvitationDialog />
      </div>

      {result.error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-md text-red-700" role="alert">
          Error al cargar invitaciones: {result.error}
        </div>
      )}

      <EntityTable
        columns={columns}
        data={result.invitations}
        error={result.error}
        emptyMessage="No hay invitaciones pendientes. Crea una para invitar a tu equipo."
        pagination={pagination}
        rowKey={(item) => item.id}
        customRenderers={{
          role: (value: unknown) => ROLE_LABELS[value as MemberRole] ?? String(value),
        }}
      />
    </div>
  );
}