# Definiciones de indicadores — PEPITO OS

Fuente única de qué se cuenta, con qué denominador y dónde se calcula. Cualquier cambio aquí sube `REPORT_VERSION`
(`apps/api/app/services/reporting.py`) para que un PDF viejo y uno nuevo no se confundan.

## Parámetros vigentes (fuente de verdad en el sistema, no en documentos)

| Parámetro | Dónde vive | Vigente |
|---|---|---|
| Precios por presentación | `price_versions` / `price_items` (versionado, con `valid_from`, `created_by`, audit) | 50 g $25 · 75 g $35 · 100 g $45 (Manual Maestro, "Precios APROBADO") |
| Meta diaria por punto | `points.daily_target_cents` / `daily_target_tx`; `daily_targets` por fecha; default `daily_sales_target_default_cents` | $2,340 · 60 tx |
| Umbrales de caja | `settings.cash_difference_threshold_cents` / `_severe_cents` (rules.params tiene precedencia) | $20 · $100 |
| Distancia de apertura | `settings.open_max_distance_m` | 50 m (puntos verificados) |
| Tolerancia de conteo | `settings.inventory_count_tolerance_units` | 3 u. |
| Costos por punto | `point_costs` (renta, permiso, resguardo, otros/mes; inversión inicial; con vigencia) | Administración → Puntos → Ficha → Costos; sin costos capturados el margen aparece vacío |
| Materia prima | `settings.raw_cost_per_kg_cents` | $70/kg |

Los documentos de negocio con precios distintos ($20/$30/$40 del estudio de mercado; $30/$40/$50 en borradores)
son históricos o hipótesis: no alimentan reportes. Una venta guarda `price_version_id` y `unit_price_cents`, así que un
cambio de precio nunca reescribe ventas anteriores.

## Ventas

| Indicador | Definición | Excluye |
|---|---|---|
| Ventas ($) | Σ `sales.total_cents` con `status = recorded`, por `occurred_at` en hora local | canceladas |
| Transacciones (tx) | número de ventas `recorded` | canceladas |
| Unidades (piezas) | Σ `sale_lines.qty` de ventas `recorded`; una pieza = una presentación (50/75/100 g) | — |
| Kilogramos teóricos | Σ qty × gramos de la presentación (peso nominal, no peso entregado) | — |
| Ticket promedio | Ventas ($) ÷ tx. Sin descuentos en el catálogo MVP; una devolución cancela la venta (`reason_code=return`) y sale del cálculo | canceladas y devueltas |
| Meta del periodo | Σ por punto de (días con turno en el periodo × meta diaria). Un punto del catálogo sin turno no suma meta | — |
| Avance vs meta | Ventas ($) ÷ meta del periodo | — |
| Meta "60" | se refiere a **transacciones** por día por punto (`daily_target_tx`); la meta en pesos es `daily_target_cents` | — |

## Caja

Efectivo esperado del turno = fondo inicial (`cash_sessions.opening_cents`, capturado al abrir) + cobros en efectivo
de ventas `recorded` + depósitos − retiros − gastos − devoluciones en efectivo (`cash_movements`, cada uno con actor,
motivo y hora; un retiro/gasto ≥ `cash_out_max_cents` abre caso de revisión; no se permite retirar más de lo que hay).
Efectivo contado = `shifts.cash_counted_cents`. Diferencia = contado − esperado; `close_status = difference` si
|diferencia| ≥ umbral; ≥ umbral grave → caso urgente + aprobación de Finanzas. Una devolución (`reason_code=return`)
saca la venta del esperado y abre un caso de revisión para el supervisor.

Pagos digitales (QR/tarjeta): son **importes declarados por el operador**; el sistema no recibe confirmación del
adquirente (fase 2). Los reportes los muestran como "digital declarado", nunca como cobro confirmado.

Un ajuste posterior no reescribe el cierre: la diferencia histórica se conserva y el ajuste queda como caso/aprobación
con actor, antes/después y motivo (`audit_log`).

## Rentabilidad (expansión)

