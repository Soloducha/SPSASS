# Feature — telegram-web-form: exponer el canal Telegram en el formulario de reglas

> Feature document ODD. Estado: **EN IMPLEMENTACIÓN**.
>
> **Decisiones de producto del usuario (2026-09-30)**: un solo campo `chat_id` que acepta ambos formatos (ID numérico y `@canal`); exponer los tres campos del schema — `chat_id`, `thread_id`, `silent`.

---

## Objetivo

Que el canal Telegram sea configurable desde la web sin tocar la API a mano. Hoy el backend lo acepta por completo pero el formulario web no lo conoce: un operador tiene que hacer `curl` para crear una regla con Telegram.

## Problema / Por qué

El canal Telegram existe y está **verificado end-to-end contra la API real** (3 mensajes confirmados visualmente, token revocado). El backend también lo acepta en reglas:

- `ALLOWED_CHANNEL_KEYS = frozenset({"webhook", "email", "telegram"})` (api/app/api/v1/schemas.py:99)
- `TelegramChannel` con `chat_id` / `thread_id` / `silent` (api/app/api/v1/schemas.py:90)
- `_validate_channels_dict` ya valida y normaliza el canal (líneas 124-132)

Pero en la web:

- `AlertRuleChannels` solo declara `webhook` y `email` (web/src/lib/api/rules.ts:18-21)
- `CreateRuleForm` y `EditRuleForm` no tienen ningún campo de Telegram
- `createAlertRuleAction` / `updateAlertRuleAction` nunca parsean Telegram del `FormData`
- `validateCreateRuleData` / `validateUpdateRuleData` no validan Telegram

Resultado: el canal existe en la API y es invisible en la UI. Es exactamente la clase de hueco que hace que un producto se sienta terminado cuando no lo está.

### El defecto real: la aritmética de "obligatorio" está hardcodeada a dos canales

Este es el hallazgo que convierte el trabajo de "agregar un campo" en "arreglar un modelo roto". Los dos formularios calculan el asterisco de campo obligatorio con una condición de dos canales:

```js
{hasWebhook ? '' : ' *'}   // en el campo email
{hasEmail ? '' : ' *'}     // en el campo webhook
```

Con tres canales eso queda conceptualmente mal. Peor: **el mensaje de error es literalmente falso** — dice `"Se requiere al menos un canal (email o webhook)"` en los dos formularios y en las dos Server Actions. Con Telegram disponible, el mensaje no menciona el canal que el usuario podría estar overlooking.

Se corrige de raíz: la obligatoriedad pasa a ser *"no hay ningún otro canal configurado"* y el mensaje enumera los tres. No es un parche cosmético; es el mismo modelo mental que ya existía, extendido.

## Decisiones de diseño

**Un solo campo `chat_id`, con validación según el formato.** El backend lo tipa como `Annotated[str, Field(min_length=1)]` — string sin validación de formato. No inventamos una restricción que el servidor no tiene, pero sí damos feedback útil en cliente:

| Formato | Regex | Ejemplo |
|---|---|---|
| ID numérico | `^-?\d+$` (grupos de canal empiezan por `-100`) | `-1003838482124` |
| Username | `^@[A-Za-z0-9_]{5,32}$` | `@spsaasBot` |

Ambos se envían como string, que es lo que espera el backend.

**`thread_id` y `silent` se exponen.** Son opcionales, el backend ya los soporta y normaliza, y dejarlos fuera ignoraría contrato existente. `thread_id` solo aplica a grupos con topics habilitados — por eso la ayuda debe decirlo, no esconderlo.

**El `FormData` distingue tres estados, igual que ya hace email/webhook.** En creación: vacío = no enviar el canal. En edición: vacío explícito = limpiar el canal. Es el mismo patrón que ya existe para los otros dos, sin inventar nada.

## Alcance (in/out)

**In:**
- `TelegramChannelConfig` en `web/src/lib/api/rules.ts` + `AlertRuleChannels.telegram`
- `CreateRuleForm` y `EditRuleForm`: campos chat_id / thread_id / silent, validación en cliente, aritmética de obligatorio corregida a N canales
- `actions.ts`: parseo del `FormData` en create y update, validación de Telegram
- `RulesTable.tsx`: mostrar el canal Telegram en la columna de canales (verificar cómo se renderizan hoy)
- Tests del backend: no hacen falta — el backend ya acepta Telegram. **Sí** hace falta un test de que el backend sigue aceptando `telegram` en create/update, como guarda de regresión del contrato.

**Out:**
- Validar el token del bot desde la UI (requiere llamada a la API de Telegram en cada carga — ver `getUpdates`; decision del usuario: no)
- Cualquier cambio en el backend. Este slice es 100% web.

## Tasks

