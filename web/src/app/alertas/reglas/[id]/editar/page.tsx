/**
 * Página de edición de regla de alerta (/alertas/reglas/[id]/editar).
 * Server Component que obtiene la regla y la lista de servidores, renderiza el formulario pre-rellenado.
 */

import Link from 'next/link';
import { notFound } from 'next/navigation';
import { getAlertRule } from '@/lib/api/rules';
import { getDashboardOverview } from '@/lib/api/dashboard';
import { EditRuleForm } from './components/EditRuleForm';
import { mapApiError } from '../../utils';

export const dynamic = 'force-dynamic';

interface EditarReglaPageProps {
  params: Promise<{ id: string }>;
}

export default async function EditarReglaPage({ params }: EditarReglaPageProps) {
  const { id: ruleId } = await params;

  const [{ data: rule, error: ruleError, status: ruleStatus }, { data: overview, error: overviewError, status: overviewStatus }] = await Promise.all([
    getAlertRule(ruleId),
    getDashboardOverview(),
  ]);

  const servers = overview?.servers ?? [];

  if (ruleError) {
    // 404 → notFound() using typed status, not string sniffing
    if (ruleStatus === 404) {
      notFound();
    }
    // Missing token (status === null with specific message) → neutral missing-token pattern
    const isMissingToken = ruleStatus === null && ruleError.includes('Token de dashboard no configurado');
    return (
      <main className="mx-auto max-w-3xl px-4 py-10" id="editar-regla-main">
        <header className="mb-8">
          <nav className="mb-4 flex items-center gap-2 text-sm" aria-label="Ruta de navegación">
            <Link href="/" className="text-gray-500 hover:text-gray-700">Inicio</Link>
            <span className="text-gray-300" aria-hidden="true">/</span>
            <Link href="/alertas" className="text-gray-500 hover:text-gray-700">Alertas</Link>
            <span className="text-gray-300" aria-hidden="true">/</span>
            <Link href="/alertas/reglas" className="text-gray-500 hover:text-gray-700">Reglas</Link>
            <span className="text-gray-300" aria-hidden="true">/</span>
            <span className="text-gray-900 font-medium" aria-current="page">Editar regla</span>
          </nav>
          <h1 id="editar-regla-heading" className="text-2xl font-bold text-gray-900">
            Editar regla de alerta
          </h1>
        </header>
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700" role="alert">
          {isMissingToken
            ? 'Token de dashboard no configurado. Configure SPSAAS_DASHBOARD_TOKEN en el entorno del servidor.'
            : `No se pudo cargar la regla: ${mapApiError(ruleStatus, ruleError)}`}
        </div>
      </main>
    );
  }

  if (!rule) {
    notFound();
  }

  return (
    <main className="mx-auto max-w-3xl px-4 py-10" id="editar-regla-main">
      <header className="mb-8">
        <nav className="mb-4 flex items-center gap-2 text-sm" aria-label="Ruta de navegación">
          <Link href="/" className="text-gray-500 hover:text-gray-700">Inicio</Link>
          <span className="text-gray-300" aria-hidden="true">/</span>
          <Link href="/alertas" className="text-gray-500 hover:text-gray-700">Alertas</Link>
          <span className="text-gray-300" aria-hidden="true">/</span>
          <Link href="/alertas/reglas" className="text-gray-500 hover:text-gray-700">Reglas</Link>
          <span className="text-gray-300" aria-hidden="true">/</span>
          <span className="text-gray-900 font-medium" aria-current="page">Editar regla</span>
        </nav>
        <h1 id="editar-regla-heading" className="text-2xl font-bold text-gray-900">
          Editar regla de alerta
        </h1>
        <p className="mt-1 text-sm text-gray-500">
          Modifique la configuración de la regla: {rule.id.slice(0, 8)}…
        </p>
      </header>

      {overviewError ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700" role="alert">
          No se pudo cargar la lista de servidores: {mapApiError(overviewStatus, overviewError)}
        </div>
      ) : (
        <EditRuleForm rule={rule} servers={servers} />
      )}
    </main>
  );
}