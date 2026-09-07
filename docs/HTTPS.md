# HTTPS para PEPITO OS (Caddy)

La PWA necesita HTTPS fuera de `localhost`: sin él el navegador no registra el service worker (offline), no permite
instalarla ni entrega GPS. El `docker-compose.yml` incluye un contenedor `caddy` que pone TLS delante de todo.

| Modo | Cuándo | Variables en `.env` | Resultado |
|---|---|---|---|
| **LAN sin dominio** (piloto en la VM 104) | Los teléfonos llegan por IP | `PUBLIC_HOST=192.168.100.164`, `CADDY_TLS=tls internal` | `https://192.168.100.164:8443` operador · `:8444` backoffice · `:8445` API. Certificados firmados por la CA interna de Caddy |
| **Dominio público** | Hay DNS apuntando a la VM y puertos 80/443 abiertos | `SITE_OPERATOR=https://operador.tudominio.mx`, `SITE_BACKOFFICE=https://oficina.tudominio.mx`, `SITE_API=https://api.tudominio.mx`, `CADDY_TLS=` (vacío) | Let's Encrypt automático, renovación incluida |

## Modo LAN: instalar la CA en los teléfonos (una vez por teléfono)

1. Abrir en el teléfono `http://192.168.100.164:8446/ca.crt` (HTTP, sin certificado) y descargar.
2. **Android**: Ajustes → Seguridad → Cifrado y credenciales → Instalar certificado → Certificado de CA → elegir `ca.crt`.
   **iOS**: abrir el archivo → Ajustes → Perfil descargado → Instalar; luego Ajustes → General → Información → Ajustes de certificados de confianza → activar.
3. Abrir `https://192.168.100.164:8443`, "Añadir a pantalla de inicio". A partir de ahí funciona offline y con GPS.

La CA es única por instalación (vive en el volumen `caddydata`); si se borra el volumen, hay que reinstalarla en los teléfonos.
Para producción real conviene el modo con dominio: evita distribuir la CA y funciona fuera de la LAN.

## Si el GPS "no funciona" en el teléfono

La app lo diagnostica sola: pastilla roja **Sin GPS** en la barra superior y, en *Ajustes → Ubicación (GPS) → Probar GPS*, el motivo con la acción a tomar.

| Motivo mostrado | Causa | Qué hacer |
|---|---|---|
| *La app no está en modo seguro (https)* | Se abrió por `http://IP:8081` o por `https` con la CA **sin instalar** (el navegador la trata como insegura y no expone GPS aunque se "acepte" la advertencia) | Instalar la CA (arriba) y abrir `https://IP:8443`; volver a "Añadir a pantalla de inicio" desde esa dirección |
| *Ubicación bloqueada para esta app* | El operador pulsó "Bloquear" o la app instalada no tiene permiso | Android: Ajustes → Apps → Chrome (o la app instalada) → Permisos → Ubicación → Permitir. iOS: Ajustes → Safari → Ubicación → Permitir |
| *El teléfono no entrega ubicación* | Ubicación del sistema desactivada / modo ahorro extremo | Activar Ubicación en los ajustes rápidos; en Android usar precisión "Alta" |
| *Sin señal GPS por ahora* | Interior, cielo cubierto | Se reintenta solo (alta y luego baja precisión); el último fix reciente se reutiliza para ventas/ayuda/cierre |

## HTTPS también en PC/Mac; un solo origen por dispositivo

- `http://IP:8081` **no** es equivalente a `https://IP:8443` ni en computadora: sin contexto seguro no hay service worker
  (modo offline), ni geolocalización, ni instalación como app. La excepción de los navegadores aplica sólo a
  `localhost`/`127.0.0.1`, no a una IP de LAN. Uso recomendado: HTTPS (`8443` operador, `8444` backoffice) para todo uso
  normal y pruebas funcionales; HTTP sólo para diagnóstico puntual.
- Instalar la CA **no** activa el GPS ni el offline por sí mismo: valida la conexión HTTPS. El GPS además requiere el
  permiso del usuario; el offline requiere que la app haya cargado y guardado sus recursos una vez con red.
- **No alternar** `http://…:8081` y `https://…:8443` en un mismo teléfono con registros pendientes: IndexedDB y la cola
  cifrada son por origen; lo pendiente en un origen no aparece en el otro (no se pierde, pero no se envía hasta volver
  al origen donde se capturó). Fijar la dirección HTTPS antes de capturar operaciones reales.
- La PWA y el backoffice llaman a la API por **ruta relativa `/v1`** sobre su mismo origen (nginx/Caddy la proxean a
  `api:8000`): no hay contenido mixto ni CORS entre `8443/8444/8445`. `8445` (API directa) es sólo para scripts.
- Fuera de la LAN (Metro Insurgentes, Parque México, Alameda): el operador trabaja con la cola offline y sincroniza al
  tener red hacia `PUBLIC_HOST`; si se expone el servicio a internet, hacerlo con dominio y certificado real
  (`CADDY_TLS` automático), nunca con la CA interna. Control Tower muestra `last_seen_at` y marca `sync_stale`
  cuando un carrito deja de comunicar; nunca inventa las ventas pendientes del teléfono.
- El certificado interno incluye la IP en `subjectAltName` (Caddy `tls internal` lo hace por `PUBLIC_HOST`); si se
  cambia la IP hay que regenerarlo y reinstalar la CA. Verificar la huella de la CA con el administrador antes de
  confiar en ella.

## Notas

- Los puertos HTTP `8081/8082/8000` siguen expuestos para pruebas y scripts; se pueden quitar del compose en producción.
- Detrás de Caddy, la API recibe `X-Forwarded-For` real, que es lo que usa el límite de intentos de login por IP.
- Con `STORAGE_PUBLIC_URL` vacío las fotos se sirven a través de la API (`/v1/evidence/{id}/file`), con permisos; MinIO no se expone.

## Síntoma en el teléfono: «Conexión no segura»

Si la PWA se abre por `http://IP:puerto` (no `https://`), el navegador no expone WebCrypto ni GPS: la cola cifrada no
puede guardar y **ninguna venta, aviso o conteo se registra**. Desde el change 004 la app lo detecta y muestra un aviso
rojo fijo arriba («Conexión no segura…») y, al intentar registrar algo, el mensaje «La app se abrió sin conexión
segura…» en lugar de un error técnico (`can't access property "importKey"…`). Solución: instalar/abrir la app desde la
URL `https://` de Caddy (con la CA interna instalada en el teléfono, §2) — nunca desde el puerto http del contenedor.
