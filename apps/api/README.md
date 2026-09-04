# PEPITO OS — API

Backend del sistema operativo para la red de carritos de pepitas en CDMX. Implementa el contrato
[`docs/CONTRATOS.md`](../../docs/CONTRATOS.md) (v1.0 MVP): operador (ABRIR / VENDER / PIDE AYUDA / CERRAR),
supervisor (excepciones, ruta, auditorías), backoffice (Control Tower, reglas, aprobaciones, reportes, admin).

Stack: Python 3.11 · FastAPI · SQLAlchemy 2.x (sync) · Alembic · psycopg 3 · Pydantic v2 · PyJWT · bcrypt · APScheduler · PostgreSQL 16.

## Arranque rápido (desarrollo)

```bash
cd apps/api
pip install --break-system-packages -r requirements.txt   # o: make install
./scripts/dev_db.sh start          # PostgreSQL 16 local en :5433 (initdb en ../../.pgdata la primera vez)
cp .env.example .env               # ajusta JWT_SECRET si quieres
alembic upgrade head               # crea el esquema (0001 inicial + 0002 auth hardening + 0003 gate 6-20)
python -m app.seed                 # datos demo §10 (idempotente; SEED_MODE=demo por default)
uvicorn app.main:app --reload --port 8000
```

O todo junto: `make up`. Docs interactivas en `http://localhost:8000/docs`. Salud: `GET /v1/health`.

`scripts/dev_db.sh` acepta `start | stop | status`. Si se ejecuta como root crea el usuario de sistema `pg`
y corre postgres con él. Variables: `PGDATA`, `PGPORT` (5433), `PGBIN` (`/usr/lib/postgresql/16/bin`).

### Usuarios demo

| usuario | contraseña | rol |
|---|---|---|
| `admin` | `admin123` | admin |
| `ops` | `ops123` | ops |
| `finanzas` | `fin123` | finance |
| `sup1` | `sup123` | supervisor (zona Centro) |
| `op1`, `op2`, `op3` | `op123` | operator (asignaciones de hoy 08:00–18:00 en Metro Insurgentes, Parque México, Alameda Central; carritos C-001..C-003) |

Ejemplo:

```bash
TOKEN=$(curl -s -X POST localhost:8000/v1/auth/login -H 'content-type: application/json' \
  -d '{"username":"op1","password":"op123","device_id":"dev-demo-1"}' | jq -r .access_token)
curl -s localhost:8000/v1/me/assignment -H "Authorization: Bearer $TOKEN" | jq .
```

### Seed de producción (`SEED_MODE`)

`python -m app.seed` lee `SEED_MODE` (`demo` | `prod` | `none`, default `demo`):

- `demo`: todo lo anterior (usuarios, puntos, carritos, asignaciones de hoy, inventario). **Prohibido** con
  `APP_ENV=production` (el comando aborta con código 2 y mensaje claro).
- `prod`: sólo la zona `Default`, el usuario `admin` con la contraseña de `ADMIN_INITIAL_PASSWORD` (obligatoria, ≥8
  caracteres) y `must_change_password=true`, más el catálogo (producto, presentaciones, sabores, versión de precio `v1`,
  reglas y checklists). **Sin** puntos, carritos, operadores, asignaciones ni inventario. Idempotente: si `admin` ya
  existe no toca su contraseña.
- `none`: no hace nada.

```bash
APP_ENV=production SEED_MODE=prod ADMIN_INITIAL_PASSWORD='una-clave-inicial' python -m app.seed
```

El primer login de `admin` devuelve `must_change_password: true`; hasta que llame a `POST /v1/auth/change-password`,
cualquier ruta salvo `/v1/auth/*` y `/v1/health` responde `403 PASSWORD_CHANGE_REQUIRED`.

## Autenticación

### Login, refresh y cambio de contraseña

`POST /v1/auth/login {username, password, device_id, device_name?, platform?}` →

