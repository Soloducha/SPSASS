# SPSAAS — Manual de Usuario

**Versión:** Mes 6 (Beta Cerrada) — Octubre 2026
**Público:** Administradores de sistemas, equipos de operaciones, DevOps

---

## 1. Introducción

SPSAAS es una plataforma de monitoreo SaaS para servidores Linux y entornos legacy. Te permite:

- **Ver métricas en tiempo real** de CPU, memoria, disco, load average
- **Monitorear servicios (systemd) y procesos** con auto-restart configurable
- **Ejecutar y supervisar jobs cron/batch** con alertas por fallo
- **Crear reglas de alerta** que te avisan por Telegram, Email o Webhook
- **Generar reportes de disponibilidad y SLA** automáticos

> **Time-to-value:** 15 minutos desde que instalas el agente hasta ver métricas en el dashboard.

---

## 2. Primeros pasos — Onboarding

### 2.1 Registro y creación de tenant

1. Ve a `https://app.spsaas.io/onboarding`
2. **Paso 1 — Organización:** Ingresa el nombre de tu empresa y tu email admin
3. **Paso 2 — Primer servidor:** Hostname, IP (opcional), SO (Linux/Windows/FreeBSD)
4. **Paso 3 — API Key:** Se genera automáticamente. **Guárdala ahora** (no se vuelve a mostrar)
5. **Paso 4 — Instrucciones de instalación:**
   - **Linux (systemd):**
     ```bash
     curl -fsSL https://get.spsaas.io/install.sh | bash -s -- --api-key TU_API_KEY --api-url https://api.tudominio.com
     ```
   - **Windows (NSSM):** Descarga el binario desde [releases](https://github.com/tuorg/spsaas-agent/releases) y configura `agent.toml`
6. **Paso 5 — Verificación:** El agente reporta su primer heartbeat (1-2 min)
7. **¡Listo!** Te lleva al dashboard

### 2.2 Instalación manual del agente (si el script falla)

**Configuración (`/etc/spsaas/agent.toml`):**
```toml
[agent]
api_key = "TU_API_KEY"
api_url = "https://api.tudominio.com"
server_id = "UUID_DEL_SERVIDOR"  # Opcional: se auto-registra si omitido
```

**Verificar servicio:**
```bash
systemctl status spsaas-agent
journalctl -u spsaas-agent -f
```

---

## 3. Dashboard principal

Accede a `https://app.spsaas.io/`

### 3.1 Vista general
- **Tarjetas totales:** Servidores totales, en línea, desconectados, degradados
- **Tabla de servidores:** Hostname, IP, SO, estado, últimas métricas, último heartbeat
- **Métricas históricas:** Gráficos por servidor (CPU, memoria, disco, load)

### 3.2 Estados de servidor
| Estado | Significado |
|--------|-------------|
| 🟢 En línea | Heartbeat recibido < 2 min |
| 🟡 Degradado | Heartbeat 2-5 min |
| 🔴 Desconectado | Sin heartbeat > 5 min |
| ⚪ Desconocido | Recién registrado, sin heartbeat |

---

## 4. Entidades monitoreadas

### 4.1 Servicios (systemd)
`/entidades/servicios` → **Nuevo servicio**
- **Nombre:** Nombre del unit (ej. `nginx`, `postgresql`)
- **Servidor:** Donde corre
- **Estado deseado:** `running` / `stopped`
- **Auto-restart:** Si falla, reintenta con backoff

### 4.2 Procesos
`/entidades/procesos` → **Nuevo proceso**
- **Patrón regex:** Para detectar el proceso en `ps aux` (ej. `java.*mi-app`)
- **Cantidad esperada:** Cuántas instancias deben estar corriendo
- **Auto-restart:** Reintenta si baja de lo esperado

### 4.3 Jobs (cron / batch)
`/entidades/jobs` → **Nuevo job**
- **Tipo:** `CRON` (programado) / `BATCH` (bajo demanda) / `SCHEDULED` (una vez)
- **Schedule cron:** Ej. `0 2 * * *` (cada día 2 AM)
- **Comando:** Lo que ejecuta el agente (`/scripts/backup.sh`)
- **Timeout:** Max tiempo de ejecución (default 1h)
- **Alert on fail:** Te avisa si falla (requiere canal de alerta en el servidor)

---

## 5. Alertas

### 5.1 Crear regla de alerta
`/alertas/reglas/nueva`

| Campo | Descripción |
|-------|-------------|
| **Entidad** | Server / Service / Process / Job / Métrica custom |
| **Métrica** | `cpu_usage`, `mem_usage`, `disk_usage`, `load_avg1`, etc. |
| **Operador** | `>`, `>=`, `<`, `<=`, `==`, `!=` |
| **Umbral** | Valor numérico (ej. 85 para 85%) |
| **Duración** | Segundos sostenidos antes de disparar (default 60s) |
| **Severidad** | `info` / `warning` / `critical` |
| **Canales** | ≥1 obligatorio: Webhook, Email, Telegram |

### 5.2 Canales de notificación

| Canal | Configuración | Requisitos |
|-------|---------------|------------|
| **Webhook** | URL + headers opcionales | Endpoint HTTP que acepte POST JSON |
| **Email** | Lista de destinatarios | SMTP configurado en `.env` del servidor |
| **Telegram** | Chat ID + thread ID opcional | Bot token en `.env` del servidor |

> **Dedupe:** Una vez disparada, la alerta no re-dispara hasta que se resuelva o se silencie manualmente.

### 5.3 Gestionar alertas activas
`/alertas` — Lista con filtros por estado, severidad, regla
- **Acuse (ack):** Marca como vista, para el timer de escalación
- **Resolver:** Cierra la alerta (si la condición ya no se cumple, se auto-resuelve)
- **Silenciar:** Oculta temporalmente (para mantenimiento planificado)

---

## 6. Invitaciones al equipo

### 6.1 Invitar miembro
`/invitaciones` → **Nueva invitación**
1. Email del invitado
2. Rol: `owner` / `admin` / `member` / `viewer`
3. Se envía email con link de aceptación (expira 7 días)
4. **Si falla el email:** Copia el token y comparte el link manualmente: `https://app.spsaas.io/accept-invitation/<token>`

### 6.2 Aceptar invitación
1. Click en link del email → `/accept-invitation/<token>`
2. Si no tienes cuenta: crea password + nombre opcional
3. Si ya tienes cuenta: solo agrega la membresía al tenant
4. Te lleva al dashboard del tenant invitado

### 6.3 Roles y permisos
| Rol | Permisos |
|-----|----------|
| **owner** | Todo + gestionar plan/billing, eliminar tenant |
| **admin** | Todo excepto billing/plan + invitar miembros |
| **member** | Ver dashboard, crear/editar entidades, alertas, reportes |
| **viewer** | Solo lectura (dashboard, alertas, reportes) |

---

## 7. Plan Gates — Límites por plan

| Recurso | Free | Starter | Growth | Enterprise |
|---------|------|---------|--------|------------|
| **Servidores** | 3 | 10 | 50 | ∞ |
| **Retención métricas** | 7 días | 30 días | 90 días | 365 días |
| **Canales alerta** | Email | Email + Telegram | + WhatsApp | Todos |
| **Reportes/mes** | 1 | 5 | 20 | ∞ |
| **API Keys** | 1 | 5 | 20 | ∞ |

> Si alcanzas el límite: **Error 403** con mensaje claro → Upgrade en `/settings/plan` (próximamente) o contacta soporte.

---

## 8. Reportes

`/reportes` → **Generar reporte**

| Tipo | Descripción |
|------|-------------|
| **Availability** | % uptime por servidor/servicio |
| **Incidents** | Alertas disparadas, tiempo de resolución |
| **Alerts** | Volumen por severidad, canal, regla |
| **SLA** | Cumplimiento de objetivos de disponibilidad |
| **Metrics** | Promedios, percentiles de métricas |

- **Período:** Inicio + fin (ej. mes calendario)
- **Generación:** Async (estado `pending` → `generating` → `completed`/`failed`)
- **Descarga:** JSON o archivo cuando `completed`

---

## 9. Documentación técnica

`/docs` — Documentación completa (MDX + búsqueda)

### Secciones principales:
| Sección | Contenido |
|---------|-----------|
| **Instalación** | Linux (systemd), Windows (NSSM), configuración avanzada |
| **Alertas** | Crear reglas, canales, dedupe, escalación |
| **Reportes** | Tipos, parámetros, interpretación, SLA |
| **Troubleshooting** | Agente no conecta, métricas no aparecen, alertas no disparan |
| **API Reference** | `/docs/api/reference` — Swagger UI interactiva |

---

## 10. Pricing page

`/pricing` — Compara planes, FAQ, CTA a onboarding

| Plan | Precio | Ideal para |
|------|--------|------------|
| **Free** | $0 | Pruebas, 1-2 servidores |
| **Starter** | $29/mes | Equipos pequeños, 5-10 servidores |
| **Growth** | $79/mes | Empresas medianas, 20-50 servidores |
| **Enterprise | Custom | MSPs, regulados, SSO/SAML, on-prem |

---

## 11. API Keys (para agentes y scripts)

`/auth/api-keys` (requiere JWT) → **Crear API key**
- Prefijo: `spsk_`
- **Una sola vez visible** — guárdala segura
- Header: `X-Api-Key: spsk_...`
- Scopes: `ingest` (métricas), `commands` (auto-restart), `admin` (todo)

---

## 12. Health checks (para tu monitoring)

| Endpoint | Qué verifica | Uso |
|----------|--------------|-----|
| `GET /healthz` | API viva, DB + Redis alcanzables | Liveness probe (k8s, LB) |
| `GET /readyz` | + Migraciones aplicadas, rate limiter OK | Readiness probe (k8s) |

**Respuestas:**
- `200 OK` → `{"api":"ok","database":"ok","redis":"ok",...}`
- `503 Service Unavailable` → Detalle de qué falla

---

## 13. Troubleshooting rápido

| Problema | Causa probable | Solución |
|----------|----------------|----------|
| Agente no aparece en dashboard | API key inválida, firewall saliente | Verifica `api_key` en `agent.toml`, permite `api.tudominio.com:443` |
| Métricas no actualizan | Agente caído, clock drift | `systemctl restart spsaas-agent`, sincroniza NTP |
| Alerta no dispara | Duración no cumplida, canal mal configurado | Revisa `duration_s`, prueba canal en `/alertas/reglas` |
| Email no llega | SMTP no configurado | Configura `SMTP_HOST`, `SMTP_FROM`, `SMTP_USER` en `.env` |
| 403 "Límite de plan" | Alcanzaste cuota | Upgrade plan o limpia recursos no usados |

---

## 14. Beta Cerrada — Para pilotos

Si eres parte de la beta cerrada:

1. **Feature flags activas:** `BETA_ENABLED`, feedback widget, métricas adopción
2. **Feedback in-app:** Botón "Feedback" en dashboard → categoría (bug/feature/ux/performance/other) + rating 1-5
3. **Métricas de adopción:** Se recolectan diario (DAU, servers, alertas, reportes, invitaciones)
4. **Canal Slack privado:** Soporte directo con el equipo SPSAAS
5. **Estados de piloto:** `pending` → `active` (onboarded) → `completed`

---

## 15. Comandos útiles (CLI)

```bash
# Crear piloto beta (admin)
python api/scripts/create_pilot.py --sqlite create <tenant-uuid> --notes "Piloto Empresa X"

# Listar pilotos
python api/scripts/create_pilot.py --sqlite list

# Activar piloto (onboarded)
python api/scripts/create_pilot.py --sqlite activate <pilot-uuid>

# Snapshot métricas diarias (cron 00:30 UTC)
python api/scripts/daily_metrics_snapshot.py --sqlite --date 2026-10-12

# Backfill últimos 7 días
python api/scripts/daily_metrics_snapshot.py --sqlite --backfill 7
```

---

## 16. Soporte y contacto

- **Email:** soporte@spsaas.io
- **Slack (beta):** Canal privado `#spsaas-pilotos`
- **Documentación:** `/docs` + `/docs/api/reference`
- **Issues:** GitHub (repo privado)

---

## 17. Glosario

| Término | Definición |
|---------|------------|
| **Tenant** | Tu organización/espacio aislado (multi-tenant nativo) |
| **Agente** | Binario Go que corre en cada servidor monitoreado |
| **Heartbeat** | Ping cada 30s del agente → API (salud + métricas) |
| **Rollup** | Agregación de métricas (1m → 5m → 1h → 1d) |
| **Dedupe** | Evita alertas duplicadas mientras la condición persiste |
| **Plan Gate** | Límite duro por plan (servidores, retención, canales, etc.) |
| **API Key** | Credencial para agentes (`spsk_...`), distinta de JWT usuario |

---

*Documento vivo — actualizado con cada release. Última actualización: 2026-10-13 (Mes 6 Beta).*