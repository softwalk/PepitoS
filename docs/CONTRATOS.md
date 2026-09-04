# PEPITO OS — Contratos técnicos (v1.0 MVP)

Documento normativo para todos los componentes. Derivado del PRD v2 Simplificado IA-First y del OpenSpec v2
(`version3/Sistema`). Si un componente y este documento difieren, gana este documento; si este documento y el
OpenSpec difieren, se corrige aquí y se avisa.

## 1. Stack decidido

| Capa | Tecnología | Motivo |
|---|---|---|
| Backend API | Python 3.11 · FastAPI · SQLAlchemy 2.x · Alembic · psycopg 3 · Pydantic v2 · APScheduler | Stack del equipo (FastAPI); reglas y agentes IA en Python |
| Base de datos | PostgreSQL 16 | Ledger transaccional, JSONB para payloads/eventos |
| PWA Operador | React 18 · Vite · TypeScript · vite-plugin-pwa · idb (IndexedDB) | Offline-first, instalable |
| Backoffice + Supervisor | React 18 · Vite · TypeScript · react-router · leaflet | Control Tower web responsive; supervisor = rutas móviles del mismo app |
| Infra | Docker Compose (postgres, api, web-operator, web-backoffice) | Dev/Staging/Prod idénticos |

Regla técnica (PRD §18): **un LLM nunca escribe en ventas, caja o inventario**. En MVP no hay llamadas a LLM en la
ruta crítica; el módulo `ai/` solo clasifica texto de casos "otro" con reglas por palabras clave y deja un
`AIRecommendation` trazable. La integración con un modelo real se hace vía la interfaz `ai/classifier.py`
(`classify_help_text(text) -> {category, confidence, model_version}`) sin tocar ledgers.

## 2. Roles y permisos (RBAC)

| Rol | Ve | Permisos clave |
|---|---|---|
| `operator` | Solo su asignación/turno/punto | shift.open, shift.close, sale.create, sale.cancel_own_5min, waste.create, help.create, inventory.receipt |
| `supervisor` | Su zona (`zone_id`) | + cases.read/update, audits.create, cash_count.surprise, sale.cancel, shift.transfer |
| `ops` | Toda la red | + control_tower.read, rules.read/update, inventory.*, maintenance.*, people.read |
| `finance` | Toda la red | + reconciliation.read, approvals.decide(payment), reports.read |
| `admin` | Todo | + admin.* (usuarios, puntos, carritos, precios, dispositivos, revocación), rules.run, shift.reopen |

Reglas: mínimo privilegio; toda ruta declara permisos requeridos; `403` con `FORBIDDEN` si falta.
Datos de operador filtrados por `shift.operator_id == user.id`; supervisor por `point.zone_id == user.zone_id`.

## 3. Autenticación

- `POST /v1/auth/login` `{username, password, device_id, device_name?, platform?}` →
  `{access_token, token_type:"bearer", expires_in, user:{id, name, role, zone_id}}`.
  Registra/actualiza `Device` (`device_id` lo genera el cliente, UUID persistido localmente).
- JWT HS256, claims `sub` (user id), `role`, `device_id`, `exp` (12 h). Header `Authorization: Bearer`.
- Cada request valida que el `Device` no esté `revoked`; si lo está → `401 DEVICE_REVOKED`.
- `POST /v1/auth/logout` → revoca el token actual (tabla `revoked_tokens` por `jti`).
- Admin: `POST /v1/admin/devices/{id}/revoke`.
- Passwords con bcrypt. Secretos por variables de entorno (`JWT_SECRET`, `DATABASE_URL`).

## 4. Convenciones HTTP

- Prefijo `/v1`. JSON UTF-8. Fechas ISO-8601 en UTC (`2026-09-03T14:05:00Z`). Dinero en **centavos enteros** (`amount_cents`).
- Escrituras móviles llevan `idempotency_key` (UUID generado en dispositivo) en el body. Repetir la misma clave devuelve
  el mismo resultado con `200` y `"duplicate": true` (nunca crea dos veces). Misma clave con payload distinto → `409 IDEMPOTENCY_CONFLICT`.
