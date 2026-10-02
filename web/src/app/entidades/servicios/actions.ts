/** Server Actions para servicios. */

'use server';

import { createService, updateService, deleteService, getService, ServiceCreate, ServiceUpdate } from '@/lib/api/services';
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