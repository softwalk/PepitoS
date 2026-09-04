// GPS: lectura puntual con diagnóstico y reintento, pings periódicos con `watchPosition` mientras el turno está abierto,
// y un estado observable (para la barra superior y Ajustes) que explica POR QUÉ no hay ubicación.
//
// Causas típicas en el teléfono, en orden de frecuencia:
//  - insecure:   la app se abrió por http:// (no localhost) o con un certificado no confiable → el navegador bloquea
//                geolocation sin siquiera preguntar. Solución: abrir por https y con la CA instalada (docs/HTTPS.md).
//  - denied:     el operador pulsó "Bloquear" o la app instalada no tiene permiso de ubicación en Android/iOS.
//  - timeout:    sin fix (interior, GPS apagado, modo ahorro); se reintenta con baja precisión.
//  - unavailable: el sistema no pudo obtener posición (ubicación desactivada en el teléfono).
import type { GPS } from '../types';
import { enqueue } from './queue';
import { trigger } from './sync';
import { readBattery } from './battery';

export type GpsReason = 'unsupported' | 'insecure' | 'denied' | 'unavailable' | 'timeout';
export interface GpsStatus {
  /** Último fix conocido (aunque sea de hace unos minutos). */
  last: GPS | null;
  /** Motivo del último fallo, o null si el último intento tuvo éxito. */
  reason: GpsReason | null;
  /** Momento del último intento (ISO). */
  tried_at: string | null;
  /** Permiso según Permissions API cuando está disponible. */
  permission: 'granted' | 'denied' | 'prompt' | 'unknown';
}

const status: GpsStatus = { last: null, reason: null, tried_at: null, permission: 'unknown' };
type Listener = (s: GpsStatus) => void;
const listeners = new Set<Listener>();
function emit() {
  for (const l of listeners) l({ ...status });
}
export function subscribeGps(l: Listener): () => void {
  listeners.add(l);
  l({ ...status });
  return () => listeners.delete(l);
}
export function gpsStatus(): GpsStatus {
  return { ...status };
}

/** Texto para el operador según el motivo (corto, accionable). */
export const GPS_REASON_TEXT: Record<GpsReason, { title: string; action: string }> = {
  unsupported: { title: 'Este navegador no tiene GPS', action: 'Usa Chrome o Safari actualizado.' },
  insecure: { title: 'La app no está en modo seguro (https)', action: 'Ábrela desde la dirección https:// e instala el certificado (pide ayuda al supervisor).' },
  denied: { title: 'Ubicación bloqueada para esta app', action: 'Ajustes del teléfono → Apps → Chrome/Safari → Permisos → Ubicación: Permitir.' },
  unavailable: { title: 'El teléfono no entrega ubicación', action: 'Activa la Ubicación del teléfono (barra de ajustes rápidos) y vuelve a intentar.' },
  timeout: { title: 'Sin señal GPS por ahora', action: 'Sal a cielo abierto o acércate a una ventana; se reintenta solo.' },
};

export function isSecureForGeolocation(): boolean {
  if (typeof window === 'undefined') return true;
  // `isSecureContext` cubre https, localhost y file. Con certificado inválido "aceptado" el navegador NO expone GPS.
  return window.isSecureContext !== false;
}

async function readPermission(): Promise<GpsStatus['permission']> {
  try {
    if (typeof navigator === 'undefined' || !navigator.permissions?.query) return 'unknown';
    const p = await navigator.permissions.query({ name: 'geolocation' as PermissionName });
    return p.state === 'granted' || p.state === 'denied' || p.state === 'prompt' ? p.state : 'unknown';
  } catch {
    return 'unknown';
  }
}

function toGPS(pos: GeolocationPosition): GPS {
  return {
    lat: pos.coords.latitude,
    lng: pos.coords.longitude,
    accuracy_m: pos.coords.accuracy ?? null,
    mocked: false,
    at: new Date(pos.timestamp || Date.now()).toISOString(),
  };
}

function reasonFromError(e: GeolocationPositionError | undefined): GpsReason {
  if (!e) return 'unavailable';
  if (e.code === 1) return isSecureForGeolocation() ? 'denied' : 'insecure';
  if (e.code === 3) return 'timeout';
  return 'unavailable';
}

function once(opts: PositionOptions): Promise<{ gps: GPS | null; reason: GpsReason | null }> {
  return new Promise((resolve) => {
    let done = false;
    const finish = (v: { gps: GPS | null; reason: GpsReason | null }) => {
      if (!done) {
        done = true;
        resolve(v);
      }
    };
    // Timeout propio por si el navegador no llama nunca al callback (ocurre en algunos WebViews).
    const t = setTimeout(() => finish({ gps: null, reason: 'timeout' }), (opts.timeout ?? 8000) + 500);
    try {
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          clearTimeout(t);
          finish({ gps: toGPS(pos), reason: null });
        },
        (err) => {
          clearTimeout(t);
          finish({ gps: null, reason: reasonFromError(err) });
        },
        opts,
      );
    } catch {
      clearTimeout(t);
      finish({ gps: null, reason: 'unavailable' });
    }
  });
}

