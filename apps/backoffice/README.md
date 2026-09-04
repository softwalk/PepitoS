# PEPITO OS — Backoffice (Control Tower + Supervisor)

Aplicación web responsive para Operaciones, Finanzas, Administración y Supervisores de zona.
Consume la API FastAPI de `apps/api` (contratos en `docs/CONTRATOS.md`).

## Stack

React 18 · Vite 5 · TypeScript · react-router 6 · leaflet + react-leaflet (tiles OSM) · recharts · CSS propio (tema claro, tablas densas, badges con texto).
Sin UI kits. Un solo bundle con chunks separados para mapa y gráficas.

## Arranque

```bash
cp .env.example .env          # VITE_API_URL=http://localhost:8000
npm install
npm run dev                   # http://localhost:5174 (proxy /v1 → API)
npm run build                 # tsc + vite build → dist/
npm run preview               # sirve dist/ en :4174 con el mismo proxy
npm test                      # vitest (jsdom)
npm run smoke                 # Playwright (python) contra preview + API real
```

Usuarios demo: `admin/admin123`, `ops/ops123`, `finanzas/fin123`, `sup1/sup123` (zona Centro).
Los operadores (`op1..op3`) no entran aquí: usan la PWA `apps/operator`.

## Rutas

| Ruta | Roles | Contenido |
|---|---|---|
| `/login` | — | Usuario/contraseña; `device_id` UUID persistido en `localStorage`; ante 429 muestra cuenta regresiva y deshabilita el botón |
| `/cambiar-contrasena` | supervisor, ops, finance, admin | Contraseña actual / nueva (≥8) / confirmación. Obligatoria mientras `must_change_password` (el Guard redirige ahí); voluntaria desde el menú de usuario |
| `/ct` | ops, finance, admin | KPIs (puntos abiertos/tarde/cerrados/sin señal, ventas vs meta con barra, transacciones, ticket, forecast) con semáforos PRD §15, contador URGENTE/REVISAR/NORMAL, mapa leaflet con marcador por estado y popup, tabla de puntos, alertas recientes. Auto-refresh 60 s. Botón **Ejecutar reglas ahora** (ops/admin) |
| `/ct/briefing` | ops, finance, admin | Headline, decisiones con recomendación y enlace al caso, números |
| `/excepciones` | supervisor, ops, finance, admin | Casos con filtros (estado, severidad, punto) ordenados por `priority_score` |
| `/casos/:id` | supervisor, ops, finance, admin | Detalle: línea de tiempo (apertura, IA, acciones, audit log), cambio de estado/severidad/categoría/asignación, resolución, acciones correctivas (responsable + fecha, marcar hecha), sugerencia IA con botón *Aceptar* |
| `/supervisor` | supervisor, ops, admin | Tres bloques URGENTE / REVISAR / NORMAL con tarjetas táctiles y botón **Atender** |
| `/supervisor/ruta` | supervisor, ops, admin | Paradas ordenadas con motivo, distancia, mini-mapa numerado y enlace a navegación |
| `/supervisor/auditoria/:pointId` | supervisor, ops, admin | Checklist Sí/No grande (limpieza, uniforme, producto, exhibición, precios visibles, carrito seguro, POS), arqueo sorpresa, notas con dictado (Web Speech API, fallback textarea), acciones correctivas → `POST /v1/audits` |
| `/ventas` | supervisor, ops, finance, admin | Reporte diario con selector de fecha, KPIs, gráfica por punto (recharts), tabla por turno y totales |
| `/inventario` | supervisor, ops, admin | Stock por punto/presentación con riesgo; lotes con **Bloquear** (motivo) y puntos afectados (ops/admin) |
| `/personas` | supervisor, ops, admin | Asistencia del día |
| `/activos` | ops, admin | Activos con preventivos; tickets de mantenimiento (crear, iniciar, resolver, cerrar) |
| `/reglas` | ops, admin | Toggle `enabled`, edición de `params` campo por campo (+ alta de parámetro), severidad; guarda con `PUT /v1/rules/{key}` |
| `/aprobaciones` | ops, finance, admin | Pendientes con aprobar/rechazar + nota (decide finance/admin) |
| `/auditoria` | ops, finance, admin | Audit log con filtros por entidad, id, acción y límite; diff antes/después |
| `/admin` | admin | CRUD de usuarios (con **Restablecer contraseña**: muestra la temporal en un modal con botón copiar; badge *Debe cambiar contraseña*), puntos, carritos, asignaciones (crear la de hoy), presentaciones, versiones de precio (nueva versión, nunca in-place), dispositivos (revocar/reactivar), zonas |

Semáforos (PRD §15): ventas/día ≥60 verde · 45–59 ámbar · <45 rojo; ticket ≥$39 · $36–38.99 · <$36; merma ≤2% · 2–4% · >4%.
Estados en mapa: abierto verde · tarde ámbar · sin señal gris · cerrado azul · no programado gris claro.

## Comportamiento transversal

