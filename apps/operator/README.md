# PEPITO OS — PWA del Operador

App móvil (PWA instalable, offline-first) para el operador de un punto de venta. Sólo cuatro acciones:
**ABRIR PUESTO · VENDER · NECESITO AYUDA · CERRAR PUESTO**. Sigue `docs/CONTRATOS.md` (§3, §4, §5 Operador, §9 Offline).

Stack: React 18 · Vite 5 · TypeScript · react-router · vite-plugin-pwa (Workbox) · idb · uuid. Sin librería de UI (CSS propio).

## Correr en desarrollo

Requisitos: Node 20+, npm, y la API corriendo (ver `apps/api/README.md`; por defecto en `http://localhost:8000`).

```bash
cd apps/operator
npm install
cp .env.example .env          # VITE_API_URL=http://localhost:8000
npm run dev                   # http://localhost:5173 (Vite hace proxy de /v1 → API)
```

Usuario demo: `op1` / `op123` (tiene asignación de hoy en el seed).

Para probarla desde un teléfono en la misma red: `npm run dev -- --host` y abre `http://<ip-de-tu-pc>:5173`.
Nota: el GPS y la instalación como PWA requieren HTTPS o `localhost`; en una IP de red local Chrome bloquea la
geolocalización (la app sigue funcionando con GPS = null).

## Build y vista previa

```bash
npm run build                 # tsc + vite build → dist/ (incluye sw.js y manifest.webmanifest)
npm run preview               # sirve dist/ en http://localhost:4173 con proxy /v1 → API
```

En producción sirve `dist/` con cualquier servidor estático y haz proxy de `/v1` a la API (la app llama a rutas relativas).
Si prefieres apuntar a una URL absoluta, compila con `VITE_API_BASE=https://api.tu-dominio.com npm run build`
(la API debe permitir CORS para ese origen).

Los iconos PNG (`public/icons/`) se regeneran con `npm run icons` (no requiere dependencias).

## Instalar como PWA

1. Abre la app en Chrome (Android) o Safari (iOS) sobre HTTPS (o `localhost`).
2. Android/Chrome: menú ⋮ → **Instalar aplicación** (o el aviso "Agregar a pantalla de inicio").
3. iOS/Safari: botón Compartir → **Agregar a pantalla de inicio**.
4. La app queda como icono "PEPITO", abre a pantalla completa (`display: standalone`) y funciona sin señal
   gracias al service worker (precache de la app; la API nunca se cachea).

## Pruebas

```bash
npm test                      # vitest: cola offline (idempotencia, orden, ok/duplicate/error, backoff), efectivo esperado local y sesión (refresh, 401→reintento, refresh fallido)
```

Smoke end-to-end contra el backend real (Playwright + Chromium ya instalados en el contenedor):

```bash
# con la API en :8000 y `npm run preview` en :4173
PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers python3 scripts/smoke.py           # login → abrir → 2 ventas → cerrar → verifica en API
PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers python3 scripts/smoke_offline.py   # todo sin red → reinicio → vuelve la red → sincroniza
PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers python3 scripts/smoke_refresh.py   # venta sin red + access token inválido → reinicio → refresh → sincroniza sin login
```

Cada smoke consume la asignación de hoy de `op1`; para repetirlo: `psql ... -f scripts/reset-demo-op1.sql` (sólo demo).

## Estructura

```
src/
  api/client.ts        cliente tipado de todos los endpoints del operador (§3, §5); sesión en memoria, refresh con lock y reintento ante 401
  types.ts             Catalog, OperatorConfig, GPS, payloads y respuestas iguales al contrato
  offline/
    db.ts              IndexedDB (idb): session, assignment, catalog, queue, shift_state, sales_local, waste_local, secrets, settings
    crypto.ts          AES-GCM (WebCrypto) sobre los payloads de la cola; clave por sesión en IndexedDB
    queue.ts           enqueue / flush → POST /v1/sync/batch; ok/duplicate/error; resolución de shift_id local
    sync.ts            dispara en `online`, cada 30 s y tras cada acción; lock; backoff; aplica ACKs al estado local
    expected.ts        efectivo y producto esperados calculados en el teléfono (cierre sin red)
    gps.ts             posición con timeout (fallback null) y pings cada gps_interval_seconds con el turno abierto
    battery.ts · speech.ts · device.ts
  state/
    actions.ts         login, refreshSession, changePassword, abrir, vender, deshacer/cancelar, merma, ayuda, esperado, cerrar
    store.tsx          contexto React que lee IndexedDB y se refresca con cada ACK
  screens/             Login · ChangePassword · Home · OpenShift · Sell · Help · CloseShift · Settings
  components/          Layout (barra: punto, carrito, estado de sync, batería) · YesNo · Numpad
test/                  vitest (fake-indexeddb)
scripts/               gen-icons.mjs · smoke.py · smoke_offline.py · smoke_refresh.py · reset-demo-op1.sql
```

## Cómo funciona el modo offline

