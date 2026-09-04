# Trazabilidad OpenSpec v2 → implementación

Estado: ✅ implementado y probado · 🟡 parcial · ⬜ fuera del MVP (roadmap).

## specs/operator-app
| Requisito | Estado | Dónde |
|---|---|---|
| Home con 4 acciones | ✅ | `apps/operator/src/screens/Home.tsx` |
| Apertura automática (operador, turno, punto, carrito, hora, dispositivo, GPS) + checklist visual | ✅ | `OpenShift.tsx`, `services/shifts.open_shift` |
| Apertura ≤2 min; fotos sólo por excepción | 🟡 | Fotos sólo en AYUDA "otro"; muestreo (`photo_sampling_pct`) definido pero no aplicado en apertura |
| Requisito crítico falla → excepción + acción simple | ✅ | `open_shift` crea caso `open_<check>` |
| Venta 1–2 toques, precios versionados nunca hard-coded | ✅ | `Sell.tsx`, `price_versions` |
| Venta offline cifrada, idempotente, estado Guardado/Pendiente | ✅ | `offline/queue.ts`, `crypto.ts`, `sync.ts`; smoke offline |
| Merma cantidad + motivo visual | ✅ | `Sell.tsx` (MERMA) |
| Cierre: esperado, contado, conteo mínimo, ≤5 min; diferencia → caso sin formularios | ✅ | `CloseShift.tsx`, `services/shifts.close_shift` |

## specs/offline-sync
| Requisito | Estado | Dónde |
|---|---|---|
| ABRIR/VENDER/MERMA/cierre básico sin red | ✅ | smoke_offline.py |
| ID único por comando (idempotencia) | ✅ | `idempotency_keys` + test |
| Reinicio recupera turno y cola | ✅ | `store.tsx resumeShift`, smoke offline |
| Venta conserva versión de precio | ✅ | `sales.price_version_id`, `sale_lines.unit_price_cents` |
| Estados simples Guardado / Pendiente / Requiere ayuda | ✅ | `components/Layout.tsx` |

## specs/pos-cash
Ledger con folio/actor/timestamp/contexto ✅ · append-only ✅ (cancelación como registro nuevo) · conciliación POS × efectivo × digital × inventario ✅ (`services/cash`) · cierre conciliado / diferencia material → caso sin tocar ledger ✅ · cancelaciones/descuentos con permiso y motivo ✅ (descuentos: ⬜ no existen en el catálogo MVP).

## specs/inventory
Inventario central/por punto/en tránsito 🟡 (por punto y movimientos completos; almacén central y "en tránsito" existen como tablas `warehouses`/tipos `transfer_*` pero sin UI de almacén) · operador sin SKU/lote ✅ (recepción por QR/confirmación en API; sin pantalla en PWA 🟡) · consumo teórico vs conteo ✅ · reposición por reglas (`stock_critical`) ✅.

## specs/incidents
Botón único NECESITO AYUDA con 6 categorías ✅ · seguridad → crítico, captura mínima ✅ · "otro" con foto/voz y clasificación IA corregible ✅ (`ai/classifier.py`, `ai_recommendations.accepted`).

## specs/supervisor
Cola URGENTE/REVISAR/NORMAL ✅ · ruta sugerida por severidad/impacto/antigüedad/distancia ✅ (`supervisor/route`, vecino más cercano) · muestreo de puntos normales 🟡 (no hay muestreo aleatorio configurable) · auditoría Sí/No con evidencia opcional y notas por voz ✅ · correctivos con responsable/fecha/estado ✅ · seguimiento automático 🟡 (estado `overdue` calculado, sin recordatorios push/WhatsApp).

## specs/control-tower
Estado de red ✅ · excepciones ordenadas por severidad/impacto/antigüedad ✅ (`priority_score`; "confianza" ⬜) · 10 reglas MVP configurables ✅ + `stock_critical` · briefing de dirección ✅.

## specs/people-locations
Check-in/out, puntualidad, ausencia ✅ (`attendance`, `/people/attendance`) · cobertura/flotantes ⬜ · cambio de operador con transferencia formal ✅ (`/shifts/{id}/transfer`) · ubicaciones con dirección/GPS/horarios/serie diaria ✅ · `SiteScore` ⬜ (tabla creada, sin cálculo).

## specs/maintenance-quality
Activos con historial ✅ · tickets con severidad/estado ✅ · preventivos programables ✅ (`next_maintenance_at` + regla) · auditorías con no conformidad y correctivo ✅ · bloqueo de lote → puntos afectados y bloqueo de entregas/ventas ✅ · IA no libera sanitariamente ✅ (no existe tal acción automática).

## specs/security · security-ai-governance
RBAC ✅ · auditoría antes/después ✅ · MFA ⬜ · GPS con política de retención 🟡 (parámetros definidos; sin job de purga) · GPS simulado como señal ✅ (`gps_pings.mocked`, regla no sanciona) · segregación de funciones ✅ · dispositivo perdido ✅ · TLS ⬜ (responsabilidad del despliegue) · rate limiting ⬜ · LLM no escribe ledgers ✅ · versionado de modelo ✅ (`model_version`) · evaluación/drift ⬜.

## specs/ai-governance
Reglas primero ✅ · human-in-the-loop ✅ (`approvals`) · trazabilidad de recomendaciones ✅ · escrituras críticas sólo determinísticas ✅ · evaluación contra baseline ⬜.

## acceptance.md (resumen)
UX operador: 8/8 implementados; los tiempos (≤30 min aprendizaje, ≤2 min apertura, ≤5 min cierre) requieren prueba de usabilidad con operadores reales (Epic 0). Confiabilidad: 5/5 (el ≥99 % de captura se mide en piloto). Control: 7/7. Supervisión: 4/4. NFR: disponibilidad/P95 se miden en staging; "puntos por configuración, no por código" ✅ (`/admin`).