```json
{
  "access_token": "<JWT HS256, 12 h>", "token_type": "bearer", "expires_in": 43200,
  "refresh_token": "<opaco, 64 chars urlsafe>", "refresh_expires_at": "2026-10-04T12:00:00Z",
  "user": {"id": "…", "name": "Operador Uno", "role": "operator", "zone_id": "…", "username": "op1"},
  "must_change_password": false
}
```

- El access token sigue siendo un JWT de `JWT_EXPIRES_HOURS` (12 h) con `sub, role, device_id, jti, exp`.
- El refresh token es opaco (48 bytes aleatorios urlsafe; en DB sólo se guarda su SHA-256), dura
  `REFRESH_EXPIRES_DAYS` (30) y está ligado al `device_id`. Un login nuevo en el mismo `device_id` revoca los refresh
  anteriores de ese dispositivo.
- `POST /v1/auth/refresh {refresh_token, device_id}` → misma respuesta que login (nuevo access y **nuevo** refresh).
  Rotación: el token anterior queda revocado (`replaced_by`). Reutilizar un token ya rotado/revocado (detección de
  robo) revoca **toda la familia del dispositivo** y responde `401 AUTH_INVALID`; dispositivo revocado → `401
  DEVICE_REVOKED`; usuario inactivo / token de otro device / expirado → `401 AUTH_INVALID`. El refresh no cuenta para el
  límite por usuario, pero sus fallos sí cuentan para el límite por IP.
- `POST /v1/auth/logout` (Bearer) revoca el `jti` del access token **y** los refresh del dispositivo actual.
  `POST /v1/admin/devices/{id}/revoke` también revoca los refresh de ese dispositivo.
- `POST /v1/auth/change-password {current_password, new_password}` (Bearer) → `200 {"ok": true}`. Política: ≥8
  caracteres (`PASSWORD_MIN_LENGTH`) y distinta de la actual (`422 VALIDATION`); contraseña actual incorrecta → `401
  AUTH_INVALID`. Pone `must_change_password=false`, revoca los refresh tokens del usuario en **otros** dispositivos y
  deja `audit_log user.password_change`.
- `POST /v1/admin/users/{id}/reset-password {new_password?}` (admin) → `{"ok": true, "user_id": "…",
  "must_change_password": true, "temporary_password": "…"}`; `temporary_password` sólo aparece cuando no se envió
  `new_password` (se genera una de 12 caracteres). Revoca todos los refresh del usuario y deja `audit_log
  user.password_reset`.
- `GET /v1/auth/me` incluye `must_change_password`.

Flujo sugerido en el cliente: guardar `access_token` + `refresh_token`; ante `401 AUTH_INVALID` por token expirado
llamar a `/refresh` una sola vez y reemplazar **ambos** tokens; si `/refresh` responde 401, volver al login. Ante
`403 PASSWORD_CHANGE_REQUIRED` mostrar la pantalla de cambio de contraseña.

### Rate limiting de login

Tabla `login_attempts(username, ip, at, success)`. `LOGIN_MAX_FAILS_USER` (5) fallos de un usuario en
`LOGIN_WINDOW_MINUTES` (15) bloquean ese usuario `LOGIN_LOCK_MINUTES` (15); `LOGIN_MAX_FAILS_IP` (30) fallos desde una
IP en la misma ventana bloquean la IP (login y refresh). Respuesta:

```
HTTP 429  Retry-After: 873
{"error":{"code":"RATE_LIMITED","message":"Demasiados intentos. Intenta en 15 minutos","details":{"retry_after_seconds":873}}}
```

La IP es el primer valor de `X-Forwarded-For` si existe, si no `request.client.host`. Al alcanzar el máximo de un
usuario se registra `audit_log auth.lockout` (actor null, `entity=user`). Un login correcto borra los fallos previos
de ese usuario. Los intentos de más de `LOGIN_ATTEMPTS_RETENTION_DAYS` (7) días se purgan en cada login.

## Variables de entorno

