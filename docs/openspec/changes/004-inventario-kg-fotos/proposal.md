# Change 004 — Inventario en kilogramos y fotos con sello (conteo, recepción, incidente)

## Why

El supervisor y Operaciones piensan el producto en kilogramos (así se compra la materia prima y se planea la
reposición), pero la app sólo mostraba piezas. Además, un conteo o un incidente sin foto es difícil de revisar a
distancia: la evidencia debe llevar fecha, hora, punto y ubicación de forma que no dependa de metadatos editables.

## What changes

- **PWA**: Contar y Recibir producto muestran el total en kg (piezas × gramos nominales) y lo esperado en kg; botón
  «Tomar foto» que estampa etiqueta, fecha/hora, punto (y GPS en AYUDA) dentro de la imagen antes de encolarla.
  Nunca bloquea: sin cámara se registra sin foto. Viaja en el comando offline (`photo_base64`).
- **API**: `photo_base64` opcional en `inventory_count` / `inventory_receipt` → `evidence` (kinds nuevos
  `inventory_count`, `inventory_receipt`, entidades `inventory_count` / `receipt`); `product_expected_kg` en
  `/shifts/{id}/expected`; kg en `/inventory/status`; `GET /inventory/counts` y `/inventory/receipts` con kg y
  evidencias; el caso incluye `point.lat/lng`; reporte Inventario v1.2 con KPI «Existencia total (kg)», columna kg y
  tabla de conteos con kg, fotos y enlace.
- **Backoffice**: Inventario con kg por punto/total, tarjetas Conteos físicos y Recepciones (galería de fotos, detalle
  por presentación, `?count=` desde el reporte); detalle de caso con «Ubicación del incidente» (mapa/esquemático,
  GPS ±m, enlace a OSM) y la foto de AYUDA.

## Success

- Conteo con foto desde la PWA → evidencia `inventory_count` visible en Inventario y en el reporte (smoke operador +
  `smoke_inventory.py`).
- kg iguales en PWA, `/inventory/counts` y reporte para el mismo conteo (pytest `test_inventory_kg_and_count_receipt_photos`).
- Caso de AYUDA con GPS y foto muestra ubicación y galería en el backoffice (vitest `inventory-kg.test.tsx`).
