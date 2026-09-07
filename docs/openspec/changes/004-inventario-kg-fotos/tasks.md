# Tareas — change 004

| # | Tarea | Estado | Dónde |
|---|---|---|---|
| 1 | Sello de foto (fecha/hora/punto/GPS) dentro de la imagen | ✅ | `apps/operator/src/offline/image.ts` `stampImage`/`stampLines`, `components/PhotoCapture.tsx` |
| 2 | Total en kg en Contar/Recibir (+ esperado) | ✅ | `screens/Inventory.tsx` `KgTotal`, `kilograms()`; test `kg-stamp.test.ts` |
| 3 | Foto en Contar/Recibir/AYUDA (comando offline) | ✅ | `state/actions.ts` (`photo_base64`), `screens/Help.tsx` (GPS en el sello) |
| 4 | API: evidencia de conteo/recepción, kg, listados | ✅ | `services/sync.py`, `routers/inventory.py`, `services/inventory.py` (`grams_of`, `kg_of`), `services/shifts.py` |
| 5 | Reporte Inventario v1.2 (kg, fotos, enlace) | ✅ | `services/reporting.py` (`REPORT_VERSION = "1.2"`) |
| 6 | Backoffice Inventario: kg, conteos, recepciones, galería | ✅ | `pages/Inventory.tsx`, `components/EvidenceGallery.tsx` |
| 7 | Backoffice caso: ubicación del incidente + foto | ✅ | `pages/CaseDetail.tsx`, `components/PointsMap.tsx` `IncidentMap` (`point.lat/lng` en `serialize_case`) |
| 8 | Pruebas | ✅ | pytest (+1), vitest operador (+4), backoffice (+4), smokes operador y `scripts/smoke_inventory.py` |
| 9 | Docs | ✅ | `INDICADORES.md`, `CONTRATOS.md`, manuales operador/supervisor/ops/admin |
| — | Peso real (báscula) en lugar de gramos nominales | ⬜ | fase 2 |
