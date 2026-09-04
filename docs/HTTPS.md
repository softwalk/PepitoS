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

## Notas

- Los puertos HTTP `8081/8082/8000` siguen expuestos para pruebas y scripts; se pueden quitar del compose en producción.
- Detrás de Caddy, la API recibe `X-Forwarded-For` real, que es lo que usa el límite de intentos de login por IP.
- Con `STORAGE_PUBLIC_URL` vacío las fotos se sirven a través de la API (`/v1/evidence/{id}/file`), con permisos; MinIO no se expone.
