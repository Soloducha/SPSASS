/** Página para editar un servicio - Server Component que carga datos. */

import { Metadata } from 'next';
import { notFound } from 'next/navigation';
import { getServiceData } from '../../actions';
import { ServiceEditForm } from './components/EditServiceForm';

interface EditServicePageProps {
  params: Promise<{ id: string }>;
}

export async function generateMetadata({ params }: EditServicePageProps): Promise<Metadata> {
  const { id } = await params;
  return {
    title: `Editar servicio ${id.slice(0, 8)} - SPSAAS`,
  };
}

export default async function EditServicePage({ params }: EditServicePageProps) {
  const { id } = await params;
  const service = await getServiceData(id);

  if (!service) {
    notFound();
  }

  return <ServiceEditForm initialData={service} serviceId={id} />;
}