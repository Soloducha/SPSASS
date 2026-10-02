/** Formulario para editar un proceso. */

'use client';

import { EntityForm, FormField } from '@/components/EntityForm';
import { EntityActions } from '@/components/EntityActions';
import { updateProcessAction, deleteProcessAction, restartProcessAction } from '../../../actions';
import { useActionState } from 'react';
import { useRouter } from 'next/navigation';

interface ProcessEditFormProps {
  initialData: {
    id: string;
    name: string;
    server_id: string;
    pattern: string;
    expected_count: number;
    auto_restart: boolean;
  };
  processId: string;
}

export function ProcessEditForm({ initialData, processId }: ProcessEditFormProps) {
  const router = useRouter();

  const [updateState, updateAction, isUpdatePending] = useActionState(
    (prevState: { success: boolean; message: string }, formData: FormData) =>
      updateProcessAction(processId, prevState, formData),
    { success: false, message: '' }
  );

  const [deleteState, deleteAction, isDeletePending] = useActionState(
    async (prevState: { success: boolean; message: string }) => {
      const result = await deleteProcessAction(processId);
      if (result.success) {
        router.push('/entidades/procesos');
        router.refresh();
      }
      return result;
    },
    { success: false, message: '' }
  );

  const [restartState, restartAction, isRestartPending] = useActionState(
    async () => {
      const result = await restartProcessAction(initialData.server_id, initialData.name);
      return result;
    },
    { success: false, message: '' }
  );

  const fields: FormField[] = [
    {
      name: 'name',
      label: 'Nombre del proceso',
      type: 'text',
      required: true,
      placeholder: 'nginx, redis, postgres...',
    },
    {
      name: 'pattern',
      label: 'Pattern (regex)',
      type: 'text',
      required: true,
      placeholder: 'nginx.*master, redis-server.*',
      helpText: 'Regex para matchear el proceso en la lista del sistema',
    },
    {
      name: 'expected_count',
      label: 'Conteo esperado',
      type: 'number',
      required: true,
      helpText: 'Número mínimo de procesos que deben estar corriendo',
    },
    {
      name: 'auto_restart',
      label: 'Auto-restart',
      type: 'checkbox',
      required: false,
      helpText: 'Si está habilitado, el agente intentará reiniciar automáticamente al detectar fallo',
    },
  ];

  const handleDelete = async () => {
    return deleteAction();
  };

  return (
    <div className="p-6 max-w-2xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Editar proceso</h1>
          <p className="text-gray-500 mt-1">{initialData.name} ({initialData.id.slice(0, 8)}…)</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="md:col-span-2">
          <EntityForm
            fields={fields}
            initialData={initialData}
            action={updateAction}
            cancelHref="/entidades/procesos"
            isLoading={isUpdatePending}
            title="Datos del proceso"
            submitLabel="Guardar cambios"
          />
        </div>

        <div className="space-y-4">
          <div className="bg-gray-50 p-4 rounded-lg">
            <h3 className="font-medium text-gray-900 mb-3">Información</h3>
            <dl className="space-y-2 text-sm">
              <div className="flex justify-between">
                <dt className="text-gray-500">ID</dt>
                <dd className="font-mono text-gray-900">{initialData.id}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-500">Servidor</dt>
                <dd className="font-mono text-gray-900">{initialData.server_id.slice(0, 8)}…</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-500">Pattern</dt>
                <dd className="font-mono text-gray-900">{initialData.pattern}</dd>
              </div>
            </dl>
          </div>

          {initialData.auto_restart && (
            <div className="mt-4 p-3 bg-blue-50 border border-blue-200 rounded-lg">
              <p className="text-sm text-blue-800 mb-2">
                Auto-restart está habilitado para este proceso.
              </p>
              <button
                type="button"
                onClick={() => restartAction()}
                disabled={isRestartPending}
                className="px-4 py-2 bg-blue-600 text-white rounded-md text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {isRestartPending ? (
                  <span className="flex items-center gap-2">
                    <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                    Reiniciando...
                  </span>
                ) : (
                  'Reiniciar ahora'
                )}
              </button>
              {restartState.message && (
                <p className={`mt-2 text-sm ${
                  restartState.success ? 'text-green-700' : 'text-red-700'
                }`}>
                  {restartState.message}
                </p>
              )}
            </div>
          )}

          <EntityActions
            entityName={initialData.name}
            onEdit={() => {}}
            onDelete={handleDelete}
            isDeleting={isDeletePending}
            deleteLabel="Eliminar proceso"
          />
        </div>
      </div>

      {(updateState.message || deleteState.message) && (
        <div
          className={`p-4 rounded-md ${
            (updateState.success || deleteState.success) ? 'bg-green-50 text-green-700 border border-green-200' : 'bg-red-50 text-red-700 border border-red-200'
          }`}
          role="alert"
        >
          {updateState.message || deleteState.message}
        </div>
      )}
    </div>
  );
}