- Errores: `{"error": {"code": "STRING_ESTABLE", "message": "texto corto en español", "details": {...}}}`.

Códigos: `AUTH_INVALID`, `DEVICE_REVOKED`, `FORBIDDEN`, `NOT_FOUND`, `VALIDATION`, `NO_ASSIGNMENT`,
`SHIFT_ALREADY_OPEN`, `CART_IN_USE`, `SHIFT_NOT_OPEN`, `IDEMPOTENCY_CONFLICT`, `PRICE_VERSION_INVALID`,
`CANCEL_NOT_ALLOWED`, `LOT_BLOCKED`, `CONFLICT`.

## 5. Endpoints

### Operador
| Método | Ruta | Body → Respuesta |
|---|---|---|
| GET | `/v1/me/assignment` | → `{assignment:{id, shift_date, planned_start, planned_end, point:{id,name,address,lat,lng,geofence_radius_m}, cart:{id,code}}|null, active_shift:{id, opened_at, status, ready, exceptions}|null, catalog:Catalog, config:OperatorConfig}`. `active_shift` puede ser un turno **reabierto** por el administrador tras un cierre: la PWA lo adopta (GPS, esperado y ventas previas del servidor) |
| POST | `/v1/shifts/open` | Regla de distancia: con GPS, si el operador está a más de `open_max_distance_m` (50 m; puntos verificados) o de `geofence_radius_m` (puntos por validar) del punto asignado, excepción **crítica** `out_of_geofence` con `distance_m`/`limit_m` ("Estás a N m del punto asignado (máximo L m)"), `ready=false`, caso **urgente** `open_out_of_geofence` + alerta en Control Tower. `Point` expone `geo_verified` y `meta` (ficha del catálogo) |
| POST | `/v1/shifts/open` (detalle) | `{idempotency_key, assignment_id, opened_at, checklist:{cart_secure,battery_ok,product_ok,clean_ok,pos_ok:boolean}, gps:GPS|null, photos?:[{key,base64}]}` → `201 {shift_id, status:"open"|"open_with_exception", exceptions:[{code,message}], ready:boolean}` |
| GET | `/v1/shifts/{id}/expected` | → `{sales_count, sales_total_cents, cash_expected_cents, digital_total_cents, product_expected:{presentation_id:qty}, waste_units}` |
| POST | `/v1/shifts/{id}/close` | `{idempotency_key, closed_at, cash_counted_cents, product_counts:{presentation_id:qty}, checklist:{off_ok,clean_ok,secured_ok,stored_ok,charging_ok}, gps}` → `{shift_id, status:"reconciled"|"difference", cash_expected_cents, cash_counted_cents, difference_cents, product_diff:{presentation_id:int}, case_id|null}` |
| POST | `/v1/shifts/{id}/transfer` | `{idempotency_key, to_operator_id, cash_counted_cents, product_counts, gps}` → `{closed_shift_id, new_shift_id}` |
| POST | `/v1/admin/points/import-authorized` | **Admin.** Re-importa el catálogo `app/data/puntos_autorizados_cdmx.json` (100 ubicaciones CDMX; zona = alcaldía). Idempotente por `meta.ranking`; no pisa coordenadas `geo_verified`. → `{created, updated, total, zones_created}` |
| POST | `/v1/admin/points/{id}/verify-location` | **Admin.** `{verified, lat?, lng?, source?}` marca las coordenadas como validadas en campo (audit `points.verify_location`). Con `geo_verified=true` la apertura exige ≤ `open_max_distance_m` (50 m); si no, tolera `geofence_radius_m` |
| POST | `/v1/shifts/{id}/reopen` | **Sólo admin.** Continuar un turno terminado: `{reason}` (≥5 car.) → turno con `status:"open"`. Requiere `status=closed` y que ni el operador ni el carrito tengan otro turno abierto (409 `SHIFT_ALREADY_OPEN`). Conserva ventas y el cierre anterior en `audit_log` (`shift.reopen`) + evento `ShiftReopened`; el siguiente cierre concilia contra todas las ventas. |
| POST | `/v1/sales` | `{idempotency_key, shift_id, occurred_at, price_version_id, lines:[{presentation_id, qty, flavor_id?}], payments:[{method:"cash"|"qr"|"card", amount_cents}], offline_created:boolean, gps?}` → `201 {sale_id, folio, total_cents, status:"recorded", duplicate:false}` |
| POST | `/v1/sales/{id}/cancel` | `{idempotency_key, reason_code, note?}` → `{sale_id, status:"cancelled"}` |
| POST | `/v1/waste` | `{idempotency_key, shift_id, occurred_at, presentation_id, qty, reason_code:"spill"|"quality"|"expired"|"sample"|"other", note?}` → `201 {waste_id}` |
| POST | `/v1/help-cases` | `{idempotency_key, shift_id?, occurred_at, category:"cart"|"battery"|"product"|"payment"|"security"|"other", note?, photo_base64?, gps?}` → `201 {case_id, severity, category, status:"open"}` |
| POST | `/v1/inventory/receipts` | `{idempotency_key, shift_id, occurred_at, qr_code?, lines:[{presentation_id, qty, lot_code?}]}` → `201 {receipt_id}` |
| POST | `/v1/inventory/counts` | `{idempotency_key, shift_id, occurred_at, counts:{presentation_id:qty}}` → `{count_id, differences:{presentation_id:int}}` |
| POST | `/v1/gps/pings` | `{pings:[{shift_id, at, lat, lng, accuracy_m, mocked:boolean, battery_pct?}]}` → `{accepted:int}` |
| POST | `/v1/sync/batch` | `{device_id, commands:[{idempotency_key, type:"sale"|"waste"|"shift_open"|"shift_close"|"help_case"|"gps_ping"|"inventory_receipt"|"inventory_count"|"sale_cancel", created_at, payload}]}` → `{results:[{idempotency_key, status:"ok"|"duplicate"|"error", code?, message?, result?}]}` (procesa en orden; un error no detiene los demás) |
| GET | `/v1/catalog` | → `Catalog` |
| GET | `/v1/prices/current` | → `{price_version_id, valid_from, prices:{presentation_id:amount_cents}}` |

