// Acciones de dominio: UI optimista → IndexedDB → cola → sync. Nunca exponen "reintentar API" al operador.
import { v4 as uuidv4 } from 'uuid';
import { api, ApiError, NetworkError, setAuthToken } from '../api/client';
import {
  assignmentStore,
  catalogStore,
  salesLocalStore,
  sessionStore,
  shiftStore,
  wasteLocalStore,
  wipeLocal,
  type SaleLocalRecord,
  type ShiftStateRecord,
} from '../offline/db';
import { computeLocalExpected, computeLocalProductExpected } from '../offline/expected';
import { getDeviceId, deviceName } from '../offline/device';
import { startGpsPings, stopGpsPings } from '../offline/gps';
import * as queue from '../offline/queue';
import { syncNow, trigger } from '../offline/sync';
import type {
  AssignmentResponse,
  CloseChecklist,
  GPS,
  HelpCategory,
  OpenChecklist,
  PaymentMethod,
  Presentation,
  ShiftException,
  ShiftExpected,
  WasteReason,
} from '../types';

export const UNDO_WINDOW_MS = 60_000;

const OPEN_MESSAGES: Record<string, { message: string; action: string }> = {
  cart_secure: { message: 'Carrito no asegurado', action: 'Revisa candado y resguardo' },
  battery_ok: { message: 'Batería insuficiente', action: 'Conecta el cargador o pide reemplazo' },
  product_ok: { message: 'Producto insuficiente o en mal estado', action: 'Pide reposición' },
  clean_ok: { message: 'Carrito sucio', action: 'Limpia antes de vender' },
  pos_ok: { message: 'Terminal POS no funciona', action: 'Cobra sólo en efectivo y pide ayuda' },
  out_of_geofence: { message: 'Estás fuera del punto asignado', action: 'Ve al punto o avisa al supervisor' },
  gps_mocked: { message: 'La ubicación parece simulada', action: 'Desactiva ubicación falsa' },
};
const CRITICAL_OPEN = new Set(['cart_secure', 'battery_ok', 'product_ok', 'pos_ok']);

export function suggestedAction(code: string): string {
  return OPEN_MESSAGES[code]?.action ?? 'Avisa al supervisor';
}

// ---------- sesión ----------
export async function login(username: string, password: string): Promise<AssignmentResponse> {
  const device_id = getDeviceId();
  const res = await api.login({ username, password, device_id, device_name: deviceName(), platform: 'pwa' });
  await sessionStore.set({
    access_token: res.access_token,
    expires_at: new Date(Date.now() + res.expires_in * 1000).toISOString(),
    device_id,
    user: res.user,
  });
  setAuthToken(res.access_token);
  const a = await refreshAssignment();
  return a;
}

/** Descarga asignación + catálogo + config y los guarda; adopta un turno abierto en el servidor si no hay uno local. */
export async function refreshAssignment(): Promise<AssignmentResponse> {
  const a = await api.myAssignment();
  await assignmentStore.set(a);
  await catalogStore.set(a.catalog, a.config);
  const local = await shiftStore.get();
  const pendingCmds = (await queue.counts()).pending;
  if (a.active_shift && pendingCmds === 0 && (!local || local.status === 'closed')) {
    await shiftStore.set({
      local_id: a.active_shift.id,
      server_id: a.active_shift.id,
      assignment_id: a.assignment?.id ?? '',
      point_name: a.assignment?.point.name ?? '',
      cart_code: a.assignment?.cart.code ?? '',
      opened_at: a.active_shift.opened_at,
      status: 'open',
      ready: a.active_shift.ready ?? true,
      exceptions: a.active_shift.exceptions ?? [],
      last_expected: null,
      close_result: null,
    });
    await salesLocalStore.clearShift(a.active_shift.id);
  } else if (local && local.server_id && !a.active_shift && pendingCmds === 0 && (local.status === 'open' || local.status === 'open_pending')) {
    // El servidor ya no tiene el turno abierto (lo cerró un supervisor, transferencia...): limpiar localmente.
    await clearShiftLocal(local);
  }
  return a;
}