/**
 * Lectura con diagnóstico. Estrategia: alta precisión con `timeoutMs`; si expira o no hay proveedor, reintento en baja
 * precisión aceptando un fix de hasta 2 min (red/celdas). Nunca lanza: devuelve `{gps:null, reason}`.
 */
export async function getPositionDetailed(timeoutMs = 8000): Promise<{ gps: GPS | null; reason: GpsReason | null }> {
  status.tried_at = new Date().toISOString();
  if (typeof navigator === 'undefined' || !('geolocation' in navigator)) {
    status.reason = 'unsupported';
    emit();
    return { gps: null, reason: 'unsupported' };
  }
  if (!isSecureForGeolocation()) {
    status.reason = 'insecure';
    emit();
    return { gps: null, reason: 'insecure' };
  }
  status.permission = await readPermission();
  if (status.permission === 'denied') {
    status.reason = 'denied';
    emit();
    return { gps: null, reason: 'denied' };
  }
  let r = await once({ enableHighAccuracy: true, timeout: timeoutMs, maximumAge: 15000 });
  if (!r.gps && (r.reason === 'timeout' || r.reason === 'unavailable')) {
    r = await once({ enableHighAccuracy: false, timeout: Math.max(3000, Math.floor(timeoutMs / 2)), maximumAge: 120000 });
  }
  if (r.gps) {
    status.last = r.gps;
    status.reason = null;
    status.permission = 'granted';
  } else {
    status.reason = r.reason;
    if (r.reason === 'denied') status.permission = 'denied';
  }
  emit();
  return r;
}

/** Compatibilidad: sólo la posición (null si no hay). */
export async function getPosition(timeoutMs = 8000): Promise<GPS | null> {
  return (await getPositionDetailed(timeoutMs)).gps;
}

/** Último fix si es reciente (para no bloquear una venta esperando al GPS). */
export function recentPosition(maxAgeMs = 3 * 60_000): GPS | null {
  if (!status.last) return null;
  return Date.now() - new Date(status.last.at).getTime() <= maxAgeMs ? status.last : null;
}

// ---------- pings mientras el turno está abierto ----------
let pingTimer: ReturnType<typeof setInterval> | null = null;
let watchId: number | null = null;
let currentShift: string | null = null;
let lastSentAt = 0;
let intervalMs = 120_000;

async function sendPing(gps: GPS) {
  if (!currentShift) return;
  lastSentAt = Date.now();
  const battery = await readBattery();
  await enqueue('gps_ping', {
    pings: [{ shift_id: currentShift, at: gps.at, lat: gps.lat, lng: gps.lng, accuracy_m: gps.accuracy_m, mocked: gps.mocked, battery_pct: battery?.pct ?? null }],
  });
  trigger();
}

/**
 * Inicia pings cada `intervalSeconds` para el turno indicado (id local o del servidor).
 * Usa `watchPosition` (mantiene el GPS "caliente" en Android y responde mejor que lecturas sueltas) y un temporizador
 * de respaldo que fuerza una lectura si el watch no ha entregado nada en todo el intervalo.
 */
export function startGpsPings(shiftId: string, intervalSeconds: number) {
  if ((pingTimer || watchId !== null) && currentShift === shiftId) return;
  stopGpsPings();
  currentShift = shiftId;
  intervalMs = Math.max(30, intervalSeconds) * 1000;
  lastSentAt = 0;

  if (typeof navigator !== 'undefined' && 'geolocation' in navigator && isSecureForGeolocation()) {
    try {
      watchId = navigator.geolocation.watchPosition(
        (pos) => {
          const gps = toGPS(pos);
          status.last = gps;
          status.reason = null;
          status.permission = 'granted';
          emit();
          if (Date.now() - lastSentAt >= intervalMs) void sendPing(gps);
        },
        (err) => {
          status.reason = reasonFromError(err);
          if (status.reason === 'denied') status.permission = 'denied';
          status.tried_at = new Date().toISOString();
          emit();
        },
        { enableHighAccuracy: true, maximumAge: 15000, timeout: 20000 },
      );
    } catch {
      watchId = null;
    }
  }

  const tick = async () => {
    if (!currentShift) return;
    if (Date.now() - lastSentAt < intervalMs) return; // el watch ya envió
    const r = await getPositionDetailed(10000);
    if (r.gps && currentShift) await sendPing(r.gps);
  };
  pingTimer = setInterval(() => void tick(), intervalMs);
  void tick();
}

export function stopGpsPings() {
  if (pingTimer) clearInterval(pingTimer);
  pingTimer = null;
  if (watchId !== null && typeof navigator !== 'undefined' && 'geolocation' in navigator) {
    try {
      navigator.geolocation.clearWatch(watchId);
    } catch {
      /* nada */
    }
  }
  watchId = null;
  currentShift = null;
}
