/** Página para editar un proceso - Server Component que carga datos. */

import { Metadata } from 'next';
import { notFound } from 'next/navigation';
import { getProcessData } from '../../actions';
import { ProcessEditForm } from './components/EditProcessForm';

interface EditProcessPageProps {
  params: Promise<{ id: string }>;
}

export async function generateMetadata({ params }: EditProcessPageProps): Promise<Metadata> {
  const { id } = await params;
  return {
    title: `Editar proceso ${id.slice(0, 8)} - SPSAAS`,
  };
}

export default async function EditProcessPage({ params }: EditProcessPageProps) {
  const { id } = await params;
  const process = await getProcessData(id);

  if (!process) {
    notFound();
  }

  return <ProcessEditForm initialData={process} processId={id} />;
}