export async function logout(opts: { force?: boolean } = {}): Promise<{ blocked: 'pending' } | { ok: true }> {
  const c = await queue.counts();
  if (c.pending + c.failed > 0 && !opts.force) return { blocked: 'pending' };
  try {
    await api.logout();
  } catch {
    /* sin red: el token expira solo */
  }
  stopGpsPings();
  await wipeLocal({ keepQueue: false });
  setAuthToken(null);
  return { ok: true };
}

// ---------- turno ----------
export function localOpenExceptions(checklist: OpenChecklist): ShiftException[] {
  return (Object.keys(checklist) as (keyof OpenChecklist)[])
    .filter((k) => !checklist[k])
    .map((k) => ({ code: k, message: OPEN_MESSAGES[k]?.message ?? k }));
}

export async function openShift(checklist: OpenChecklist, gps: GPS | null): Promise<ShiftStateRecord> {
  const a = (await assignmentStore.get())?.data;
  if (!a?.assignment) throw new ApiError('NO_ASSIGNMENT', 'No tienes asignación para hoy', 409);
  const cfg = (await catalogStore.get())?.config;
  const local_id = `local:${uuidv4()}`;
  const exceptions = localOpenExceptions(checklist);
  const ready = !exceptions.some((e) => CRITICAL_OPEN.has(e.code));
  const opened_at = new Date().toISOString();
  await shiftStore.set({
    local_id,
    server_id: null,
    assignment_id: a.assignment.id,
    point_name: a.assignment.point.name,
    cart_code: a.assignment.cart.code,
    opened_at,
    status: 'open_pending',
    ready,
    exceptions,
    last_expected: null,
    close_result: null,
  });
  await queue.enqueue('shift_open', { assignment_id: a.assignment.id, opened_at, checklist, gps });
  // Si hay red, esperamos la confirmación para mostrar excepciones del servidor (geocerca, etc.).
  await syncNow();
  const st = (await shiftStore.get())!;
  startGpsPings(st.server_id ?? st.local_id, cfg?.gps_interval_seconds ?? 120);
  // Cachear esperado inicial (producto) para el cierre offline.
  if (st.server_id) void cacheExpected(st.server_id);
  return st;
}

async function cacheExpected(serverId: string) {
  try {
    const e = await api.shiftExpected(serverId);
    await shiftStore.update({ last_expected: { fetched_at: new Date().toISOString(), cash_expected_cents: e.cash_expected_cents, product_expected: e.product_expected } });
  } catch {
    /* sin red */
  }
}

function currentShiftId(st: ShiftStateRecord): string {
  return st.server_id ?? st.local_id;
}

/** Reanuda pings y adopta un turno del servidor si hace falta (al arrancar la app). */
export async function resumeShift() {
  const st = await shiftStore.get();
  const cfg = (await catalogStore.get())?.config;
  if (st && (st.status === 'open' || st.status === 'open_pending')) {
    startGpsPings(currentShiftId(st), cfg?.gps_interval_seconds ?? 120);
  }
}

// ---------- ventas ----------
export async function recordSale(p: Presentation, method: PaymentMethod, flavor_id: string | null, gps: GPS | null = null): Promise<SaleLocalRecord> {
  const st = await shiftStore.get();
  if (!st || (st.status !== 'open' && st.status !== 'open_pending')) throw new ApiError('SHIFT_NOT_OPEN', 'Primero abre el puesto', 409);
  const cat = (await catalogStore.get())?.catalog;
  if (!cat?.price_version_id || p.price_cents == null) throw new ApiError('PRICE_VERSION_INVALID', 'No hay precios vigentes', 422);
  const key = uuidv4();
  const occurred_at = new Date().toISOString();
  const rec: SaleLocalRecord = {
    idempotency_key: key,
    shift_local_id: st.local_id,
    occurred_at,
    presentation_id: p.id,
    presentation_name: p.name,
    grams: p.grams,
    qty: 1,
    flavor_id,
    unit_price_cents: p.price_cents,
    total_cents: p.price_cents,
    price_version_id: cat.price_version_id,
    method,
    status: 'pending',
    sale_id: null,
    folio: null,
  };
  await salesLocalStore.put(rec);
  await queue.enqueue(
    'sale',
    {
      shift_id: currentShiftId(st),
      occurred_at,
      price_version_id: cat.price_version_id,
      lines: [{ presentation_id: p.id, qty: 1, flavor_id }],
      payments: [{ method, amount_cents: p.price_cents }],
      offline_created: !navigator.onLine,
      gps,
    },
    key,
  );
  trigger();
  return rec;
}

