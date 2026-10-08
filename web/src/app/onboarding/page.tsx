'use client';

import type { FormEvent, ReactElement } from 'react';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { onboardingAction } from './actions';

const STEPS = [
  { key: 'register', label: 'Registro', description: 'Crea tu tenant y usuario admin' },
  { key: 'server', label: 'Servidor', description: 'Registra tu primer servidor' },
  { key: 'apikey', label: 'API Key', description: 'Genera tu clave de API para el agente' },
  { key: 'instructions', label: 'Instrucciones', description: 'Instala el agente en tu servidor' },
  { key: 'verify', label: 'Verificación', description: 'Confirma que el agente reporta métricas' },
  { key: 'complete', label: '¡Listo!', description: 'Onboarding completado' },
] as const;

type StepKey = (typeof STEPS)[number]['key'];

interface OnboardingState {
  step: StepKey;
  tenantId?: string;
  serverId?: string;
  hostname?: string;
  apiKey?: string;
  error?: string;
  loading?: boolean;
}

const inputClass =
  'w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus-opacity-20 min-h-[44px]';

function OnboardingForm() {
  const router = useRouter();
  const [state, setState] = useState<OnboardingState>({
    step: 'register',
    loading: false,
  });

  const currentStepIndex = STEPS.findIndex(s => s.key === state.step);
  const currentStep = STEPS[currentStepIndex];

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setState(prev => ({ ...prev, loading: true, error: undefined }));

    const formData = new FormData(event.currentTarget);
    const hostname = (formData.get('hostname') as string) || undefined;

    const result = await onboardingAction({ step: state.step }, formData);

    if (result.error) {
      setState(prev => ({ ...prev, error: result.error, loading: false }));
      return;
    }

    if (result.step === 'complete') {
      router.push('/');
      return;
    }

    setState(prev => ({
      ...prev,
      step: result.step,
      tenantId: result.tenantId ?? prev.tenantId,
      serverId: result.serverId ?? prev.serverId,
      hostname: hostname ?? prev.hostname,
      apiKey: result.apiKey ?? prev.apiKey,
      loading: false,
    }));
  }

  function goBack() {
    if (currentStepIndex > 0) {
      setState(prev => ({ ...prev, step: STEPS[currentStepIndex - 1].key, error: undefined }));
    }
  }

  function renderStepContent(): ReactElement {
    switch (state.step) {
      case 'register':
        return (
          <div className="space-y-4">
            <div>
              <label htmlFor="tenantName" className="block text-sm font-medium text-gray-700 mb-1">
                Nombre de tu organización <span className="text-red-500">*</span>
              </label>
              <input type="text" id="tenantName" name="tenantName" required className={inputClass} placeholder="Mi Empresa" />
            </div>
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-1">
                Email <span className="text-red-500">*</span>
              </label>
              <input type="email" id="email" name="email" required className={inputClass} placeholder="admin@miempresa.com" />
            </div>
            <div>
              <label htmlFor="password" className="block text-sm font-medium text-gray-700 mb-1">
                Contraseña <span className="text-red-500">*</span>
              </label>
              <input
                type="password"
                id="password"
                name="password"
                required
                minLength={8}
                className={inputClass}
                placeholder="Mínimo 8 caracteres"
              />
            </div>
          </div>
        );

      case 'server':
        return (
          <div className="space-y-4">
            <div>
              <label htmlFor="hostname" className="block text-sm font-medium text-gray-700 mb-1">
                Hostname del servidor <span className="text-red-500">*</span>
              </label>
              <input type="text" id="hostname" name="hostname" required className={inputClass} placeholder="web-prod-01" />
            </div>
            <div>
              <label htmlFor="ip" className="block text-sm font-medium text-gray-700 mb-1">
                IP (opcional)
              </label>
              <input type="text" id="ip" name="ip" className={inputClass} placeholder="192.168.1.10" />
            </div>
            <div>
              <label htmlFor="os" className="block text-sm font-medium text-gray-700 mb-1">
                Sistema operativo (opcional)
              </label>
              <select id="os" name="os" className={inputClass}>
                <option value="">Seleccionar...</option>
                <option value="linux">Linux</option>
                <option value="windows">Windows</option>
                <option value="freebsd">FreeBSD</option>
              </select>
            </div>
          </div>
        );

      case 'apikey':
        return (
          <div className="space-y-6">
            <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
              <h3 className="text-lg font-semibold text-gray-900 mb-2">Tu API Key</h3>
              <div className="rounded-lg border border-gray-300 bg-gray-50 p-4 font-mono text-sm break-all text-indigo-600">
                {state.apiKey || 'Generando...'}
              </div>
              <p className="mt-3 text-sm text-gray-500">
                Guarda esta clave en un lugar seguro. No se volverá a mostrar.
              </p>
            </div>
          </div>
        );

      case 'instructions':
        return (
          <div className="space-y-6">
            <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
              <h3 className="text-lg font-semibold text-gray-900 mb-4">Instalación del Agente</h3>
              <p className="text-gray-600 mb-4">
                Ejecuta el siguiente comando en tu servidor para instalar y configurar el agente SPSAAS:
              </p>
              <div className="rounded-lg border border-gray-300 bg-gray-900 p-4 font-mono text-sm text-green-300 overflow-x-auto">
                <pre>{`curl -fsSL https://get.spsaas.io/install.sh | bash -s -- --api-key ${state.apiKey} --api-url https://api.tudominio.com`}</pre>
              </div>
              <p className="mt-4 text-sm text-gray-500">
                <strong>Requisitos:</strong> Linux (systemd), curl, bash. Para Windows, descarga el binario desde{' '}
                <a href="https://github.com/tuorg/spsaas-agent/releases" target="_blank" rel="noopener noreferrer" className="text-indigo-600 hover:underline">
                  releases
                </a>
                .
              </p>
            </div>
            <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
              <h4 className="font-medium text-gray-900 mb-2">Configuración manual (opcional)</h4>
              <p className="text-sm text-gray-600 mb-2">Crea el archivo de configuración:</p>
              <div className="rounded-lg border border-gray-300 bg-gray-50 p-4 font-mono text-sm overflow-x-auto">
                <pre>{`[agent]
api_key = "${state.apiKey}"
api_url = "https://api.tudominio.com"
server_id = "${state.serverId}"`}</pre>
              </div>
              <p className="mt-2 text-sm text-gray-500">
                Ubicación: <code className="font-mono bg-gray-100 px-1 rounded">/etc/spsaas/agent.toml</code>
              </p>
            </div>
          </div>
        );

      case 'verify':
        return (
          <div className="space-y-6">
            <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm text-center">
              <div className="mx-auto w-16 h-16 rounded-full border-4 border-indigo-500 border-t-transparent animate-spin mb-4" />
              <h3 className="text-lg font-semibold text-gray-900">Verificando conexión del agente...</h3>
              <p className="mt-2 text-gray-600">Esperando primer heartbeat del agente...</p>
            </div>
            <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm text-sm text-gray-600">
              <p>El agente debería reportar métricas dentro de 1-2 minutos después de la instalación.</p>
              <p className="mt-2">Si el agente no conecta, verifica:</p>
              <ul className="mt-2 list-disc list-inside space-y-1 text-sm">
                <li>El servidor tiene acceso a internet</li>
                <li>La API Key es correcta</li>
                <li>
                  El firewall permite conexiones salientes a{' '}
                  <code className="font-mono">api.tudominio.com:443</code>
                </li>
                <li>
                  El servicio <code className="font-mono">spsaas-agent</code> está corriendo:{' '}
                  <code className="font-mono bg-gray-100 px-1 rounded">systemctl status spsaas-agent</code>
                </li>
              </ul>
            </div>
          </div>
        );

      case 'complete':
        return (
          <div className="space-y-6 text-center">
            <div className="mx-auto w-20 h-20 rounded-full bg-green-100 flex items-center justify-center">
              <svg className="w-10 h-10 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h2 className="text-2xl font-bold text-gray-900">¡Onboarding completado!</h2>
            <p className="text-gray-600 max-w-md mx-auto">
              Tu tenant está configurado, el servidor registrado y el agente instalado. Ya puedes ver métricas en tiempo
              real en el dashboard.
            </p>
            <div className="mt-8 flex justify-center gap-4">
              <Link
                href="/"
                className="px-6 py-3 bg-indigo-600 text-white rounded-md text-sm font-medium hover:bg-indigo-700 transition-colors"
              >
                Ir al Dashboard
              </Link>
              <Link
                href="/entidades/servidores"
                className="px-6 py-3 border border-gray-300 text-gray-700 rounded-md text-sm font-medium hover:bg-gray-50 transition-colors"
              >
                Ver servidores
              </Link>
            </div>
          </div>
        );
    }
  }

  return (
    <form id="onboarding-form" onSubmit={handleSubmit} className="mx-auto max-w-2xl px-4 py-10">
      {/* Progress indicator */}
      <nav className="mb-8" aria-label="Pasos del onboarding">
        <ol className="flex items-center" role="list">
          {STEPS.map((step, index) => (
            <li key={step.key} className="flex items-center flex-1">
              <span
                className={`flex h-8 w-8 items-center justify-center rounded-full text-sm font-medium ${
                  index <= currentStepIndex ? 'bg-indigo-600 text-white' : 'bg-gray-200 text-gray-500'
                }`}
              >
                {index + 1}
              </span>
              {index < STEPS.length - 1 && <div className="flex-1 h-1 mx-2 bg-gray-200" />}
              <span
                className={`hidden sm:block text-xs font-medium text-center ${
                  index <= currentStepIndex ? 'text-indigo-600' : 'text-gray-400'
                }`}
              >
                {step.label}
              </span>
            </li>
          ))}
        </ol>
      </nav>

      {/* Hidden fields: el action se deriva del paso actual */}
      <input type="hidden" name="action" value={state.step} />
      {state.tenantId && <input type="hidden" name="tenantId" value={state.tenantId} />}
      {state.serverId && <input type="hidden" name="serverId" value={state.serverId} />}
      {state.hostname && <input type="hidden" name="hostname" value={state.hostname} />}

      {state.error && (
        <div className="mb-6 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700" role="alert">
          {state.error}
        </div>
      )}

      <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
        <h2 className="mb-4 text-xl font-semibold text-gray-900">{currentStep?.label}</h2>
        <p className="mb-6 text-gray-600">{currentStep?.description}</p>
        {renderStepContent()}
      </div>

      {/* Navigation */}
      {state.step !== 'complete' && (
        <div className="mt-6 flex justify-between">
          {state.step !== 'register' ? (
            <button
              type="button"
              onClick={goBack}
              className="px-4 py-2 text-gray-700 border border-gray-300 rounded-md hover:bg-gray-50 transition-colors"
            >
              ← Anterior
            </button>
          ) : (
            <span />
          )}
          <button
            type="submit"
            disabled={state.loading}
            className="px-6 py-3 bg-indigo-600 text-white rounded-md text-sm font-medium hover:bg-indigo-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {state.loading ? 'Procesando...' : state.step === 'verify' ? 'Completar' : 'Siguiente →'}
          </button>
        </div>
      )}
    </form>
  );
}

export default function OnboardingPage() {
  return <OnboardingForm />;
}