# Módulo de Reportes (BI) — PEPITO OS

Reportes ejecutivos para tomar decisiones sobre la operación de carritos: qué punto reforzar, qué diferencia de caja escalar, qué vendedor acompañar, qué carrito reparar, dónde abrir. Diez reportes, cada uno con un propósito, alcance por rol aplicado en la API, filtros en la URL, comparativos vs periodo anterior, hallazgos generados a partir de los datos y exportación a PDF sin dependencias nuevas.

- API: `apps/api/app/services/reporting.py` (agregaciones + hallazgos) y `apps/api/app/routers/reports_bi.py` (`/v1/reports/bi`).
- Backoffice: `pages/Reports.tsx` (Centro), `pages/ReportView.tsx` (reporte + filtros), `pages/ReportPrint.tsx` (impresión), `components/ReportBlocks.tsx` (KPIs, gráficas, tablas, hallazgos), `lib/reports.ts`.
- Migración `0008_reportes_bi` (índices). Tests: `tests/test_reports_bi.py`, `test/reports.test.tsx`, `scripts/smoke_reports.py`.

## 1. Análisis: catálogo de reportes candidatos

Fuentes disponibles (tablas): `sales`, `sale_lines`, `payments`, `sale_cancellations`, `shifts` (apertura/cierre, excepciones, caja, GPS), `cash_sessions`, `gps_pings` (batería, geocerca, mock), `checklist_results`, `assignments`, `attendance`, `points` (meta diaria, score y ficha del catálogo), `zones`, `users` (ranking día/mes/año), `carts`, `assets`, `maintenance_tickets`, `inventory_movements`, `waste`, `receipts`, `inventory_counts`, `lots`, `cases`, `alerts`, `audits`, `actions`, `approvals`, `evidence`, `events`, `audit_log`, `settings`, `rules`.

Candidatos evaluados (26) y decisión:

| Área | Candidato | Decisión |
|---|---|---|
| Dirección | Resumen ejecutivo diario/semanal | **Top 10 · executive** |
| Dirección | Forecast de cierre del día | Ya existe en Control Tower (`forecast_close_cents`); no se duplica |
| Comercial | Ventas por dimensión (día/zona/punto/vendedor/presentación/hora/medio de pago) | **Top 10 · sales** |
| Comercial | Elasticidad por versión de precio | Fase 2: requiere más de una versión de precios con historial |
| Comercial | Ranking de puntos con score estratégico | **Top 10 · points** |
| Comercial | Sabores más vendidos | Incluido como dimensión futura (sale_lines.flavor_id); hoy el sabor es opcional y escaso |
| Finanzas | Caja y conciliación (esperado/contado/diferencias/aprobaciones/arqueos/reaperturas) | **Top 10 · cash** |
| Finanzas | Rentabilidad por punto (costos, renta, payback) | Fase 2: no hay captura de costos. Campos preparados en `expansion` (`cost_cents`, `rent_cents`, `margin_cents`, `payback_days`) |
| Finanzas | Conciliación de pagos digitales vs terminal | Fase 2: requiere integración con el adquirente |
| Operación | Productividad de vendedores (ventas/hora, ticket, merma, caja, asistencia, cancelaciones, ranking) | **Top 10 · people** |
| Operación | Cumplimiento y GPS (tarde/sin abrir/fuera de punto/geocerca/sync/fotos) | **Top 10 · compliance** |
| Operación | Tiempos de respuesta a casos (SLA por severidad) | Fusionado como KPI en `quality` (acciones vencidas) y pendiente de SLA formal (fase 2) |
| Operación | Transferencias de turno | Volumen bajo; visible en Control Tower. Descartado |
| Inventario | Consumo, merma, ajustes, existencias, días de inventario, lotes bloqueados | **Top 10 · inventory** |
| Inventario | Trazabilidad por lote (de recepción a venta) | Fase 2: las ventas no llevan lote todavía |
| Inventario | Reposición sugerida por punto | Incluida como hallazgo/recomendación en `inventory` (< 1.5 días) |
| Calidad | Auditorías, no conformidades, acciones correctivas, excepciones de apertura | **Top 10 · quality** |
| Calidad | Fotos de muestreo cumplidas | Incluido como KPI en `compliance` |
| Mantenimiento | Activos, preventivos vencidos, tickets, disponibilidad, batería, MTTR | **Top 10 · maintenance** |
| Mantenimiento | MTBF por activo | Se calcula cuando haya ≥ 2 fallas por activo; hoy sólo MTTR |
| Expansión | Puntos activos vs catálogo de 100 ubicaciones, GO/AJUSTAR/NO GO, candidatos | **Top 10 · expansion** |
| Expansión | Canibalización entre puntos cercanos | Fase 2: requiere ≥ 2 puntos operando a < 500 m |
| Sistema | Uso del sistema (logins, dispositivos, sync) | Descartado del Top 10: operativo, no de negocio; disponible vía `audit_log` |
| Sistema | Salud del motor de reglas (alertas por regla) | Cubierto por `/v1/rules` y Excepciones |
| Todos | Ranking de vendedores día/mes/año | Ya existe en Personas y en la PWA; se integra en `people` |
| Todos | Diario de turnos | Ya existe (`/v1/reports/daily`, página Ventas) |

