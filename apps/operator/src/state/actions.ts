// Acciones de dominio: UI optimista → IndexedDB → cola → sync. Nunca exponen "reintentar API" al operador.
import { v4 as uuidv4 } from 'uuid';
import { api, ApiError, NetworkError, configureClient, refreshSession as clientRefreshSession, sessionFromLogin, setAuthSession, type AuthSession } from '../api/client';
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
import { haversineM, openLimitM } from '../offline/geo';
import * as queue from '../offline/queue';
import { syncNow, trigger } from '../offline/sync';
import type {
  AssignmentResponse,
  CloseChecklist,
  LoginResponse,
  GPS,
  HelpCategory,
  OpenChecklist,
  PaymentMethod,
  Photo,
  Presentation,
  ShiftException,
  ShiftExpected,
  WasteReason,
} from '../types';

/** Ventana de "Deshacer" local (la venta aún no salió del teléfono o acaba de salir). */
export const UNDO_WINDOW_MS = 60_000;
/** Fallbacks sólo si aún no se descargó `config` (mismos defaults que el servidor). */
export const DEFAULT_GPS_INTERVAL_S = 120;
export const DEFAULT_CANCEL_WINDOW_MIN = 5;

/** Config del operador cacheada en IndexedDB (se refresca con cada `GET /v1/me/assignment`). */
export async function getConfig() {
  return (await catalogStore.get())?.config ?? null;
}

export async function gpsIntervalSeconds(): Promise<number> {
  const cfg = await getConfig();
  return cfg?.gps_interval_seconds ?? DEFAULT_GPS_INTERVAL_S;
}

/** Ventana (ms) en la que el operador puede cancelar su propia venta ya enviada (`cancel_window_minutes`). */
export async function cancelWindowMs(): Promise<number> {
  const cfg = await getConfig();
  return (cfg?.cancel_window_minutes ?? DEFAULT_CANCEL_WINDOW_MIN) * 60_000;
}

const OPEN_MESSAGES: Record<string, { message: string; action: string }> = {
  cart_secure: { message: 'Carrito no asegurado', action: 'Revisa candado y resguardo' },
  battery_ok: { message: 'Batería insuficiente', action: 'Conecta el cargador o pide reemplazo' },
  product_ok: { message: 'Producto insuficiente o en mal estado', action: 'Pide reposición' },
  clean_ok: { message: 'Carrito sucio', action: 'Limpia antes de vender' },
  pos_ok: { message: 'Terminal POS no funciona', action: 'Cobra sólo en efectivo y pide ayuda' },
  out_of_geofence: { message: 'Estás fuera del punto asignado', action: 'Ve al punto o avisa al supervisor' },
  gps_mocked: { message: 'La ubicación parece simulada', action: 'Desactiva ubicación falsa' },
};
// out_of_geofence es crítica: el operador ve "abierto con pendientes" y el servidor abre caso urgente.
const CRITICAL_OPEN = new Set(['cart_secure', 'battery_ok', 'product_ok', 'pos_ok', 'out_of_geofence']);

export function suggestedAction(code: string): string {
  return OPEN_MESSAGES[code]?.action ?? 'Avisa al supervisor';
}

// ---------- sesión ----------
/** Guarda en IndexedDB la respuesta de login/refresh (ambos tokens) y la deja activa en el cliente HTTP. */
export async function persistSession(res: LoginResponse, device_id: string): Promise<AuthSession> {
  const auth = sessionFromLogin(res, device_id);
  await sessionStore.set({
    access_token: auth.access_token,
    expires_at: auth.expires_at,
    refresh_token: auth.refresh_token,
    refresh_expires_at: auth.refresh_expires_at,
    device_id,
    user: res.user,
    must_change_password: !!res.must_change_password,
  });
  setAuthSession(auth);
  return auth;
}

export interface LoginOutcome {
  must_change_password: boolean;
  assignment: AssignmentResponse | null;
}

