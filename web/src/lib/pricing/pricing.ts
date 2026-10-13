/**
 * Pricing configuration for SPSAAS.
 * Single source of truth for all pricing-related data.
 */

export interface PlanFeature {
  name: string;
  included: boolean;
  limit?: string; // e.g., "3", "10", "∞"
  tooltip?: string;
}

export interface Plan {
  id: string;
  name: string;
  description: string;
  monthlyPrice: number; // in USD cents (e.g., 0, 2900, 9900, 29900)
  yearlyPrice: number; // in USD cents with discount applied
  badge?: string; // e.g., "Popular", "Best Value"
  badgeColor?: 'blue' | 'green' | 'purple' | 'orange' | 'gray';
  features: PlanFeature[];
  ctaText: string;
  ctaHref: string;
  popular?: boolean;
  limits: {
    servers: number | null; // null = unlimited
    apiKeys: number | null;
    reportsPerMonth: number | null;
    members: number | null;
    retentionDays: number;
    alertChannels: string[];
  };
}

export const PLANS: Plan[] = [
  {
    id: 'free',
    name: 'Free',
    description: 'Para proyectos personales y pruebas',
    monthlyPrice: 0,
    yearlyPrice: 0,
    badge: 'Gratis para siempre',
    badgeColor: 'gray',
    features: [
      { name: 'Hasta 3 servidores', included: true, limit: '3' },
      { name: '1 API Key', included: true, limit: '1' },
      { name: '1 reporte/mes', included: true, limit: '1' },
      { name: '3 miembros', included: true, limit: '3' },
      { name: 'Retención 7 días', included: true, limit: '7 días' },
      { name: 'Alertas por Email', included: true },
      { name: 'Dashboards básicos', included: true },
      { name: 'API REST completa', included: true },
      { name: 'Webhooks', included: false },
      { name: 'Telegram/Slack/PagerDuty', included: false },
      { name: 'Soporte prioritario', included: false },
      { name: 'SSO/SAML', included: false },
    ],
    ctaText: 'Empezar gratis',
    ctaHref: '/onboarding',
    limits: {
      servers: 3,
      apiKeys: 1,
      reportsPerMonth: 1,
      members: 3,
      retentionDays: 7,
      alertChannels: ['email'],
    },
  },
  {
    id: 'starter',
    name: 'Starter',
    description: 'Para equipos pequeños que empiezan a monitorizar en serio',
    monthlyPrice: 2900, // $29/mes
    yearlyPrice: 27840, // $278.40/año (20% descuento)
    badge: 'Más popular',
    badgeColor: 'blue',
    popular: true,
    features: [
      { name: 'Hasta 10 servidores', included: true, limit: '10' },
      { name: '5 API Keys', included: true, limit: '5' },
      { name: '5 reportes/mes', included: true, limit: '5' },
      { name: '10 miembros', included: true, limit: '10' },
      { name: 'Retención 30 días', included: true, limit: '30 días' },
      { name: 'Alertas Email + Telegram', included: true },
      { name: 'Dashboards avanzados', included: true },
      { name: 'API REST completa', included: true },
      { name: 'Webhooks', included: false },
      { name: 'Slack/PagerDuty', included: false },
      { name: 'Soporte prioritario', included: false },
      { name: 'SSO/SAML', included: false },
    ],
    ctaText: 'Empezar prueba gratis',
    ctaHref: '/onboarding',
    limits: {
      servers: 10,
      apiKeys: 5,
      reportsPerMonth: 5,
      members: 10,
      retentionDays: 30,
      alertChannels: ['email', 'telegram'],
    },
  },
  {
    id: 'growth',
    name: 'Growth',
    description: 'Para empresas en crecimiento con infraestructura crítica',
    monthlyPrice: 9900, // $99/mes
    yearlyPrice: 95040, // $950.40/año (20% descuento)
    badge: 'Mejor valor',
    badgeColor: 'green',
    features: [
      { name: 'Hasta 50 servidores', included: true, limit: '50' },
      { name: '20 API Keys', included: true, limit: '20' },
      { name: '20 reportes/mes', included: true, limit: '20' },
      { name: '50 miembros', included: true, limit: '50' },
      { name: 'Retención 90 días', included: true, limit: '90 días' },
      { name: 'Alertas Email + Telegram + WhatsApp', included: true },
      { name: 'Dashboards avanzados + personalizados', included: true },
      { name: 'API REST completa', included: true },
      { name: 'Webhooks', included: true },
      { name: 'Slack/PagerDuty', included: false },
      { name: 'Soporte prioritario (4h)', included: true },
      { name: 'SSO/SAML', included: false },
    ],
    ctaText: 'Contactar ventas',
    ctaHref: '/contact?plan=growth',
    limits: {
      servers: 50,
      apiKeys: 20,
      reportsPerMonth: 20,
      members: 50,
      retentionDays: 90,
      alertChannels: ['email', 'telegram', 'whatsapp'],
    },
  },
  {
    id: 'enterprise',
    name: 'Enterprise',
    description: 'Para organizaciones grandes con requisitos de compliance',
    monthlyPrice: 29900, // $299/mes
    yearlyPrice: 287040, // $2,870.40/año (20% descuento)
    badge: 'Para empresas',
    badgeColor: 'purple',
    features: [
      { name: 'Servidores ilimitados', included: true, limit: '∞' },
      { name: 'API Keys ilimitadas', included: true, limit: '∞' },
      { name: 'Reportes ilimitados', included: true, limit: '∞' },
      { name: 'Miembros ilimitados', included: true, limit: '∞' },
      { name: 'Retención 365 días', included: true, limit: '365 días' },
      { name: 'Todos los canales de alerta', included: true },
      { name: 'Dashboards white-label', included: true },
      { name: 'API REST completa', included: true },
      { name: 'Webhooks + Slack + PagerDuty', included: true },
      { name: 'Soporte 24/7 dedicado', included: true },
      { name: 'SSO/SAML + SCIM', included: true },
      { name: 'On-premise / VPC privado', included: true },
      { name: 'Auditoría completa + compliance', included: true },
      { name: 'SLA 99.99%', included: true },
    ],
    ctaText: 'Contactar ventas',
    ctaHref: '/contact?plan=enterprise',
    limits: {
      servers: null,
      apiKeys: null,
      reportsPerMonth: null,
      members: null,
      retentionDays: 365,
      alertChannels: ['email', 'telegram', 'whatsapp', 'webhook', 'slack', 'pagerduty'],
    },
  },
];

