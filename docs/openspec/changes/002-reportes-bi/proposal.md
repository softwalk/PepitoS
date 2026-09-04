# Change 002 — Módulo de Reportes (BI)

## Why

Control Tower y Briefing resuelven el "ahora"; dirección, finanzas, operaciones y supervisión no tenían una vista
comparable por periodo para decidir qué punto reforzar o reubicar, qué diferencia escalar, a quién acompañar, qué carrito
reparar y dónde abrir el siguiente punto del catálogo de 100 ubicaciones.

## What changes

- Nueva spec `specs/reports`.
- Permisos `reports.<área>` (+ `reports.self`) en los cinco roles existentes; sin roles nuevos.
- API `/v1/reports/bi` (catálogo, opciones, reporte) con alcance por zona/operador aplicado en la consulta, hallazgos
  etiquetados y auditoría `report.view` / `report.export`.
- Backoffice: menú Monitoreo → Reportes, Centro de Reportes, 10 páginas con filtros en la URL, vista de impresión.
- Migración de índices para consultas por fecha/punto/operador.
- Ajuste normativo en `people-locations`: el scoring de ubicaciones se materializa como score del catálogo + reporte de
  expansión (GO / AJUSTAR / NO GO); decisión final humana.

## Success

- Los 10 reportes responden con datos reales de la operación en < 1 s (P95) con 100 puntos.
- RBAC probado por rol en la API (403 auditado); el supervisor no puede salir de su zona por URL.
- Filtros compartibles por URL; comparativo vs periodo anterior en todos los KPIs.
- PDF exportable desde cualquier reporte con la misma autorización.
- Hallazgos etiquetados, sin causas no demostradas.

## Status

Implementado en `pepito-os` (commit `feat(reportes)`), 76 pruebas API, 35 pruebas backoffice y smoke E2E en verde.