- [x] T1 — `TelegramChannelConfig` en el cliente + `AlertRuleChannels.telegram` — `214805f`
- [x] T2 — `actions.ts`: parseo create/update + validación de los tres campos — `0a1f8dc`
- [x] T3 — `CreateRuleForm`: campos + validación + obligatoriedad a N canales — `6466844`
- [x] T4 — `EditRuleForm`: lo mismo + precarga desde la regla — `785aedd`
- [x] T5 — `RulesTable`: render del canal — `c78126c`
- [x] T6 — tests de regresión backend (telegram en create/update de reglas **y en jobs**) — `b1bc662` + `2bf66a9`
- [x] T7 — verificación (build, lint, pytest, ruff, mypy) — ver tabla
- [x] T8 — fix del typecheck roto de `main` heredado del PR #29 — `26863a4`
- [x] T9 — job de web en el CI (lint + typecheck) — `fd984a5`
- [x] T10 — `web/public` para que el target `runner` construya — `9849b31`
- [x] T11 — ignorar la copia del favicon que genera el build standalone — commit de `.gitignore`

## Verificación

| Check | Resultado |
|-------|-----------|
| `npm run lint` (`eslint .`) | limpio |
| `npm run build` (`next build` — corre el typecheck) | **PASS** tras corregir `AlertsTable.tsx` (ver abajo) |
| `docker compose build --parallel` | **PASS** — las 3 imágenes construidas (`spsaas-api`, `spsaas-worker`, `spsaas-web`). Ojo: para el web usa `target: dev`, que **no** compila ni typechequea. |
| `docker build --target runner --no-cache ./web` | typecheck **PASS** con el fix. Con el código previo al fix **falla** con los 3 errores TS (evidencia de que el typecheck solo corre en `runner`). Falla después en `COPY /app/public`, por defecto preexistente del Dockerfile. |
| `pytest` (suite completa) | **255 passed, 2 failed (SMTP ambiental), 1 skipped, 1 xfailed, 2 xpassed** — +6 sobre las 249 previas |
| `ruff check app tests` | limpio |
| `mypy app` | limpio, 62 archivos |

### Regresión encontrada y corregida: `main` tenía el typecheck roto

El primer `npm run build` de este slice falló con 3 errores de TypeScript en `AlertsTable.tsx` — **un archivo del PR #29, no de este slice**.

Tres errores, todos del mismo origen:
- `SILENCED_STYLES`/`SILENCED_LABELS` indexados con `alert.silenced.toString()`, algo que TS no puede verificar contra unas claves `true`/`false` sin tipar.
- El estado `filters` guardaba `initialParams.silenced` (`boolean | null`) sin convertir a string, dejando el `value` del select como `string | boolean`.

Corregido en `26863a4`. De paso, la variante `'Activa'` del badge era **código muerto**: el badge solo se renderiza cuando `silenced` es `true`. Quedó colapsado a un único estilo y label.

**Corrección a una afirmación previa mía, que era FALSA — dos veces撤回, y la segunda importa más.**

Escribí primero que "el CI no tiene job de web". Luego lo corregí a "el CI sí cubre el web vía `web/Dockerfile` stage builder". **Ambas afirmaciones eran incorrectas.** Verificado empíricamente levantando Docker Desktop y ejecutando los builds:

`docker-compose.yml:133` construye el web con **`target: dev`**. El stage `dev` del Dockerfile **no compila** — solo hace `pnpm install --frozen-lockfile`, copia el código y corre `pnpm dev`. El stage que sí corre `pnpm run build` (y por lo tanto el typecheck) es **`builder`**, que alimenta al target **`runner`**, y compose **no lo usa**.

Prueba directa: `docker compose build web --no-cache` con el código roto del PR #29 **construye la imagen sin error**, porque nunca ejecuta el typecheck.

Prueba del target correcto: `docker build --target runner --no-cache ./web` con ese mismo código roto **falla**:

```
#14 [builder 4/4] RUN pnpm run build
AlertsTable.tsx(242,13): error TS2322: Type 'string | boolean' is not assignable ...
AlertsTable.tsx(332,27): error TS7053: ...
AlertsTable.tsx(335,26): error TS7053: ...
Failed to type check.
ERROR: process "/bin/sh -c pnpm run build" did not complete successfully: exit code: 1
```

Con el fix aplicado (`26863a4`), ese mismo build pasa el step `#14 [builder 4/4] RUN pnpm run build`.

**Conclusión, con la evidencia que la sostiene:** el CI **no** typechequea el dashboard. El job `docker-build` corre `docker compose build --parallel`, que para el web usa `target: dev` y no compila. Mi afirmación original era correcta por el motivo equivocado —la conclusionMessages_right_por_accidente—and I "verified" it with a partial grep instead of reading what compose actually builds.

La causa real de que el PR #29 llegara a `main` son **dos** hechos, no uno:
1. Solo corrí la mitad de los gates (ruff, mypy, pytest — todos Python) y reporté "verificado".
2. El pipeline nunca habría typechequeado el web aunque lo hubiera corrido.

### Defecto preexistente adicional: el target `runner` no construye

Con el typecheck ya pasando, `docker build --target runner` falla después, en el stage `runner`:

```
ERROR: failed to calculate checksum of ref ...: "/app/public": not found
```

