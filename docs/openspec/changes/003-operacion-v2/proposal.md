# Change 003 — Operación v2: captura confiable, avisos que se convierten en trabajo, seguridad y decisión

## Why

La revisión de diseño (sept-2026) priorizó: captura sencilla para el vendedor, información confiable para el supervisor
y decisiones claras para Dirección. Faltaban fondo de caja y salidas (el efectivo esperado no cuadraba con la calle),
devoluciones, aviso inmediato al supervisor, SLA con escalado, MFA, costos para decidir expansión y un mapa que
funcione sin internet en la VM del piloto.

## What changes

- **Caja**: `cash_movements` (fondo, retiro, gasto, devolución en efectivo) y `opening_cents` al abrir; efectivo
  esperado = fondo + efectivo − salidas en servidor y offline. Devolución = cancelación `return` con caso de revisión.
- **Supervisión**: SLA por severidad con escalado y notificación; notificaciones Web Push (VAPID, RFC 8291 propio) y
  WhatsApp (Twilio) con dedupe y bitácora; transferencia de turno desde el teléfono; muestreo de puntos en la ruta;
  caso manual desde hallazgos de reportes.
- **Operador**: recibir/contar producto en la PWA, «Enviar ahora», bienvenida con Probar GPS, diferencia en vivo al
  cerrar, alto contraste, contexto (lluvia, cierre planeado…) en AYUDA, guía por voz.
- **Decisión**: costos por punto con vigencia → margen y payback en `expansion`; CSV; envío por correo y reporte
  diario programado; forecast por perfil horario.
- **Seguridad/infra**: MFA TOTP (admin/finanzas, `mfa_enforce`), rate limit por IP, cabeceras Caddy (HSTS/CSP),
  respaldos diarios con restore verificable, cuentas demo con cambio de contraseña obligatorio fuera de development.
- **UI**: KPI unificado, tablas ordenables con selector de columnas, estados diferenciados, mapa esquemático sin tiles,
  alertas deduplicadas, tema oscuro y densidad.

## Success

- El efectivo esperado del cierre coincide con fondo + ventas − salidas (prueba E2E en smoke del operador).
- Un caso urgente sin tomar en 15 min escala y avisa a Operaciones (pytest `test_sla_escalation`).
- Push cifrado verificable (roundtrip RFC 8291), suscripción/preferencias por API y UI.
- Login de admin con MFA exige código; el `mfa_token` no sirve como sesión.
- Expansión muestra margen/payback sólo con costos capturados; nunca «utilidad» sin base.
- 87 pruebas API, 40 backoffice, 43 operador; smokes E2E de operador (con fondo, devolución, gasto, recepción,
  conteo), offline, backoffice y reportes en verde.
