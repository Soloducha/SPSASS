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

export default async function ServicesPage({ searchParams }: ServicesPageProps) {
  const { result, offset, limit } = await getServicesPage(searchParams);

  const columns = [
    {
      key: 'name',
      header: 'Nombre',
      type: 'link' as const,
      linkBasePath: '/entidades/servicios/',
    },
    {
      key: 'server_id',
      header: 'Servidor',
      type: 'text' as const,
      // Custom rendering via customRenderer
      customRenderer: 'server_id_short',
    },
    {
      key: 'desired_state',
      header: 'Estado deseado',
      type: 'badge' as const,
      badgeVariantMap: {
        running: 'success' as const,
        stopped: 'error' as const,
        failed: 'error' as const,
        unknown: 'warning' as const,
      },
    },
    {
      key: 'last_status',
      header: 'Estado actual',
      type: 'badge' as const,
      badgeVariantMap: {
        running: 'success' as const,
        stopped: 'error' as const,
        failed: 'error' as const,
        unknown: 'warning' as const,
      },
    },
    {
      key: 'last_checked_at',
      header: 'Última verificación',
      type: 'date' as const,
      dateOptions: { dateStyle: 'short' as const, timeStyle: 'short' as const },
    },
    {
      key: 'auto_restart',
      header: 'Auto-restart',
      type: 'boolean' as const,
      booleanLabels: { true: 'Sí', false: 'No' },
    },
  ];

  const currentPage = Math.floor(offset / limit);
  const pagination = {
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
        <a
          href="/entidades/servicios/nueva"
          className="px-4 py-2 bg-blue-600 text-white rounded-md text-sm font-medium hover:bg-blue-700 transition-colors"
        >
          Nuevo servicio
        </a>
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
        pagination={{
          currentPage: Math.floor(offset / limit),
          hasNext: result.hasNext,
          onPrevious: () => {
            const newOffset = Math.max(0, offset - limit);
            window.location.href = `/entidades/servicios?offset=${newOffset}&limit=${limit}`;
          },
          onNext: () => {
            const newOffset = offset + limit;
            window.location.href = `/entidades/servicios?offset=${newOffset}&limit=${limit}`;
          },
        }}
        rowKey={(item) => item.id}
      />
    </div>
  );
}