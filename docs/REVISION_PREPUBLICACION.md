# Revisión prepublicación — PEPITO OS v1.0

> **Actualización rama `fix/prepublicacion` (v1.1):** B1, B2, B3 y B5 quedaron resueltos (ver sección "Resuelto en v1.1").
> **Actualización rama `feat/gate-6-20` (v1.2):** B4, B6 y B8 resueltos de punta a punta (API con migración `0003_gate_6_20`,
> PWA y backoffice) más HTTPS con Caddy y MinIO en el compose. Queda **B7** (clave de cifrado local), que depende de la decisión
> teléfono corporativo vs BYOD; hoy la cola cifrada protege contra lectura casual y la sesión se puede revocar por dispositivo.
>
> | # | v1.2 | Verificación |
> |---|---|---|
> | B4 | Tabla `evidence` + storage `s3\|local\|none` (MinIO en compose, servido por la API con permisos); fotos de ayuda, apertura/cierre por muestreo (`require_open_photo` estable por asignación) y auditorías (hasta 3); galería en casos y `/auditorias/:id`; retención `evidence_retention_days` con purga | 13 tests API; `smoke_photo.py` (apertura sin red con foto → evidencia en API); smoke backoffice (auditoría con foto → galería); CI sube una foto a MinIO y la descarga |
> | B6 | Tabla `settings` (9 parámetros) editable en `/admin → Parámetros`, con audit log; `/me/assignment.config`, cierre, regla `cash_difference`, arqueo sorpresa y `cancel_window` leen de ahí; precedencia `rules.params > settings > default` visible en `/reglas` con "Quitar override"; purga de GPS por `gps_retention_days` | tests: cambiar umbral cambia el resultado del cierre siguiente; smoke backoffice |
> | B8 | `price_versions.deactivated_at`; venta offline con versión desactivada se acepta hasta `PRICE_OFFLINE_GRACE_HOURS=72` y queda marcada `price_version_stale` (columna "Precio vencido" en `/ventas`); Desactivar/Reactivar en `/admin` con aviso | tests: 1 h → aceptada y marcada; 4 días → rechazada |
> | HTTPS | Caddy con `tls internal` (LAN, CA descargable en `:8446/ca.crt`) o Let's Encrypt con dominio; `docs/HTTPS.md` | CI comprueba `https://localhost:8443/8444/8445` |
> | UI | Icono de carrito = render V5-B Food Bike; icono de producto = mascota Pepito (PWA: cabecera, checklist, ayuda) | capturas |

Revisión independiente del sistema generado (backend, PWA operador, backoffice, infra) contra el PRD v2 y el OpenSpec v2,
hecha después de construirlo. Se divide en: lo que **ya corregí** durante la revisión, lo que **corregiría antes de publicar**
(bloqueante), y lo que **puede esperar** al piloto.

## Evidencia de verificación

| Verificación | Resultado |
|---|---|
| `apps/api` pytest | 28/28 en verde (incluye idempotencia por usuario y auto-resolución añadidas en la revisión) |
| `apps/operator` build + vitest | build OK (tsc + vite + SW), 11/11 |
| `apps/backoffice` build + vitest | build OK, 7/7 |
| Smoke E2E operador online (Chromium → PWA → API real) | OK: login → abrir → 2 ventas → cierre conciliado |
| Smoke E2E operador **offline** | OK: abrir/vender/deshacer/merma sin red → reinicio → sincroniza → cierre conciliado |
| Smoke E2E backoffice | OK: Control Tower, excepciones, ventas, supervisor móvil, auditoría → caso + correctivo |
| `docker compose build` | **No verificado** (sin Docker en el entorno de generación). Los Dockerfiles siguen el patrón estándar, pero hay que construirlos una vez antes de publicar |

## Corregido durante la revisión

