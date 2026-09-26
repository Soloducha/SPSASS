/**
 * Página de lista de alertas (/alertas).
 * Server Component que obtiene la lista inicial y renderiza la tabla interactiva.
 */

import Link from 'next/link';
import { listAlerts } from '@/lib/api/alerts';
import { AlertsTable } from './components/AlertsTable';
import type { AlertListParams, AlertResponse, AlertStatus, AlertSeverity } from '@/lib/api/alerts';

export const dynamic = 'force-dynamic';

interface AlertsPageProps {
  searchParams: Promise<{
    status?: string;
    severity?: string;
    rule_id?: string;
    offset?: string;
    limit?: string;
  }>;
}

const DEFAULT_LIMIT = 50;
const MAX_LIMIT = 50;

function parseAlertStatus(value: string | undefined): AlertStatus | undefined {
  if (!value) return undefined;
  const validStatuses: AlertStatus[] = ['open', 'acknowledged', 'resolved'];
  return validStatuses.includes(value as AlertStatus) ? (value as AlertStatus) : undefined;
}

function parseAlertSeverity(value: string | undefined): AlertSeverity | undefined {
  if (!value) return undefined;
  const validSeverities: AlertSeverity[] = ['info', 'warning', 'critical'];
  return validSeverities.includes(value as AlertSeverity) ? (value as AlertSeverity) : undefined;
}

function parseOffset(value: string | undefined): number {
  if (!value) return 0;
  const parsed = parseInt(value, 10);
  return Number.isNaN(parsed) || parsed < 0 ? 0 : parsed;
}

function parseLimit(value: string | undefined): number {
  if (!value) return DEFAULT_LIMIT;
  const parsed = parseInt(value, 10);
  return Number.isNaN(parsed) || parsed < 1 ? DEFAULT_LIMIT : Math.min(parsed, MAX_LIMIT);
}

export default async function AlertasPage({ searchParams }: AlertsPageProps) {
  const params = await searchParams;

  const status = parseAlertStatus(params.status);
  const severity = parseAlertSeverity(params.severity);
  const rule_id = params.rule_id?.trim() || undefined;
  const offset = parseOffset(params.offset);
  const limit = parseLimit(params.limit);

  // If filters are provided but offset is not 0, we still use the provided offset
  // but the client component will reset to 0 when filters change via form submission

  const { alerts, hasNext, error } = await listAlerts({
    status,
    severity,
    rule_id,
    offset,
    limit,
  });

  // Build the initial params for the client component
  const initialParams: AlertListParams = {
    status,
    severity,
    rule_id,
    offset,
    limit,
  };

  // Async function to be called by client component for refetching
  async function fetchAlertsClient(newParams: AlertListParams) {
    // This function will be called from the client component via server action
    // For now, we pass the initial data and the client handles navigation
    // The actual refetching happens via page reload with new searchParams
    // This is a limitation of pure Server Components without server actions for data fetching
    // In a full implementation with T2, we'd use Server Actions for mutations and revalidation
  }

  return (
    <main className="mx-auto max-w-6xl px-4 py-10" id="alertas-main">
      <header className="mb-8">
        <nav className="mb-4 flex items-center gap-2 text-sm" aria-label="Ruta de navegación">
          <Link href="/" className="text-gray-500 hover:text-gray-700">
            Inicio
          </Link>
          <span className="text-gray-300" aria-hidden="true">/</span>
          <span className="text-gray-900 font-medium" aria-current="page">Alertas</span>
        </nav>
        <h1 id="alertas-heading" className="text-2xl font-bold text-gray-900">
          Alertas
        </h1>
        <p className="mt-1 text-sm text-gray-500">
          Gestión y seguimiento de alertas del tenant
        </p>
      </header>

      {error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700" role="alert">
          No se pudieron cargar las alertas: {error}
        </div>
      ) : (
        <AlertsTable
          initialAlerts={alerts}
          initialHasNext={hasNext}
          initialParams={{ ...initialParams, offset, limit }}
          onFetch={fetchAlertsClient}
        />
      )}
    </main>
  );
}