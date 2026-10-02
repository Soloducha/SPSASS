/** Lista de servicios - Server Component con SSR y paginación. */

import { Metadata } from 'next';
import { listServices, ServiceResponse, ServiceState } from '@/lib/api/services';
import { EntityTable, Badge, PaginationProps } from '@/components/EntityTable';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'Servicios - SPSAAS',
  description: 'Gestión de servicios monitoreados',
};

interface ServicesPageProps {
  searchParams: Promise<{ offset?: string; limit?: string }>;
}

async function getServicesPage(searchParams: Promise<{ offset?: string; limit?: string }>) {
  const params = await searchParams;
  const offset = Math.max(0, parseInt(params.offset ?? '0', 10));
  const limit = Math.min(500, Math.max(1, parseInt(params.limit ?? '50', 10)));

  const result = await listServices({ offset, limit });
  return { result, offset, limit };
}

function ServiceStateBadge({ state }: { state: ServiceState }) {
  const variants: Record<ServiceState, 'success' | 'error' | 'warning' | 'info'> = {
    running: 'success',
    stopped: 'error',
    failed: 'error',
    unknown: 'warning',
  };
  return <Badge variant={variants[state] ?? 'default'}>{state}</Badge>;
}

function AutoRestartBadge({ enabled }: { enabled: boolean }) {
  if (!enabled) return null;
  return <Badge variant="info" className="ml-2">Auto-restart</Badge>;
}

export default async function ServicesPage({ searchParams }: ServicesPageProps) {
  const { result, offset, limit } = await getServicesPage(searchParams);

  const columns = [
    {
      key: 'name',
      header: 'Nombre',
      render: (item: ServiceResponse) => (
        <Link href={`/entidades/servicios/${item.id}/editar`} className="text-blue-600 hover:underline font-medium">
          {item.name}
        </Link>
      ),
    },
    {
      key: 'server_id',
      header: 'Servidor',
      render: (item: ServiceResponse) => (
        <span className="font-mono text-sm text-gray-500">{item.server_id.slice(0, 8)}…</span>
      ),
    },
    {
      key: 'desired_state',
      header: 'Estado deseado',
      render: (item: ServiceResponse) => <ServiceStateBadge state={item.desired_state} />,
    },
    {
      key: 'last_status',
      header: 'Estado actual',
      render: (item: ServiceResponse) => <ServiceStateBadge state={item.last_status} />,
    },
    {
      key: 'last_checked_at',
      header: 'Última verificación',
      render: (item: ServiceResponse) =>
        item.last_checked_at ? new Date(item.last_checked_at).toLocaleString() : 'Nunca',
    },
    {
      key: 'auto_restart',
      header: 'Auto-restart',
      render: (item: ServiceResponse) => <AutoRestartBadge enabled={item.auto_restart} />,
    },
  ];

  const currentPage = Math.floor(offset / limit);
  const pagination: PaginationProps = {
    currentPage,
    hasNext: result.hasNext,
    onPrevious: () => {
      const newOffset = Math.max(0, offset - limit);
      window.location.href = `/entidades/servicios?offset=${newOffset}&limit=${limit}`;
    },
    onNext: () => {
      const newOffset = offset + limit;
      window.location.href = `/entidades/servicios?offset=${newOffset}&limit=${limit}`;
    },
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Servicios</h1>
          <p className="text-gray-500 mt-1">Lista de servicios monitoreados en este tenant</p>
        </div>
        <Link
          href="/entidades/servicios/nueva"
          className="px-4 py-2 bg-blue-600 text-white rounded-md text-sm font-medium hover:bg-blue-700 transition-colors"
        >
          Nuevo servicio
        </Link>
      </div>

      {result.error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-md text-red-700" role="alert">
          Error al cargar servicios: {result.error}
        </div>
      )}

      <EntityTable
        columns={columns}
        data={result.services}
        error={result.error}
        emptyMessage="No hay servicios configurados. Crea uno nuevo para empezar."
        pagination={pagination}
        rowKey={(item) => item.id}
      />
    </div>
  );
}