## 2. Los 10 reportes

| Clave | Reporte | Decisión que habilita | KPIs principales | Fuente | Frecuencia | Depende de fase 2 |
|---|---|---|---|---|---|---|
| `executive` | Resumen ejecutivo | Dónde poner la atención hoy | ventas, avance vs meta, tx, ticket, puntos con turno, diferencias de caja, merma, casos abiertos; tendencia vs periodo anterior; ventas por zona; top/bottom 5 | sales, shifts, points, waste, cases | tiempo real / diaria | — |
| `sales` | Ventas y desempeño comercial | Mezcla, horarios y puntos donde empujar | ventas, tx, ticket, unidades, % digital, cancelaciones, precio vencido, offline; por día/hora, presentación, medio de pago, heatmap hora×día; por punto/vendedor/presentación | sales, sale_lines, payments | diaria / semanal | sabores (dimensión) |
| `cash` | Caja y conciliación | Qué conciliar, escalar o aprobar | esperado, contado, diferencia neta, turnos con diferencia, graves, reaperturas, arqueos sorpresa, aprobaciones pendientes | shifts, audits, approvals, audit_log | diaria | — |
| `points` | Ranking de puntos y ubicaciones | Qué punto reforzar, auditar o reubicar | puntos con ventas, promedio, en meta, en rojo, merma > 4 %; top 10; score vs meta; ranking completo con Δ y vs red | sales, points, waste, cases | semanal | — |
| `people` | Productividad de vendedores | A quién capacitar, reconocer o reasignar | $/hora abierta, ticket, merma, diferencias de caja, cancelaciones, casos, asistencia/puntualidad, ranking día/mes/año | sales, shifts, attendance, waste, sale_cancellations, users | semanal / mensual | — |
| `inventory` | Inventario, consumo y merma | Qué reponer, qué lote revisar | merma %, merma valorizada, unidades, entradas, ajustes, lotes bloqueados; existencias y días de inventario; movimientos por día; merma por punto/presentación/motivo | inventory_movements, waste, lots, inventory_counts | diaria | trazabilidad por lote |
| `quality` | Calidad y auditorías | Qué auditar y qué acción está vencida | auditorías, conformidad, acciones pendientes/vencidas, turnos con excepción de apertura, casos; NC por ítem, excepciones, casos por categoría | audits, actions, shifts, cases | semanal | SLA formal |
| `maintenance` | Mantenimiento y disponibilidad | Qué carrito atender | activos, disponibilidad promedio, preventivos vencidos, tickets abiertos, MTTR, turnos con batería < 25 % | assets, maintenance_tickets, gps_pings, carts | semanal | MTBF |
| `compliance` | Cumplimiento operativo y GPS | Quién incumple el protocolo | aperturas a tiempo, tarde, sin abrir, fuera del punto (50 m), pings fuera de geocerca, casos sin sync, fotos de muestreo | assignments, shifts, gps_pings, cases, evidence | diaria | — |
| `expansion` | Expansión y ubicaciones | Dónde abrir, cerrar o reubicar | puntos activos vs catálogo, GO/AJUSTAR/NO GO/sin datos, ubicaciones sin abrir; ventas por alcaldía; score vs meta; candidatos por score | points.meta (catálogo), sales, shifts | mensual | rentabilidad (costos, renta, payback) |

