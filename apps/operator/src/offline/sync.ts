// Sincronización: dispara en `online`, cada 30 s, y tras cada acción; con lock para no solapar y backoff ante fallos de red.
// También aplica los resultados de cada comando al estado local (shift_state, sales_local).
import { api, ApiError } from '../api/client';
import { salesLocalStore, sessionStore, shiftStore } from './db';
import { counts, flush, retryFailed, type PendingCommand } from './queue';
import type { SyncResult } from '../types';

export type SyncVisibleState = 'saved' | 'pending' | 'help';

export interface SyncStatus {
  online: boolean;
  syncing: boolean;
  pending: number;
  failed: number;
  last_ok_at: string | null;
  last_error: string | null;
  /** Estado simple para el operador: Guardado / Pendiente de enviar / Requiere ayuda. */
  visible: SyncVisibleState;
}

type Listener = (s: SyncStatus) => void;

const INTERVAL_MS = 30_000;
const BACKOFF_BASE_MS = 5_000;
const BACKOFF_MAX_MS = 5 * 60_000;

let status: SyncStatus = {
  online: typeof navigator !== 'undefined' ? navigator.onLine : true,
  syncing: false,
  pending: 0,
  failed: 0,
  last_ok_at: null,
  last_error: null,
  visible: 'saved',
};
const listeners = new Set<Listener>();
let lock: Promise<void> | null = null;
let timer: ReturnType<typeof setInterval> | null = null;
let backoffTimer: ReturnType<typeof setTimeout> | null = null;
let backoffMs = BACKOFF_BASE_MS;
let started = false;
/** Callbacks a los que avisar cuando cambie algo del dominio (ventas, turno) por un ACK. */
const domainListeners = new Set<() => void>();

function emit() {
  for (const l of listeners) l(status);
}

function setStatus(patch: Partial<SyncStatus>) {
  status = { ...status, ...patch };
  status.visible = status.failed > 0 ? 'help' : status.pending > 0 ? 'pending' : 'saved';
  emit();
}

export function getSyncStatus() {
  return status;
}

export function subscribeSync(l: Listener): () => void {
  listeners.add(l);
  l(status);
  return () => listeners.delete(l);
}

export function subscribeDomain(l: () => void): () => void {
  domainListeners.add(l);
  return () => domainListeners.delete(l);
}

function notifyDomain() {
  for (const l of domainListeners) l();
}

export async function refreshCounts() {
  const c = await counts();
  setStatus({ pending: c.pending, failed: c.failed });
}

/** Resuelve un shift_id local (`local:<uuid>`) al id del servidor si ya se conoce. */
let shiftMap: { local: string; server: string | null } | null = null;

async function loadShiftMap() {
  const s = await shiftStore.get();
  shiftMap = s ? { local: s.local_id, server: s.server_id } : null;
}

function resolveShiftId(localId: string): string | null {
  if (shiftMap && shiftMap.local === localId) return shiftMap.server;
  return null;
}

