/** Historial de ejecuciones de un job (JobRuns) - Server Component con SSR y paginación. */

import { Metadata } from 'next';
import { notFound } from 'next/navigation';
import { getJobData, getJobRunsData } from '../../actions';
import { JobRunResponse } from '@/lib/api/jobs';
import { EntityTable, Badge } from '@/components/EntityTable';
import Link from 'next/link';
import { ChevronLeftIcon, ChevronRightIcon } from '@heroicons/react/24/outline';

interface JobRunsPageProps {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ offset?: string; limit?: string }>;
}

async function getPageData(params: Promise<{ id: string }>, searchParams: Promise<{ offset?: string; limit?: string }>) {
  const { id } = await params;
  const sParams = await searchParams;
  const offset = Math.max(0, parseInt(sParams.offset ?? '0', 10));
  const limit = Math.min(500, Math.max(1, parseInt(sParams.limit ?? '50', 10)));

  const [job, runsResult] = await Promise.all([
    getJobData(id),
    getJobRunsData(id, offset, limit),
  ]);

  if (!job) {
    notFound();
  }

  return { job, runsResult, offset, limit };
}

function RunStatusBadge({ status }: { status: string }) {
  const variants: Record<string, 'success' | 'error' | 'warning' | 'info'> = {
    running: 'info',
    success: 'success',
    failed: 'error',
    timeout: 'error',
  };
  return <Badge variant={variants[status] ?? 'default'}>{status}</Badge>;
}

// Simple pagination component (Server Component - just links)
interface PaginationProps {
  jobId: string;
  currentPage: number;
  hasNext: boolean;
  offset: number;
  limit: number;
  prevOffset: number;
  nextOffset: number;
}

function Pagination({ jobId, currentPage, hasNext, prevOffset, nextOffset, limit }: PaginationProps) {
  return (
    <div className="flex items-center justify-between px-4 py-3 border-t">
      <div className="flex items-center gap-2">
        <Link
          href={`/entidades/jobs/${jobId}/runs?offset=${prevOffset}&limit=${limit}`}
          className={`p-2 rounded-md text-gray-500 hover:text-gray-700 hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed transition-colors ${
            currentPage === 0 ? 'pointer-events-none opacity-50' : ''
          }`}
          aria-label="Página anterior"
        >
          <ChevronLeftIcon className="h-5 w-5" />
        </Link>
        <span className="text-sm text-gray-600 min-w-[3rem] text-center">
          Página {currentPage + 1}
        </span>
        <Link
          href={`/entidades/jobs/${jobId}/runs?offset=${nextOffset}&limit=${limit}`}
          className={`p-2 rounded-md text-gray-500 hover:text-gray-700 hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed transition-colors ${
            !hasNext ? 'pointer-events-none opacity-50' : ''
          }`}
          aria-label="Página siguiente"
        >
          <ChevronRightIcon className="h-5 w-5" />
        </Link>
      </div>
    </div>
  );
}

export async function generateMetadata({ params }: JobRunsPageProps): Promise<Metadata> {
  const { id } = await params;
  return {
    title: `Ejecuciones del job ${id.slice(0, 8)} - SPSAAS`,
  };
}

export default async function JobRunsPage({ params, searchParams }: JobRunsPageProps) {
  const { job, runsResult, offset, limit } = await getPageData(params, searchParams);

  const columns = [
    {
      key: 'started_at',
      header: 'Iniciado',
      render: (item: JobRunResponse) => new Date(item.started_at).toLocaleString(),
    },
    {
      key: 'finished_at',
      header: 'Finalizado',
      render: (item: JobRunResponse) =>
        item.finished_at ? new Date(item.finished_at).toLocaleString() : 'En curso...',
    },
    {
      key: 'status',
      header: 'Estado',
      render: (item: JobRunResponse) => <RunStatusBadge status={item.status} />,
    },
    {
      key: 'exit_code',
      header: 'Exit code',
      render: (item: JobRunResponse) =>
        item.exit_code !== null ? (
          <span className={`font-mono text-sm ${item.exit_code === 0 ? 'text-green-600' : 'text-red-600'}`}>
            {item.exit_code}
          </span>
        ) : (
          <span className="text-gray-400">—</span>
        ),
    },
    {
      key: 'output_tail',
      header: 'Output (últimas líneas)',
      render: (item: JobRunResponse) =>
        item.output_tail ? (
          <details className="group">
            <summary className="text-gray-500 text-sm cursor-pointer hover:text-gray-700">
              Ver output ({item.output_tail.length} chars)
            </summary>
            <pre className="mt-1 p-2 bg-gray-100 rounded text-xs overflow-x-auto whitespace-pre-wrap font-mono text-gray-800">
              {item.output_tail}
            </pre>
          </details>
        ) : (
          <span className="text-gray-400">—</span>
        ),
    },
  ];

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link
            href={`/entidades/jobs/${job.id}/editar`}
            className="text-blue-600 hover:underline text-sm font-medium"
          >
            ← Volver al job
          </Link>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Ejecuciones del job</h1>
            <p className="text-gray-500 mt-1">{job.name} ({job.id.slice(0, 8)}…)</p>
          </div>
        </div>
      </div>

      {runsResult.error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-md text-red-700" role="alert">
          Error al cargar ejecuciones: {runsResult.error}
        </div>
      )}

      <EntityTable
        columns={columns}
        data={runsResult.runs}
        error={runsResult.error}
        emptyMessage="Este job no tiene ejecuciones registradas aún."
        rowKey={(item) => item.id}
      />
      <Pagination
        jobId={job.id}
        currentPage={Math.floor(offset / limit)}
        hasNext={runsResult.hasNext}
        prevOffset={Math.max(0, offset - limit)}
        nextOffset={offset + limit}
        limit={limit}
        offset={offset}
      />
    </div>
  );
}