`Catalog = {presentations:[{id,name,grams,price_cents,sort}], flavors:[{id,name,sort}], price_version_id, waste_reasons:[{code,label}], help_categories:[{code,label,icon}], checklist_open:[{key,label}], checklist_close:[{key,label}]}`
`OperatorConfig = {cash_difference_threshold_cents, cancel_window_minutes, gps_interval_seconds, photo_sampling_pct}`
`GPS = {lat, lng, accuracy_m, mocked:boolean, at}`

### Supervisor
| Método | Ruta | Respuesta |
|---|---|---|
| GET | `/v1/supervisor/exceptions` | `{urgent:[Case], review:[Case], normal:[PointStatus]}` |
| GET | `/v1/supervisor/route` | `{date, stops:[{order, point:{id,name,lat,lng}, reason, case_ids:[]}]}` |
| POST | `/v1/audits` | `{point_id, shift_id?, checklist:{key:boolean}, cash_counted_cents?, notes?, photos?:[], corrective_actions:[{description, owner_id, due_date}]}` → `201 {audit_id, case_ids:[]}` |
| GET | `/v1/cases?status=&severity=&point_id=` | `[Case]` |
| GET/PATCH | `/v1/cases/{id}` | PATCH `{status?:"open"|"in_progress"|"resolved"|"closed", assignee_id?, resolution?, severity?, category?}` |
| POST | `/v1/cases/{id}/actions` | `{description, owner_id, due_date}` → `Action` |
| PATCH | `/v1/actions/{id}` | `{status:"pending"|"done"|"overdue"}` |

`Case = {id, category, severity:"urgent"|"review"|"normal", status, title, description, source:"operator"|"rule"|"supervisor"|"system", point:{id,name}, shift_id, opened_at, age_minutes, impact_score, priority_score, assignee:{id,name}|null, actions:[Action], ai:{suggested_category, confidence}|null}`

