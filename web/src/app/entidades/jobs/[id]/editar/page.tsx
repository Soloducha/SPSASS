/** Página para editar un job - Server Component que carga datos. */

import { Metadata } from 'next';
import { notFound } from 'next/navigation';
import { getJobData } from '../../actions';
import { JobEditForm } from './components/EditJobForm';

interface EditJobPageProps {
  params: Promise<{ id: string }>;
}

export async function generateMetadata({ params }: EditJobPageProps): Promise<Metadata> {
  const { id } = await params;
  return {
    title: `Editar job ${id.slice(0, 8)} - SPSAAS`,
  };
}

export default async function EditJobPage({ params }: EditJobPageProps) {
  const { id } = await params;
  const job = await getJobData(id);

  if (!job) {
    notFound();
  }

  return <JobEditForm initialData={job} jobId={id} />;
}