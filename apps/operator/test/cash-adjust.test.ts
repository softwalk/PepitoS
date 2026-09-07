// Efectivo esperado local = fondo + depósitos − retiros/gastos/devoluciones + ventas en efectivo (misma fórmula que el servidor).
import { describe, expect, it } from 'vitest';
import { cashAdjustCents, computeLocalExpected } from '../src/offline/expected';
import type { SaleLocalRecord } from '../src/offline/db';

const sale = (cents: number, method: 'cash' | 'qr' = 'cash', status: SaleLocalRecord['status'] = 'pending'): SaleLocalRecord =>
  ({ idempotency_key: String(Math.random()), shift_local_id: 's', presentation_id: 'p', qty: 1, total_cents: cents, method, status, occurred_at: new Date().toISOString(), grams: 50 } as unknown as SaleLocalRecord);

describe('ajustes de caja', () => {
  it('suma fondo y depósitos, resta retiros/gastos/devoluciones', () => {
    expect(cashAdjustCents(null)).toBe(0);
    expect(cashAdjustCents({ opening_cents: 20000 })).toBe(20000);
    expect(cashAdjustCents({ opening_cents: 20000, cash_movements: [{ kind: 'expense', amount_cents: 3000 }, { kind: 'deposit', amount_cents: 1000 }, { kind: 'refund', amount_cents: 2500 }] })).toBe(15500);
  });
  it('entra en el esperado local sólo para efectivo', () => {
    const e = computeLocalExpected([sale(4500), sale(3500, 'qr'), sale(2500, 'cash', 'cancelled')], [], { opening_cents: 20000, cash_movements: [{ kind: 'withdrawal', amount_cents: 10000 }] });
    expect(e.cash_expected_cents).toBe(20000 - 10000 + 4500);
    expect(e.digital_total_cents).toBe(3500);
    expect(e.sales_count).toBe(2);
  });
});