### Backoffice / Control Tower
| Método | Ruta | Respuesta |
|---|---|---|
| GET | `/v1/control-tower/summary?date=` | `{date, totals:{points, open, late, closed, offline, sales_cents, target_cents, tx, ticket_cents, forecast_close_cents}, exceptions:{urgent, review, normal}, points:[PointStatus], alerts_recent:[Alert]}` |
| GET | `/v1/control-tower/briefing?date=` | `{date, headline, decisions:[{title, why, recommendation, case_id?}], numbers:{...}}` |
| GET | `/v1/reports/daily?date=` | `{date, rows:[{point, shift_id, operator, sales_cents, tx, cash_expected_cents, cash_counted_cents, difference_cents, waste_units, waste_pct, status}]}` |
| GET/PUT | `/v1/rules` · `/v1/rules/{key}` | `[{key, name, enabled, params:{}, severity}]`; PUT `{enabled?, params?, severity?}` |
| POST | `/v1/rules/run` | ejecuta motor ahora → `{alerts_created, cases_created}` |
| GET | `/v1/approvals?status=` · POST `/v1/approvals/{id}/decision` `{decision:"approve"|"reject", note}` |
| GET | `/v1/audit-log?entity=&entity_id=&limit=` |
| GET | `/v1/inventory/status` → por punto: balance, teórico, riesgo de quiebre |
| GET | `/v1/people/attendance?date=` |
| GET | `/v1/assets` · POST `/v1/maintenance/tickets` · PATCH `/v1/maintenance/tickets/{id}` |
| POST | `/v1/lots/{id}/block` `{reason}` → `{affected_points:[...]}` |
| CRUD | `/v1/admin/users`, `/v1/admin/points`, `/v1/admin/carts`, `/v1/admin/assignments`, `/v1/admin/presentations`, `/v1/admin/price-versions`, `/v1/admin/devices`, `/v1/admin/zones` |
| GET | `/v1/admin/assignments?date_from&date_to&limit` | Por defecto últimos 30 días + próximos 7 (máx. 500). Cada fila incluye `shift_id` y `shift_status` del último turno (una sola consulta `DISTINCT ON`) para **Continuar turno** |
| GET | `/v1/health` → `{status:"ok", db:"ok", version}` |

`PointStatus = {point:{id,name,lat,lng,zone_id}, status:"open"|"closed"|"late"|"offline"|"not_scheduled", shift_id, operator:{id,name}|null, opened_at, last_seen_at, last_gps:{lat,lng,at,in_geofence}|null, battery_pct, sales_cents, target_cents, tx, ticket_cents, cash_status:"ok"|"difference"|"pending", stock_risk:"ok"|"low"|"critical", open_cases:{urgent,review}}`

## 6. Reglas determinísticas (MVP)

Tabla `rules(key, enabled, params jsonb, severity)`. Se ejecutan cada `RULES_INTERVAL_SECONDS` (default 300) y con `POST /v1/rules/run`.
Cada regla evalúa y, si dispara y no existe caso abierto igual (`dedupe_key = rule_key:point_id:date`), crea `Alert` + `Case`.

| key | Condición | Severidad default | params |
|---|---|---|---|
| `no_open` | Asignación de hoy sin `ShiftOpened` pasados N min de `planned_start` | urgent | `{grace_minutes:20}` |
| `out_of_geofence` | Último GPS del turno abierto fuera del radio del punto por más de N min | urgent | `{minutes:10}` |
| `low_sales_trajectory` | Ventas del turno < X% de la meta prorrateada por hora tras M horas abiertas | review | `{pct:60, min_hours:2}` |
| `high_waste` | Merma del día / (ventas+merma) > X% | review | `{pct:4}` |
| `cash_difference` | \|contado − esperado\| > umbral en cierre | urgent si > grave, review si > umbral | `{threshold_cents:2000, severe_cents:10000}` |
| `inventory_inconsistent` | \|conteo − teórico\| > N unidades | review | `{units:3}` |
| `low_battery` | último `battery_pct` < N con turno abierto | urgent si < critical | `{warn:25, critical:10}` |
| `anomalous_cancellations` | cancelaciones del turno > N o > X% de ventas | review | `{count:3, pct:10}` |
| `sync_stale` | turno abierto sin evento/ping en N min | review | `{minutes:30}` |
| `maintenance_overdue` | activo con preventivo vencido | review | `{}` |
| `stock_critical` | balance de una presentación < mínimo | review | `{min_units:10}` |

