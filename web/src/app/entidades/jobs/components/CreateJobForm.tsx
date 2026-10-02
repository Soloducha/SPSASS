/** Formulario para crear/editar job. */

'use client';

import { EntityForm, FormField } from '@/components/EntityForm';
import { JobKind, JobStatus } from '@/lib/api/jobs';

interface CreateJobFormProps {
  initialData?: Partial<{
    server_id: string;
    name: string;
    kind: JobKind;
    schedule_cron: string;
    command: string;
    timeout_s: number;
    alert_on_fail: boolean;
    auto_restart: boolean;
    status: JobStatus;
  }>;
  action: (formData: FormData) => void;
  cancelHref: string;
  isLoading?: boolean;
  title: string;
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

export function CreateJobForm({
  initialData = {},
  action,
  cancelHref,
  isLoading,
  title,
}: CreateJobFormProps) {
  const fields: FormField[] = [
    {
      name: 'server_id',
      label: 'ID del servidor',
      type: 'text',
      required: true,
      placeholder: 'uuid-del-servidor',
      helpText: 'ID del servidor donde se ejecutará este job',
    },
    {
      name: 'name',
      label: 'Nombre del job',
      type: 'text',
      required: true,
      placeholder: 'backup-daily, cleanup-temp...',
      helpText: 'Nombre identificador del job',
    },
    {
      name: 'kind',
      label: 'Tipo de job',
      type: 'select',
      required: true,
      options: kindOptions,
      helpText: 'Cron = programado con schedule_cron; Batch = bajo demanda; Scheduled = una vez',
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
      helpText: 'Comando shell completo. Se ejecuta con timeout_s.',
    },
    {
      name: 'timeout_s',
      label: 'Timeout (segundos)',
      type: 'number',
      required: false,
      helpText: 'Tiempo máximo de ejecución antes de matar el proceso (default: 3600s)',
    },
    {
      name: 'alert_on_fail',
      label: 'Alertar en fallo',
      type: 'checkbox',
      required: false,
      helpText: 'Crear alerta automática si el job falla o hace timeout',
    },
    {
      name: 'auto_restart',
      label: 'Auto-restart',
      type: 'checkbox',
      required: false,
      helpText: 'Si está habilitado, el runner intentará re-ejecutar automáticamente al fallar',
    },
    {
      name: 'status',
      label: 'Estado',
      type: 'select',
      required: true,
      options: statusOptions,
      helpText: 'Active = se ejecuta según schedule; Paused = no se ejecuta; Disabled = deshabilitado',
    },
  ];

  return (
    <EntityForm
      fields={fields}
      initialData={initialData}
      action={action}
      cancelHref={cancelHref}
      isLoading={isLoading}
      title={title}
      submitLabel="Crear job"
    />
  );
}