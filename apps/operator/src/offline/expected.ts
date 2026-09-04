// Cálculo local de lo esperado al cierre (sin red): efectivo desde ventas locales, producto desde el último "esperado" cacheado.
import type { SaleLocalRecord, WasteLocalRecord } from './db';

export interface LocalExpected {
  sales_count: number;
  sales_total_cents: number;
  cash_expected_cents: number;
  digital_total_cents: number;
  waste_units: number;
}

/** Ventas que cuentan: pendientes o sincronizadas (no deshechas ni canceladas). */
export function countsAsSale(s: SaleLocalRecord): boolean {
  return s.status === 'pending' || s.status === 'synced' || s.status === 'failed';
}

export function computeLocalExpected(sales: SaleLocalRecord[], waste: WasteLocalRecord[] = []): LocalExpected {
  let sales_count = 0;
  let sales_total = 0;
  let cash = 0;
  let digital = 0;
  for (const s of sales) {
    if (!countsAsSale(s)) continue;
    sales_count += 1;
    sales_total += s.total_cents;
    if (s.method === 'cash') cash += s.total_cents;
    else digital += s.total_cents;
  }
  const waste_units = waste.reduce((a, w) => a + w.qty, 0);
  return { sales_count, sales_total_cents: sales_total, cash_expected_cents: cash, digital_total_cents: digital, waste_units };
}

/**
 * Producto esperado por presentación: parte del último esperado conocido del servidor y descuenta
 * las ventas/mermas locales registradas después de esa fecha.
 */
export function computeLocalProductExpected(
  cached: { fetched_at: string; product_expected: Record<string, number> } | null | undefined,
  sales: SaleLocalRecord[],
  waste: WasteLocalRecord[] = [],
): Record<string, number> {
  const out: Record<string, number> = { ...(cached?.product_expected ?? {}) };
  const since = cached ? Date.parse(cached.fetched_at) : -Infinity;
  for (const s of sales) {
    if (!countsAsSale(s) || Date.parse(s.occurred_at) <= since) continue;
    out[s.presentation_id] = (out[s.presentation_id] ?? 0) - s.qty;
  }
  for (const w of waste) {
    if (Date.parse(w.occurred_at) <= since) continue;
    out[w.presentation_id] = (out[w.presentation_id] ?? 0) - w.qty;
  }
  for (const k of Object.keys(out)) if (out[k] < 0) out[k] = 0;
  return out;
}
