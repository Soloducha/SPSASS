/** Server Actions para procesos. */

'use server';

import { createProcess, updateProcess, deleteProcess, getProcess, ProcessCreate, ProcessUpdate } from '@/lib/api/processes';
import { getDashboardToken, getSpsaasApiUrl } from '@/lib/config';
import { revalidatePath } from 'next/cache';
import { redirect } from 'next/navigation';

export async function createProcessAction(prevState: { success: boolean; message: string }, formData: FormData): Promise<{ success: boolean; message: string }> {
  const data: ProcessCreate = {
    server_id: formData.get('server_id') as string,
    name: formData.get('name') as string,
    pattern: formData.get('pattern') as string,
    expected_count: parseInt(formData.get('expected_count') as string, 10) || 1,
    auto_restart: formData.get('auto_restart') === 'on',
    config: {},
  };

  const result = await createProcess(data);

  if (result.error) {
    return { success: false, message: result.error };
  }

  revalidatePath('/entidades/procesos');
  redirect('/entidades/procesos');
}

export async function updateProcessAction(processId: string, prevState: { success: boolean; message: string }, formData: FormData): Promise<{ success: boolean; message: string }> {
  const data: ProcessUpdate = {
    name: formData.get('name') as string || undefined,
    pattern: formData.get('pattern') as string || undefined,
    expected_count: formData.get('expected_count') ? parseInt(formData.get('expected_count') as string, 10) : undefined,
    auto_restart: formData.get('auto_restart') === 'on' ? true : formData.has('auto_restart') ? false : undefined,
    config: {},
  };

  const result = await updateProcess(processId, data);

  if (result.error) {
    return { success: false, message: result.error };
  }

  revalidatePath('/entidades/procesos');
  redirect('/entidades/procesos');
}

export async function deleteProcessAction(processId: string): Promise<{ success: boolean; message: string }> {
  const result = await deleteProcess(processId);

  if (result.error) {
    return { success: false, message: result.error };
  }

  revalidatePath('/entidades/procesos');
  return { success: true, message: 'Proceso eliminado correctamente' };
}

export async function getProcessData(processId: string) {
  const result = await getProcess(processId);
  if (result.error) {
    return null;
  }
  return result.data;
}

export async function restartProcessAction(serverId: string, entityName: string): Promise<{ success: boolean; message: string }> {
  const token = getDashboardToken();
  if (!token) {
    return { success: false, message: 'Token de dashboard no configurado (SPSAAS_DASHBOARD_TOKEN)' };
  }

  const baseUrl = getSpsaasApiUrl();
  const url = `${baseUrl}/api/v1/servers/${serverId}/restart`;

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        entity_type: 'process',
        entity_name: entityName,
      }),
      cache: 'no-store',
    });

    if (!response.ok) {
      let detail = `HTTP ${response.status}`;
      try {
        const err = await response.json();
        detail = err.detail ?? detail;
      } catch {
        // ignore parse error
      }
      return { success: false, message: detail };
    }

    const data = await response.json();
    return { success: true, message: `Comando de reinicio encolado para ${entityName} (ID: ${data.id})` };
  } catch (err) {
    return { success: false, message: err instanceof Error ? err.message : 'Error de red desconocido' };
  }
}