/**
 * Get a plan by ID
 */
export function getPlan(id: string): Plan | undefined {
  return PLANS.find((p) => p.id === id);
}

/**
 * Get all plans except enterprise (for public pricing page)
 */
export function getPublicPlans(): Plan[] {
  return PLANS.filter((p) => p.id !== 'enterprise');
}

/**
 * Format price for display
 */
export function formatPrice(cents: number, currency = 'USD', locale = 'es-AR'): string {
  if (cents === 0) return 'Gratis';
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency,
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(cents / 100);
}

/**
 * Calculate yearly savings percentage
 */
export function getYearlySavings(monthly: number, yearly: number): number {
  if (monthly === 0) return 0;
  const monthlyYearly = monthly * 12;
  return Math.round(((monthlyYearly - yearly) / monthlyYearly) * 100);
}

/**
 * Format limit for display
 */
export function formatLimit(limit: number | null): string {
  if (limit === null) return 'Ilimitado';
  return limit.toString();
}

/**
 * Get alert channel icons/names for display
 */
export function getAlertChannelNames(channels: string[]): string {
  const names: Record<string, string> = {
    email: 'Email',
    telegram: 'Telegram',
    whatsapp: 'WhatsApp',
    webhook: 'Webhook',
    slack: 'Slack',
    pagerduty: 'PagerDuty',
  };
  return channels.map((c) => names[c] || c).join(', ');
}