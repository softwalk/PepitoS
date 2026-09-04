# Spec: Reports (BI)

Módulo de reportes ejecutivos para decidir sobre la red: qué punto reforzar, qué diferencia escalar, a quién acompañar,
qué carrito reparar, dónde abrir. Complementa —no sustituye— Control Tower (tiempo real) y Briefing (decisiones del día).

## Requirement: Catálogo por rol

El sistema MUST exponer un Centro de Reportes organizado por categorías (Ejecutivo · Comercial · Finanzas · Operaciones ·
Inventarios · Calidad · Mantenimiento · Expansión) que muestre **sólo** los reportes que el rol puede consultar. La lista la
decide la API (`GET /v1/reports/bi`), nunca el frontend.

## Requirement: Diez reportes de decisión

MUST existir, como mínimo, estos reportes, cada uno con la decisión que habilita:
`executive` (dónde poner la atención), `sales` (mezcla, horarios, puntos), `cash` (qué conciliar/escalar/aprobar),
`points` (reforzar/auditar/reubicar), `people` (capacitar/reconocer/reasignar), `inventory` (reponer/revisar lote),
`quality` (auditar/acciones vencidas), `maintenance` (qué carrito atender), `compliance` (quién incumple el protocolo),
`expansion` (abrir/cerrar/reubicar).

Cada reporte MUST seguir el orden **KPI → desviación → causa → acción**: KPIs con semáforo y variación vs periodo
anterior, Hallazgos y alertas, gráficas, tablas ejecutivas con drill-down.

## Requirement: RBAC por área, sin roles nuevos

Los permisos MUST modelarse como `reports.<área>` asignados a los cinco roles existentes (operator, supervisor, ops,
finance, admin). `reports.self` habilita al operador únicamente su propio desempeño.

| Reporte | admin | ops | finance | supervisor | operator |
|---|---|---|---|---|---|
| executive | ✅ | ✅ | ✅ | ❌ | ❌ |
| sales | ✅ | ✅ | ✅ | ◐ zona | ◐ propio |
| cash | ✅ | ◐ sin aprobaciones | ✅ | ◐ zona | ❌ |
| points | ✅ | ✅ | ✅ | ◐ zona | ❌ |
| people | ✅ | ✅ | ◐ sin asistencia | ◐ zona | ◐ propio |
| inventory | ✅ | ✅ | ◐ sólo merma valorizada | ◐ zona | ❌ |
| quality | ✅ | ✅ | ❌ | ◐ zona | ❌ |
| maintenance | ✅ | ✅ | ❌ | ◐ carritos de su zona | ❌ |
| compliance | ✅ | ✅ | ◐ lectura | ◐ zona | ❌ |
| expansion | ✅ | ✅ | ✅ | ❌ | ❌ |

### Scenario: acceso sin permiso
- WHEN un usuario consulta `/v1/reports/bi/{key}` sin el permiso del área (por URL directa o llamada a la API)
- THEN la API responde `403 FORBIDDEN`
- AND registra en `audit_log` la acción `report.view` con `result: denied`.

### Scenario: alcance del supervisor
- WHEN un supervisor consulta cualquier reporte con `zone_id` o `point_id` de otra zona en la URL
- THEN la respuesta contiene únicamente filas de su `zone_id` (`scope.zone_locked = true`)
- AND nunca se devuelven datos que el frontend deba ocultar después.

### Scenario: secciones parciales
- WHEN el rol tiene acceso parcial (p. ej. ops en `cash`)
- THEN las secciones no permitidas se omiten en el servidor
- AND se listan en `hidden` para que la UI lo explique.

## Requirement: Periodos, filtros y comparativos

- Periodos MUST incluir: hoy, ayer, últimos 7 días, semana actual, mes actual, mes anterior, año actual y rango
  personalizado (≤ 366 días), siempre en hora local `America/Mexico_City`.
- Dimensiones según reporte: zona, punto, vendedor, carrito, presentación, medio de pago.
- Los filtros MUST vivir en la URL (query string) para persistir y ser compartibles.
- Cada KPI MUST compararse con el periodo anterior equivalente (semana vs semana, mes vs mes, año vs año) mostrando
  diferencia absoluta, porcentual y tendencia ↑ ↓ →.
- Drill-down SHOULD reutilizar rutas existentes (`/casos/:id`, `/auditorias/:id`, `/excepciones?point_id=`).

## Requirement: Metas proporcionales a la operación real

La meta del periodo MUST calcularse como días con turno × meta diaria del punto, para que los puntos del catálogo aún sin
operación no diluyan el avance vs meta.

## Requirement: Hallazgos y alertas

Cada reporte MUST incluir hallazgos generados en el backend a partir de los datos, etiquetados como
**Hecho · Tendencia · Alerta · Hipótesis · Recomendación**. Un hallazgo MUST NOT afirmar causas que los datos no
demuestran (las causas posibles se etiquetan como Hipótesis).

## Requirement: Expansión con criterios explícitos

`expansion` MUST clasificar cada punto activo en GO / AJUSTAR / NO GO / SIN DATOS con criterios publicados
(avance vs meta, ticket, merma, casos, mínimo 3 días con turno), contrastar puntos activos contra el catálogo de
ubicaciones autorizadas (ranking, score, alcaldía, tipo de nodo, riesgo) y recomendar la siguiente apertura. La decisión
final es humana. La rentabilidad por punto (costos, renta, payback) queda en fase 2 con los campos preparados.

## Requirement: Exportación a PDF

Cada reporte MUST tener una vista de impresión (`/reportes/<clave>/imprimir?…filtros`) sin navegación, con `@page`
(Carta, orientación según reporte), sin cortes de tablas/gráficas entre páginas, que consuma el mismo endpoint con la
misma autorización y se exporte con `window.print()`. El PDF MUST incluir logo, nombre, periodo, filtros, fecha/hora,
quién lo generó, KPIs, gráficas, tablas, hallazgos y leyenda de confidencialidad cuando aplique. PDF servidor para envío
programado es fase 2.

## Requirement: Auditoría y rendimiento

- Toda consulta y exportación MUST registrarse en `audit_log` (`report.view` / `report.export`) con usuario, reporte,
  filtros, rol, alcance y resultado permitido/denegado, sin datos sensibles innecesarios.
- Las consultas MUST apoyarse en índices por fecha/punto/operador; una tabla de agregados sólo se introduce cuando el
  volumen lo justifique y sin duplicar la fuente de verdad.
- Los reportes MUST ser de sólo lectura: nunca escriben en ventas, caja ni inventario.

## Requirement: Responsive

Desktop, laptop y tablet completos. En móvil (≤ 768 px) MUST priorizar KPIs, hallazgos y tablas resumidas; las
gráficas se apilan y las tablas anchas hacen scroll interno.
