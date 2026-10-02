/** Página para crear un nuevo servicio. */

'use client';

import { createServiceAction } from '../actions';
import { CreateServiceForm } from '../components/CreateServiceForm';
import { useActionState } from 'react';
import Link from 'next/link';

export default function NuevaServicioPage() {
  const [state, formAction, isPending] = useActionState(createServiceAction, { success: false, message: '' });

  return (
    <div className="p-6 max-w-2xl mx-auto">
      <div className="mb-6">
        <Link
          href="/entidades/servicios"
          className="text-blue-600 hover:underline text-sm font-medium mb-4 inline-block"
        >
          ← Volver a servicios
        </Link>
        <h1 className="text-2xl font-bold text-gray-900">Nuevo servicio</h1>
        <p className="text-gray-500 mt-1">Configura un nuevo servicio para monitorear</p>
      </div>

      {state.message && (
        <div
          className={`mb-4 p-4 rounded-md ${
            state.success ? 'bg-green-50 text-green-700 border border-green-200' : 'bg-red-50 text-red-700 border border-red-200'
          }`}
          role="alert"
        >
          {state.message}
        </div>
      )}

      <CreateServiceForm
        action={formAction}
        cancelHref="/entidades/servicios"
        isLoading={isPending}
        title="Datos del servicio"
      />
    </div>
  );
}