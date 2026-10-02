/** Server Actions para servicios. */

'use server';

import { createService, updateService, deleteService, getService, ServiceCreate, ServiceUpdate } from '@/lib/api/services';
import { getDashboardToken, getSpsaasApiUrl } from '@/lib/config';
import { revalidatePath } from 'next/cache';
import { redirect } from 'next/navigation';

export async function createServiceAction(prevState: { success: boolean; message: string }, formData: FormData): Promise<{ success: boolean; message: string }> {
  const data: ServiceCreate = {
    server_id: formData.get('server_id') as string,
    name: formData.get('name') as string,
    desired_state: formData.get('desired_state') as 'running' | 'stopped' | 'failed' | 'unknown' || 'running',
    auto_restart: formData.get('auto_restart') === 'on',
    config: {},
  };

  const result = await createService(data);

  if (result.error) {
    return { success: false, message: result.error };
  }

  revalidatePath('/entidades/servicios');
  redirect('/entidades/servicios');
}

export async function updateServiceAction(serviceId: string, prevState: { success: boolean; message: string }, formData: FormData): Promise<{ success: boolean; message: string }> {
  const data: ServiceUpdate = {
    name: formData.get('name') as string || undefined,
    desired_state: formData.get('desired_state') as 'running' | 'stopped' | 'failed' | 'unknown' || undefined,
    auto_restart: formData.get('auto_restart') === 'on' ? true : formData.has('auto_restart') ? false : undefined,
    config: {},
  };

  const result = await updateService(serviceId, data);

  if (result.error) {
    return { success: false, message: result.error };
  }

  revalidatePath('/entidades/servicios');
  redirect('/entidades/servicios');
}

export async function deleteServiceAction(serviceId: string) {
  const result = await deleteService(serviceId);

  if (result.error) {
    return { success: false, message: result.error };
  }

  revalidatePath('/entidades/servicios');
  return { success: true, message: 'Servicio eliminado correctamente' };
}

export async function getServiceData(serviceId: string) {
  const result = await getService(serviceId);
  if (result.error) {
    return null;
  }
  return result.data;
}

export async function restartServiceAction(serverId: string, entityName: string): Promise<{ success: boolean; message: string }> {
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
        entity_type: 'service',
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