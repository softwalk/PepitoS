// Apertura con foto de muestreo: el comando shift_open en la cola lleva `photos` cuando config.require_open_photo,
// viaja sin red dentro de la cola cifrada y se envía tal cual en /v1/sync/batch. La config cacheada alimenta gps/cancel.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { setAuthSession } from '../src/api/client';
import { assignmentStore, catalogStore, resetDBForTests, sessionStore, shiftStore } from '../src/offline/db';
import { listAll } from '../src/offline/queue';
import { cancelWindowMs, closeShift, gpsIntervalSeconds, openShift } from '../src/state/actions';
import type { AssignmentResponse, OperatorConfig } from '../src/types';

vi.mock('../src/offline/gps', () => ({
  getPosition: async () => null,
  startGpsPings: vi.fn(),
  stopGpsPings: vi.fn(),
}));

const CONFIG: OperatorConfig = {
  cash_difference_threshold_cents: 2000,
  cash_difference_severe_cents: 10000,
  cancel_window_minutes: 7,
  gps_interval_seconds: 45,
  photo_sampling_pct: 100,
  require_open_photo: true,
  evidence_max_bytes: 3 * 1024 * 1024,
};

function assignment(config: OperatorConfig): AssignmentResponse {
  return {
    assignment: {
      id: 'a1',
      shift_date: '2026-09-04',
      planned_start: '2026-09-04T14:00:00Z',
      planned_end: '2026-09-04T22:00:00Z',
      point: { id: 'p1', name: 'Metro', address: null, lat: 0, lng: 0, geofence_radius_m: 100 },
      cart: { id: 'c1', code: 'C-001' },
    },
    active_shift: null,
    catalog: { presentations: [], flavors: [], price_version_id: 'pv', waste_reasons: [], help_categories: [], checklist_open: [], checklist_close: [] },
    config,
  };
}

const CHECKLIST = { cart_secure: true, battery_ok: true, product_ok: true, clean_ok: true, pos_ok: true };

beforeEach(async () => {
  await resetDBForTests();
  await sessionStore.set({ access_token: 't', expires_at: '2030-01-01T00:00:00Z', refresh_token: 'r', refresh_expires_at: '2030-01-01T00:00:00Z', device_id: 'dev', user: { id: 'u', name: 'Op', role: 'operator', zone_id: null } });
  setAuthSession({ access_token: 't', expires_at: '2030-01-01T00:00:00Z', refresh_token: 'r', refresh_expires_at: '2030-01-01T00:00:00Z', device_id: 'dev' });
  const a = assignment(CONFIG);
  await assignmentStore.set(a);
  await catalogStore.set(a.catalog, a.config);
});
afterEach(() => {
  vi.unstubAllGlobals();
  setAuthSession(null);
});

/** Sin red: fetch falla y el comando se queda en la cola. */
function offline() {
  vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('Failed to fetch'); }));
}

describe('apertura con foto (require_open_photo)', () => {
  it('encola shift_open con photos:[{key:"puesto", base64}] y sobrevive sin red', async () => {
    offline();
    const b64 = Buffer.alloc(2048, 0x7f).toString('base64');
    const st = await openShift(CHECKLIST, null, [{ key: 'puesto', base64: b64 }]);
    expect(st.status).toBe('open_pending');
    const cmds = await listAll();
    const open = cmds.find((c) => c.type === 'shift_open');
    expect(open).toBeDefined();
    expect(open!.payload).toMatchObject({ assignment_id: 'a1', checklist: CHECKLIST, photos: [{ key: 'puesto', base64: b64 }] });
  });

  it('si la cámara falla se abre igual con photos: []', async () => {
    offline();
    const st = await openShift(CHECKLIST, null, []);
    expect(st.status).toBe('open_pending');
    const open = (await listAll()).find((c) => c.type === 'shift_open')!;
    expect(open.payload.photos).toEqual([]);
  });

  it('envía las fotos tal cual en /v1/sync/batch al volver la red', async () => {
    const bodies: Record<string, unknown>[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init: RequestInit) => {
        const body = JSON.parse(String(init.body));
        bodies.push(body);
        if (String(url).endsWith('/v1/sync/batch')) {
          const results = (body.commands as { idempotency_key: string }[]).map((c) => ({ idempotency_key: c.idempotency_key, status: 'ok', result: { shift_id: 'srv-1', ready: true, exceptions: [] } }));
          return new Response(JSON.stringify({ results }), { status: 200, headers: { 'Content-Type': 'application/json' } });
        }
        return new Response(JSON.stringify({ sales_count: 0, sales_total_cents: 0, cash_expected_cents: 0, digital_total_cents: 0, product_expected: {}, waste_units: 0 }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }),
    );
    const st = await openShift(CHECKLIST, null, [{ key: 'puesto', base64: 'AAAA' }]);
    expect(st.status).toBe('open');
    expect(st.server_id).toBe('srv-1');
    const batch = bodies.find((b) => Array.isArray(b.commands)) as { commands: { type: string; payload: Record<string, unknown> }[] };
    const cmd = batch.commands.find((c) => c.type === 'shift_open')!;
    expect(cmd.payload.photos).toEqual([{ key: 'puesto', base64: 'AAAA' }]);
  });

  it('el cierre también lleva photos', async () => {
    offline();
    await shiftStore.set({ local_id: 'local:1', server_id: 'srv-1', assignment_id: 'a1', point_name: 'Metro', cart_code: 'C-001', opened_at: new Date().toISOString(), status: 'open', ready: true, exceptions: [], last_expected: null, close_result: null });
    await closeShift({ cash_counted_cents: 0, product_counts: {}, checklist: { off_ok: true, clean_ok: true, secured_ok: true, stored_ok: true, charging_ok: true }, gps: null, expected_cash_cents: 0, photos: [{ key: 'puesto', base64: 'BBBB' }] });
    const close = (await listAll()).find((c) => c.type === 'shift_close')!;
    expect(close.payload.photos).toEqual([{ key: 'puesto', base64: 'BBBB' }]);
  });
});

describe('config cacheada en IndexedDB', () => {
  it('gps_interval_seconds y cancel_window_minutes salen de la config, con fallback si no hay', async () => {
    expect(await gpsIntervalSeconds()).toBe(45);
    expect(await cancelWindowMs()).toBe(7 * 60_000);
    await resetDBForTests();
    expect(await gpsIntervalSeconds()).toBe(120);
    expect(await cancelWindowMs()).toBe(5 * 60_000);
  });
});
