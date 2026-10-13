"use client";

import { PLANS, formatPrice, getYearlySavings, formatLimit, getAlertChannelNames } from '@/lib/pricing/pricing';
import type { Plan } from '@/lib/pricing/pricing';

interface PricingTableProps {
  billingCycle?: 'monthly' | 'yearly';
  onBillingCycleChange?: (cycle: 'monthly' | 'yearly') => void;
}

export function PricingTable({ 
  billingCycle = 'monthly', 
  onBillingCycleChange 
}: PricingTableProps) {
  const plans = billingCycle === 'monthly' ? PLANS.filter(p => p.id !== 'enterprise') : PLANS.filter(p => p.id !== 'enterprise');
  
  return (
    <section className="py-16" aria-labelledby="pricing-heading">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Billing Cycle Toggle */}
        <div className="flex justify-center mb-12">
          <div className="inline-flex items-center p-1 bg-gray-100 rounded-lg" role="group" aria-label="Ciclo de facturación">
            <button
              onClick={() => onBillingCycleChange?.('monthly')}
              className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                billingCycle === 'monthly'
                  ? 'bg-white text-gray-900 shadow-sm'
                  : 'text-gray-600 hover:text-gray-900'
              }`}
              aria-pressed={billingCycle === 'monthly'}
            >
              Mensual
            </button>
            <button
              onClick={() => onBillingCycleChange?.('yearly')}
              className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                billingCycle === 'yearly'
                  ? 'bg-white text-gray-900 shadow-sm'
                  : 'text-gray-600 hover:text-gray-900'
              }`}
              aria-pressed={billingCycle === 'yearly'}
            >
              Anual
              <span className="ml-2 inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                -20%
              </span>
            </button>
          </div>
        </div>

        {/* Pricing Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8" role="list" aria-label="Planes de precios">
          {plans.map((plan) => (
            <PricingCard key={plan.id} plan={plan} billingCycle={billingCycle} />
          ))}
        </div>

        {/* Enterprise Note */}
        <div className="mt-12 text-center">
          <p className="text-gray-600 mb-4">
            ¿Necesitas algo más grande?{' '}
            <a href="/contact?plan=enterprise" className="text-blue-600 hover:text-blue-800 font-medium underline">
              Conoce el plan Enterprise
            </a>
          </p>
        </div>
      </div>
    </section>
  );
}

function PricingCard({ plan, billingCycle }: { plan: Plan; billingCycle: 'monthly' | 'yearly' }) {
  const price = billingCycle === 'monthly' ? plan.monthlyPrice : plan.yearlyPrice;
  const monthlyEquivalent = billingCycle === 'yearly' ? Math.round(price / 12) : plan.monthlyPrice;
  const savings = billingCycle === 'yearly' ? getYearlySavings(plan.monthlyPrice, plan.yearlyPrice) : 0;

  return (
    <article 
      className={`relative rounded-2xl border p-8 transition-all duration-200 ${
        plan.popular
          ? 'border-blue-500 ring-2 ring-blue-500 bg-blue-50'
          : 'border-gray-200 bg-white hover:border-gray-300'
      }`}
      role="listitem"
    >
      {/* Popular Badge */}
      {plan.popular && (
        <div className="absolute -top-3 left-1/2 -translate-x-1/2">
          <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-bold bg-blue-600 text-white">
            {plan.badge}
          </span>
        </div>
      )}

      {/* Plan Header */}
      <header className="mb-8 text-center">
        <h3 className="text-2xl font-bold text-gray-900 mb-2">{plan.name}</h3>
        <p className="text-gray-600 text-sm mb-6">{plan.description}</p>
        
        <div className="mb-4">
          <span className="text-4xl font-bold text-gray-900">
            {formatPrice(price)}
          </span>
          <span className="text-gray-500 ml-1">
            {billingCycle === 'monthly' ? '/mes' : '/año'}
          </span>
        </div>

        {billingCycle === 'yearly' && savings > 0 && (
          <p className="text-sm text-green-600 font-medium">
            Ahorra {savings}% vs pago mensual ({formatPrice(monthlyEquivalent)}/mes equivalente)
          </p>
        )}
      </header>

      {/* Features List */}
      <ul className="space-y-4 mb-8" role="list" aria-label={`${plan.name} características`}>
        {plan.features.map((feature, index) => (
          <li key={index} className="flex items-start gap-3">
            <span className={`flex-shrink-0 w-5 h-5 mt-0.5 ${
              feature.included
                ? 'text-green-500'
                : 'text-gray-300'
            }`} aria-hidden="true">
              {feature.included ? (
                <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
                  <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                </svg>
              ) : (
                <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
                  <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                </svg>
              )}
            </span>
            <div className="flex-1 min-w-0">
              <span className={feature.included ? 'text-gray-900' : 'text-gray-400 line-through'}>
                {feature.name}
              </span>
              {feature.limit && feature.included && (
                <span className="ml-2 inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-700">
                  {feature.limit}
                </span>
              )}
            </div>
          </li>
        ))}
      </ul>

      {/* CTA Button */}
      <div className="w-full">
        <a
          href={plan.ctaHref}
          className={`w-full inline-flex items-center justify-center px-6 py-3 rounded-lg font-medium text-sm transition-colors ${
            plan.popular
              ? 'bg-blue-600 text-white hover:bg-blue-700'
              : 'bg-gray-900 text-white hover:bg-gray-800'
          }`}
        >
          {plan.ctaText}
        </a>
      </div>

      {/* Plan Limits Summary */}
      <details className="mt-8 group">
        <summary className="flex items-center justify-between cursor-pointer text-sm text-gray-500 hover:text-gray-700">
          <span>Ver límites detallados</span>
          <svg className="w-5 h-5 text-gray-400 group-open:rotate-180 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </summary>
        <div className="mt-4 p-4 bg-gray-50 rounded-lg space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-gray-600">Servidores</span>
            <span className="font-medium text-gray-900">{formatLimit(plan.limits.servers)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-600">API Keys</span>
            <span className="font-medium text-gray-900">{formatLimit(plan.limits.apiKeys)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-600">Reportes/mes</span>
            <span className="font-medium text-gray-900">{formatLimit(plan.limits.reportsPerMonth)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-600">Miembros</span>
            <span className="font-medium text-gray-900">{formatLimit(plan.limits.members)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-600">Retención métricas</span>
            <span className="font-medium text-gray-900">{plan.limits.retentionDays} días</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-600">Canales de alerta</span>
            <span className="font-medium text-gray-900">{getAlertChannelNames(plan.limits.alertChannels)}</span>
          </div>
        </div>
      </details>
    </article>
  );
}