### Criterios explícitos de `expansion`
Con ≥ 3 días con turno en el periodo: **GO** = ≥ 90 % de meta (meta = días con turno × meta diaria), ticket ≥ $36, merma ≤ 4 % y ≤ 2 casos abiertos; **AJUSTAR** = ≥ 60 % de meta (se indica qué falla: ticket, merma o casos); **NO GO** = < 60 %. Con menos de 3 días: **SIN DATOS**. La recomendación de siguiente apertura toma la ubicación del catálogo con mejor score aún sin punto activo.

## 3. Seguridad (RBAC real)

Permisos nuevos en `ROLE_PERMS` (`apps/api/app/core/deps.py`): `reports.executive`, `reports.sales`, `reports.cash`, `reports.points`, `reports.people`, `reports.inventory`, `reports.quality`, `reports.maintenance`, `reports.compliance`, `reports.expansion` y `reports.self` (operador: sólo su desempeño en `sales`/`people`). No se crean roles.

| Reporte | admin | ops | finance | supervisor | operator |
|---|---|---|---|---|---|
| executive | ✅ | ✅ | ✅ | ❌ | ❌ |
| sales | ✅ | ✅ | ✅ | ◐ su zona | ◐ el suyo |
| cash | ✅ | ◐ sin aprobaciones (`hidden: approvals`) | ✅ | ◐ su zona | ❌ |
| points | ✅ | ✅ | ✅ | ◐ su zona | ❌ |
| people | ✅ | ✅ | ◐ sin asistencia (`hidden: attendance`) | ◐ su zona | ◐ el suyo |
| inventory | ✅ | ✅ | ◐ sólo merma valorizada (`hidden: movements, stock, lots, counts`) | ◐ su zona | ❌ |
| quality | ✅ | ✅ | ❌ | ◐ su zona | ❌ |
| maintenance | ✅ | ✅ | ❌ | ◐ carritos de su zona | ❌ |
| compliance | ✅ | ✅ | ◐ lectura | ◐ su zona | ❌ |
| expansion | ✅ | ✅ | ✅ | ❌ | ❌ |

- El alcance se aplica en la consulta (`build_scope`): supervisor → `zone_id` fijo (`zone_locked`), operador → `operator_id` fijo (`operator_locked`). Un `zone_id`/`point_id` de otra zona en la URL no amplía nada: se ignora o devuelve filas vacías.
- Sin permiso → `403 FORBIDDEN` y entrada en `audit_log` (`report.view`, `result: denied`). Cada consulta permitida también se audita (`report.view`/`report.export` con reporte, filtros, rol y alcance).
- Las secciones parciales por rol se omiten **en el servidor** y se listan en `hidden` para que la UI lo explique; nunca se envían datos que el frontend "oculte".
- El administrador conserva `*`; su acceso a información financiera sigue siendo un permiso explícito (`reports.cash`, `reports.executive`) heredado del comodín, documentado aquí.

## 4. API

| Método | Ruta | Respuesta |
|---|---|---|
| GET | `/v1/reports/bi` | `{categories:[{name, reports:[{key, title, description, decision, frequency, orientation, scope}]}], presets:[{key,label}]}` — sólo los permitidos al rol |
| GET | `/v1/reports/bi/options` | `{zones, points, operators, carts, presentations, methods}` dentro del alcance del rol |
| GET | `/v1/reports/bi/{key}?period=&from=&to=&zone_id=&point_id=&operator_id=&cart_id=&presentation_id=&method=&export=` | payload declarativo (abajo). `period ∈ today, yesterday, last7, week, month, prev_month, year, custom`; `custom` exige `from`/`to` (≤ 366 días). `export=true` audita como `report.export` |

