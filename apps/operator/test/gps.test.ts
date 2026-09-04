// GPS: diagnóstico del motivo (sin soporte, contexto inseguro, permiso denegado, timeout con reintento en baja precisión).
import { afterEach, describe, expect, it, vi } from 'vitest';
import { getPositionDetailed, gpsStatus, recentPosition } from '../src/offline/gps';

type Success = (p: GeolocationPosition) => void;
type Failure = (e: GeolocationPositionError) => void;

function mockGeo(impl: (ok: Success, fail: Failure, opts?: PositionOptions) => void) {
  Object.defineProperty(globalThis.navigator, 'geolocation', { value: { getCurrentPosition: vi.fn(impl), watchPosition: vi.fn(), clearWatch: vi.fn() }, configurable: true });
}
const pos = (acc: number): GeolocationPosition => ({ coords: { latitude: 19.42, longitude: -99.16, accuracy: acc, altitude: null, altitudeAccuracy: null, heading: null, speed: null, toJSON: () => ({}) }, timestamp: Date.now(), toJSON: () => ({}) }) as unknown as GeolocationPosition;
const err = (code: number): GeolocationPositionError => ({ code, message: '', PERMISSION_DENIED: 1, POSITION_UNAVAILABLE: 2, TIMEOUT: 3 }) as GeolocationPositionError;

describe('getPositionDetailed', () => {
  afterEach(() => {
    delete (globalThis.navigator as { geolocation?: unknown }).geolocation;
    delete (globalThis as { window?: unknown }).window;
  });

  it('sin geolocation → unsupported', async () => {
    expect(await getPositionDetailed(100)).toEqual({ gps: null, reason: 'unsupported' });
  });

  it('http (contexto inseguro) → insecure, sin llamar al navegador', async () => {
    const spy = vi.fn();
    mockGeo(spy);
    Object.defineProperty(globalThis, 'window', { value: { isSecureContext: false }, configurable: true });
    const r = await getPositionDetailed(100);
    expect(r.reason).toBe('insecure');
    expect(spy).not.toHaveBeenCalled();
  });

  it('permiso denegado → denied y estado observable', async () => {
    mockGeo((_ok, fail) => fail(err(1)));
    const r = await getPositionDetailed(100);
    expect(r.reason).toBe('denied');
    expect(gpsStatus().permission).toBe('denied');
  });

  it('timeout en alta precisión → reintenta en baja precisión y devuelve el fix', async () => {
    mockGeo((ok, fail, opts) => (opts?.enableHighAccuracy ? fail(err(3)) : ok(pos(800))));
    const r = await getPositionDetailed(200);
    expect(r.gps?.accuracy_m).toBe(800);
    expect(r.reason).toBeNull();
    expect(recentPosition()?.lat).toBe(19.42);
  });
});
