import { describe, expect, it } from 'vitest';
import type { SaleLocalRecord, WasteLocalRecord } from '../src/offline/db';
import { computeLocalExpected, computeLocalProductExpected } from '../src/offline/expected';

function sale(over: Partial<SaleLocalRecord>): SaleLocalRecord {
  return {
    idempotency_key: Math.random().toString(36).slice(2),
    shift_local_id: 'local:s',
    occurred_at: '2026-09-03T15:00:00Z',
    presentation_id: 'p50',
    presentation_name: 'Pepitas 50 g',
    grams: 50,
    qty: 1,
    flavor_id: null,
    unit_price_cents: 2500,
    total_cents: 2500,
    price_version_id: 'pv1',
    method: 'cash',
    status: 'pending',
    ...over,
  };
}

describe('efectivo esperado local', () => {
  it('suma solo ventas en efectivo vigentes (pendientes o sincronizadas)', () => {
    const sales = [
      sale({}),
      sale({ status: 'synced', total_cents: 3500, presentation_id: 'p75' }),
      sale({ method: 'qr', total_cents: 4500, presentation_id: 'p100' }),
      sale({ status: 'undone' }),
      sale({ status: 'cancelled' }),
      sale({ status: 'cancel_pending' }),
    ];
    const e = computeLocalExpected(sales);
    expect(e.sales_count).toBe(3);
    expect(e.sales_total_cents).toBe(2500 + 3500 + 4500);
    expect(e.cash_expected_cents).toBe(6000);
    expect(e.digital_total_cents).toBe(4500);
  });

  it('cuenta merma en unidades', () => {
    const waste: WasteLocalRecord[] = [
      { idempotency_key: 'w1', shift_local_id: 'local:s', presentation_id: 'p50', qty: 2, reason_code: 'spill', occurred_at: '2026-09-03T15:00:00Z' },
      { idempotency_key: 'w2', shift_local_id: 'local:s', presentation_id: 'p75', qty: 1, reason_code: 'quality', occurred_at: '2026-09-03T15:00:00Z' },
    ];
    expect(computeLocalExpected([], waste).waste_units).toBe(3);
  });

  it('producto esperado: parte del cache del servidor y descuenta lo posterior', () => {
    const cached = { fetched_at: '2026-09-03T14:00:00Z', product_expected: { p50: 10, p75: 5 } };
    const sales = [
      sale({ occurred_at: '2026-09-03T13:00:00Z' }), // anterior al cache: ya contado por el servidor
      sale({ occurred_at: '2026-09-03T15:00:00Z' }),
      sale({ occurred_at: '2026-09-03T15:01:00Z', presentation_id: 'p75', status: 'undone' }),
    ];
    const waste: WasteLocalRecord[] = [{ idempotency_key: 'w', shift_local_id: 'local:s', presentation_id: 'p75', qty: 2, reason_code: 'spill', occurred_at: '2026-09-03T16:00:00Z' }];
    expect(computeLocalProductExpected(cached, sales, waste)).toEqual({ p50: 9, p75: 3 });
  });

  it('sin cache no baja de cero', () => {
    expect(computeLocalProductExpected(null, [sale({})])).toEqual({ p50: 0 });
  });
});