`APP_ENV` (`development`|`staging`|`production`): en producción la API no arranca con `JWT_SECRET` débil (<32 caracteres o el de ejemplo) ni con `CORS_ORIGINS=*`, no expone `/docs`, `/redoc` ni `/openapi.json`, y el seed `demo` está prohibido.

| Variable | Default | Uso |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://pepito:pepito@localhost:5433/pepito` | Conexión (psycopg 3) |
| `JWT_SECRET` | `cambia-este-secreto` | Firma HS256 (usa ≥32 bytes) |
| `JWT_EXPIRES_HOURS` | `12` | Vigencia del token |
| `TZ_NAME` | `America/Mexico_City` | Zona para calcular "hoy" (la DB guarda `timestamptz` en UTC) |
| `RULES_INTERVAL_SECONDS` | `300` | Frecuencia del motor de reglas (APScheduler) |
| `CORS_ORIGINS` | `*` | Lista separada por comas |
| `RUN_SCHEDULER` | `true` | `false` desactiva el scheduler (tests) |
| `TEST_DATABASE_URL` | `...:5433/pepito_test` | Base que pytest recrea en cada corrida |
| `SEED_MODE` | `demo` | `demo` \| `prod` \| `none` (ver "Seed de producción") |
| `ADMIN_INITIAL_PASSWORD` | — | Contraseña inicial de `admin` en `SEED_MODE=prod` (obligatoria) |
| `LOGIN_MAX_FAILS_USER` | `5` | Fallos por usuario en la ventana antes de bloquear |
| `LOGIN_MAX_FAILS_IP` | `30` | Fallos por IP en la ventana antes de bloquear |
| `LOGIN_WINDOW_MINUTES` | `15` | Ventana de conteo |
| `LOGIN_LOCK_MINUTES` | `15` | Duración del bloqueo |
| `LOGIN_ATTEMPTS_RETENTION_DAYS` | `7` | Purga de `login_attempts` |
| `REFRESH_EXPIRES_DAYS` | `30` | Vigencia del refresh token |
| `PASSWORD_MIN_LENGTH` | `8` | Política de contraseñas |
| `STORAGE_BACKEND` | `local` | `s3` \| `local` \| `none` (ver "Evidencias") |
| `STORAGE_ENDPOINT_URL` | — | Endpoint S3-compatible (p. ej. `http://minio:9000`); vacío = AWS |
| `STORAGE_BUCKET` | `pepito-evidence` | Bucket |
| `STORAGE_ACCESS_KEY` / `STORAGE_SECRET_KEY` | — | Credenciales (vacías = cadena de credenciales de boto3) |
| `STORAGE_REGION` | `us-east-1` | Región |
| `STORAGE_PUBLIC_URL` | — | Endpoint público para presignar hacia fuera (opcional) |
| `STORAGE_LOCAL_DIR` | `./evidence` | Directorio del backend `local` |
| `EVIDENCE_MAX_BYTES` | `3145728` | Tamaño máximo por foto (3 MB) → `422 VALIDATION` |
| `EVIDENCE_RETENTION_DAYS` | `180` | Retención por defecto (la clave `evidence_retention_days` de `settings` manda) |
| `PRICE_OFFLINE_GRACE_HOURS` | `72` | Gracia para ventas offline con versión de precio desactivada |

Se leen de `.env` (pydantic-settings) o del entorno.

## Evidencias (fotos) — B4

Las fotos de `POST /v1/help-cases` (`photo_base64`), `POST /v1/shifts/open` (`photos[{key, base64}]`),
`POST /v1/shifts/{id}/close` (`photos[{key, base64}]`, opcional) y `POST /v1/audits` (`photos[]`: base64 o
`{key, base64}`) se validan y se guardan en object storage; en la DB sólo queda la referencia (tabla `evidence`).
Los mismos comandos vía `/v1/sync/batch` quedan cubiertos (mismos servicios). El hash de idempotencia excluye
`photo_base64` / `photos`.

