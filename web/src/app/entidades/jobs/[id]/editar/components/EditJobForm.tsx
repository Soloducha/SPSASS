/** Formulario para editar un job. */

'use client';

import { EntityForm, FormField } from '@/components/EntityForm';
import { EntityActions } from '@/components/EntityActions';
import { updateJobAction, deleteJobAction } from '../../../actions';
import { JobKind, JobStatus } from '@/lib/api/jobs';
import { useActionState } from 'react';
import { useRouter } from 'next/navigation';

interface JobEditFormProps {
  initialData: {
    id: string;
    name: string;
    server_id: string;
    kind: JobKind;
    schedule_cron: string | null;
    command: string;
    timeout_s: number;
    alert_on_fail: boolean;
    auto_restart: boolean;
    status: JobStatus;
  };
  jobId: string;
}

const kindOptions: { value: JobKind; label: string }[] = [
  { value: 'cron', label: 'Cron (programado)' },
  { value: 'batch', label: 'Batch (bajo demanda)' },
  { value: 'scheduled', label: 'Scheduled (una vez)' },
];

const statusOptions: { value: JobStatus; label: string }[] = [
  { value: 'active', label: 'Active' },
  { value: 'paused', label: 'Paused' },
  { value: 'disabled', label: 'Disabled' },
];

export function JobEditForm({ initialData, jobId }: JobEditFormProps) {
  const router = useRouter();

  const [updateState, updateAction, isUpdatePending] = useActionState(
    (prevState: { success: boolean; message: string }, formData: FormData) =>
      updateJobAction(jobId, prevState, formData),
    { success: false, message: '' }
  );

  const [deleteState, deleteAction, isDeletePending] = useActionState(
    async (prevState: { success: boolean; message: string }) => {
      const result = await deleteJobAction(jobId);
      if (result.success) {
        router.push('/entidades/jobs');
        router.refresh();
      }
      return result;
    },
    { success: false, message: '' }
  );

  const fields: FormField[] = [
    {
      name: 'name',
      label: 'Nombre del job',
      type: 'text',
      required: true,
      placeholder: 'backup-daily, cleanup-temp...',
    },
    {
      name: 'kind',
      label: 'Tipo de job',
      type: 'select',
      required: true,
      options: kindOptions,
    },
    {
      name: 'schedule_cron',
      label: 'Schedule cron',
      type: 'text',
      required: false,
      placeholder: '0 2 * * * (cada día a las 2 AM)',
      helpText: 'Requerido para kind=cron. Formato estándar cron (5 campos).',
    },
    {
      name: 'command',
      label: 'Comando a ejecutar',
      type: 'text',
      required: true,
      placeholder: '/usr/local/bin/backup.sh',
      helpText: 'Comando shell completo.',
    },
    {
      name: 'timeout_s',
      label: 'Timeout (segundos)',
      type: 'number',
      required: false,
      helpText: 'Tiempo máximo de ejecución (default: 3600s).',
    },
    {
      name: 'alert_on_fail',
      label: 'Alertar en fallo',
      type: 'checkbox',
      required: false,
      helpText: 'Crear alerta automática si el job falla o hace timeout.',
    },
    {
      name: 'auto_restart',
      label: 'Auto-restart',
      type: 'checkbox',
      required: false,
      helpText: 'Re-ejecutar automáticamente al fallar.',
    },
    {
      name: 'status',
      label: 'Estado',
      type: 'select',
      required: true,
      options: statusOptions,
    },
  ];

  const handleDelete = async () => {
    return deleteAction();
  };

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Editar job</h1>
          <p className="text-gray-500 mt-1">{initialData.name} ({initialData.id.slice(0, 8)}…)</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="md:col-span-2">
          <EntityForm
            fields={fields}
            initialData={initialData}
            action={updateAction}
            cancelHref="/entidades/jobs"
            isLoading={isUpdatePending}
            title="Datos del job"
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
                <dt className="text-gray-500">Tipo</dt>
                <dd>
                  <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                    initialData.kind === 'cron' ? 'bg-blue-100 text-blue-800' :
                    initialData.kind === 'batch' ? 'bg-gray-100 text-gray-800' :
                    'bg-green-100 text-green-800'
                  }`}>
                    {initialData.kind}
                  </span>
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-500">Schedule</dt>
                <dd className="font-mono text-gray-900">{initialData.schedule_cron ?? '—'}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-500">Estado</dt>
                <dd>
                  <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                    initialData.status === 'active' ? 'bg-green-100 text-green-800' :
                    initialData.status === 'paused' ? 'bg-yellow-100 text-yellow-800' :
                    'bg-red-100 text-red-800'
                  }`}>
                    {initialData.status}
                  </span>
                </dd>
              </div>
            </dl>
          </div>

          <EntityActions
            entityName={initialData.name}
            onEdit={() => {}}
            onDelete={handleDelete}
            isDeleting={isDeletePending}
            deleteLabel="Eliminar job"
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