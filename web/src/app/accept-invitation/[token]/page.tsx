'use client';

/**
 * Página de aceptación de invitación (/accept-invitation/[token]).
 *
 * Formulario público: la persona llega desde el link del email, elige
 * contraseña (y nombre opcional) y la Server Action acepta la invitación.
 * Un cliente existente en la plataforma ignora el nombre y la contraseña: la
 * invitación solo agrega la membresía al tenant.
 */

import type { FormEvent, ReactElement } from 'react';
import { use, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { acceptInvitationAction } from '../../invitations/actions';

interface AcceptInvitationPageProps {
  params: Promise<{ token: string }>;
}

const inputClass =
  'w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus-opacity-20 min-h-[44px]';

export default function AcceptInvitationPage({ params }: AcceptInvitationPageProps) {
  const { token } = use(params);
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setLoading(true);

    const formData = new FormData(event.currentTarget);
    const password = (formData.get('password') as string) || '';
    const fullName = ((formData.get('fullName') as string) || '').trim();

    const result = await acceptInvitationAction(token, password, fullName);

    if (result.error || !result.session) {
      setError(result.error ?? 'No se pudo aceptar la invitación');
      setLoading(false);
      return;
    }

    // La web todavía no tiene login con cookies (el dashboard se autentica con
    // SPSAAS_DASHBOARD_TOKEN), así que por ahora se vuelve al dashboard y los
    // tokens quedan disponibles para el flujo de login.
    router.push('/');
  }

  return (
    <main className="mx-auto max-w-md px-4 py-10" id="accept-invitation-main">
      <header className="mb-8">
        <nav className="mb-4 flex items-center gap-2 text-sm" aria-label="Ruta de navegación">
          <Link href="/" className="text-gray-500 hover:text-gray-700">Inicio</Link>
          <span className="text-gray-300" aria-hidden="true">/</span>
          <span className="text-gray-900 font-medium" aria-current="page">Aceptar invitación</span>
        </nav>
        <h1 id="accept-invitation-heading" className="text-2xl font-bold text-gray-900">
          Aceptar invitación
        </h1>
        <p className="mt-1 text-sm text-gray-500">
          Elegí una contraseña para crear tu acceso y sumarte al equipo.
        </p>
      </header>

      <form
        onSubmit={handleSubmit}
        className="space-y-4 rounded-lg border border-gray-200 bg-white p-6 shadow-sm"
        aria-labelledby="accept-invitation-heading"
      >
        <div>
          <label htmlFor="fullName" className="mb-1 block text-sm font-medium text-gray-700">
            Nombre (opcional)
          </label>
          <input
            id="fullName"
            name="fullName"
            type="text"
            maxLength={255}
            className={inputClass}
            placeholder="Tu nombre"
          />
        </div>

        <div>
          <label htmlFor="password" className="mb-1 block text-sm font-medium text-gray-700">
            Contraseña
          </label>
          <input
            id="password"
            name="password"
            type="password"
            required
            minLength={8}
            maxLength={128}
            className={inputClass}
            placeholder="Mínimo 8 caracteres"
            autoComplete="new-password"
          />
        </div>

        {error ? (
          <div
            className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700"
            role="alert"
          >
            {error}
          </div>
        ) : null}

        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60 min-h-[44px]"
        >
          {loading ? 'Aceptando…' : 'Aceptar invitación'}
        </button>
      </form>
    </main>
  );
}