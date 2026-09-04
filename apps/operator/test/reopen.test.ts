// Turno reabierto por el administrador: la PWA lo adopta con pings GPS, esperado cacheado y ventas previas del servidor.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../src/offline/gps', () => ({ startGpsPings: vi.fn(), stopGpsPings: vi.fn(), getPosition: vi.fn(async () => null) }));

import { api } from '../src/api/client';
import { resetDBForTests, salesLocalStore, shiftStore } from '../src/offline/db';
import { startGpsPings } from '../src/offline/gps';
import { getExpected, refreshAssignment } from '../src/state/actions';
import type { AssignmentResponse, ShiftExpected } from '../src/types';

const ASSIGNMENT: AssignmentResponse = {
  assignment: { id: 'a1', shift_date: '2026-09-04', planned_start: '2026-09-04T14:00:00Z', planned_end: '2026-09-05T00:00:00Z', status: 'started', point: { id: 'p1', name: 'Metro Insurgentes', lat: 0, lng: 0 }, cart: { id: 'c1', code: 'C-001' } } as AssignmentResponse['assignment'],
  active_shift: { id: 'srv-shift-1', opened_at: '2026-09-04T15:00:00Z', status: 'open', ready: true, exceptions: [] },
  catalog: { presentations: [], flavors: [], waste_reasons: [], help_categories: [], checklist_open: [], checklist_close: [], price_version_id: 'pv1' } as unknown as AssignmentResponse['catalog'],
  config: { gps_interval_seconds: 120 } as AssignmentResponse['config'],
};
const EXPECTED: ShiftExpected = { sales_count: 2, sales_total_cents: 7000, cash_expected_cents: 7000, digital_total_cents: 0, product_expected: { pres1: -2 }, waste_units: 0 } as ShiftExpected;

describe('turno reabierto por el administrador', () => {
  beforeEach(async () => {
    await resetDBForTests();
    vi.spyOn(api, 'myAssignment').mockResolvedValue(ASSIGNMENT);
    vi.spyOn(api, 'shiftExpected').mockResolvedValue(EXPECTED);
    vi.mocked(startGpsPings).mockClear();
  });
  afterEach(() => vi.restoreAllMocks());

  it('adopta el turno del servidor sin turno local: GPS + esperado + ventas previas', async () => {
    await refreshAssignment();
    await new Promise((r) => setTimeout(r, 10)); // cacheExpected es fire-and-forget
    const st = await shiftStore.get();
    expect(st?.status).toBe('open');
    expect(st?.server_id).toBe('srv-shift-1');
    expect(startGpsPings).toHaveBeenCalledWith('srv-shift-1', 120);
    expect(st?.server_sales).toEqual({ count: 2, total_cents: 7000, cash_expected_cents: 7000, digital_total_cents: 0 });
    expect(st?.last_expected?.product_expected).toEqual({ pres1: -2 });
  });

  it('sin red, el esperado suma la base del servidor a lo local', async () => {
    await refreshAssignment();
    await new Promise((r) => setTimeout(r, 10));
    Object.defineProperty(navigator, 'onLine', { value: false, configurable: true });
    try {
      const e = await getExpected();
      expect(e.source).toBe('local');
      expect(e.cash_expected_cents).toBe(7000);
      expect(e.sales_count).toBe(2);
    } finally {
      Object.defineProperty(navigator, 'onLine', { value: true, configurable: true });
    }
  });

  it('si el turno local es el mismo y quedó "closed" (pantalla de resultado), lo reabre conservando local_id y ventas', async () => {
    await shiftStore.set({ local_id: 'local-1', server_id: 'srv-shift-1', assignment_id: 'a1', point_name: 'X', cart_code: 'C', opened_at: '2026-09-04T15:00:00Z', status: 'closed', ready: true, exceptions: [], last_expected: null, close_result: { status: 'reconciled', cash_expected_cents: 0, cash_counted_cents: 0, difference_cents: 0 } as never });
    await salesLocalStore.put({ idempotency_key: 'k1', shift_local_id: 'local-1', status: 'synced', total_cents: 2500, grams: 50, method: 'cash', occurred_at: '2026-09-04T15:30:00Z' } as never);
    await refreshAssignment();
    const st = await shiftStore.get();
    expect(st?.status).toBe('open');
    expect(st?.local_id).toBe('local-1');
    expect(st?.close_result).toBeNull();
    expect(st?.server_sales ?? null).toBeNull();
    expect((await salesLocalStore.byShift('local-1')).length).toBe(1);
  });
});
