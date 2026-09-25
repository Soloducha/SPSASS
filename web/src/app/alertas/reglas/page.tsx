/**
 * Página de lista de reglas de alerta (/alertas/reglas).
 * Server Component que obtiene la lista inicial y renderiza la tabla interactiva.
 */

import Link from 'next/link';
import { listAlertRules } from '@/lib/api/rules';
import { RulesTable } from './components/RulesTable';

export const dynamic = 'force-dynamic';

interface ReglasPageProps {
  searchParams: Promise<{
    offset?: string;
    limit?: string;
  }>;
}

const DEFAULT_LIMIT = 50;
const MAX_LIMIT = 500;

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

export default async function ReglasPage({ searchParams }: ReglasPageProps) {
  const params = await searchParams;

  const offset = parseOffset(params.offset);
  const limit = parseLimit(params.limit);

  const { rules, hasNext, error: rulesError } = await listAlertRules({ offset, limit });

  const initialParams = { offset, limit };

  return (
    <main className="mx-auto max-w-6xl px-4 py-10" id="reglas-main">
      <header className="mb-8">
        <nav className="mb-4 flex items-center gap-2 text-sm" aria-label="Ruta de navegación">
          <Link href="/" className="text-gray-500 hover:text-gray-700">
            Inicio
          </Link>
          <span className="text-gray-300" aria-hidden="true">/</span>
          <Link href="/alertas" className="text-gray-500 hover:text-gray-700">
            Alertas
          </Link>
          <span className="text-gray-300" aria-hidden="true">/</span>
          <span className="text-gray-900 font-medium" aria-current="page">Reglas</span>
        </nav>
        <div className="flex items-center justify-between">
          <div>
            <h1 id="reglas-heading" className="text-2xl font-bold text-gray-900">
              Reglas de alerta
            </h1>
            <p className="mt-1 text-sm text-gray-500">
              Gestión de reglas de alerta del tenant
            </p>
          </div>
          <Link
            href="/alertas/reglas/nueva"
            className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-opacity-20 min-h-[44px] min-w-[44px] inline-flex items-center justify-center"
          >
            Crear regla
          </Link>
        </div>
      </header>

      {rulesError ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700" role="alert">
          No se pudieron cargar las reglas: {rulesError}
        </div>
      ) : (
        <RulesTable
          initialRules={rules}
          initialHasNext={hasNext}
          initialParams={initialParams}
        />
      )}
    </main>
  );
}