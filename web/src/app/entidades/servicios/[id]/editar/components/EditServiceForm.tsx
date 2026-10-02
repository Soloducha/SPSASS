/** Formulario para editar un servicio. */

'use client';

import { EntityForm, FormField } from '@/components/EntityForm';
import { EntityActions } from '@/components/EntityActions';
import { updateServiceAction, deleteServiceAction } from '../../../actions';
import { ServiceState } from '@/lib/api/services';
import { useActionState } from 'react';
import { useRouter } from 'next/navigation';

interface ServiceEditFormProps {
  initialData: {
    id: string;
    name: string;
    server_id: string;
    desired_state: ServiceState;
    auto_restart: boolean;
    last_status: ServiceState;
    last_checked_at: string | null;
  };
  serviceId: string;
}

const stateOptions: { value: ServiceState; label: string }[] = [
  { value: 'running', label: 'Running' },
  { value: 'stopped', label: 'Stopped' },
  { value: 'failed', label: 'Failed' },
  { value: 'unknown', label: 'Unknown' },
];

export function ServiceEditForm({ initialData, serviceId }: ServiceEditFormProps) {
  const router = useRouter();

  const [updateState, updateAction, isUpdatePending] = useActionState(
    (prevState: { success: boolean; message: string }, formData: FormData) =>
      updateServiceAction(serviceId, prevState, formData),
    { success: false, message: '' }
  );

  const [deleteState, deleteAction, isDeletePending] = useActionState(
    async (prevState: { success: boolean; message: string }) => {
      const result = await deleteServiceAction(serviceId);
      if (result.success) {
        router.push('/entidades/servicios');
        router.refresh();
      }
      return result;
    },
    { success: false, message: '' }
  );

  const fields: FormField[] = [
    {
      name: 'name',
      label: 'Nombre del servicio',
      type: 'text',
      required: true,
      placeholder: 'nginx, postgresql, redis...',
    },
    {
      name: 'desired_state',
      label: 'Estado deseado',
      type: 'select',
      required: true,
      options: stateOptions,
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
          <h1 className="text-2xl font-bold text-gray-900">Editar servicio</h1>
          <p className="text-gray-500 mt-1">{initialData.name} ({initialData.id.slice(0, 8)}…)</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="md:col-span-2">
          <EntityForm
            fields={fields}
            initialData={initialData}
            action={updateAction}
            cancelHref="/entidades/servicios"
            isLoading={isUpdatePending}
            title="Datos del servicio"
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
                <dt className="text-gray-500">Estado actual</dt>
                <dd>
                  <span
                    className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                      initialData.last_status === 'running' ? 'bg-green-100 text-green-800' :
                      initialData.last_status === 'stopped' ? 'bg-red-100 text-red-800' :
                      initialData.last_status === 'failed' ? 'bg-red-100 text-red-800' :
                      'bg-yellow-100 text-yellow-800'
                    }`}
                  >
                    {initialData.last_status}
                  </span>
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-500">Última verificación</dt>
                <dd className="text-gray-900">
                  {initialData.last_checked_at
                    ? new Date(initialData.last_checked_at).toLocaleString()
                    : 'Nunca'}
                </dd>
              </div>
            </dl>
          </div>

          <EntityActions
            entityName={initialData.name}
            onEdit={() => {}}
            onDelete={handleDelete}
            isDeleting={isDeletePending}
            deleteLabel="Eliminar servicio"
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