- Entrada: data URL (`data:image/jpeg;base64,…`) o base64 puro. Se valida por firma real: JPEG, PNG o WebP; ≤
  `EVIDENCE_MAX_BYTES` (3 MB). Si no cumple → `422 VALIDATION` y el comando no se ejecuta (la clave de idempotencia
  no se consume).
- `evidence(id, kind: help_case|shift_open|shift_close|audit|case_note, entity: case|shift|audit, entity_id, point_id,
  shift_id, uploaded_by, storage_key, content_type, size_bytes, sha256, taken_at, created_at, retention_until,
  deleted_at)`. `retention_until = now + settings.evidence_retention_days`.
- Backends (`app/services/storage.py`, interfaz `put(key, bytes, content_type)`, `get_url(key, expires=900)`,
  `delete(key)`): `s3` (boto3; `get_url` presignada 15 min, `STORAGE_PUBLIC_URL` para firmar con el host público),
  `local` (`STORAGE_LOCAL_DIR`; `url` = `/v1/evidence/{id}/file`, servido por la API), `none` (valida y descarta).
  Default `local` en dev/tests; en producción usa `s3`.
- `GET /v1/evidence?entity=case|shift|audit&entity_id=…` → `[{id, kind, entity, entity_id, content_type, size_bytes,
  sha256, taken_at, url}]`. Permisos: operador sólo las que subió; supervisor las de su zona; ops/finance/admin todo.
  `GET /v1/evidence/{id}` → el mismo objeto. `GET /v1/evidence/{id}/file`: en `local` sirve el archivo (mismos
  permisos); en `s3` responde `302` a la URL presignada.
- `serialize_case` (GET/PATCH `/v1/cases/{id}`, listados) incluye `evidence: [...]` (mismo formato) y
  `payload.evidence_ids`. `GET /v1/audits`, `GET /v1/audits/{id}` y la respuesta de `POST /v1/audits` incluyen
  `evidence: [...]`; `audits.photos` guarda sólo `[{evidence_id, key}]`. Las respuestas de `shifts/open` y
  `shifts/{id}/close` traen `evidence_ids`.
- Retención: `purge_expired_evidence(db, now)` borra del storage y marca `deleted_at`; corre en el job del motor de
  reglas (`run_maintenance`, cada `RULES_INTERVAL_SECONDS`) junto con `purge_old_gps(db, now)` (`gps_retention_days`).
- Muestreo de foto en apertura: `GET /v1/me/assignment` → `config.require_open_photo` (bool) decidido en servidor:
  `sha256(assignment_id)[:8] % 100 < photo_sampling_pct` (estable durante el día para la asignación).

## Parámetros operativos (`settings`) — B6

Tabla `settings(key, value jsonb, updated_at, updated_by)` con esquema de tipos en `app/services/settings.py`
(`SETTINGS_SCHEMA`). Claves (seed demo y prod; la migración 0003 también las inserta):

| clave | default | uso |
|---|---|---|
| `cash_difference_threshold_cents` | 2000 | cierre, arqueo sorpresa, regla `cash_difference`, `config` del operador |
| `cash_difference_severe_cents` | 10000 | idem (urgente + aprobación de Finanzas) |
| `cancel_window_minutes` | 5 | `cancel_sale` del operador (REST y sync) |
| `gps_interval_seconds` | 120 | `config` del operador |
| `photo_sampling_pct` | 10 | `require_open_photo` |
| `evidence_retention_days` | 180 | `retention_until` de evidencias |
| `gps_retention_days` | 90 | `purge_old_gps` |
| `daily_sales_target_default_cents` | 234000 | meta por punto cuando el punto no tiene una / al crear puntos sin meta |
| `inventory_count_tolerance_units` | 3 | `apply_count` y regla `inventory_inconsistent` |

- `GET /v1/admin/settings` (admin, ops, finance) → `[{key, value, type, default, description, updated_at, updated_by}]`;
  `GET /v1/admin/settings/{key}`.
- `PUT /v1/admin/settings/{key} {"value": …}` (admin) → el mismo objeto. Tipo inválido / fuera de rango → `422
  VALIDATION`; clave desconocida → `404`. Deja `audit_log settings.update` (`entity=setting`, `before/after = {key,
  value}`).