export async function login(username: string, password: string): Promise<LoginOutcome> {
  const device_id = getDeviceId();
  const res = await api.login({ username, password, device_id, device_name: deviceName(), platform: 'pwa' });
  await persistSession(res, device_id);
  if (res.must_change_password) return { must_change_password: true, assignment: null };
  const a = await refreshAssignment();
  return { must_change_password: false, assignment: a };
}

/**
 * Rota el refresh token con el device_id persistido y reemplaza ambos tokens en IndexedDB.
 * Con lock (en el cliente HTTP): dos llamadas simultáneas comparten la misma petición.
 * Devuelve null si no hay sesión local con refresh token. Si el servidor responde 401 la sesión
 * local se cierra (conservando la cola cifrada) y se relanza el error.
 */
export async function refreshSession(): Promise<LoginResponse | null> {
  return clientRefreshSession();
}

/** Cambia la contraseña del usuario actual; al terminar, la sesión deja de exigir cambio. */
export async function changePassword(current_password: string, new_password: string): Promise<void> {
  await api.changePassword({ current_password, new_password });
  await sessionStore.update({ must_change_password: false });
}

/** Cierra la sesión localmente (token inválido, dispositivo revocado) sin tocar la cola cifrada ni el turno. */
export async function dropLocalSession(): Promise<void> {
  stopGpsPings();
  await sessionStore.clear();
  setAuthSession(null);
}

/**
 * Conecta el cliente HTTP con IndexedDB: persiste tokens rotados, cierra la sesión local cuando el
 * refresh falla (401) o el dispositivo es revocado, y marca `must_change_password` ante 403
 * PASSWORD_CHANGE_REQUIRED. `onChange` avisa a la UI para que relea el estado.
 */
export function installSessionHooks(opts: { onChange?: () => void } = {}) {
  configureClient({
    onSessionLost: async () => {
      await dropLocalSession();
      opts.onChange?.();
    },
    onSessionRefreshed: async (res, auth) => {
      await sessionStore.update({
        access_token: auth.access_token,
        expires_at: auth.expires_at,
        refresh_token: auth.refresh_token,
        refresh_expires_at: auth.refresh_expires_at,
        user: res.user,
        must_change_password: !!res.must_change_password,
      });
      if (res.must_change_password) opts.onChange?.();
    },
    onPasswordChangeRequired: async () => {
      await sessionStore.update({ must_change_password: true });
      opts.onChange?.();
    },
  });
}

/** Descarga asignación + catálogo + config y los guarda; adopta un turno abierto en el servidor si no hay uno local. */
export async function refreshAssignment(): Promise<AssignmentResponse> {
  const a = await api.myAssignment();
  await assignmentStore.set(a);
  await catalogStore.set(a.catalog, a.config);
  const local = await shiftStore.get();
  const pendingCmds = (await queue.counts()).pending;
  if (a.active_shift && pendingCmds === 0 && local && local.server_id === a.active_shift.id && local.status === 'closed') {
    // El administrador reabrió ESTE turno mientras aún se veía el resultado del cierre: conservar local_id y ventas locales.
    await shiftStore.update({ status: 'open', close_result: null, ready: a.active_shift.ready ?? true, exceptions: a.active_shift.exceptions ?? [] });
    startGpsPings(a.active_shift.id, await gpsIntervalSeconds());
    void cacheExpected(a.active_shift.id);
  } else if (a.active_shift && pendingCmds === 0 && (!local || local.status === 'closed')) {
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
      server_sales: null,
      last_expected: null,
      close_result: null,
    });
    await salesLocalStore.clearShift(a.active_shift.id);
    // Turno adoptado (abierto en otro teléfono o reabierto por el administrador): pings GPS y esperado como en una apertura normal.
    startGpsPings(a.active_shift.id, await gpsIntervalSeconds());
    void cacheExpected(a.active_shift.id, { withServerSales: true });
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
  setAuthSession(null);
  return { ok: true };
}

// ---------- turno ----------
export function localOpenExceptions(checklist: OpenChecklist): ShiftException[] {
  return (Object.keys(checklist) as (keyof OpenChecklist)[])
    .filter((k) => !checklist[k])
    .map((k) => ({ code: k, message: OPEN_MESSAGES[k]?.message ?? k }));
}

