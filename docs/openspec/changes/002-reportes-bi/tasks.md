# Reports (BI) — Implementation Tasks

## Análisis
- [x] Inventario de fuentes (tablas, eventos, endpoints).
- [x] Catálogo de 26 reportes candidatos y selección del Top 10 sin redundancias (`docs/REPORTES.md`).

## API
- [x] Permisos `reports.*` + `reports.self` en `ROLE_PERMS` (sin roles nuevos).
- [x] `services/reporting.py`: periodos, alcance, 10 constructores, hallazgos.
- [x] `routers/reports_bi.py`: catálogo, opciones, reporte; audit `report.view` / `report.export`; 403 auditado.
- [x] Migración `0008_reportes_bi` (índices).
- [x] Pruebas: catálogo por rol, RBAC en API, alcance supervisor/operador, secciones parciales, periodos, auditoría,
      números del ejecutivo, opciones en alcance.

## Backoffice
- [x] Menú Monitoreo → Reportes (icono SVG inline, móvil).
- [x] Centro de Reportes por categorías (sólo lo permitido).
- [x] Página genérica: filtros en URL, segmentado de periodo, dimensiones, comparativo, KPIs, hallazgos, gráficas, tablas.
- [x] Vista de impresión `/reportes/:key/imprimir` (`@page`, `window.print()`).
- [x] Responsive ≤ 768 px.
- [x] Pruebas vitest (formatos, semáforos, filtros ↔ URL, Centro por rol, filtros que cambian URL, 403) y smoke E2E.

## Documentación
- [x] `docs/REPORTES.md`, `docs/CONTRATOS.md`, `docs/ARQUITECTURA.md`.
- [x] Sección "Reportes" en manuales de supervisor, operaciones, finanzas y administrador.
- [x] OpenSpec: `specs/reports`, este change, `api-contracts`, `data-model`, `acceptance`, `roadmap`, `security-ai-governance`.

## Pendiente (fase 2)
- [ ] Rentabilidad por punto (captura de costos/renta → margen y payback).
- [ ] PDF servidor para envío programado.
- [ ] Tabla de agregados diarios cuando el volumen lo justifique.
