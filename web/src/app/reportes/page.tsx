/** Lista de reportes - Server Component con SSR y paginación. */

import { Metadata } from 'next';
import { listReports, ReportResponse, ReportStatus, ReportType } from '@/lib/api/reports';
import { EntityTable, BadgeVariant } from '@/components/EntityTable';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'Reportes - SPSAAS',
  description: 'Gestión y visualización de reportes generados',
};

interface ReportsPageProps {
  searchParams: Promise<{
    offset?: string;
    limit?: string;
    type?: string;
    status?: string;
    period_start?: string;
    period_end?: string;
    page?: string;
  }>;
}

async function getReportsPage(searchParams: Promise<{
  offset?: string;
  limit?: string;
  type?: string;
  status?: string;
  period_start?: string;
  period_end?: string;
  page?: string;
}>) {
  const params = await searchParams;
  const page = Math.max(1, parseInt(params.page ?? '1', 10));
  const limit = Math.min(200, Math.max(1, parseInt(params.limit ?? '50', 10)));
  const offset = (page - 1) * limit;

  const result = await listReports({
    type: params.type as ReportType | undefined,
    status: params.status as ReportStatus | undefined,
    period_start: params.period_start,
    period_end: params.period_end,
    offset,
    limit,
    page,
  });

  return { result, page, limit, offset };
}

export default async function ReportsPage({ searchParams }: { searchParams: Promise<{
  offset?: string;
  limit?: string;
  type?: string;
  status?: string;
  period_start?: string;
  period_end?: string;
  page?: string;
}> }) {
  const { result, page, limit, offset } = await getReportsPage(searchParams);

  const columns = [
    {
      key: 'type',
      header: 'Tipo',
      type: 'badge' as const,
      badgeVariantMap: {
        availability: 'info' as BadgeVariant,
        incidents: 'warning' as BadgeVariant,
        alerts: 'warning' as BadgeVariant,
        sla: 'info' as BadgeVariant,
        metrics: 'info' as BadgeVariant,
      } as Record<string, BadgeVariant>,
      customRenderer: 'type_label',
    },
    {
      key: 'period_start',
      header: 'Período inicio',
      type: 'date' as const,
      dateOptions: { dateStyle: 'short' as const, timeStyle: 'short' as const },
    },
    {
      key: 'period_end',
      header: 'Período fin',
      type: 'date' as const,
      dateOptions: { dateStyle: 'short' as const, timeStyle: 'short' as const },
    },
    {
      key: 'status',
      header: 'Estado',
      type: 'badge' as const,
      badgeVariantMap: {
        pending: 'warning' as BadgeVariant,
        generating: 'info' as BadgeVariant,
        completed: 'success' as BadgeVariant,
        failed: 'error' as BadgeVariant,
        cancelled: 'warning' as BadgeVariant,
      } as Record<string, BadgeVariant>,
      customRenderer: 'status_label',
    },
    {
      key: 'generated_at',
      header: 'Generado',
      type: 'date' as const,
      dateOptions: { dateStyle: 'short' as const, timeStyle: 'short' as const },
    },
    {
      key: 'file_path',
      header: 'Archivo',
      type: 'text' as const,
      customRenderer: 'file_path_short',
    },
  ];

  const pagination = {
    currentPage: page - 1,
    hasNext: offset + limit < result.total,
    onPrevious: () => {
      const newPage = Math.max(1, page - 1);
      window.location.href = `/reportes?page=${newPage}&limit=${limit}`;
    },
    onNext: () => {
      const newPage = page + 1;
      window.location.href = `/reportes?page=${newPage}&limit=${limit}`;
    },
  };

  const typeLabelMap: Record<string, string> = {
    availability: 'Disponibilidad',
    incidents: 'Incidentes',
    alerts: 'Alertas',
    sla: 'SLA',
    metrics: 'Métricas',
  };

  const statusLabelMap: Record<string, string> = {
    pending: 'Pendiente',
    generating: 'Generando',
    completed: 'Completado',
    failed: 'Fallido',
    cancelled: 'Cancelado',
  };

  const customRenderers = {
    type_label: (value: unknown) => <span>{typeLabelMap[String(value)] ?? String(value)}</span>,
    status_label: (value: unknown) => <span>{statusLabelMap[String(value)] ?? String(value)}</span>,
    file_path_short: (value: unknown) => {
      const val = value as string | null;
      return val ? val.split('/').pop() ?? val : '—';
    },
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Reportes</h1>
          <p className="text-gray-500 mt-1">Gestión y visualización de reportes generados</p>
        </div>
        <div className="flex gap-2">
          <Link
            href="/reportes/nuevo"
            className="px-4 py-2 bg-blue-600 text-white rounded-md text-sm font-medium hover:bg-blue-700 transition-colors"
          >
            Generar reporte
          </Link>
        </div>
      </div>

      {result.error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-md text-red-700" role="alert">
          Error al cargar reportes: {result.error}
        </div>
      )}

      <EntityTable
        columns={columns}
        data={result.reports}
        error={result.error}
        emptyMessage="No hay reportes generados. Crea uno nuevo para empezar."
        pagination={pagination}
        rowKey={(item) => item.id}
        customRenderers={customRenderers}
      />
    </div>
  );
}

const typeLabelMap: Record<string, string> = {
  availability: 'Disponibilidad',
  incidents: 'Incidentes',
  alerts: 'Alertas',
  sla: 'SLA',
  metrics: 'Métricas',
};

const statusLabelMap: Record<string, string> = {
  pending: 'Pendiente',
  generating: 'Generando',
  completed: 'Completado',
  failed: 'Fallido',
  cancelled: 'Cancelado',
};

const customRenderers = {
  type_label: (value: unknown) => <span>{typeLabelMap[String(value)] ?? String(value)}</span>,
  status_label: (value: unknown) => <span>{statusLabelMap[String(value)] ?? String(value)}</span>,
  file_path_short: (value: unknown) => {
    const val = value as string | null;
    return val ? val.split('/').pop() ?? val : '—';
  },
};