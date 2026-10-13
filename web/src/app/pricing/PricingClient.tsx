"use client";

import { useState } from 'react';
import { PricingTable } from '@/components/pricing/PricingTable';
import { FAQAccordion } from '@/components/pricing/FAQAccordion';
import { PLANS } from '@/components/pricing';
import { FinalCTA } from './FinalCTA';
import { FeatureComparisonTable } from './FeatureComparisonTable';

interface PricingClientProps {
  faqContent?: string;
}

export function PricingClient({ faqContent }: PricingClientProps) {
  const [billingCycle, setBillingCycle] = useState<'monthly' | 'yearly'>('monthly');

  return (
    <div className="min-h-screen bg-white">
      {/* Hero Section */}
      <section className="relative py-20 lg:py-32 overflow-hidden">
        {/* Background decoration */}
        <div className="absolute inset-0 -z-10 overflow-hidden">
          <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-blue-100 rounded-full blur-3xl opacity-50" />
          <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-green-100 rounded-full blur-3xl opacity-50" />
        </div>

        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
          <div className="text-center max-w-3xl mx-auto">
            <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold text-gray-900 tracking-tight mb-6">
              Precios simples y transparentes
            </h1>
            <p className="text-xl sm:text-2xl text-gray-600 mb-10 max-w-2xl mx-auto">
              Elige el plan que se adapte a tu equipo. Sin sorpresas, sin contratos de permanencia, 
              cancela cuando quieras.
            </p>
            
            {/* Trust indicators */}
            <div className="flex flex-wrap items-center justify-center gap-8 text-gray-500 text-sm">
              <span className="flex items-center gap-2">
                <svg className="w-5 h-5 text-green-500" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 12.586 7.707 11.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4a1 1 0 000-1.414z" clipRule="evenodd" />
                </svg>
                Sin tarjeta de crédito para empezar
              </span>
              <span className="flex items-center gap-2">
                <svg className="w-5 h-5 text-green-500" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 12.586 7.707 11.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4a1 1 0 000-1.414z" clipRule="evenodd" />
                </svg>
                Cancela cuando quieras
              </span>
              <span className="flex items-center gap-2">
                <svg className="w-5 h-5 text-green-500" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 12.586 7.707 11.293a1 1 0 001.414 1.414l2 2a1 1 0 001.414 0l4-4a1 1 0 000-1.414z" clipRule="evenodd" />
                </svg>
                14 días prueba gratis (Starter/Growth)
              </span>
            </div>
          </div>
        </div>
      </section>

      {/* Pricing Table */}
    <PricingTable billingCycle={billingCycle} onBillingCycleChange={setBillingCycle} />

    {/* Feature Comparison Table */}
    <FeatureComparisonTable plans={PLANS.filter(p => p.id !== 'enterprise')} />

    {/* FAQ Section */}
    {faqContent && (
      <FAQAccordion source={faqContent} />
    )}

    {/* Final CTA */}
    <FinalCTA />
  </div>
  );
}