Margen del punto en el periodo = ventas − materia prima (gramos vendidos × `raw_cost_per_kg_cents`) − costos fijos
mensuales vigentes × días con turno ÷ 30. Payback (meses) = inversión inicial ÷ margen mensualizado. Sólo se muestra
para puntos con costos capturados; nunca se llama "utilidad neta" a una cifra que no descuenta todo lo anterior.

## Merma e inventario

| Indicador | Definición |
|---|---|
| Merma (%) | unidades de `waste` ÷ (unidades vendidas + unidades de merma). Sólo merma **registrada** con motivo |
| Merma valorizada | unidades de merma × último precio de venta de la presentación (no costo) |
| Ajustes por conteo | `inventory_movements.count_adjustment`: diferencia entre conteo físico y teórico. Se muestra aparte de la merma; no se clasifica como robo |
| Existencia | Σ `inventory_movements.qty` por punto/presentación (reconstruible) |
| Existencia en kg | Σ existencia × gramos nominales de la presentación ÷ 1000 (peso teórico, no pesado). **Siempre 2 decimales**, redondeo mitad hacia arriba (8 025 g → 8.03 kg), en una sola función por capa: `kg2()` en la API, `gramsToKg()` en la PWA, `fmtKg()` en el backoffice; formato `kg` en reportes |
| Conteo físico | `inventory_counts`: piezas contadas vs teóricas por presentación; se informa en piezas y kg. La foto del producto (opcional) se guarda como evidencia `inventory_count` con fecha/hora/punto impresos en la imagen por el teléfono |
| Días de inventario | existencia ÷ consumo promedio diario del periodo (unidades vendidas ÷ días) |

Pérdida de peso en preparación y consumo de materia prima no se capturan (fase 2, almacén central).

## Personas

| Indicador | Definición |
|---|---|
| Horas abiertas | Σ (`closed_at` o ahora − `opened_at`) de los turnos del periodo |
| Venta por hora | ventas ($) ÷ horas abiertas. Compara contra el promedio de los vendedores con ventas en el alcance |
| Puntualidad | `attendance.late_minutes` > 15 → tarde; `absent` si no abrió y venció el turno planeado |
| Ranking día/mes/año | rango denso por ventas `recorded`, recalculado cada 5 min y en cada cierre (`users.sales_rank_*`) |

Las comparaciones entre vendedores son por hora abierta, no por venta bruta; una diferencia se etiqueta como
Hipótesis hasta revisar punto, horario y contexto.

## Cumplimiento, calidad, mantenimiento

| Indicador | Definición |
|---|---|
| Apertura a tiempo | `opened_at` ≤ `planned_start` + gracia (`rules.no_open.grace_minutes`, 20 min) |
| Sin abrir | sin turno cuando ya venció la gracia o el fin planeado |
| Fuera del punto | apertura con excepción `out_of_geofence` (distancia > 50 m en puntos verificados; > geocerca en los demás) |
| Conformidad | 1 − no conformidades ÷ ítems evaluados en auditorías |
| Disponibilidad de carrito | 1 − horas de tickets correctivos abiertos sobre activos del carrito ÷ horas del periodo. No distingue todavía cierre planeado de falla (fase 2: calendario de operación) |
| MTTR | promedio de horas entre creación y resolución de tickets correctivos resueltos |

## Comparativos y cobertura

- Periodo anterior equivalente: misma longitud inmediatamente anterior; mes → mismos días del mes anterior; año → año
  anterior. Si el periodo anterior no tiene base (0 o sin datos) el KPI muestra **"Sin base comparable"**, nunca un %.
- **Corte de datos** (`data_as_of`): fin del periodo, o el momento de la consulta si el periodo incluye hoy. Se imprime
  junto con la fecha de generación y la versión del cálculo.
- **Cobertura**: cada reporte informa turnos abiertos (sus cifras cambiarán al cierre), cierres vencidos y casos de
  sincronización abiertos (puede haber registros pendientes en el teléfono; el servidor no inventa ese número). Con
  turnos abiertos el reporte se marca **Cifras preliminares**.