/**
 * Abre el puesto. `photos` (foto del puesto, key "puesto") sólo cuando `config.require_open_photo`; si la cámara falla
 * se abre igual con `photos: []`. La foto viaja dentro del comando `shift_open` (cola cifrada) cuando no hay red.
 */
export async function openShift(checklist: OpenChecklist, gps: GPS | null, photos: Photo[] = []): Promise<ShiftStateRecord> {
  const a = (await assignmentStore.get())?.data;
  if (!a?.assignment) throw new ApiError('NO_ASSIGNMENT', 'No tienes asignación para hoy', 409);
  const local_id = `local:${uuidv4()}`;
  const exceptions = localOpenExceptions(checklist);
  // Regla de distancia (misma que el servidor) para que el aviso se vea también al abrir sin señal.
  if (gps) {
    const cfg = (await getConfig()) ?? undefined;
    const limit = openLimitM(a.assignment.point, cfg?.open_max_distance_m);
    const d = haversineM(gps.lat, gps.lng, a.assignment.point.lat, a.assignment.point.lng);
    if (d > limit) exceptions.push({ code: 'out_of_geofence', message: `Estás a ${Math.round(d)} m del punto asignado (máximo ${limit} m)` });
  }
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
  await queue.enqueue('shift_open', { assignment_id: a.assignment.id, opened_at, checklist, gps, photos });
  // Si hay red, esperamos la confirmación para mostrar excepciones del servidor (geocerca, etc.).
  await syncNow();
  const st = (await shiftStore.get())!;
  startGpsPings(st.server_id ?? st.local_id, await gpsIntervalSeconds());
  // Cachear esperado inicial (producto) para el cierre offline.
  if (st.server_id) void cacheExpected(st.server_id);
  return st;
}

async function cacheExpected(serverId: string, opts: { withServerSales?: boolean } = {}) {
  try {
    const e = await api.shiftExpected(serverId);
    await shiftStore.update({
      last_expected: { fetched_at: new Date().toISOString(), cash_expected_cents: e.cash_expected_cents, product_expected: e.product_expected },
      ...(opts.withServerSales ? { server_sales: { count: e.sales_count, total_cents: e.sales_total_cents, cash_expected_cents: e.cash_expected_cents, digital_total_cents: e.digital_total_cents } } : {}),
    });
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
  if (st && (st.status === 'open' || st.status === 'open_pending')) {
    startGpsPings(currentShiftId(st), await gpsIntervalSeconds());
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

/**
 * Deshacer: si aún está en cola (≤60 s) se elimina; si ya sincronizó hace falta motivo (cancelación), siempre que
 * siga dentro de `cancel_window_minutes` (config del servidor); después de eso sólo el supervisor puede cancelar.
 */
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
  const cancelWindow = await cancelWindowMs();
  if (age > cancelWindow) return 'too_late';
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
  // Sin red: lo local + lo que el servidor ya tenía cuando se adoptó el turno (reabierto por el administrador).
  const local = computeLocalExpected(sales, waste);
  const base = st.server_sales;
  return {
    source: 'local',
    cash_expected_cents: local.cash_expected_cents + (base?.cash_expected_cents ?? 0),
    sales_count: local.sales_count + (base?.count ?? 0),
    sales_total_cents: local.sales_total_cents + (base?.total_cents ?? 0),
    digital_total_cents: local.digital_total_cents + (base?.digital_total_cents ?? 0),
    product_expected: computeLocalProductExpected(st.last_expected, sales, waste),
  };
}

export async function closeShift(input: {
  cash_counted_cents: number;
  product_counts: Record<string, number>;
  checklist: CloseChecklist;
  gps: GPS | null;
  expected_cash_cents: number;
  /** Foto del puesto al cerrar (key "puesto") cuando `config.require_open_photo`; vacío si falló la cámara. */
  photos?: Photo[];
}): Promise<NonNullable<ShiftStateRecord['close_result']>> {
  const st = await shiftStore.get();
  if (!st) throw new ApiError('SHIFT_NOT_OPEN', 'No hay turno', 409);
  const cfg = await getConfig();
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
    photos: input.photos ?? [],
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
