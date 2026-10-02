/** Lista de procesos - Server Component con SSR y paginación. */

import { Metadata } from 'next';
import { listProcesses, ProcessResponse } from '@/lib/api/processes';
import { EntityTable, Badge, PaginationProps } from '@/components/EntityTable';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'Procesos - SPSAAS',
  description: 'Gestión de procesos monitoreados',
};

interface ProcessesPageProps {
  searchParams: Promise<{ offset?: string; limit?: string }>;
}

async function getProcessesPage(searchParams: Promise<{ offset?: string; limit?: string }>) {
  const params = await searchParams;
  const offset = Math.max(0, parseInt(params.offset ?? '0', 10));
  const limit = Math.min(500, Math.max(1, parseInt(params.limit ?? '50', 10)));

  const result = await listProcesses({ offset, limit });
  return { result, offset, limit };
}

function AutoRestartBadge({ enabled }: { enabled: boolean }) {
  if (!enabled) return null;
  return <Badge variant="info" className="ml-2">Auto-restart</Badge>;
}

export default async function ProcessesPage({ searchParams }: ProcessesPageProps) {
  const { result, offset, limit } = await getProcessesPage(searchParams);

  const columns = [
    {
      key: 'name',
      header: 'Nombre',
      render: (item: ProcessResponse) => (
        <Link href={`/entidades/procesos/${item.id}/editar`} className="text-blue-600 hover:underline font-medium">
          {item.name}
        </Link>
      ),
    },
    {
      key: 'pattern',
      header: 'Pattern (regex)',
      render: (item: ProcessResponse) => (
        <span className="font-mono text-sm text-gray-500">{item.pattern}</span>
      ),
    },
    {
      key: 'expected_count',
      header: 'Esperado',
      render: (item: ProcessResponse) => <span className="text-center">{item.expected_count}</span>,
      className: 'text-center',
    },
    {
      key: 'server_id',
      header: 'Servidor',
      render: (item: ProcessResponse) => (
        <span className="font-mono text-sm text-gray-500">{item.server_id.slice(0, 8)}…</span>
      ),
    },
    {
      key: 'auto_restart',
      header: 'Auto-restart',
      render: (item: ProcessResponse) => <AutoRestartBadge enabled={item.auto_restart} />,
    },
  ];

  const currentPage = Math.floor(offset / limit);
  const pagination: PaginationProps = {
    currentPage,
    hasNext: result.hasNext,
    onPrevious: () => {
      const newOffset = Math.max(0, offset - limit);
      window.location.href = `/entidades/procesos?offset=${newOffset}&limit=${limit}`;
    },
    onNext: () => {
      const newOffset = offset + limit;
      window.location.href = `/entidades/procesos?offset=${newOffset}&limit=${limit}`;
    },
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Procesos</h1>
          <p className="text-gray-500 mt-1">Lista de procesos monitoreados en este tenant</p>
        </div>
        <Link
          href="/entidades/procesos/nueva"
          className="px-4 py-2 bg-blue-600 text-white rounded-md text-sm font-medium hover:bg-blue-700 transition-colors"
        >
          Nuevo proceso
        </Link>
      </div>

      {result.error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-md text-red-700" role="alert">
          Error al cargar procesos: {result.error}
        </div>
      )}

      <EntityTable
        columns={columns}
        data={result.processes}
        error={result.error}
        emptyMessage="No hay procesos configurados. Crea uno nuevo para empezar."
        pagination={pagination}
        rowKey={(item) => item.id}
      />
    </div>
  );
}