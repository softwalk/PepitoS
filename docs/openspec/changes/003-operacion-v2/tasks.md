# Operación v2 — Tasks

- [x] Migración 0009: cash_movements, point_costs, users.totp_secret/mfa_*/notify_prefs, push_subscriptions, notification_log.
- [x] API: cash movements + opening_cents + fórmula de esperado; devolución; SLA (`services/sla.py`); notificaciones (`webpush.py`, `notifications.py`, router); MFA (`mfa.py`, rutas auth/admin); costos y margen; CSV/send/job diario; caso manual; tags de AYUDA; muestreo de ruta; forecast por perfil; rate limit; demo gating.
- [x] PWA operador: fondo de caja, /devolucion, /recibir, /contar, Enviar ahora, bienvenida+GPS, diferencia en vivo, alto contraste, contexto, voz.
- [x] Backoffice: login MFA, /seguridad, sw.js push, tema/densidad, SchematicMap, dedupe alertas, DataTable, Kpi, StateBox/OfflineBanner, SlaChip, TransferShift, PointCosts, CSV/✉/+Crear caso.
- [x] Infra: Caddy headers, servicio backup + scripts/backup.sh, CI con logs de diagnóstico, .env/compose.
- [x] Docs: OPERACION.md, INDICADORES.md (caja/rentabilidad), CONTRATOS, ARQUITECTURA, REPORTES, manuales, trazabilidad.
- [ ] Fase 2: WAL/PITR para RPO 15 min, PDF servidor en la imagen (WeasyPrint), reporte histórico de SLA, tiles propios en la VM, plantillas WhatsApp aprobadas.
