/** Server Actions para jobs. */

'use server';

import { createJob, updateJob, deleteJob, getJob, listJobRuns, JobCreate, JobUpdate } from '@/lib/api/jobs';
import { revalidatePath } from 'next/cache';
import { redirect } from 'next/navigation';

export async function createJobAction(prevState: { success: boolean; message: string }, formData: FormData): Promise<{ success: boolean; message: string }> {
  const data: JobCreate = {
    server_id: formData.get('server_id') as string,
    name: formData.get('name') as string,
    kind: formData.get('kind') as 'cron' | 'batch' | 'scheduled',
    schedule_cron: formData.get('schedule_cron') as string || undefined,
    command: formData.get('command') as string,
    timeout_s: parseInt(formData.get('timeout_s') as string, 10) || 3600,
    alert_on_fail: formData.get('alert_on_fail') === 'on',
    auto_restart: formData.get('auto_restart') === 'on',
    status: formData.get('status') as 'active' | 'paused' | 'disabled' || 'active',
    config: {},
  };

  const result = await createJob(data);

  if (result.error) {
    return { success: false, message: result.error };
  }

  revalidatePath('/entidades/jobs');
  redirect('/entidades/jobs');
}

export async function updateJobAction(jobId: string, prevState: { success: boolean; message: string }, formData: FormData): Promise<{ success: boolean; message: string }> {
  const data: JobUpdate = {
    name: formData.get('name') as string || undefined,
    kind: formData.get('kind') as 'cron' | 'batch' | 'scheduled' || undefined,
    schedule_cron: formData.get('schedule_cron') ? (formData.get('schedule_cron') as string) : undefined,
    command: formData.get('command') as string || undefined,
    timeout_s: formData.get('timeout_s') ? parseInt(formData.get('timeout_s') as string, 10) : undefined,
    alert_on_fail: formData.get('alert_on_fail') === 'on' ? true : formData.has('alert_on_fail') ? false : undefined,
    auto_restart: formData.get('auto_restart') === 'on' ? true : formData.has('auto_restart') ? false : undefined,
    status: formData.get('status') as 'active' | 'paused' | 'disabled' || undefined,
    config: {},
  };

  const result = await updateJob(jobId, data);

  if (result.error) {
    return { success: false, message: result.error };
  }

  revalidatePath('/entidades/jobs');
  redirect('/entidades/jobs');
}

export async function deleteJobAction(jobId: string): Promise<{ success: boolean; message: string }> {
  const result = await deleteJob(jobId);

  if (result.error) {
    return { success: false, message: result.error };
  }

  revalidatePath('/entidades/jobs');
  return { success: true, message: 'Job eliminado correctamente' };
}

export async function getJobData(jobId: string) {
  const result = await getJob(jobId);
  if (result.error) {
    return null;
  }
  return result.data;
}

export async function getJobRunsData(jobId: string, offset = 0, limit = 50) {
  const result = await listJobRuns(jobId, { offset, limit });
  if (result.error) {
    return { runs: [], hasNext: false, error: result.error };
  }
  return { runs: result.runs, hasNext: result.hasNext, error: null };
}