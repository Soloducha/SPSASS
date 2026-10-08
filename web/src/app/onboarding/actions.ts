'use server';

/**
 * Server Actions para Onboarding.
 * Flujo: registro tenant → crear servidor → generar API key → instrucciones agente → verify heartbeat.
 */

import { getDashboardToken, getSpsaasApiUrl } from '@/lib/config';
import { registerServer, createApiKey } from '@/lib/api/servers';

type StepKey = 'register' | 'server' | 'apikey' | 'instructions' | 'verify' | 'complete';

export interface OnboardingActionResult {
  step: StepKey;
  message?: string;
  tenantId?: string;
  serverId?: string;
  apiKey?: string;
  error?: string;
}

/** Extrae el detalle de error de una respuesta JSON de FastAPI, si viene. */
async function readErrorDetail(res: Response, fallback: string): Promise<string> {
  try {
    const err = await res.json();
    return err.detail ?? fallback;
  } catch {
    return fallback;
  }
}

async function registerTenant(
  email: string,
  password: string,
  tenantName: string
): Promise<{ tenantId: string; token: string } | { error: string }> {
  const token = getDashboardToken();
  if (!token) {
    return { error: 'Token de dashboard no configurado (SPSAAS_DASHBOARD_TOKEN)' };
  }

  const url = `${getSpsaasApiUrl()}/auth/register`;

  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ email, password, full_name: tenantName }),
      cache: 'no-store',
    });

    if (!res.ok) {
      return { error: await readErrorDetail(res, `HTTP ${res.status}`) };
    }

    const body = await res.json();
    return { tenantId: body.tenant_id, token: body.access_token };
  } catch (err) {
    return { error: err instanceof Error ? err.message : 'Error de red al registrar tenant' };
  }
}

async function createServerAction(
  _tenantId: string,
  hostname: string,
  ip: string | undefined,
  os: string | undefined
): Promise<{ serverId: string } | { error: string }> {
  return registerServer({ hostname, ip, os });
}

/**
 * Genera la API key del agente para el tenant del usuario autenticado.
 *
 * El nombre es único por tenant en BD, así que se deriva del hostname del
 * servidor: permite reintentar el onboarding sin chocar con el unique constraint.
 */
async function createApiKeyAction(hostname: string): Promise<{ apiKey: string } | { error: string }> {
  return createApiKey({ name: `Agente ${hostname}` });
}

async function verifyHeartbeat(
  _tenantId: string,
  serverId: string
): Promise<{ success: boolean; error?: string }> {
  const token = getDashboardToken();
  if (!token) {
    return { success: false, error: 'Token de dashboard no configurado' };
  }

  const url = `${getSpsaasApiUrl()}/api/v1/servers/${serverId}`;

  try {
    const res = await fetch(url, {
      headers: { Authorization: `Bearer ${token}` },
      cache: 'no-store',
    });

    if (!res.ok) {
      return { success: false, error: 'No se pudo verificar el servidor' };
    }

    const data = await res.json();
    return {
      success: data.status === 'online',
      error: data.status === 'online' ? undefined : 'Servidor aún no reporta métricas',
    };
  } catch {
    return { success: false, error: 'Error al verificar heartbeat' };
  }
}

export async function onboardingAction(
  _prevState: { step: string; error?: string },
  formData: FormData
): Promise<OnboardingActionResult> {
  const step = formData.get('step') as StepKey;
  const action = formData.get('action') as string;

  try {
    switch (step) {
      case 'register': {
        if (action !== 'register') return { step: 'register', error: 'Acción inválida' };

        const email = formData.get('email') as string;
        const password = formData.get('password') as string;
        const tenantName = formData.get('tenantName') as string;

        if (!email || !password || !tenantName) {
          return { step: 'register', error: 'Todos los campos son obligatorios' };
        }

        const registerResult = await registerTenant(email, password, tenantName);
        if ('error' in registerResult) return { step: 'register', error: registerResult.error };

        return { step: 'server', tenantId: registerResult.tenantId, message: 'Tenant creado correctamente' };
      }

      case 'server': {
        if (action !== 'server') return { step: 'server', error: 'Acción inválida' };

        const tenantId = formData.get('tenantId') as string;
        const hostname = formData.get('hostname') as string;
        const ip = (formData.get('ip') as string) || undefined;
        const os = (formData.get('os') as string) || undefined;

        if (!tenantId || !hostname) {
          return { step: 'server', error: 'Tenant ID y hostname son obligatorios' };
        }

        const serverResult = await createServerAction(tenantId, hostname, ip, os);
        if ('error' in serverResult) return { step: 'server', error: serverResult.error };

        return {
          step: 'apikey',
          tenantId,
          serverId: serverResult.serverId,
          message: 'Servidor creado correctamente',
        };
      }

      case 'apikey': {
        if (action !== 'apikey') return { step: 'apikey', error: 'Acción inválida' };

        const tenantId = formData.get('tenantId') as string;
        const hostname = formData.get('hostname') as string;
        if (!tenantId || !hostname) return { step: 'apikey', error: 'Datos incompletos' };

        const apiKeyResult = await createApiKeyAction(hostname);
        if ('error' in apiKeyResult) return { step: 'apikey', error: apiKeyResult.error };

        return { step: 'instructions', tenantId, apiKey: apiKeyResult.apiKey, message: 'API Key generada' };
      }

      case 'instructions': {
        return { step: 'verify', message: 'Instrucciones mostradas' };
      }

      case 'verify': {
        const tenantId = formData.get('tenantId') as string;
        const serverId = formData.get('serverId') as string;

        if (!tenantId || !serverId) return { step: 'verify', error: 'Datos incompletos' };

        const verifyResult = await verifyHeartbeat(tenantId, serverId);
        if (!verifyResult.success) {
          return { step: 'verify', error: verifyResult.error || 'Agente no conectado aún' };
        }

        return { step: 'complete', message: 'Agente verificado correctamente' };
      }

      case 'complete': {
        return { step: 'complete', message: 'Onboarding completado' };
      }

      default:
        return { step: 'register', error: 'Paso inválido' };
    }
  } catch (err) {
    return { step: 'register', error: err instanceof Error ? err.message : 'Error inesperado' };
  }
}