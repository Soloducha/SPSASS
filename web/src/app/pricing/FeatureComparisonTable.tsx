"use client";

import { PLANS } from '@/components/pricing';

interface FeatureComparisonTableProps {
  plans: typeof PLANS;
}

const features = [
  { key: 'servers', label: 'Servidores', unit: '' },
  { key: 'apiKeys', label: 'API Keys', unit: '' },
  { key: 'reportsPerMonth', label: 'Reportes/mes', unit: '' },
  { key: 'members', label: 'Miembros', unit: '' },
  { key: 'retentionDays', label: 'Retención métricas', unit: ' días' },
  { key: 'alertChannels', label: 'Canales de alerta', unit: '' },
  { key: 'webhooks', label: 'Webhooks', unit: '' },
  { key: 'slackPagerduty', label: 'Slack / PagerDuty', unit: '' },
  { key: 'sso', label: 'SSO/SAML', unit: '' },
  { key: 'whiteLabel', label: 'White-label', unit: '' },
  { key: 'support', label: 'Soporte', unit: '' },
  { key: 'sla', label: 'SLA', unit: '' },
];

const planData = {
  free: {
    servers: '3', apiKeys: '1', reportsPerMonth: '1', members: '3',
    retentionDays: '7', alertChannels: 'Email', webhooks: 'No',
    slackPagerduty: 'No', sso: 'No', whiteLabel: 'No',
    support: 'Email (48h)', sla: 'Best effort',
  },
  starter: {
    servers: '10', apiKeys: '5', reportsPerMonth: '5', members: '10',
    retentionDays: '30', alertChannels: 'Email + Telegram', webhooks: 'No',
    slackPagerduty: 'No', sso: 'No', whiteLabel: 'No',
    support: 'Email (24h)', sla: '99.9%',
  },
  growth: {
    servers: '50', apiKeys: '20', reportsPerMonth: '20', members: '50',
    retentionDays: '90', alertChannels: 'Email + Telegram + WhatsApp', webhooks: 'Sí',
    slackPagerduty: 'No', sso: 'No', whiteLabel: 'No',
    support: 'Prioritario (4h)', sla: '99.95%',
  },
};

function getFeatureValue(planId: string, featureKey: string, data: Record<string, Record<string, string>>): string {
  return data[planId]?.[featureKey] || '—';
}

interface FeatureComparisonTableProps {
  plans: typeof PLANS;
}

export function FeatureComparisonTable({ plans }: FeatureComparisonTableProps) {
  return (
    <section className="py-16 bg-gray-50" aria-labelledby="comparison-heading">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <header className="text-center mb-12">
          <h2 id="comparison-heading" className="text-3xl font-bold text-gray-900 mb-4">
            Comparativa de características
          </h2>
          <p className="text-xl text-gray-600 max-w-2xl mx-auto">
            Todo lo que necesitas saber para elegir el plan correcto
          </p>
        </header>

        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200" role="table">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Característica
                </th>
                {plans.map((plan) => (
                  <th key={plan.id} className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                    {plan.name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {features.map((feature) => (
                <tr key={feature.key} className="hover:bg-gray-50">
                  <td className="px-6 py-4 text-sm font-medium text-gray-900">
                    {feature.label}
                  </td>
                  {plans.map((plan) => (
                    <td key={plan.id} className="px-6 py-4 text-center text-sm text-gray-600">
                      {getFeatureValue(plan.id, feature.key, planData)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}