/** Server Actions para procesos. */

'use server';

import { createProcess, updateProcess, deleteProcess, getProcess, ProcessCreate, ProcessUpdate } from '@/lib/api/processes';
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