Payload:
```
{key, title, category, description, decision, frequency, orientation, generated_at,
 period:{preset, preset_label, from, to, label, days}, compare:{...periodo anterior equivalente},
 filters:{...aplicados}, scope:{role, zone_id, operator_id, ..., zone_locked, operator_locked},
 kpis:[{key, label, value, format: money|int|pct|float|text, prev, delta_pct, delta_abs, trend: up|down|flat, tone: ok|warn|bad|neutral, hint}],
 charts:[{key, title, type: line|bar|stacked|donut|heatmap|scatter, x, y?, layout?, data:[...], series:[{key,label,format,dashed?,axis?,color?}], x_labels?, y_labels?, domain?}],
 tables:[{key, title, columns:[{key,label,format,tone?,link?}], rows:[...], link?}],
 insights:[{kind: fact|trend|alert|hypothesis|recommendation, text, link}],
 hidden:[...secciones omitidas para el rol]}
```
Periodo anterior: misma longitud inmediatamente anterior; `month` → mismos días del mes anterior; `year` → año anterior. Todo en hora local `America/Mexico_City` (`_bounds` = `local_day_bounds`). Series por hora cuando el periodo es un día; por día en el resto.

## 5. Backoffice

- Menú **Monitoreo → Reportes** (`/reportes`, icono `reports`), visible para supervisor, ops, finance y admin; en móvil está en la barra inferior.
- **Centro de Reportes**: categorías Ejecutivo · Comercial · Finanzas · Operaciones · Inventarios · Calidad · Mantenimiento · Expansión, sólo con lo que la API devuelve.
- `/reportes/<clave>?period=…&point_id=…`: filtros en la URL (`lib/reports.ts`: `filtersFrom/filtersToQuery`), segmentado de periodo, selects de dimensión (zona bloqueada para supervisor; punto/vendedor se filtran por zona), botón **Limpiar filtros**, chips de periodo/comparativo/alcance, KPIs con semáforo y Δ vs periodo anterior, **Hallazgos y alertas** primero, gráficas (recharts) y tablas ejecutivas paginadas (25 filas; 60 en impresión) con enlaces de drill-down (`/reportes/points?point_id=`, `/reportes/people?operator_id=`, `/casos/:id`, `/auditorias/:id`, `/excepciones`).
- **Exportar PDF** → `/reportes/<clave>/imprimir?…` (fuera del Layout): logo, título, periodo, comparativo, filtros con nombres, generado por, KPIs, hallazgos, gráficas SVG, tablas, pie con leyenda de confidencialidad; `@page { size: Letter portrait|landscape }` según el reporte, `break-inside: avoid`, `window.print()` automático (`?noprint=1` lo evita, usado en pruebas). Misma autorización que el reporte.
- Responsive: KPIs a 2 columnas, gráficas apiladas y tablas con scroll horizontal en ≤ 768 px.

## 6. Rendimiento

- Índices (migración 0008): `sales(occurred_at, point_id)`, `sales(operator_id, occurred_at)`, `sale_lines(presentation_id, sale_id)`, `payments(method, occurred_at)`, `inventory_movements(point_id, occurred_at)`, `waste(occurred_at, point_id)`, `cases(point_id, opened_at)`, `shifts(opened_at, point_id)`, `gps_pings(at, shift_id)`, `audits(performed_at, point_id)`, `assignments(shift_date, point_id)`, `audit_log(action, at)`.
- Sin tabla de agregados: con el volumen actual (≤ 100 puntos × ≤ 100 ventas/día) cada reporte tarda < 50 ms sobre la base demo. Si el mes supera ~1 M de ventas, el siguiente paso es un agregado diario por punto/vendedor/presentación actualizado en `run_rules_job` (misma sesión), sin duplicar la fuente de verdad.
- Tablas limitadas a 200 filas en la API y paginadas en la UI; rangos personalizados ≤ 366 días.

## 7. Fase 2 (documentado, no implementado)

Rentabilidad por punto (captura de costos y rentas → margen y payback en `expansion`), trazabilidad por lote hasta la venta, SLA por severidad de caso, MTBF, canibalización entre puntos cercanos, conciliación con el adquirente de pagos digitales y **PDF servidor** para envío programado (evaluar WeasyPrint; la vista de impresión actual ya es el HTML fuente).
