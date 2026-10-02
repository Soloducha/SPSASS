/** Formulario para editar un proceso. */

'use client';

import { EntityForm, FormField } from '@/components/EntityForm';
import { EntityActions } from '@/components/EntityActions';
import { updateProcessAction, deleteProcessAction } from '../../../actions';
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