/** Página para crear un nuevo proceso. */

'use client';

import { createProcessAction } from '../actions';
import { CreateProcessForm } from '../components/CreateProcessForm';
import { useActionState } from 'react';
import Link from 'next/link';

export default function NuevoProcesoPage() {
  const [state, formAction, isPending] = useActionState(createProcessAction, { success: false, message: '' });

  return (
    <div className="p-6 max-w-2xl mx-auto">
      <div className="mb-6">
        <Link
          href="/entidades/procesos"
          className="text-blue-600 hover:underline text-sm font-medium mb-4 inline-block"
        >
          ← Volver a procesos
        </Link>
        <h1 className="text-2xl font-bold text-gray-900">Nuevo proceso</h1>
        <p className="text-gray-500 mt-1">Configura un nuevo proceso para monitorear</p>
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

      <CreateProcessForm
        action={formAction}
        cancelHref="/entidades/procesos"
        isLoading={isPending}
        title="Datos del proceso"
      />
    </div>
  );
}