- Guard de rutas por rol; un rol sin acceso se redirige a su inicio (`/ct` o `/supervisor`).
- Sesión y refresh: ver la sección siguiente. Sólo un refresh fallido (401) o `DEVICE_REVOKED` limpian la sesión y vuelven a `/login`.
- `403 PASSWORD_CHANGE_REQUIRED` en cualquier llamada marca la sesión y el Guard redirige a `/cambiar-contrasena`.
- Los errores del backend (`{error:{code,message}}`) se muestran como toast con el `message`.
- Layout: navegación lateral en escritorio; en ≤768 px barra superior + navegación inferior (para supervisor: Excepciones, Supervisor, Ruta, Inventario).
- Dinero siempre en centavos desde la API; se formatea en la UI (`lib/format.ts`).

## Sesión y refresh de tokens

- `POST /v1/auth/login` devuelve `access_token` (corto) y `refresh_token` (rotativo, ligado al `device_id`). Se guardan en
  `localStorage` (`pepito.backoffice.session`: `token`, `expiresAt`, `refreshToken`, `refreshExpiresAt`, `user`,
  `mustChangePassword`). `getSession()` sigue devolviendo la sesión aunque el access token haya vencido si el refresh
  token está vigente; sólo se descarta cuando tampoco hay refresh utilizable.
- `src/api/client.ts` aplica en cada petición autenticada:
  - si el access token vence en **menos de 5 min**, refresca antes de enviar (`refreshSession()`, con lock: refrescos
    simultáneos comparten una petición);
  - ante **401 `AUTH_INVALID`** llama a `POST /v1/auth/refresh {refresh_token, device_id}`, reemplaza ambos tokens y
    **reintenta una sola vez**;
  - si el refresh responde 401 (token inválido, rotado o expirado) se limpia la sesión y `onUnauthorized` lleva a `/login`;
  - **401 `DEVICE_REVOKED`** limpia la sesión sin intentar refresh;
  - un fallo de red/5xx en el refresh conserva la sesión (se reintenta en la siguiente petición).
- `AuthProvider` expone `refresh()`, `changePassword()` y `mustChangePassword`; la UI se entera de tokens rotados por
  `onSessionChanged`.
- **429 `RATE_LIMITED`** en `/login`: "Demasiados intentos. Espera N minutos" con cuenta regresiva
  (`details.retry_after_seconds` o header `Retry-After`) y botón deshabilitado.
- **Restablecer contraseña** (admin → Usuarios): `POST /v1/admin/users/{id}/reset-password` sin cuerpo genera una
  contraseña temporal que se muestra una sola vez en un modal (botón copiar); el usuario queda con
  `must_change_password` y, al entrar, es forzado a `/cambiar-contrasena` (`POST /v1/auth/change-password`).

## Estructura

```
src/
  api/client.ts        fetch con bearer, refresh rotativo con lock, reintento único ante 401, hooks onUnauthorized/onSessionChanged
  state/session.ts     sesión (access + refresh token, mustChangePassword) + device_id en localStorage
  state/auth.tsx       AuthProvider (login/logout/refresh/changePassword/hasRole/mustChangePassword)
  lib/format.ts        dinero, fechas, semáforos, etiquetas
  lib/useFetch.ts      fetch declarativo con auto-refresh
  components/          Layout, Toast, PointsMap (leaflet), ui (badges, cards, modal)
  pages/               una página por ruta
test/                  vitest: format.test.ts, control-tower.test.tsx, auth.test.tsx
scripts/smoke.py       smoke Playwright (chromium en /opt/pw-browsers)
screenshots/           ct, excepciones, supervisor, ventas, caso-auditoria
```

## Tests

- `npm test`: semáforos y formatos de dinero; render del Control Tower con `fetch` mockeado (mapa sustituido por stub en jsdom); sesión (refresh rota tokens, lock, 401→refresh→reintento, refresh proactivo, refresh fallido limpia sesión, DEVICE_REVOKED, 403 PASSWORD_CHANGE_REQUIRED, 429 con cuenta regresiva, Guard a `/cambiar-contrasena`).
- `npm run smoke` (requiere API en :8000 y `npm run preview` en :4174): login ops → `/ct` con puntos y KPIs → `/excepciones` → `/ventas` → login sup1 en viewport móvil → `/supervisor` con bloques → auditoría con una no conformidad y acción correctiva → verifica que el caso y la acción existan vía API → invalida el access token en `localStorage` y comprueba que la app refresca sola (refresh rotado, el anterior ya no sirve) → admin restablece la contraseña de un usuario temporal, lee la temporal del modal, entra con ella, es forzado a `/cambiar-contrasena`, la cambia y llega a `/ct`. Guarda capturas en `screenshots/`.

## Notas

- Los tiles de OpenStreetMap requieren salida a internet; sin red el mapa muestra fondo gris pero los marcadores y popups funcionan.
- El dictado usa `SpeechRecognition`/`webkitSpeechRecognition` (Chrome/Edge/Safari); en otros navegadores se muestra sólo el textarea.
