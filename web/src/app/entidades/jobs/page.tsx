/** Lista de jobs - Server Component con SSR y paginación. */

import { Metadata } from 'next';
import { listJobs, JobResponse, JobKind, JobStatus } from '@/lib/api/jobs';
import { EntityTable, Badge, PaginationProps } from '@/components/EntityTable';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'Jobs - SPSAAS',
  description: 'Gestión de jobs programados',
};

interface JobsPageProps {
  searchParams: Promise<{ offset?: string; limit?: string }>;
}

async function getJobsPage(searchParams: Promise<{ offset?: string; limit?: string }>) {
  const params = await searchParams;
  const offset = Math.max(0, parseInt(params.offset ?? '0', 10));
  const limit = Math.min(500, Math.max(1, parseInt(params.limit ?? '50', 10)));

  const result = await listJobs({ offset, limit });
  return { result, offset, limit };
}

function JobKindBadge({ kind }: { kind: JobKind }) {
  const variants: Record<JobKind, 'info' | 'default' | 'success'> = {
    cron: 'info',
    batch: 'default',
    scheduled: 'success',
  };
  return <Badge variant={variants[kind] ?? 'default'}>{kind}</Badge>;
}

function JobStatusBadge({ status }: { status: JobStatus }) {
  const variants: Record<JobStatus, 'success' | 'warning' | 'error'> = {
    active: 'success',
    paused: 'warning',
    disabled: 'error',
  };
  return <Badge variant={variants[status] ?? 'default'}>{status}</Badge>;
}

function AutoRestartBadge({ enabled }: { enabled: boolean }) {
  if (!enabled) return null;
  return <Badge variant="info" className="ml-2">Auto-restart</Badge>;
}

export default async function JobsPage({ searchParams }: JobsPageProps) {
  const { result, offset, limit } = await getJobsPage(searchParams);

  const columns = [
    {
      key: 'name',
      header: 'Nombre',
      render: (item: JobResponse) => (
        <Link href={`/entidades/jobs/${item.id}/editar`} className="text-blue-600 hover:underline font-medium">
          {item.name}
        </Link>
      ),
    },
    {
      key: 'kind',
      header: 'Tipo',
      render: (item: JobResponse) => <JobKindBadge kind={item.kind} />,
    },
    {
      key: 'schedule_cron',
      header: 'Schedule (cron)',
      render: (item: JobResponse) =>
        item.schedule_cron ? (
          <span className="font-mono text-sm text-gray-500">{item.schedule_cron}</span>
        ) : (
          <span className="text-gray-400">—</span>
        ),
    },
    {
      key: 'command',
      header: 'Comando',
      render: (item: JobResponse) => (
        <span className="font-mono text-sm text-gray-500 max-w-[300px] truncate block">{item.command}</span>
      ),
    },
    {
      key: 'status',
      header: 'Estado',
      render: (item: JobResponse) => <JobStatusBadge status={item.status} />,
    },
    {
      key: 'auto_restart',
      header: 'Auto-restart',
      render: (item: JobResponse) => <AutoRestartBadge enabled={item.auto_restart} />,
    },
  ];

  const currentPage = Math.floor(offset / limit);
  const pagination: PaginationProps = {
    currentPage,
    hasNext: result.hasNext,
    onPrevious: () => {
      const newOffset = Math.max(0, offset - limit);
      window.location.href = `/entidades/jobs?offset=${newOffset}&limit=${limit}`;
    },
    onNext: () => {
      const newOffset = offset + limit;
      window.location.href = `/entidades/jobs?offset=${newOffset}&limit=${limit}`;
    },
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Jobs</h1>
          <p className="text-gray-500 mt-1">Lista de jobs programados en este tenant</p>
        </div>
        <Link
          href="/entidades/jobs/nueva"
          className="px-4 py-2 bg-blue-600 text-white rounded-md text-sm font-medium hover:bg-blue-700 transition-colors"
        >
          Nuevo job
        </Link>
      </div>

      {result.error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-md text-red-700" role="alert">
          Error al cargar jobs: {result.error}
        </div>
      )}

      <EntityTable
        columns={columns}
        data={result.jobs}
        error={result.error}
        emptyMessage="No hay jobs configurados. Crea uno nuevo para empezar."
        pagination={pagination}
        rowKey={(item) => item.id}
      />
    </div>
  );
}