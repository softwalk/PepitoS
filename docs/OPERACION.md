# Operación de PEPITO OS — runbook

Qué configurar y cómo operar lo que no es código: notificaciones, MFA, respaldos, reportes por correo, límites y
cuentas demo. Complementa `docs/HTTPS.md` (TLS/LAN) y `PEPITO_OS_LEEME.md` (levantar el sistema).

## 1. Notificaciones al supervisor (push + WhatsApp)

Política (`services/notifications.py`): caso **URGENTE** → supervisores de la zona del punto + Operaciones/admin;
**REVISAR** → supervisores de la zona; **SLA vencido** → Operaciones/admin; los normales no notifican. Una misma clave
(regla + punto) no se repite en `notify_dedupe_minutes` (60). Todo queda en `notification_log` (Seguridad y avisos →
Últimas notificaciones). Sin claves configuradas el canal es `log`: el piloto ve qué habría avisado.

1. **Web Push**: generar claves VAPID una sola vez y ponerlas en `.env`:
   `docker compose exec api python -m app.services.webpush genkeys` → `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`.
   Reiniciar `api`. Cada supervisor entra a **Seguridad y avisos → Activar en este navegador** (HTTPS obligatorio;
   en iOS la PWA del backoffice debe estar añadida a la pantalla de inicio). «Enviar prueba» confirma la entrega.
2. **WhatsApp de respaldo** (sólo urgentes cuando ningún push se entregó): cuenta Twilio con WhatsApp habilitado,
   `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM=whatsapp:+1…`; cada usuario captura su teléfono
   E.164 en Seguridad y avisos. Twilio exige plantillas aprobadas fuera de la ventana de 24 h: el texto es
   `PEPITO · <título>\n<detalle>\n<url>`.
3. Preferencias por usuario (`users.notify_prefs`): push y WhatsApp se pueden apagar por separado.

## 2. SLA de casos

`sla_urgent_minutes` (15) y `sla_review_minutes` (240) en Administración → Parámetros. Un caso «tomado» es el que
tiene responsable o está en proceso. Al vencer sin tomar: `payload.sla_breached_at`, severidad review → urgent,
+10 de impacto, evento `CaseSlaBreached` y aviso a Operaciones. Excepciones y el detalle del caso muestran el chip
SLA (restante / vencido / ok). Cada corrida del motor (5 min) evalúa el SLA.

## 3. MFA (verificación en dos pasos)

TOTP (RFC 6238) para **admin y finanzas** (los demás roles pueden activarlo). Seguridad y avisos → Activar MFA →
clave manual u `otpauth://` en la app autenticadora → confirmar con un código. Login: usuario/contraseña → código.
`mfa_enforce=true` (Parámetros) bloquea el backoffice a admin/finanzas hasta activarlo (`403 MFA_ENROLLMENT_REQUIRED`).
Teléfono perdido: un administrador usa `POST /v1/admin/users/{id}/mfa-reset` (queda en audit log) y el usuario vuelve
a activarlo. El reto de login (`mfa_token`) dura 5 min y no sirve como sesión.

## 4. Respaldos y restore (RPO 15 min del NFR → respaldo diario + WAL queda para fase 2)

Servicio `backup` de docker-compose: `pg_dump` comprimido cada día a `BACKUP_HOUR_UTC` (08:00 UTC = 02:00 CDMX),
conserva `BACKUP_KEEP_DAYS` (14) en el volumen `backups`. Comandos (`scripts/backup.sh`):

```
docker compose exec backup sh /backup.sh once                    # respaldo ahora
docker compose exec backup ls -lh /backups                       # listar
docker compose exec backup sh /backup.sh verify /backups/pepito-20260907-0805.sql.gz   # prueba de restore en pepito_verify (no toca producción)
docker compose stop api && docker compose exec backup sh /backup.sh restore /backups/pepito-….sql.gz && docker compose start api
```

Copiar el volumen fuera de la VM (p. ej. `rsync` nocturno a otro host) forma parte del plan de continuidad; el
script sólo cubre el respaldo local. Las evidencias (MinIO, volumen `miniodata`) se respaldan aparte.
**Prueba de restore documentada**: ejecutar `verify` mensualmente y anotar fecha y conteos en la bitácora de operación.

## 5. Reportes programados por correo

Job diario 07:05 hora local (`REPORTS_DAILY_HOUR_LOCAL`): Resumen ejecutivo y Caja de **ayer** a `REPORTS_EMAIL_TO`
(separados por coma). Requiere `SMTP_HOST/PORT/USER/PASSWORD/FROM`; sin SMTP el archivo se guarda en el volumen
`reportsout` (`/app/reports_out`) y queda en la bitácora. PDF si la imagen incluye WeasyPrint (`pip install weasyprint`
+ dependencias de sistema); si no, HTML autocontenido. Bajo demanda: Reportes → ✉ Enviar (misma autorización del
usuario, auditado como `report.export`).

## 6. Límites y cuentas

- `RATE_LIMIT_PER_MINUTE` (600 por IP y minuto, ventana deslizante; `/v1/health` exento) además del límite de
  intentos de login. Detrás de Caddy se usa `X-Forwarded-For`.
- Cabeceras de seguridad en Caddy (HSTS, nosniff, frame-ancestors, CSP para las SPA, Permissions-Policy).
- Cuentas demo (`admin/admin123`, `op1/op123`…): sólo con `SEED_MODE=demo`; prohibidas en `APP_ENV=production`;
  fuera de `development` se crean con `must_change_password=true`, así el piloto cambia las claves al primer acceso.
  Antes de operar con dinero real: `SEED_MODE=prod` + `ADMIN_INITIAL_PASSWORD` y alta de usuarios reales.

## 7. Fondo de caja

`cash_float_default_cents` (Parámetros, $500) es el fondo que la app propone al abrir; el vendedor confirma o corrige y
la diferencia con el estándar se muestra como aviso. Mezcla recomendada: 8×$5, 8×$10, 6×$20, 4×$50 (+1×$100 si se
aceptan billetes de $500). Retiro parcial al supervisor cuando el efectivo pase de ~$1,500.

## 8. Mapa sin internet

La VM del piloto no tiene salida a internet: Control Tower muestra el **mapa esquemático** (cuadrícula con los puntos)
cuando los tiles de OpenStreetMap no cargan. Para un mapa real en LAN, servir tiles propios (p. ej. `tileserver-gl`
con un MBTiles de CDMX) y compilar el backoffice con `VITE_TILES_URL=http://<host>:8080/tile/{z}/{x}/{y}.png`.
