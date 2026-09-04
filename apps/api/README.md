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
alembic upgrade head               # crea todo el esquema (una migración inicial)
python -m app.seed                 # datos demo §10 (idempotente)
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

## Variables de entorno

`APP_ENV` (`development`|`staging`|`production`): en producción la API no arranca con `JWT_SECRET` débil (<32 caracteres o el de ejemplo) ni con `CORS_ORIGINS=*`.

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

Se leen de `.env` (pydantic-settings) o del entorno.

## Pruebas

```bash
make test        # = python -m pytest -q
```

`tests/conftest.py` recrea `pepito_test` (DROP/CREATE), aplica `alembic upgrade head`, ejecuta el seed y levanta la app
con `TestClient` (`RUN_SCHEDULER=false`). Cubre: login/asignación, RBAC, revocación de dispositivo, logout (jti),
flujo completo del operador, cierre con diferencia → caso, diferencia grave → urgente + aprobación, apertura con
excepción, `CART_IN_USE` / `SHIFT_ALREADY_OPEN` / `NO_ASSIGNMENT`, transferencia, idempotencia (venta y cierre),
`sync/batch` mixto con error y duplicado, ventana de cancelación y permisos, inventario reconstruible (API, movimientos
y vista SQL), bloqueo de lote, motor de reglas (`no_open`, `cash_difference`, `low_battery`, `out_of_geofence`,
`sync_stale`, `high_waste`, `stock_critical`, `anomalous_cancellations`, `maintenance_overdue`), configuración de reglas
con audit log, auditoría con acciones correctivas.

## Docker

```bash
docker build -t pepito-os-api .
docker run --rm -p 8000:8000 -e DATABASE_URL=postgresql+psycopg://pepito:pepito@host.docker.internal:5433/pepito \
  -e JWT_SECRET=... -e SEED=true pepito-os-api
```

El contenedor corre `alembic upgrade head`, opcionalmente el seed (`SEED=true`) y `uvicorn`.

## Estructura

```
app/
  main.py                 FastAPI, CORS, handlers de error, APScheduler (motor de reglas)
  core/   config, db (engine/Session/Base), security (bcrypt/JWT), errors (§4), deps (auth + RBAC `require`), timeutil
  models/ org (zonas, usuarios, dispositivos, puntos, carritos, activos, asignaciones, asistencia)
          ops (turnos, gps_pings, checklists, cash_sessions) · catalog (productos, presentaciones, sabores, precios, metas)
          sales (sales, sale_lines, payments, sale_cancellations) · inventory (almacenes, lotes, movimientos, merma, recepciones, conteos)
          cases (casos, alertas, acciones, auditorías, mantenimiento, aprobaciones, ai_recommendations, rules)
          system (idempotency_keys, events, audit_log)
  schemas/ operator.py, backoffice.py (Pydantic v2)
  routers/ auth, me, shifts, sales, waste, help, inventory, gps, sync, supervisor, cases, control_tower, rules,
           approvals, reports (daily, attendance, audit-log), assets (activos, mantenimiento, lotes), admin, health
  services/ shifts, sales, cash, inventory, cases, rules_engine, priority, geo, events, audit, idempotency, sync, control_tower
  ai/classifier.py        clasificador por palabras clave (interfaz `classify_help_text`)
  seed.py                 datos demo (idempotente)
alembic/                  una migración inicial (`0001_esquema_inicial.py`) con todas las tablas + vista `inventory_balances`
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
  dentro de `cancel_window_minutes` (5); supervisor (de su zona) / ops / admin siempre, con motivo.
- **Inventario**: `inventory_movements` es la fuente de verdad (tipos `receipt, sale, waste, count_adjustment,
  transfer_out, transfer_in, return, blocked`). Balance = `SUM(qty)` por punto/presentación; la vista SQL
  `inventory_balances` lo expone. Conteos generan `count_adjustment` (+ caso `inventory_inconsistent` si |dif| > `units`).
- **Cierre**: esperado = pagos `cash` de ventas `recorded` del turno; `|dif| > threshold_cents` → caso (`review`, o
  `urgent` si > `severe_cents`) + evento `CashDifferenceDetected`; si es grave también se crea una `Approval` para Finanzas.
- **Turnos**: índices únicos parciales `shifts(cart_id) WHERE status='open'` y `shifts(operator_id) WHERE status='open'`
  (→ `CART_IN_USE` / `SHIFT_ALREADY_OPEN`). La transferencia cierra el turno saliente (caja/conteo intermedio), abre uno
  para `to_operator_id` y registra `transfer_out`/`transfer_in`.
- **Auth**: JWT HS256 con `sub, role, device_id, jti, exp`; `revoked_tokens` por `jti` (logout); dispositivo revocado →
  `401 DEVICE_REVOKED` en cada request y en login.
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
- Fotos (`photos`, `photo_base64`) no se almacenan (no hay object storage en MVP); sólo se registra que se enviaron.
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
