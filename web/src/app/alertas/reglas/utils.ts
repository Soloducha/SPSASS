/**
 * Shared error mapping utilities for alert rules.
 * Pure functions — no 'use server', safe to import from Server Components and Server Actions.
 */

export function mapApiError(status: number | null, detail: string): string {
  if (status === 404) {
    return 'La regla ya no existe o no pertenece a este tenant';
  }
  if (status === 401) {
    return 'El token de API configurado es inválido o ha expirado';
  }
  if (status === 422) {
    return `Datos inválidos: ${detail}`;
  }
  return detail;
}