1. **Clave de idempotencia sin dueño.** `idempotency_keys` usaba la clave como PK global: otro usuario que enviara la misma clave recibía la respuesta ajena. Ahora la clave pertenece a quien la creó; un tercero recibe `409 IDEMPOTENCY_CONFLICT`. Test añadido.
2. **Secretos por defecto en producción.** Con `APP_ENV=production` la API se niega a arrancar si `JWT_SECRET` es el de ejemplo/corto o si `CORS_ORIGINS=*`.
3. **Casos "Punto sin abrir" que seguían URGENTES después de abrir.** Las reglas transitorias (`no_open`, `sync_stale`, `out_of_geofence`, `low_battery`) ahora resuelven solas su caso cuando la condición desaparece y nadie lo ha tomado; queda evento `AlertResolved` con `auto:true`.
4. **`sync_stale` se auto-anulaba** porque un evento del propio sistema (AlertResolved) contaba como "actividad". Ahora sólo cuentan eventos originados en el dispositivo (ventas, merma, apertura, ayuda…).
5. **Forecast de cierre absurdo (780 % de la meta)** por extrapolar 20 minutos de ventas a 10 horas. Ritmo amortiguado a mínimo 1 h y acotado a 1.5× la meta del punto.
6. **Títulos de casos con claves internas** (`prices_visible`) → etiquetas en español.

## Resuelto en v1.1 (`fix/prepublicacion`)

| # | Qué se hizo | Verificación |
|---|---|---|
| B1 | `SEED_MODE=demo\|prod\|none`; `prod` crea sólo `admin` con `ADMIN_INITIAL_PASSWORD` y `must_change_password=true`; `APP_ENV=production` + `SEED_MODE=demo` aborta; `/docs` y `/openapi.json` apagados en producción; `POST /v1/auth/change-password`; `POST /v1/admin/users/{id}/reset-password` (temporal mostrada una vez); gate `403 PASSWORD_CHANGE_REQUIRED`; pantallas de cambio obligatorio en PWA y backoffice | 42 tests API; smokes; CI comprueba que el seed demo se rechaza en producción |
| B2 | Tabla `login_attempts`; 5 fallos/usuario o 30/IP en 15 min → `429 RATE_LIMITED` + `Retry-After` durante 15 min; audit `auth.lockout`; login correcto limpia fallos; purga >7 días; las apps muestran cuenta regresiva | tests con reloj inyectado |
| B3 | Refresh tokens opacos (sha256 en DB), 30 días, ligados al `device_id`, rotación en cada uso, reutilización → revoca la familia del dispositivo; logout y revocación de dispositivo los invalidan; las apps refrescan proactivamente (<5 min) y ante 401, y la cola offline sincroniza tras refresh sin pedir login | `smoke_refresh.py`: venta hecha sin red con access token inválido se sincroniza al volver la red |
| B5 | `.github/workflows/ci.yml`: pytest con Postgres 16, vitest + build de ambas apps, `docker compose build` + arranque + health + login + rechazo de seed demo en producción | Se ejecuta en cada push a `main`/`fix/**`/`feat/**` y en PRs |

Residuales de estos cambios: el límite por IP confía en `X-Forwarded-For`, correcto detrás del nginx del compose; si la API se expone directa en :8000, ese header es falsificable (el límite por usuario sigue aplicando). El cambio de contraseña no invalida access tokens ya emitidos (expiran en ≤12 h).

## Corregiría ANTES de publicar (bloqueante) — estado original v1.0

