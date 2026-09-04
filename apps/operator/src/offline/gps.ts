// GPS: lectura puntual con timeout (fallback null) y pings periódicos mientras el turno está abierto.
import type { GPS } from '../types';
import { enqueue } from './queue';
import { trigger } from './sync';
import { readBattery } from './battery';

export function getPosition(timeoutMs = 8000): Promise<GPS | null> {
  if (typeof navigator === 'undefined' || !('geolocation' in navigator)) return Promise.resolve(null);
  return new Promise((resolve) => {
    let done = false;
    const finish = (v: GPS | null) => {
      if (!done) {
        done = true;
        resolve(v);
      }
    };
    const t = setTimeout(() => finish(null), timeoutMs);
    try {
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          clearTimeout(t);
          finish({
            lat: pos.coords.latitude,
            lng: pos.coords.longitude,
            accuracy_m: pos.coords.accuracy ?? null,
            mocked: false,
            at: new Date(pos.timestamp || Date.now()).toISOString(),
          });
        },
        () => {
          clearTimeout(t);
          finish(null);
        },
        { enableHighAccuracy: true, timeout: timeoutMs, maximumAge: 15000 },
      );
    } catch {
      clearTimeout(t);
      finish(null);
    }
  });
}

let pingTimer: ReturnType<typeof setInterval> | null = null;
let currentShift: string | null = null;

/** Inicia pings cada `intervalSeconds` para el turno indicado (id local o del servidor). */
export function startGpsPings(shiftId: string, intervalSeconds: number) {
  if (pingTimer && currentShift === shiftId) return;
  stopGpsPings();
  currentShift = shiftId;
  const tick = async () => {
    const gps = await getPosition(10000);
    if (!gps || !currentShift) return;
    const battery = await readBattery();
    await enqueue('gps_ping', {
      pings: [{ shift_id: currentShift, at: gps.at, lat: gps.lat, lng: gps.lng, accuracy_m: gps.accuracy_m, mocked: gps.mocked, battery_pct: battery?.pct ?? null }],
    });
    trigger();
  };
  pingTimer = setInterval(() => void tick(), Math.max(30, intervalSeconds) * 1000);
  void tick();
}

export function stopGpsPings() {
  if (pingTimer) clearInterval(pingTimer);
  pingTimer = null;
  currentShift = null;
}
