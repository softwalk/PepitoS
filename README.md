# PEPITO OS — Sistema operativo de la red PEPITO (MVP v1.0)

Implementación completa del **PRD v2 Simplificado IA-First** y del **OpenSpec v2** (`version3/Sistema`).
Principio rector: *el operador vende y cuida el puesto; el sistema registra; las reglas vigilan; el supervisor resuelve
excepciones; Dirección decide.*

| Componente | Carpeta | Stack | Puerto dev |
|---|---|---|---|
| API + motor de reglas + seeds | `apps/api` | Python 3.11 · FastAPI · SQLAlchemy 2 · Alembic · PostgreSQL 16 · APScheduler | 8000 |
| PWA Operador (ABRIR · VENDER · AYUDA · CERRAR, offline-first) | `apps/operator` | React 18 · Vite · TS · vite-plugin-pwa · IndexedDB cifrado | 5173 (dev) / 4173 (preview) |
| Backoffice + Supervisor (Control Tower) | `apps/backoffice` | React 18 · Vite · TS · leaflet · recharts | 5174 / 4174 |
| Infra | `docker-compose.yml`, `infra/`, Dockerfiles | Docker Compose · nginx · Caddy (HTTPS) · MinIO (evidencias) | 8081/8082 HTTP · 8443/8444/8445 HTTPS |
| Documentación | `docs/` | Contratos, arquitectura, trazabilidad con el OpenSpec, runbook, revisión prepublicación | — |

## Arranque rápido (Docker)

```bash
cp .env.example .env            # ajusta JWT_SECRET y POSTGRES_PASSWORD
docker compose up --build -d    # db + minio + api (migra y siembra) + operador :8081 + backoffice :8082 + caddy https :8443/:8444/:8445
# PWA desde un teléfono: usa https://<PUBLIC_HOST>:8443 e instala la CA (docs/HTTPS.md)
```

## Arranque en desarrollo (sin Docker)

```bash
# 1. API (requiere PostgreSQL 16; el script levanta uno local en :5433)
cd apps/api && cp .env.example .env && make install && make up     # db + migrate + seed + uvicorn :8000
make test                                                           # 28 pruebas

# 2. PWA Operador
cd apps/operator && npm ci && npm run dev                           # http://localhost:5173 (proxy /v1 → :8000)
npm test -- --run && npm run build

# 3. Backoffice
cd apps/backoffice && npm ci && npm run dev                         # http://localhost:5174
npm test -- --run && npm run build
```

## Usuarios demo (seed)

| Usuario | Contraseña | Rol | Entra a |
|---|---|---|---|
| `op1` `op2` `op3` | `op123` | operador | PWA Operador (asignación de hoy en Metro Insurgentes / Parque México / Alameda Central) |
| `sup1` | `sup123` | supervisor zona Centro | Backoffice → *Supervisor* (vista móvil) |
| `ops` | `ops123` | operaciones | Backoffice → Control Tower |
| `finanzas` | `fin123` | finanzas | Backoffice → reportes/aprobaciones |
| `admin` | `admin123` | admin | Todo + `/admin` |

Precios demo (versión vigente, configurable en `/admin`): 50 g $25 · 75 g $35 · 100 g $45. Meta diaria: 60 ventas / $2,340 por punto.

## Qué cubre el MVP (PRD §13)

Login/turno · ABRIR (GPS + checklist Sí/No) · VENDER (1–2 toques, efectivo/QR/tarjeta, sabor opcional, deshacer) · MERMA ·
NECESITO AYUDA (6 categorías, seguridad prioritaria, clasificación IA de "otro") · CERRAR ("Debes tener $X" → "Tengo $__" →
conteo → checklist) · offline-first con cola cifrada, idempotencia y recuperación tras reinicio · caja conciliada
POS × efectivo × digital × inventario · inventario reconstruible desde movimientos · lotes con bloqueo · 11 reglas
determinísticas configurables (no apertura, geocerca, ventas bajas, merma, caja, inventario, batería, cancelaciones,
sin sincronizar, mantenimiento, stock) con auto-resolución de condiciones transitorias · casos URGENTE/REVISAR/NORMAL con
prioridad · ruta del supervisor · auditorías con arqueo y correctivos · Control Tower (mapa, KPIs con semáforo PRD §15,
briefing de dirección) · reportes diarios · aprobaciones con segregación · RBAC de mínimo privilegio · revocación de
dispositivos · audit log de todo cambio crítico · outbox de eventos de dominio.

Lee **`docs/REVISION_PREPUBLICACION.md`** antes de publicar: contiene lo que corregiría o completaría primero.
