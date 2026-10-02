/** Formulario para crear/editar proceso. */

'use client';

import { EntityForm, FormField } from '@/components/EntityForm';

interface CreateProcessFormProps {
  initialData?: Partial<{
    server_id: string;
    name: string;
    pattern: string;
    expected_count: number;
    auto_restart: boolean;
  }>;
  action: (formData: FormData) => void;
  cancelHref: string;
  isLoading?: boolean;
  title: string;
}

export function CreateProcessForm({
  initialData = {},
  action,
  cancelHref,
  isLoading,
  title,
}: CreateProcessFormProps) {
  const fields: FormField[] = [
    {
      name: 'server_id',
      label: 'ID del servidor',
      type: 'text',
      required: true,
      placeholder: 'uuid-del-servidor',
      helpText: 'ID del servidor donde corre este proceso',
    },
    {
      name: 'name',
      label: 'Nombre del proceso',
      type: 'text',
      required: true,
      placeholder: 'nginx, redis, postgres...',
      helpText: 'Nombre identificador del proceso',
    },
    {
      name: 'pattern',
      label: 'Pattern (regex)',
      type: 'text',
      required: true,
      placeholder: 'nginx.*master, redis-server.*',
      helpText: 'Regex para matchear el proceso en la lista del sistema (se compara contra name y cmdline)',
    },
    {
      name: 'expected_count',
      label: 'Conteo esperado',
      type: 'number',
      required: true,
      helpText: 'Número mínimo de procesos que deben estar corriendo (alert si hay menos)',
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
      submitLabel="Crear proceso"
    />
  );
}