export type UndoOutcome = 'removed' | 'needs_reason' | 'too_late';

/** Deshacer: si aún está en cola (≤60 s) se elimina; si ya sincronizó hace falta motivo (cancelación). */
export async function undoSale(key: string): Promise<UndoOutcome> {
  const s = await salesLocalStore.get(key);
  if (!s) return 'too_late';
  const age = Date.now() - Date.parse(s.occurred_at);
  if (s.status === 'pending' && (await queue.has(key)) && age <= UNDO_WINDOW_MS) {
    await queue.remove(key);
    await salesLocalStore.update(key, { status: 'undone' });
    trigger();
    return 'removed';
  }
  if (s.status === 'synced' && s.sale_id) return 'needs_reason';
  if (s.status === 'pending') {
    // Sincronizó justo ahora: esperar a que el ACK actualice el registro.
    await syncNow();
    const again = await salesLocalStore.get(key);
    if (again?.status === 'synced' && again.sale_id) return 'needs_reason';
  }
  return 'too_late';
}

export async function cancelSale(key: string, reason_code: string): Promise<void> {
  const s = await salesLocalStore.get(key);
  if (!s?.sale_id) return;
  await salesLocalStore.update(key, { status: 'cancel_pending' });
  await queue.enqueue('sale_cancel', { sale_id: s.sale_id, reason_code });
  trigger();
}

// ---------- merma ----------
export async function recordWaste(presentation_id: string, qty: number, reason_code: WasteReason): Promise<void> {
  const st = await shiftStore.get();
  if (!st) throw new ApiError('SHIFT_NOT_OPEN', 'Primero abre el puesto', 409);
  const occurred_at = new Date().toISOString();
  const key = uuidv4();
  await wasteLocalStore.put({ idempotency_key: key, shift_local_id: st.local_id, presentation_id, qty, reason_code, occurred_at });
  await queue.enqueue('waste', { shift_id: currentShiftId(st), occurred_at, presentation_id, qty, reason_code }, key);
  trigger();
}

// ---------- ayuda ----------
export async function requestHelp(category: HelpCategory, opts: { note?: string; photo_base64?: string; gps?: GPS | null } = {}): Promise<void> {
  const st = await shiftStore.get();
  const payload: Record<string, unknown> = {
    shift_id: st && st.status !== 'closed' ? currentShiftId(st) : null,
    occurred_at: new Date().toISOString(),
    category,
    note: opts.note || undefined,
    photo_base64: opts.photo_base64 || undefined,
    gps: opts.gps ?? null,
  };
  await queue.enqueue('help_case', payload);
  trigger();
}

// ---------- cierre ----------
export interface ExpectedView {
  source: 'server' | 'local';
  cash_expected_cents: number;
  sales_count: number;
  sales_total_cents: number;
  digital_total_cents: number;
  product_expected: Record<string, number>;
}

