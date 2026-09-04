// Cola de comandos idempotentes (CONTRATOS §9): enqueue → cifrado → POST /v1/sync/batch en orden.
// Maneja ok/duplicate/error por comando; un error de red deja todo pendiente para reintento con backoff (ver sync.ts).
import { v4 as uuidv4 } from 'uuid';
import { decryptJSON, encryptJSON } from './crypto';
import { getDB, type QueueRecord } from './db';
import type { SyncCommand, SyncCommandType, SyncResult } from '../types';

export interface PendingCommand {
  idempotency_key: string;
  seq: number;
  type: SyncCommandType;
  created_at: string;
  status: QueueRecord['status'];
  attempts: number;
  last_error?: { code: string; message: string } | null;
  payload: Record<string, unknown>;
}

export const BATCH_SIZE = 50;

// Número de orden monótono (sobrevive reinicios porque parte del reloj; el contador evita empates).
let lastSeq = 0;
function nextSeq(): number {
  lastSeq = Math.max(lastSeq + 1, Date.now() * 1000);
  return lastSeq;
}

/** Encola un comando. Si ya existe un comando con la misma clave, no se duplica. Devuelve la clave. */
export async function enqueue(type: SyncCommandType, payload: Record<string, unknown>, idempotency_key: string = uuidv4()): Promise<string> {
  const db = await getDB();
  const existing = await db.get('queue', idempotency_key);
  if (existing) return idempotency_key;
  const cipher = await encryptJSON({ ...payload, idempotency_key: type === 'gps_ping' ? undefined : idempotency_key });
  await db.put('queue', {
    idempotency_key,
    seq: nextSeq(),
    type,
    created_at: new Date().toISOString(),
    cipher,
    status: 'pending',
    attempts: 0,
    last_error: null,
  } as QueueRecord);
  return idempotency_key;
}

export async function remove(idempotency_key: string): Promise<void> {
  const db = await getDB();
  await db.delete('queue', idempotency_key);
}

export async function has(idempotency_key: string): Promise<boolean> {
  const db = await getDB();
  return (await db.getKey('queue', idempotency_key)) !== undefined;
}

export async function counts(): Promise<{ pending: number; failed: number }> {
  const db = await getDB();
  const all = await db.getAll('queue');
  let pending = 0;
  let failed = 0;
  for (const r of all) (r.status === 'failed' ? failed++ : pending++);
  return { pending, failed };
}

/** Lista los comandos (descifrados) en orden de creación. */
export async function listAll(): Promise<PendingCommand[]> {
  const db = await getDB();
  const rows = await db.getAllFromIndex('queue', 'by_seq');
  const out: PendingCommand[] = [];
  for (const r of rows) {
    const payload = await decryptJSON<Record<string, unknown>>(r.cipher);
    out.push({
      idempotency_key: r.idempotency_key,
      seq: r.seq ?? 0,
      type: r.type,
      created_at: r.created_at,
      status: r.status,
      attempts: r.attempts,
      last_error: r.last_error,
      payload,
    });
  }
  return out;
}

/** Vuelve a marcar como pendientes los comandos fallidos (botón "Reintentar enviar"). */
export async function retryFailed(): Promise<number> {
  const db = await getDB();
  const rows = await db.getAll('queue');
  let n = 0;
  const tx = db.transaction('queue', 'readwrite');
  for (const r of rows) {
    if (r.status === 'failed') {
      await tx.store.put({ ...r, status: 'pending', last_error: null });
      n++;
    }
  }
  await tx.done;
  return n;
}

/** Errores que no vale la pena reintentar automáticamente: quedan en "Requiere ayuda". */
export const NON_RETRYABLE = new Set([
  'VALIDATION',
  'IDEMPOTENCY_CONFLICT',
  'NOT_FOUND',
  'FORBIDDEN',
  'NO_ASSIGNMENT',
  'SHIFT_NOT_OPEN',
  'SHIFT_ALREADY_OPEN',
  'CART_IN_USE',
  'PRICE_VERSION_INVALID',
  'CANCEL_NOT_ALLOWED',
  'LOT_BLOCKED',
  'CONFLICT',
]);

export interface FlushDeps {
  device_id: string;
  send: (device_id: string, commands: SyncCommand[]) => Promise<{ results: SyncResult[] }>;
  /** Traduce un shift_id local a uno de servidor. Devuelve null si aún no se conoce. */
  resolveShiftId?: (localId: string) => string | null;
  /** Llamado por cada resultado ok/duplicate/error (para actualizar sales_local, shift_state...). */
  onResult?: (cmd: PendingCommand, result: SyncResult) => Promise<void> | void;
}