`web/Dockerfile:46` hace `COPY --from=builder /app/public ./public`, pero **`web/public` no existe en el repositorio**. El target `runner` —el que produce la imagen de producción según el comentario del propio Dockerfile (línea 4: `docker build --target runner -t spsaas-web ./web`)— **está roto desde antes de este trabajo**. Nadie lo notó porque compose construye `dev`.

Esto no lo arreglo acá: es un slice propio, con decisión de producto (crear el directorio, o hacer el `COPY` condicional).

### Segundo defecto tapado: un autofix de eslint que no arreglaba nada

Al revisar el árbol apareció una modificación sin commitear en `actions.ts`: un autofix de eslint había reescrito la anotación de tipo a `import('@/lib/api/rules').TelegramChannelConfig`. Eso **tapaba** el error sin corregirlo — y al descartarlo apareció la causa real:

```
AlertRuleUpdate['channels'] es AlertRuleChannels | undefined
AlertRuleUpdate['channels']['telegram']  →  TS2339
```

`channels` es opcional en `AlertRuleUpdate`, así que indexarlo directamente falla. El fix correcto es `NonNullable<AlertRuleUpdate['channels']>['telegram']`, que declara la restricción en vez de esconderla. Corregido en `55642e3`.

Sin esto, `npm run build` fallaba y el "PASS" del writer era falso dos veces por razones distintas.

## Verificación por mutación de los tests de regresión de Telegram

Quitando `"telegram"` de `ALLOWED_CHANNEL_KEYS`, fallan los 7 tests nuevos — cubren create/update de reglas y también el canal en **jobs** (`TestJobConfigChannelsValidation`), que no estaba en el encargo original y quedó cubierto igual.

## Hallazgo sobre el reporte del writer

El writer reportó `npm run build` como **PASS** y en la misma línea mencionó "3 pre-existing TS errors". Eso no es un PASS: el build había fallado. Los errores no eran preexistentes en el sentido de "ajenos a este trabajo" — eran de un PR ya mergeado. Ninguno de los dos hubs de verificación del web se había corrido nunca en este repo, por eso el defecto del PR #29 llegó a `main`.

## Hallazgos resueltos (T9, T10)

Ambos nacieron de verificar con Docker en vez de razonar, y los dos eran reales.

### T9 — El CI no typechequea el web (`fd984a5`)

Nuevo job `web` en `.github/workflows/ci.yml`: `pnpm run lint` + `pnpm run build` (que es lo que corre tsc). Node 24 y pnpm 12.8.1 pineados para coincidir con `web/Dockerfile`, cuya imagen base es `node:24-alpine` y activa pnpm por corepack.

**Verificado:** el job detecta el bug. Rompí `SILENCED_BADGE_STYLE` a propósito con una anotación de tipo inválida y `pnpm run build` falló con `error TS2322` — el mismo mecanismo de error que dejó pasar el PR #29.

### T10 — El target `runner` no construía (`9849b31`)

`web/Dockerfile` documenta el target `runner` como el build de producción (línea 4), y fallaba en `COPY --from=builder /app/public ./public` porque `web/public` no existía. **La imagen de producción web no se podía construir desde este repositorio.**

Agregado `web/public/README.md` (Next.js espera el directorio; ahí van favicon, robots.txt y assets de raíz).

**Verificado:** `docker build --target runner -t spsaas-web-runner-test ./web` completa todas las capas, y la imagen contiene `server.js`, `.next/`, `node_modules/` y `public/` bajo el usuario no-root `nextjs`.

### T11 — El favicon que appeared solo (`c767...` en `.gitignore`)

Tras el build apareció un `web/public/favicon.ico` de 32KB sin trackear. **Origen verificado:** el build standalone copia `web/src/app/favicon.ico` — que sí existe y sí está trackeado — hacia `public/`. Es output de build, no un asset del proyecto. Agregado a `web/.gitignore` con un comentario que explica de dónde viene, para que el próximo build no ensucie el árbol ni duplique el favicon real.

## Pendiente que este slice destapó

Nada abierto de los tres hallazgos: los tres están corregidos y verificados con ejecución real, no con razonamiento.

Lo que sigue siendo decisión tuya, y **no** lo toqué porque son cambios de producto:

- Si `docker compose build` debe dejar de usar `target: dev`. Es lo correcto para un pipeline de despliegue, pero el target `dev` existe a propósito para hot-reload con los volume mounts (`./web:/app`). Cambiarlo rompe el flujo de desarrollo local. Lo correcto es dejarlos separados: compose para desarrollo, un target de producción aparte para despliegue. Hoy ese target existe (`runner`) pero no había forma de ejercitarlo desde compose.
- El job `web` del CI **no** corre tests: no hay framework de tests en `web/`. Solo lint + typecheck. Agregar Vitest es un slice propio.

## Notas de ejecución

- Los asteriscos de "obligatorio" de los dos formularios cambian a `"no hay ningún otro canal configurado"`. Es un cambio de comportamiento visible: el mensaje de error deja de decir "email o webhook" y pasa a enumerar los tres canales.
- La UI del proyecto ya está en español (`ENTITY_TYPE_LABELS`, `STATUS_LABELS` etc.), así que los labels nuevos van en español, consistente con el archivo.
