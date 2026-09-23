/** Configuración del cliente (server-side).

El token de servicio es un bridge temporal: mientras no exista login web
(mes 3+), el dashboard SSR se autentica con este token contra el API.

Se leen como funciones (no constantes) para que Next las evalúe en request
time, no en build time.
*/

export function getSpsaasApiUrl(): string {
  return process.env.SPSAAS_API_URL ?? 'http://localhost:8000';
}

export function getDashboardToken(): string | undefined {
  return process.env.SPSAAS_DASHBOARD_TOKEN;
}