Prioridad de caso: `priority_score = severity_weight(urgent=100, review=50, normal=10) + impact_score + min(age_minutes/30, 20)`.

## 7. Eventos de dominio

Tabla `events(id, type, occurred_at, actor_id, point_id, shift_id, entity, entity_id, payload jsonb)` (outbox append-only).
Tipos: `ShiftOpened, ShiftClosed, ShiftTransferred, ShiftReopened, SaleRecorded, SaleCancelled, PaymentRecorded, WasteRecorded, InventoryMoved,
CashDifferenceDetected, PointLate, PointOffline, HelpRequested, AlertRaised, AlertResolved, AuditCompleted, MaintenanceTicketCreated,
LotBlocked, ApprovalRequested, ApprovalDecided, AIRecommendationCreated`.
`audit_log(id, at, actor_id, action, entity, entity_id, before jsonb, after jsonb, reason, ip, device_id)` para cambios críticos.

## 8. Modelo de datos (tablas)

`zones, users, devices, revoked_tokens, points, carts, assets, assignments, shifts, attendance, gps_pings, products, presentations, flavors,
price_versions, price_items, sales, sale_lines, payments, sale_cancellations, cash_sessions, warehouses, lots, inventory_movements,
inventory_balances (vista/consulta desde movimientos), waste, receipts, inventory_counts, checklists, checklist_results, audits,
cases, alerts, actions, maintenance_tickets, approvals, ai_recommendations, rules, idempotency_keys, events, audit_log, daily_targets`.

Invariantes (OpenSpec data-model): venta confirmada no se borra (cancelación = nuevo registro); inventario reconstruible desde
`inventory_movements`; cierre referencia turno; un carrito no puede tener dos turnos abiertos (constraint parcial único
`shifts(cart_id) WHERE status='open'`); venta offline conserva `idempotency_key` y `price_version_id`.

## 9. Offline (PWA Operador)

- Almacén local IndexedDB (`idb`): `session`, `assignment`, `catalog`, `queue` (comandos pendientes), `shift_state`, `sales_local`.
- Cada acción crea un comando `{idempotency_key: uuid, type, created_at, payload}` → UI optimista → `POST /v1/sync/batch`
  en cuanto hay red (evento `online`, cada 30 s, y tras cada acción). ACK → se elimina de la cola.
- Estado visible: **Guardado** (en cola local), **Pendiente de enviar** (n), **Requiere ayuda** (error no recuperable).
- Cifrado: cola local cifrada con WebCrypto AES-GCM; clave derivada de secreto por sesión guardado en IndexedDB
  (limitación conocida: el navegador no ofrece keystore; se documenta).
- Reinicio: al arrancar, restaura `shift_state` y cola. Precio: la venta guarda `price_version_id` y `unit_price_cents` vigentes.
- Deshacer: la última venta puede eliminarse de la cola local si aún no se sincronizó (≤60 s); si ya sincronizó → cancelación con motivo.

## 10. Datos demo (seed)

Usuarios (password entre paréntesis): `admin` (admin123), `ops` (ops123), `finanzas` (fin123), `sup1` (sup123, zona Centro),
`op1`, `op2`, `op3` (op123). Puntos CDMX: Metro Insurgentes, Parque México, Alameda Central (zona Centro), con carritos `C-001..C-003`
y asignaciones de hoy para op1..op3 (08:00–18:00 local, America/Mexico_City). Presentaciones: 50 g $25, 75 g $35, 100 g $45
(versión de precio vigente; configurable). Sabores: Natural, Limón, Chile, Enchilado, Salado. Meta diaria por punto: 60 ventas / $2,340.
Reglas con parámetros de §6. Un activo por carrito (batería, cargador, POS) con preventivo programado.