/** Aplica el resultado de un comando al estado local. */
async function applyResult(cmd: PendingCommand, r: SyncResult) {
  const res = (r.result ?? {}) as Record<string, unknown>;
  switch (cmd.type) {
    case 'shift_open': {
      const st = await shiftStore.get();
      if (!st) return;
      if (r.status === 'ok' || r.status === 'duplicate') {
        const serverId = String(res.shift_id ?? '');
        await shiftStore.update({
          server_id: serverId || st.server_id,
          status: st.status === 'open_pending' ? 'open' : st.status,
          ready: typeof res.ready === 'boolean' ? res.ready : st.ready,
          exceptions: Array.isArray(res.exceptions) ? (res.exceptions as { code: string; message: string }[]) : st.exceptions,
        });
        await loadShiftMap();
      } else if (r.code === 'SHIFT_ALREADY_OPEN' || r.code === 'CART_IN_USE') {
        // Ya existe un turno abierto en el servidor (p. ej. reinstalación): adoptarlo.
        try {
          const a = await api.myAssignment();
          if (a.active_shift) {
            await shiftStore.update({ server_id: a.active_shift.id, status: 'open', exceptions: a.active_shift.exceptions ?? st.exceptions, ready: a.active_shift.ready ?? st.ready });
            await loadShiftMap();
            await retryFailed();
          }
        } catch {
          /* se reintenta luego */
        }
      }
      break;
    }
    case 'sale': {
      if (r.status === 'ok' || r.status === 'duplicate') {
        await salesLocalStore.update(cmd.idempotency_key, {
          status: 'synced',
          sale_id: typeof res.sale_id === 'string' ? res.sale_id : null,
          folio: typeof res.folio === 'string' ? res.folio : null,
        });
      } else {
        await salesLocalStore.update(cmd.idempotency_key, { status: 'failed' });
      }
      break;
    }
    case 'sale_cancel': {
      const saleId = String(cmd.payload.sale_id ?? '');
      const all = await salesLocalStore.all();
      const local = all.find((s) => s.sale_id === saleId);
      if (local) {
        await salesLocalStore.update(local.idempotency_key, { status: r.status === 'error' ? 'synced' : 'cancelled' });
      }
      break;
    }
    case 'shift_close': {
      const st = await shiftStore.get();
      if (!st) return;
      if (r.status === 'ok' || r.status === 'duplicate') {
        await shiftStore.update({
          status: 'closed',
          close_result: {
            status: (res.status as 'reconciled' | 'difference') ?? 'reconciled',
            cash_expected_cents: Number(res.cash_expected_cents ?? st.close_result?.cash_expected_cents ?? 0),
            cash_counted_cents: Number(res.cash_counted_cents ?? st.close_result?.cash_counted_cents ?? 0),
            difference_cents: Number(res.difference_cents ?? st.close_result?.difference_cents ?? 0),
            closed_at: st.close_result?.closed_at ?? new Date().toISOString(),
          },
        });
      } else if (r.code === 'SHIFT_NOT_OPEN') {
        // El servidor ya lo considera cerrado.
        await shiftStore.update({ status: 'closed', close_result: st.close_result ? { ...st.close_result, status: 'reconciled' } : null });
      }
      break;
    }
    default:
      break;
  }
  notifyDomain();
}

/** Ejecuta un flush si no hay otro en curso. Devuelve cuando termina (o inmediatamente si ya había uno). */
export async function syncNow(): Promise<void> {
  if (lock) return lock;
  lock = (async () => {
    try {
      const session = await sessionStore.get();
      if (!session) return;
      await loadShiftMap();
      const c = await counts();
      if (c.pending === 0) {
        setStatus({ pending: 0, failed: c.failed });
        return;
      }
      setStatus({ syncing: true });
      const out = await flush({
        device_id: session.device_id,
        send: (d, cmds) => api.syncBatch(d, cmds),
        resolveShiftId,
        onResult: applyResult,
      });
      const after = await counts();
      if (out.networkFailed) {
        setStatus({ syncing: false, pending: after.pending, failed: after.failed, last_error: 'Sin conexión', online: navigator.onLine });
        scheduleBackoff();
      } else {
        backoffMs = BACKOFF_BASE_MS;
        setStatus({ syncing: false, pending: after.pending, failed: after.failed, last_ok_at: new Date().toISOString(), last_error: null, online: true });
      }
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : 'Sin conexión';
      const after = await counts();
      setStatus({ syncing: false, pending: after.pending, failed: after.failed, last_error: msg });
      scheduleBackoff();
    } finally {
      lock = null;
    }
  })();
  return lock;
}

function scheduleBackoff() {
  if (backoffTimer) clearTimeout(backoffTimer);
  backoffTimer = setTimeout(() => {
    backoffTimer = null;
    void syncNow();
  }, backoffMs);
  backoffMs = Math.min(backoffMs * 2, BACKOFF_MAX_MS);
}

/** Dispara sincronización sin esperar (tras cada acción). */
export function trigger() {
  void refreshCounts().then(() => syncNow());
}

export function startSync() {
  if (started) return;
  started = true;
  window.addEventListener('online', () => {
    setStatus({ online: true });
    backoffMs = BACKOFF_BASE_MS;
    void syncNow();
  });
  window.addEventListener('offline', () => setStatus({ online: false }));
  timer = setInterval(() => void syncNow(), INTERVAL_MS);
  void refreshCounts().then(() => syncNow());
}

export function stopSync() {
  if (timer) clearInterval(timer);
  if (backoffTimer) clearTimeout(backoffTimer);
  timer = null;
  backoffTimer = null;
  started = false;
}