- **Precedencia** para los umbrales que también existen en reglas: `rules.params` (sólo si la clave está definida
  explícitamente: `cash_difference.threshold_cents|severe_cents`, `inventory_inconsistent.units`) > `settings` >
  default de código. El seed ya no escribe esos parámetros en `rules` y la migración 0003 los elimina de `rules.params`
  cuando tenían el valor por defecto. `PUT /v1/rules/{key}` acepta `null` en un parámetro para eliminar el override.
  `OPERATOR_CONFIG_DEFAULTS` desapareció: `/v1/me/assignment.config` se arma desde `settings`.

## Ventana de precio para ventas offline — B8

- `price_versions.deactivated_at` se fija con `PATCH /v1/admin/price-versions/{id} {"is_active": false}` (admin; también
  `name`, `valid_to`; `is_active: true` la reactiva y limpia `deactivated_at`). `GET /v1/admin/price-versions` incluye
  `deactivated_at` y `sales_count`.
- `create_sale` acepta la versión si `valid_from <= occurred_at + 5 min` **y** (`is_active` **o**
  `occurred_at <= deactivated_at + PRICE_OFFLINE_GRACE_HOURS`). Fuera de eso → `422 PRICE_VERSION_INVALID` con mensaje
  claro (`no existe` / `todavía no estaba vigente` / `desactivada hace más de N h`) y `details` (`deactivated_at`,
  `grace_hours`, `occurred_at`).
- Si entra por la gracia, `sales.price_version_stale=true` (también en `SaleRecorded.payload` y en `GET
  /v1/sales/{id}`). `GET /v1/reports/daily` añade `stale_price_sales` por fila y en `totals` para Finanzas.

## Pruebas

```bash
make test        # = python -m pytest -q
```

`tests/conftest.py` recrea `pepito_test` (DROP/CREATE), aplica `alembic upgrade head`, ejecuta el seed demo y levanta la app
con `TestClient` (`RUN_SCHEDULER=false`). `tests/test_auth_hardening.py` cubre refresh rotativo (reutilización → familia
revocada), logout/revocación de dispositivo, rate limiting por usuario e IP (reloj inyectado vía
`app.services.auth.current_time`, sin dormir), lockout con audit log, `PASSWORD_CHANGE_REQUIRED`, política y cambio de
contraseña, reset por admin, seed `prod` (en una base aparte `pepito_test_seed`) y docs desactivadas en producción.
El resto cubre: login/asignación, RBAC, revocación de dispositivo, logout (jti),
flujo completo del operador, cierre con diferencia → caso, diferencia grave → urgente + aprobación, apertura con
excepción, `CART_IN_USE` / `SHIFT_ALREADY_OPEN` / `NO_ASSIGNMENT`, transferencia, idempotencia (venta y cierre),
`sync/batch` mixto con error y duplicado, ventana de cancelación y permisos, inventario reconstruible (API, movimientos
y vista SQL), bloqueo de lote, motor de reglas (`no_open`, `cash_difference`, `low_battery`, `out_of_geofence`,
`sync_stale`, `high_waste`, `stock_critical`, `anomalous_cancellations`, `maintenance_overdue`), configuración de reglas
con audit log, auditoría con acciones correctivas. `tests/test_gate_6_20.py` cubre B4 (evidencia en help-case /
apertura / cierre / auditoría / sync, permisos, >3 MB → 422, retención, `require_open_photo`), B6 (settings: PUT, tipo
inválido, audit log, umbral de caja en cierre y en la regla con/sin override, ventana de cancelación, tolerancia de
inventario, purga de GPS) y B8 (venta offline con versión desactivada hace 1 h aceptada con `price_version_stale`, 4
días rechazada, `reports/daily.stale_price_sales`, `PATCH price-versions`). El storage de pruebas es `local` en un
directorio temporal.

## Docker

