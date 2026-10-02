/** Formulario para crear/editar servicio. */

'use client';

import { EntityForm, FormField } from '@/components/EntityForm';
import { ServiceState } from '@/lib/api/services';

interface CreateServiceFormProps {
  initialData?: Partial<{
    server_id: string;
    name: string;
    desired_state: ServiceState;
    auto_restart: boolean;
  }>;
  action: (formData: FormData) => void;
  cancelHref: string;
  isLoading?: boolean;
  title: string;
}

const stateOptions: { value: ServiceState; label: string }[] = [
  { value: 'running', label: 'Running' },
  { value: 'stopped', label: 'Stopped' },
  { value: 'failed', label: 'Failed' },
  { value: 'unknown', label: 'Unknown' },
];

export function CreateServiceForm({
  initialData = {},
  action,
  cancelHref,
  isLoading,
  title,
}: CreateServiceFormProps) {
  const fields: FormField[] = [
    {
      name: 'server_id',
      label: 'ID del servidor',
      type: 'text',
      required: true,
      placeholder: 'uuid-del-servidor',
      helpText: 'ID del servidor donde corre este servicio',
    },
    {
      name: 'name',
      label: 'Nombre del servicio',
      type: 'text',
      required: true,
      placeholder: 'nginx, postgresql, redis...',
      helpText: 'Nombre del servicio systemd (ej: nginx, postgresql-15)',
    },
    {
      name: 'desired_state',
      label: 'Estado deseado',
      type: 'select',
      required: true,
      options: stateOptions,
      helpText: 'Estado que se espera que tenga el servicio',
    },
    {
      name: 'auto_restart',
      label: 'Auto-restart',
      type: 'checkbox',
      required: false,
      helpText: 'Si está habilitado, el agente intentará reiniciar automáticamente al detectar fallo',
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
      submitLabel="Crear servicio"
    />
  );
}