export interface FlushOutcome {
  sent: number;
  ok: number;
  duplicate: number;
  error: number;
  /** true si la red falló y hay que reintentar con backoff. */
  networkFailed: boolean;
  /** true si quedaron comandos bloqueados esperando resolución de shift_id. */
  blocked: boolean;
}

const LOCAL_SHIFT_FIELDS = ['shift_id'] as const;

function substituteShiftIds(payload: Record<string, unknown>, resolve: (id: string) => string | null): { payload: Record<string, unknown>; unresolved: boolean } {
  const out: Record<string, unknown> = { ...payload };
  let unresolved = false;
  for (const f of LOCAL_SHIFT_FIELDS) {
    const v = out[f];
    if (typeof v === 'string' && v.startsWith('local:')) {
      const server = resolve(v);
      if (server) out[f] = server;
      else unresolved = true;
    }
  }
  // gps_ping: {pings:[{shift_id...}]}
  if (Array.isArray(out.pings)) {
    out.pings = (out.pings as Record<string, unknown>[]).map((p) => {
      const r = substituteShiftIds(p, resolve);
      if (r.unresolved) unresolved = true;
      return r.payload;
    });
  }
  return { payload: out, unresolved };
}

/**
 * Envía los comandos pendientes en orden. Se detiene ante un comando cuyo shift_id local aún no se
 * puede resolver (por ejemplo, hasta que el shift_open previo sea confirmado); ese caso se resuelve en el
 * mismo flush porque tras cada lote se vuelven a evaluar las resoluciones.
 */
export async function flush(deps: FlushDeps): Promise<FlushOutcome> {
  const outcome: FlushOutcome = { sent: 0, ok: 0, duplicate: 0, error: 0, networkFailed: false, blocked: false };
  const resolve = deps.resolveShiftId ?? (() => null);
  for (let round = 0; round < 20; round++) {
    const all = (await listAll()).filter((c) => c.status === 'pending');
    if (all.length === 0) return outcome;
    const batch: { cmd: PendingCommand; wire: SyncCommand }[] = [];
    let blocked = false;
    for (const cmd of all) {
      const { payload, unresolved } = substituteShiftIds(cmd.payload, resolve);
      if (unresolved) {
        blocked = true;
        break;
      }
      batch.push({ cmd, wire: { idempotency_key: cmd.idempotency_key, type: cmd.type, created_at: cmd.created_at, payload } });
      if (batch.length >= BATCH_SIZE) break;
    }
    if (batch.length === 0) {
      outcome.blocked = blocked;
      return outcome;
    }
    let results: SyncResult[];
    try {
      results = (await deps.send(deps.device_id, batch.map((b) => b.wire))).results ?? [];
    } catch (e) {
      // Red caída o 5xx: nada cambia, se reintenta luego.
      await bumpAttempts(batch.map((b) => b.cmd.idempotency_key));
      outcome.networkFailed = true;
      return outcome;
    }
    outcome.sent += batch.length;
    const byKey = new Map(results.map((r) => [r.idempotency_key, r]));
    for (const { cmd } of batch) {
      const r = byKey.get(cmd.idempotency_key);
      if (!r) {
        // Sin resultado para este comando: se reintenta en el siguiente ciclo.
        await bumpAttempts([cmd.idempotency_key]);
        continue;
      }
      if (r.status === 'ok' || r.status === 'duplicate') {
        await remove(cmd.idempotency_key);
        if (r.status === 'ok') outcome.ok++;
        else outcome.duplicate++;
      } else {
        outcome.error++;
        const code = r.code ?? 'ERROR';
        if (NON_RETRYABLE.has(code)) await markFailed(cmd.idempotency_key, { code, message: r.message ?? '' });
        else await bumpAttempts([cmd.idempotency_key], { code, message: r.message ?? '' });
      }
      if (deps.onResult) await deps.onResult(cmd, r);
    }
  }
  return outcome;
}

async function bumpAttempts(keys: string[], err?: { code: string; message: string }) {
  const db = await getDB();
  const tx = db.transaction('queue', 'readwrite');
  for (const k of keys) {
    const r = await tx.store.get(k);
    if (r) await tx.store.put({ ...r, attempts: r.attempts + 1, last_error: err ?? r.last_error ?? null });
  }
  await tx.done;
}

async function markFailed(key: string, err: { code: string; message: string }) {
  const db = await getDB();
  const r = await db.get('queue', key);
  if (r) await db.put('queue', { ...r, status: 'failed', attempts: r.attempts + 1, last_error: err });
}

export async function clearAll() {
  const db = await getDB();
  await db.clear('queue');
}