- Cada acción crea un comando `{idempotency_key (UUID), type, created_at, payload}` cifrado en la cola local y
  actualiza la UI de inmediato. La cola se envía en orden a `POST /v1/sync/batch`; `ok`/`duplicate` la eliminan,
  un error no reintentable la deja en **Requiere ayuda** (Ajustes → "Reintentar enviar"); un fallo de red la
  conserva y reintenta con backoff (5 s → 5 min) además de los disparadores normales.
- Abrir sin red: el turno queda **abierto pendiente** con un id local (`local:<uuid>`); ventas, merma, ayuda y
  pings lo referencian y la cola sustituye el id real cuando el servidor confirma el `shift_open`.
- Cada venta guarda `price_version_id` y `unit_price_cents` vigentes en el momento de registrarla.
- Deshacer: la última venta se elimina de la cola si aún no se envió (≤60 s); si ya sincronizó, se pide un
  motivo visual y se encola `sale_cancel`.
- Cerrar sin red: "Debes tener $X" se calcula con las ventas locales (y el último esperado conocido del servidor
  para el producto); el resultado definitivo (conciliado/diferencia) lo fija el servidor al sincronizar.
- Al reiniciar la app se restauran sesión, asignación, catálogo, turno, ventas locales y cola.

## Sesión y refresh de tokens

- `POST /v1/auth/login` devuelve `access_token` (corto) y `refresh_token` (rotativo, ligado al `device_id`).
  Ambos se guardan en IndexedDB (`session`) junto con `expires_at`, `refresh_expires_at`, el usuario y
  `must_change_password`; el `device_id` es el UUID persistido en `localStorage`.
- El cliente HTTP (`src/api/client.ts`) mantiene la sesión en memoria y aplica estas reglas en cada petición:
  - si el access token vence en **menos de 5 min**, refresca antes de enviar;
  - ante **401 `AUTH_INVALID`** llama a `POST /v1/auth/refresh {refresh_token, device_id}`, reemplaza ambos tokens
    y **reintenta una sola vez**; refrescos simultáneos comparten una única petición (lock);
  - si el refresh responde 401 (token inválido, rotado o expirado) la sesión local se cierra y la app vuelve al
    login **conservando la cola cifrada, el turno y las ventas locales** (`dropLocalSession`); tras iniciar sesión
    de nuevo con el mismo usuario todo se sincroniza;
  - **401 `DEVICE_REVOKED`** cierra la sesión sin intentar refresh;
  - si el refresh falla por red o 5xx se conserva la sesión y se reintenta más tarde (la cola aplica su backoff).
- La cola offline usa el mismo cliente: si el access token venció mientras no había señal, al volver la red el
  primer `sync/batch` recibe 401, se refresca y se reenvía sin pedir login (`scripts/smoke_refresh.py` lo verifica).
- **429 `RATE_LIMITED`** en el login: se muestra "Demasiados intentos. Espera N minutos" con cuenta regresiva
  (`details.retry_after_seconds` o header `Retry-After`) y el botón ENTRAR deshabilitado hasta que termine.
- **Cambio de contraseña obligatorio**: si login/refresh devuelven `must_change_password: true`, o cualquier
  llamada responde **403 `PASSWORD_CHANGE_REQUIRED`**, la app muestra la pantalla *Cambia tu contraseña*
  (actual, nueva ≥8 caracteres, confirmación) antes del Home; `POST /v1/auth/change-password` y luego continúa.

## Limitaciones conocidas

- **Cifrado local**: la cola se cifra con AES-GCM, pero la clave vive en IndexedDB del mismo origen (el navegador
  no ofrece keystore de hardware). Protege contra lectura casual del almacenamiento, no contra un atacante con
  control total del dispositivo. La clave se borra al cerrar sesión.
- **Fotos**: sólo en "Otro" de NECESITO AYUDA, se reducen a ≤1024 px JPEG y viajan en base64 dentro del comando
  (`photo_base64`). No hay galería ni reintento de subida por separado; no se piden fotos en apertura/cierre
  (el contrato las contempla por muestreo/regla, pendiente de integrar).
- **Cerrar sesión con pendientes**: se avisa y, si el operador insiste, se pierden los comandos no enviados.
- **GPS**: si el teléfono niega el permiso o tarda >8 s, se envía `gps: null`; la ubicación simulada no se detecta
  en el navegador (`mocked` siempre `false`).
- **Batería**: la Battery Status API sólo existe en Chrome/Android; en iOS no se muestra.
- **Sesión**: el access token se renueva solo con el refresh token; si el refresh expira (p. ej. muchos días sin
  abrir la app) o el dispositivo es revocado, la app vuelve al login conservando la cola.
- **Inventario**: `inventory_receipt` / `inventory_count` están en el cliente API pero no tienen pantalla en el MVP.
- **Transferencia de turno** (`/v1/shifts/{id}/transfer`) la inicia el supervisor; el operador sólo la ve como
  turno cerrado al refrescar.
