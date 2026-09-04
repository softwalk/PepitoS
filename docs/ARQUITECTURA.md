# Arquitectura PEPITO OS (MVP)

```
 Operador (PWA)            Supervisor / Backoffice (web)
 ┌──────────────┐          ┌──────────────────────────┐
 │ 4 acciones   │          │ Control Tower · Excepc.  │
 │ IndexedDB    │          │ Ruta · Auditoría · Admin │
 │ cola cifrada │          └────────────┬─────────────┘
 └──────┬───────┘                       │ HTTPS /v1 (JWT)
        │ /v1/sync/batch (idempotente)  │
        ▼                               ▼
 ┌───────────────────────────────────────────────────────┐
 │ API FastAPI (modular por dominio)                     │
 │ routers → services (shifts, sales, cash, inventory,   │
 │ cases, sync, control_tower) → SQLAlchemy              │
 │ · idempotency_keys   · events (outbox)  · audit_log   │
 │ · APScheduler → rules_engine (11 reglas, cada 5 min)  │
 │ · ai/classifier (sólo propone; nunca escribe ledger)  │
 └───────────────────────────┬───────────────────────────┘
                             ▼
                    PostgreSQL 16 (41 tablas + vista inventory_balances)
```

## Decisiones

| Tema | Decisión | Por qué |
|---|---|---|
| Un solo backend modular (no microservicios) | Routers/servicios por dominio en un proceso | 1–100 puntos no justifican red de servicios; los límites de dominio quedan en `services/` para extraer después |
| Ledger append-only | `sales` nunca se borra; cancelación = `sale_cancellations` + movimiento `return` | Invariante 1 del data-model; conciliación siempre reconstruible |
| Inventario por movimientos | `inventory_movements` es la fuente; `inventory_balances` es vista | Invariante 3; un conteo crea `count_adjustment`, no reescribe |
| Idempotencia en servidor | `idempotency_keys(key PK, user_id, request_hash, response)` por usuario | Venta offline no se duplica; misma clave + payload distinto → 409; clave ajena → 409 |
| Turno único por carrito/operador | Índices únicos parciales `WHERE status='open'` | Invariante 5 (dos operadores, un carrito) |
| Precio versionado | `price_versions` + `price_items`; la venta guarda `price_version_id` y `unit_price_cents` | PRD §17: cambio de precio con ventas offline |
| Reglas antes que IA | `rules` en tabla, evaluadas por APScheduler; LLM fuera de la ruta crítica | PRD §6/§18 y spec ai-governance |
| Auto-resolución | `no_open`, `sync_stale`, `out_of_geofence`, `low_battery` se resuelven solos cuando la condición desaparece (si nadie los tomó) | Evita que el supervisor vea "Punto sin abrir" cuando el punto ya abrió |
| Offline en cliente | Cola de comandos con UUID, `local:<uuid>` para turnos abiertos sin red, sustitución tras ACK | Spec offline-sync; el operador nunca ve "reintentar API" |
| Fechas | UTC en DB; "hoy" y jornadas en `America/Mexico_City` | Series diarias comparables por punto |
| Dinero | Centavos enteros | Sin errores de flotante en conciliación |

## Flujo de una venta offline

1. Toque en `50 g` → comando `{idempotency_key, type:"sale", payload:{shift_id, price_version_id, lines, payments}}` cifrado en IndexedDB → UI "Guardado".
2. Vuelve la red → `POST /v1/sync/batch` con los comandos en orden (shift_open primero si estaba pendiente).
3. Servidor: `run_idempotent` → `create_sale` (valida precio/versión, crea `sale`, `sale_lines`, `payments`, movimiento `sale`, eventos `SaleRecorded`/`PaymentRecorded`) → commit → respuesta guardada en `idempotency_keys`.
4. Cliente aplica ACK (`ok`/`duplicate` eliminan el comando; `error` no reintentable → "Requiere ayuda").

## Flujo de cierre

`GET /shifts/{id}/expected` → "Debes tener $X" → `POST /shifts/{id}/close` con `cash_counted_cents` y `product_counts` → servidor:
diferencia de caja (umbral → caso `review`; grave → caso `urgent` + `Approval`), `count_adjustment` por presentación (umbral → caso),
`ShiftClosed`, `CashDifferenceDetected`; asignación pasa a `done`.

## Flujo de reapertura (continuar un turno terminado)

Sólo `admin` (`shift.reopen`). `POST /v1/shifts/{id}/reopen {reason}` exige: `status=closed`, turno abierto en el día local actual, cierre hace menos de `shift_reopen_window_hours` (parámetro B6, 24 h por defecto) y que ni el operador ni el carrito tengan otro turno abierto (la carrera contra una apertura simultánea la resuelven los índices únicos parciales → 409). Se reabre el mismo turno (caja, asistencia, asignación a `started`), se conserva íntegro el cierre anterior en `audit_log` (`shift.reopen`) y en el evento `ShiftReopened`, y los casos `cash_difference` / `inventory_inconsistent` y la aprobación de diferencia grave de ese cierre se marcan **superados** (caso `closed`, aprobación `cancelled`) porque el siguiente cierre vuelve a conciliar contra todas las ventas del turno. La PWA, cuando no tiene turno abierto local, re-consulta `/v1/me/assignment` al volver a primer plano y cada 60 s; al adoptar el turno arranca pings GPS, cachea el esperado y guarda las ventas previas del servidor (`server_sales`) para los contadores y el cierre sin red.

## Seguridad

JWT HS256 12 h con `jti` revocable · dispositivo registrado y revocable (`401 DEVICE_REVOKED`) · bcrypt · RBAC por permiso en cada
ruta + filtrado por operador/zona · audit log con antes/después/actor/motivo/IP · segregación (quien solicita una aprobación
no la decide) · en `APP_ENV=production` el arranque falla con `JWT_SECRET` débil o `CORS_ORIGINS=*`.

## Observabilidad

`/v1/health` (DB) · logs estructurados de uvicorn · el motor de reglas registra excepciones por regla sin detener las demás.
Pendiente (ver revisión): métricas Prometheus, tracing, alertas del propio sistema.