```bash
docker build -t pepito-os-api .
docker run --rm -p 8000:8000 -e DATABASE_URL=postgresql+psycopg://pepito:pepito@host.docker.internal:5433/pepito \
  -e JWT_SECRET=... -e SEED_MODE=demo pepito-os-api
# producción:
docker run --rm -p 8000:8000 -e APP_ENV=production -e DATABASE_URL=... -e JWT_SECRET=... -e CORS_ORIGINS=https://app.ejemplo.mx \
  -e SEED_MODE=prod -e ADMIN_INITIAL_PASSWORD=... pepito-os-api
```

El contenedor corre `alembic upgrade head`, el seed según `SEED_MODE` (`demo` | `prod` | `none`; sin la variable no
siembra; `SEED=true` sigue funcionando como alias de `demo`) y `uvicorn`.

## Estructura

```
app/
  main.py                 FastAPI, CORS, handlers de error, APScheduler (motor de reglas)
  core/   config, db (engine/Session/Base), security (bcrypt/JWT), errors (§4), deps (auth + RBAC `require` + gate de cambio de contraseña), timeutil
  models/ org (zonas, usuarios, dispositivos, refresh_tokens, login_attempts, puntos, carritos, activos, asignaciones, asistencia)
          ops (turnos, gps_pings, checklists, cash_sessions) · catalog (productos, presentaciones, sabores, precios, metas)
          sales (sales, sale_lines, payments, sale_cancellations) · inventory (almacenes, lotes, movimientos, merma, recepciones, conteos)
          cases (casos, alertas, acciones, auditorías, mantenimiento, aprobaciones, ai_recommendations, rules)
          system (idempotency_keys, events, audit_log)
  schemas/ operator.py, backoffice.py (Pydantic v2)
  routers/ auth, me, shifts, sales, waste, help, inventory, gps, sync, supervisor (+ audits), cases, control_tower, rules,
           approvals, reports (daily, attendance, audit-log), assets (activos, mantenimiento, lotes), admin (+ settings,
           price-versions), evidence, health
  services/ auth (rate limiting, refresh tokens, política de contraseña), shifts, sales, cash, inventory, cases, rules_engine
           (+ purgas), priority, geo, events, audit, idempotency, sync, control_tower, storage (s3|local|none),
           evidence (validación, retención), settings (parámetros editables)
  ai/classifier.py        clasificador por palabras clave (interfaz `classify_help_text`)
  seed.py                 SEED_MODE demo | prod | none (idempotente)
alembic/                  `0001_esquema_inicial.py` (todas las tablas + vista `inventory_balances`), `0002_auth_hardening.py`,
                          `0003_gate_6_20.py` (evidence, settings, price_versions.deactivated_at, sales.price_version_stale)
scripts/dev_db.sh         PostgreSQL local
tests/                    pytest + httpx TestClient
```

## Decisiones de implementación

- **Idempotencia** (`services/idempotency.py`): tabla `idempotency_keys(key PK, user_id, request_hash, response, status_code)`.
  El hash es SHA-256 del payload canónico sin `idempotency_key`. Misma clave + mismo hash → respuesta guardada con
  `duplicate: true` y HTTP 200; hash distinto → `409 IDEMPOTENCY_CONFLICT`. Si el comando falla no se guarda la clave.
  Aplica a ventas, merma, apertura/cierre/transferencia, ayuda, recepciones, conteos, cancelaciones y a cada comando de
  `/v1/sync/batch` (mismos servicios; un error devuelve `status:"error"` en su resultado y sigue con los demás).
- **Ledger append-only**: `sales` nunca se borra; cancelar crea `sale_cancellations`, marca `sales.status='cancelled'`,
  registra movimiento `return`, evento `SaleCancelled` y `audit_log`. Operador: sólo ventas propias, turno abierto y
  dentro de `settings.cancel_window_minutes` (5); supervisor (de su zona) / ops / admin siempre, con motivo.
