# Reports (BI) — Technical Design

## Components

1. `services/reporting.py`: periodos locales (`parse_period`, `previous_period`), alcance (`build_scope`), diez
   constructores de reporte y generación de hallazgos. Sin agregados; consulta la fuente de verdad.
2. `routers/reports_bi.py`: `GET /v1/reports/bi` (catálogo por rol), `/options` (dimensiones en alcance),
   `/{key}` (payload declarativo), auditoría de cada consulta.
3. Backoffice: `pages/Reports.tsx` (Centro), `pages/ReportView.tsx` (filtros en URL + cuerpo), `pages/ReportPrint.tsx`
   (impresión fuera del layout), `components/ReportBlocks.tsx` (KPIs, gráficas recharts, tablas, hallazgos),
   `lib/reports.ts` (filtros ↔ URL, formatos, semáforos).
4. Migración `0008_reportes_bi`: índices `sales(occurred_at, point_id)`, `sales(operator_id, occurred_at)`,
   `sale_lines(presentation_id, sale_id)`, `payments(method, occurred_at)`, `inventory_movements(point_id, occurred_at)`,
   `waste(occurred_at, point_id)`, `cases(point_id, opened_at)`, `shifts(opened_at, point_id)`, `gps_pings(at, shift_id)`,
   `audits(performed_at, point_id)`, `assignments(shift_date, point_id)`, `audit_log(action, at)`.

## Payload declarativo

`{key, title, category, period, compare, filters, scope, kpis[], charts[], tables[], insights[], hidden[]}` — el
frontend no conoce cada reporte; renderiza por tipo (`line | bar | stacked | donut | heatmap | scatter`, formatos
`money | int | pct | float | delta | status | link | verdict`, semáforos por columna `target | ticket | waste | diff | days | avail`).

## Alcance

- supervisor → `zone_id` fijo (`zone_locked`); un `point_id` de otra zona devuelve filas vacías.
- operator → `operator_id` fijo (`operator_locked`), sólo `sales` y `people`.
- ops / finance / admin → red completa; secciones parciales según matriz (`hidden`).

## Meta y comparativos

Meta del periodo = Σ (días con turno del punto × meta diaria). Periodo anterior = misma longitud inmediatamente
anterior; mes → mismos días del mes anterior; año → año anterior. Series por hora cuando el periodo es un día.

## Criterios de expansión

≥ 3 días con turno; GO = ≥ 90 % de meta, ticket ≥ $36, merma ≤ 4 %, ≤ 2 casos; AJUSTAR = ≥ 60 %; NO GO = < 60 %;
SIN DATOS = < 3 días. Candidatos = ubicaciones del catálogo sin punto activo, ordenadas por score.

## Fase 2

Rentabilidad por punto (costos/renta/payback), trazabilidad por lote hasta la venta, SLA por severidad, MTBF,
canibalización entre puntos cercanos, conciliación con adquirente, PDF servidor (WeasyPrint) para envío programado,
tabla de agregados diarios si el volumen supera ~1 M ventas/mes.
