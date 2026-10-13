import { Metadata } from 'next';
import { getDoc } from '@/lib/docs/utils';
import { PricingClient } from './PricingClient';

export const metadata: Metadata = {
  title: 'Precios - SPSAAS',
  description: 'Planes simples y transparentes. Desde gratis para siempre hasta Enterprise. Sin sorpresas, sin contratos de permanencia.',
  openGraph: {
    title: 'Precios - SPSAAS',
    description: 'Planes simples y transparentes. Desde gratis para siempre hasta Enterprise.',
    type: 'website',
  },
};

export default async function PricingPage() {
  // Get FAQ content from MDX (server-side only)
  const faqDoc = getDoc('pricing/faq');

  return (
    <PricingClient faqContent={faqDoc?.content} />
  );
}