'use server';

/**
 * Server Actions para mutaciones de reglas de alerta (crear, actualizar, toggle, eliminar).
 * Cada acción valida independientemente el token antes de llamar al backend.
 */

import { revalidatePath } from 'next/cache';
import {
  createAlertRule,
  deleteAlertRule,
  toggleRuleEnabled,
  updateAlertRule,
  type AlertRuleResponse,
  type FetchResult,
} from '@/lib/api/rules';
import { getDashboardToken } from '@/lib/config';
import {
  validateCreateRuleData,
  validateEntityId,
  validateRuleId,
  validateUpdateRuleData,
} from '@/lib/rule-validation';
import { parseCreateRuleFormData, parseUpdateRuleFormData } from '@/lib/rule-form-parsing';
import { mapApiError } from './utils';

interface CreateRuleResult {
  rule: AlertRuleResponse | null;
  error?: string;
}

interface UpdateRuleResult {
  rule: AlertRuleResponse | null;
  error?: string;
}

interface ToggleRuleResult {
  rule: AlertRuleResponse | null;
  error?: string;
}

interface DeleteRuleResult {
  success: boolean;
  error?: string;
}

async function validateToken(): Promise<string | null> {
  const token = getDashboardToken();
  if (!token) {
    return 'Token de dashboard no configurado (SPSAAS_DASHBOARD_TOKEN)';
  }
  return null;
}

/**
 * Server Action para crear una regla de alerta.
 * Valida el token y los datos de entrada antes de llamar al backend.
 */
export async function createAlertRuleAction(
  _prevState: CreateRuleResult,
  formData: FormData
): Promise<CreateRuleResult> {
  const tokenError = await validateToken();
  if (tokenError) {
    return { rule: null, error: tokenError };
  }

  const { ruleData, error: parseError } = parseCreateRuleFormData(formData);
  if (parseError || !ruleData) {
    return { rule: null, error: parseError ?? 'Error al parsear los datos del formulario' };
  }

  // Validate (including entity_id UUID guard)
  const validationError = validateCreateRuleData(ruleData);
  if (validationError) {
    return { rule: null, error: validationError };
  }
  const entityIdError = validateEntityId(ruleData.entity_id);
  if (entityIdError) {
    return { rule: null, error: entityIdError };
  }

  try {
    const result: FetchResult<AlertRuleResponse> = await createAlertRule(ruleData);

    if (result.error) {
      const message = mapApiError(result.status, result.error);
      return { rule: null, error: message };
    }

    revalidatePath('/alertas/reglas');
    return { rule: result.data!, error: undefined };
  } catch (err) {
    return {
      rule: null,
      error: err instanceof Error ? err.message : 'Error inesperado al crear la regla',
    };
  }
}

/**
 * Server Action para actualizar una regla de alerta.
 * Valida el token, el ID de regla, el ID de entidad (UUID) y los datos antes de llamar al backend.
 */
export async function updateAlertRuleAction(
  _prevState: UpdateRuleResult,
  formData: FormData
): Promise<UpdateRuleResult> {
  const tokenError = await validateToken();
  if (tokenError) {
    return { rule: null, error: tokenError };
  }

  const ruleId = formData.get('ruleId') as string;
  const idError = validateRuleId(ruleId);
  if (idError) {
    return { rule: null, error: idError };
  }

  const { ruleData, error: parseError } = parseUpdateRuleFormData(formData);
  if (parseError || !ruleData) {
    return { rule: null, error: parseError ?? 'Error al parsear los datos del formulario' };
  }

  // Validate (including entity_id UUID guard)
  const validationError = validateUpdateRuleData(ruleData);
  if (validationError) {
    return { rule: null, error: validationError };
  }
  const entityIdError = validateEntityId(ruleData.entity_id ?? undefined);
  if (entityIdError) {
    return { rule: null, error: entityIdError };
  }

  try {
    const result: FetchResult<AlertRuleResponse> = await updateAlertRule(ruleId, ruleData);

    if (result.error) {
      const message = mapApiError(result.status, result.error);
      return { rule: null, error: message };
    }

    revalidatePath('/alertas/reglas');
    revalidatePath(`/alertas/reglas/${ruleId}/editar`);
    return { rule: result.data!, error: undefined };
  } catch (err) {
    return {
      rule: null,
      error: err instanceof Error ? err.message : 'Error inesperado al actualizar la regla',
    };
  }
}

/**
 * Server Action para alternar el estado activo/inactivo de una regla.
 */
export async function toggleRuleEnabledAction(
  _prevState: ToggleRuleResult,
  formData: FormData
): Promise<ToggleRuleResult> {
  const tokenError = await validateToken();
  if (tokenError) {
    return { rule: null, error: tokenError };
  }

  const ruleId = formData.get('ruleId') as string;
  const isActive = formData.get('is_active') === 'true';

  const idError = validateRuleId(ruleId);
  if (idError) {
    return { rule: null, error: idError };
  }

  try {
    const result: FetchResult<AlertRuleResponse> = await toggleRuleEnabled(ruleId, isActive);

    if (result.error) {
      const message = mapApiError(result.status, result.error);
      return { rule: null, error: message };
    }

    revalidatePath('/alertas/reglas');
    return { rule: result.data!, error: undefined };
  } catch (err) {
    return {
      rule: null,
      error: err instanceof Error ? err.message : 'Error inesperado al cambiar el estado',
    };
  }
}

/**
 * Server Action para eliminar una regla de alerta.
 */
export async function deleteAlertRuleAction(
  _prevState: DeleteRuleResult,
  formData: FormData
): Promise<DeleteRuleResult> {
  const tokenError = await validateToken();
  if (tokenError) {
    return { success: false, error: tokenError };
  }

  const ruleId = formData.get('ruleId') as string;

  const idError = validateRuleId(ruleId);
  if (idError) {
    return { success: false, error: idError };
  }

  try {
    const result: FetchResult<null> = await deleteAlertRule(ruleId);

    if (result.error) {
      const message = mapApiError(result.status, result.error);
      return { success: false, error: message };
    }

    revalidatePath('/alertas/reglas');
    return { success: true, error: undefined };
  } catch (err) {
    return {
      success: false,
      error: err instanceof Error ? err.message : 'Error inesperado al eliminar la regla',
    };
  }
}