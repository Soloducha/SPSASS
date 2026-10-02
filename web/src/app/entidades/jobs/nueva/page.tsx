/** Página para crear un nuevo job. */

'use client';

import { createJobAction } from '../actions';
import { CreateJobForm } from '../components/CreateJobForm';
import { useActionState } from 'react';
import Link from 'next/link';

export default function NuevoJobPage() {
  const [state, formAction, isPending] = useActionState(createJobAction, { success: false, message: '' });

  return (
    <div className="p-6 max-w-3xl mx-auto">
      <div className="mb-6">
        <Link
          href="/entidades/jobs"
          className="text-blue-600 hover:underline text-sm font-medium mb-4 inline-block"
        >
          ← Volver a jobs
        </Link>
        <h1 className="text-2xl font-bold text-gray-900">Nuevo job</h1>
        <p className="text-gray-500 mt-1">Configura un nuevo job programado</p>
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

      <CreateJobForm
        action={formAction}
        cancelHref="/entidades/jobs"
        isLoading={isPending}
        title="Datos del job"
      />
    </div>
  );
}