- **Inventario**: `inventory_movements` es la fuente de verdad (tipos `receipt, sale, waste, count_adjustment,
  transfer_out, transfer_in, return, blocked`). Balance = `SUM(qty)` por punto/presentación; la vista SQL
  `inventory_balances` lo expone. Conteos generan `count_adjustment` (+ caso `inventory_inconsistent` si |dif| > `units`).
- **Cierre**: esperado = pagos `cash` de ventas `recorded` del turno; `|dif| > cash_difference_threshold_cents` → caso
  (`review`, o `urgent` si > `cash_difference_severe_cents`) + evento `CashDifferenceDetected`; si es grave también se
  crea una `Approval` para Finanzas. Umbrales: `rules.params` > `settings` > default (ver B6).
- **Turnos**: índices únicos parciales `shifts(cart_id) WHERE status='open'` y `shifts(operator_id) WHERE status='open'`
  (→ `CART_IN_USE` / `SHIFT_ALREADY_OPEN`). La transferencia cierra el turno saliente (caja/conteo intermedio), abre uno
  para `to_operator_id` y registra `transfer_out`/`transfer_in`.
- **Auth**: JWT HS256 con `sub, role, device_id, jti, exp`; `revoked_tokens` por `jti` (logout); dispositivo revocado →
  `401 DEVICE_REVOKED` en cada request, en login y en refresh. Refresh tokens opacos rotativos en `refresh_tokens`
  (hash SHA-256, `replaced_by`, familia por `device_id`). El cambio de contraseña no invalida los access tokens ya
  emitidos en otros dispositivos (expiran solos en ≤12 h); sí revoca sus refresh tokens.
- **Motor de reglas** (`services/rules_engine.py`): `run_rules(db, now)`; dedupe `rule_key:point_id:fecha_local` contra
  casos `open/in_progress`; cada disparo crea `Alert` + `Case` + evento `AlertRaised`. Corre por APScheduler
  (`RULES_INTERVAL_SECONDS`) y por `POST /v1/rules/run`. `priority_score` según §6.
- **Ruta del supervisor**: puntos con casos abiertos agrupados por severidad (urgent → review → normal); dentro de cada
  grupo, el primero es el de mayor `priority_score` y el resto se encadena por vecino más cercano (haversine).
- **IA**: `ai/classifier.py` sólo sugiere categoría para casos "otro" (palabras clave); persiste `ai_recommendations` y
  emite `AIRecommendationCreated`. Nunca escribe en ventas/caja/inventario. El humano corrige vía `PATCH /v1/cases/{id}`
  (`category`), lo que marca `accepted` en la recomendación.

## Desviaciones y limitaciones conocidas

- `POST /v1/rules/run` lo puede ejecutar `admin` (`rules.run`) y también `ops` (`rules.update`); el contrato lo lista sólo
  para admin. `ops` también tiene `reports.read` para alimentar el Control Tower.
- Fotos: con `STORAGE_BACKEND=none` se validan y se descartan (comportamiento previo al B4); con `local` el
  directorio es efímero en Docker salvo que se monte un volumen. Producción: `s3`.
- `maintenance_overdue` deduplica por activo (`rule_key:asset_id:fecha`) porque un activo no siempre tiene punto.
- Los casos de auditoría (`audit_nonconformity`, `surprise_cash_count`) y de apertura con excepción (`open_<check>`) usan
  `rule_key` propios aunque no sean reglas del motor, para reutilizar el mismo mecanismo de alerta/caso.
- Aprobaciones: se crean automáticamente sólo para diferencias de caja graves; también pueden crearse manualmente
  (`POST /v1/approvals`). Segregación: quien solicita no puede decidir (salvo admin).
- `GET /v1/cases` acepta `status` con varios valores separados por coma (`open,in_progress`).
- `PATCH /v1/admin/*/{id}` y `DELETE` hacen baja lógica (`is_active=false`) cuando la entidad la tiene; nada referenciado
  por el ledger se borra físicamente.
- El scheduler corre dentro del proceso de la API (un solo worker). Con varios workers hay que dejar `RUN_SCHEDULER=true`
  sólo en uno.
