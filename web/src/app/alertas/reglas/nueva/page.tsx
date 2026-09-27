/**
 * Página de creación de regla de alerta (/alertas/reglas/nueva).
 * Server Component que obtiene la lista de servidores y renderiza el formulario.
 */

import Link from 'next/link';
import { getDashboardOverview } from '@/lib/api/dashboard';
import { CreateRuleForm } from './components/CreateRuleForm';

export const dynamic = 'force-dynamic';

export default async function NuevaReglaPage() {
  const { data: overview, error: overviewError } = await getDashboardOverview();

  const servers = overview?.servers ?? [];

  return (
    <main className="mx-auto max-w-3xl px-4 py-10" id="nueva-regla-main">
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
          <Link href="/alertas/reglas" className="text-gray-500 hover:text-gray-700">
            Reglas
          </Link>
          <span className="text-gray-300" aria-hidden="true">/</span>
          <span className="text-gray-900 font-medium" aria-current="page">Nueva regla</span>
        </nav>
        <h1 id="nueva-regla-heading" className="text-2xl font-bold text-gray-900">
          Crear regla de alerta
        </h1>
        <p className="mt-1 text-sm text-gray-500">
          Define una nueva regla para monitorear métricas y disparar alertas
        </p>
      </header>

      {overviewError ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700" role="alert">
          No se pudo cargar la lista de servidores: {overviewError}
        </div>
      ) : (
        <CreateRuleForm servers={servers} />
      )}
    </main>
  );
}