export async function getExpected(): Promise<ExpectedView> {
  const st = await shiftStore.get();
  if (!st) throw new ApiError('SHIFT_NOT_OPEN', 'No hay turno', 409);
  const sales = await salesLocalStore.byShift(st.local_id);
  const waste = await wasteLocalStore.byShift(st.local_id);
  if (st.server_id && navigator.onLine) {
    try {
      // Empujar lo pendiente primero para que el servidor tenga todo.
      await syncNow();
      const e: ShiftExpected = await api.shiftExpected(st.server_id);
      await shiftStore.update({ last_expected: { fetched_at: new Date().toISOString(), cash_expected_cents: e.cash_expected_cents, product_expected: e.product_expected } });
      // Si aún quedan ventas sin enviar, súmalas al valor del servidor.
      const remaining = (await salesLocalStore.byShift(st.local_id)).filter((s) => s.status === 'pending');
      const extra = computeLocalExpected(remaining);
      return {
        source: 'server',
        cash_expected_cents: e.cash_expected_cents + extra.cash_expected_cents,
        sales_count: e.sales_count + extra.sales_count,
        sales_total_cents: e.sales_total_cents + extra.sales_total_cents,
        digital_total_cents: e.digital_total_cents + extra.digital_total_cents,
        product_expected: computeLocalProductExpected({ fetched_at: new Date().toISOString(), product_expected: e.product_expected }, remaining),
      };
    } catch (e) {
      if (!(e instanceof NetworkError) && !(e instanceof ApiError && e.status >= 500)) throw e;
    }
  }
  const local = computeLocalExpected(sales, waste);
  return {
    source: 'local',
    cash_expected_cents: local.cash_expected_cents,
    sales_count: local.sales_count,
    sales_total_cents: local.sales_total_cents,
    digital_total_cents: local.digital_total_cents,
    product_expected: computeLocalProductExpected(st.last_expected, sales, waste),
  };
}

export async function closeShift(input: {
  cash_counted_cents: number;
  product_counts: Record<string, number>;
  checklist: CloseChecklist;
  gps: GPS | null;
  expected_cash_cents: number;
}): Promise<NonNullable<ShiftStateRecord['close_result']>> {
  const st = await shiftStore.get();
  if (!st) throw new ApiError('SHIFT_NOT_OPEN', 'No hay turno', 409);
  const cfg = (await catalogStore.get())?.config;
  const threshold = cfg?.cash_difference_threshold_cents ?? 2000;
  const closed_at = new Date().toISOString();
  const diff = input.cash_counted_cents - input.expected_cash_cents;
  await shiftStore.update({
    status: 'closing',
    close_result: {
      status: 'pending',
      cash_expected_cents: input.expected_cash_cents,
      cash_counted_cents: input.cash_counted_cents,
      difference_cents: diff,
      closed_at,
    },
  });
  await queue.enqueue('shift_close', {
    shift_id: currentShiftId(st),
    closed_at,
    cash_counted_cents: input.cash_counted_cents,
    product_counts: input.product_counts,
    checklist: input.checklist,
    gps: input.gps,
  });
  stopGpsPings();
  await syncNow();
  const after = (await shiftStore.get())!;
  if (after.status === 'closed' && after.close_result) return after.close_result;
  // Sin red: resultado provisional con el umbral local; el servidor concilia al sincronizar.
  return { ...after.close_result!, status: Math.abs(diff) <= threshold ? 'reconciled' : 'difference' };
}

async function clearShiftLocal(st: ShiftStateRecord) {
  stopGpsPings();
  await salesLocalStore.clearShift(st.local_id);
  await wasteLocalStore.clearShift(st.local_id);
  await shiftStore.clear();
}

/** Tras ver el resultado del cierre: limpiar el turno local (si ya no hay comandos pendientes de ese turno). */
export async function finishClosedShift(): Promise<void> {
  const st = await shiftStore.get();
  if (st) {
    const c = await queue.counts();
    if (st.status === 'closed' && c.pending === 0) {
      await clearShiftLocal(st);
    }
    // Si sigue "closing" (sin red), se limpia automáticamente cuando el cierre sincronice (autoCleanup).
  }
  try {
    if (navigator.onLine) await refreshAssignment();
  } catch {
    /* sin red */
  }
}

/** Limpieza automática: turno cerrado y confirmado sin comandos pendientes → borrar estado local. */
export async function autoCleanup(): Promise<boolean> {
  const st = await shiftStore.get();
  if (!st || st.status !== 'closed') return false;
  const c = await queue.counts();
  if (c.pending > 0) return false;
  await clearShiftLocal(st);
  return true;
}