| # | Qué | Riesgo | Propuesta |
|---|---|---|---|
| B1 | **Credenciales demo en el seed** (`admin/admin123`, etc.) y `SEED=true` por defecto en `docker-compose.yml` | Acceso trivial si se despliega tal cual | `SEED=false` en prod; seed de producción sólo con `admin` y contraseña desde variable; forzar cambio en primer login |
| B2 | **Sin rate limiting ni bloqueo por intentos** en `POST /v1/auth/login` | Fuerza bruta contra contraseñas cortas de operadores | Límite por IP/usuario (p. ej. `slowapi` o contador en DB), bloqueo temporal tras N fallos, registro en audit log |
| B3 | **Token de 12 h sin refresh.** Un operador que pasa >12 h sin red no puede sincronizar hasta volver a iniciar sesión (la cola cifrada se conserva, pero el flujo es confuso) | Pérdida aparente de ventas en piloto | Refresh token de 30 días ligado al `device_id` revocable; la cola sincroniza tras renovar sin intervención |
| B4 | **Fotos no se persisten** (apertura/ayuda las aceptan y las descartan) | El PRD las pide "sólo por excepción", pero cuando se piden deben existir para auditoría | Object storage (S3/MinIO) + tabla `evidence`; guardar sólo referencia en el caso |
| B5 | **Docker no probado** y frontends sin `.dockerignore` verificado en CI | Publicar algo que no levanta | Pipeline CI: pytest + vitest + `docker compose build` + smoke contra los contenedores |
| B6 | **Parámetros del operador hard-coded** (`cancel_window_minutes`, umbral de caja, intervalo GPS, muestreo de fotos en `OPERATOR_CONFIG_DEFAULTS`) | La regla `cash_difference` es configurable pero el umbral que ve el operador no; se desincronizan | Tabla `settings` editable desde `/admin` y leída por `/me/assignment` y por las reglas |
| B7 | **Cifrado local de la PWA guarda la clave junto a los datos** (IndexedDB) | Protege contra lectura casual, no contra un atacante con acceso al dispositivo; el PRD pide "cola local cifrada" | Documentado en el README del operador; si se exige más, teléfono corporativo con cifrado de disco + PIN de app (decisión pendiente PRD §20) |
| B8 | **Ventana de precio para ventas offline**: una venta sincronizada con un `price_version_id` desactivado se rechaza (`PRICE_VERSION_INVALID`) y queda en "Requiere ayuda" | Si Finanzas desactiva una versión mientras hay ventas offline, se pierden hasta intervención | No desactivar versiones con ventas pendientes; aceptar versiones inactivas si la venta ocurrió dentro de su vigencia |

## Puede esperar al piloto (no bloqueante)

- **Outbox de eventos sin consumidor**: `events` se escribe pero nada lo despacha (webhooks, WhatsApp, colas). Es correcto para MVP; añadir un dispatcher cuando exista el primer consumidor.
- **Scheduler dentro del proceso API**: con varios workers hay que dejar `RUN_SCHEDULER=true` en uno solo; a partir de 21–50 puntos conviene un worker aparte.
- **Retención de GPS/fotos**: parámetros definidos, sin job de purga. Decisión de privacidad pendiente (PRD §20).
- **Crecimiento de `idempotency_keys` y `gps_pings`**: sin TTL; purga mensual por cron.
- **Muestreo aleatorio de puntos NORMAL** para la ruta del supervisor y muestreo de fotos en apertura: definidos en el spec, no implementados.
- **MFA** para admin/finanzas (SHOULD en el spec).
- **Observabilidad**: sólo `/v1/health` y logs; faltan métricas (Prometheus) y tracing para medir los NFR (P95 <2 s / <3 s).
- **Cobertura de pruebas del frontend**: los smokes cubren los flujos principales; faltan pruebas unitarias de pantallas (checklist con "No", cancelación tras sincronizar, transferencia de turno).
- **Mapa**: los tiles de OpenStreetMap requieren internet; en producción usar un proveedor con clave (o tiles propios).
- **Peso del backoffice**: chunk de gráficas 372 KB; cargar recharts de forma diferida.
- **Pantallas no construidas en la PWA**: recepción de inventario por QR y conteo intermedio (los endpoints existen). En MVP el abasto se confirma desde backoffice.
- **Nombres de alertas cuando el punto no existe**: algunos títulos usan `point.name if point else ''`; con datos consistentes no ocurre.
- **Desviaciones menores del contrato**: `ops` puede ejecutar reglas y leer reportes; `maintenance_overdue` deduplica por activo; `inventory_balances` es vista SQL. Están documentadas en `apps/api/README.md`.

## Decisiones de negocio que el software deja abiertas (PRD §20)

Proveedor POS/terminal · teléfono corporativo vs BYOD · política de efectivo y depósitos · frecuencia y retención de GPS + aviso de
privacidad · WhatsApp Business · ERP/contabilidad destino · umbrales de aprobación · política de evidencia fotográfica · precios
vigentes (el sistema los versiona; el seed usa 25/35/45 como hipótesis).

## Recomendación

Publicable como **MVP para piloto de 1→3 puntos en un entorno controlado** una vez atendidos B1, B2, B3 y B5 (un par de días de
trabajo). B4, B6, B7 y B8 conviene cerrarlos antes del gate de 6–20 puntos.
