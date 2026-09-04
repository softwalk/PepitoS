// Almacén local IndexedDB (CONTRATOS §9): session, assignment, catalog, queue, shift_state, sales_local (+ secrets para la clave AES).
import { openDB, type DBSchema, type IDBPDatabase } from 'idb';
import type { AssignmentResponse, Catalog, OperatorConfig, PaymentMethod, ShiftException, SyncCommandType } from '../types';

export interface SessionRecord {
  id: 'current';
  access_token: string;
  expires_at: string;
  /** Refresh token rotativo (null en sesiones antiguas sin refresh). */
  refresh_token?: string | null;
  refresh_expires_at?: string | null;
  device_id: string;
  user: { id: string; name: string; role: string; zone_id: string | null; username?: string };
  /** El servidor exige cambiar la contraseña antes de operar. */
  must_change_password?: boolean;
}

export interface AssignmentRecord {
  id: 'current';
  fetched_at: string;
  data: AssignmentResponse;
}

export interface CatalogRecord {
  id: 'current';
  fetched_at: string;
  catalog: Catalog;
  config: OperatorConfig;
}

export type QueueStatus = 'pending' | 'failed';

/** Comando en cola. El payload viaja cifrado (AES-GCM); solo los metadatos quedan en claro. */
export interface QueueRecord {
  idempotency_key: string;
  seq?: number; // autoincrement: orden de creación
  type: SyncCommandType;
  created_at: string;
  cipher: { iv: ArrayBuffer; data: ArrayBuffer };
  status: QueueStatus;
  attempts: number;
  last_error?: { code: string; message: string } | null;
}

export type ShiftLocalStatus = 'open_pending' | 'open' | 'closing' | 'closed';

export interface ShiftStateRecord {
  id: 'current';
  local_id: string; // UUID generado en el dispositivo; se usa como shift_id hasta que el servidor confirme
  server_id: string | null;
  assignment_id: string;
  point_name: string;
  cart_code: string;
  opened_at: string;
  status: ShiftLocalStatus;
  ready: boolean;
  exceptions: ShiftException[];
  /** Ventas que el servidor ya tenía cuando este teléfono adoptó el turno (p. ej. turno reabierto por el administrador
   *  tras un cierre): no están en sales_local, así que se suman a los contadores en pantalla. */
  server_sales?: { count: number; total_cents: number; cash_expected_cents: number; digital_total_cents: number } | null;
  /** Último "esperado" conocido del servidor (para cierre offline). */
  last_expected?: { fetched_at: string; cash_expected_cents: number; product_expected: Record<string, number> } | null;
  close_result?: {
    status: 'reconciled' | 'difference' | 'pending';
    cash_expected_cents: number;
    cash_counted_cents: number;
    difference_cents: number;
    closed_at: string;
  } | null;
}

export type SaleLocalStatus = 'pending' | 'synced' | 'undone' | 'cancel_pending' | 'cancelled' | 'failed';

export interface SaleLocalRecord {
  idempotency_key: string;
  shift_local_id: string;
  occurred_at: string;
  presentation_id: string;
  presentation_name: string;
  grams: number;
  qty: number;
  flavor_id: string | null;
  unit_price_cents: number;
  total_cents: number;
  price_version_id: string;
  method: PaymentMethod;
  status: SaleLocalStatus;
  sale_id?: string | null;
  folio?: string | null;
}

export interface WasteLocalRecord {
  idempotency_key: string;
  shift_local_id: string;
  presentation_id: string;
  qty: number;
  reason_code: string;
  occurred_at: string;
}

export interface SecretRecord {
  id: 'queue_key';
  raw: ArrayBuffer;
}

export interface SettingsRecord {
  id: 'current';
  audio: boolean;
  large_text: boolean;
}

interface PepitoDB extends DBSchema {
  session: { key: 'current'; value: SessionRecord };
  assignment: { key: 'current'; value: AssignmentRecord };
  catalog: { key: 'current'; value: CatalogRecord };
  queue: { key: string; value: QueueRecord; indexes: { by_seq: number } };
  shift_state: { key: 'current'; value: ShiftStateRecord };
  sales_local: { key: string; value: SaleLocalRecord; indexes: { by_shift: string } };
  waste_local: { key: string; value: WasteLocalRecord; indexes: { by_shift: string } };
  secrets: { key: 'queue_key'; value: SecretRecord };
  settings: { key: 'current'; value: SettingsRecord };
}

export const DB_NAME = 'pepito-operator';
export const DB_VERSION = 1;

let dbPromise: Promise<IDBPDatabase<PepitoDB>> | null = null;

export function getDB(): Promise<IDBPDatabase<PepitoDB>> {
  if (!dbPromise) {
    dbPromise = openDB<PepitoDB>(DB_NAME, DB_VERSION, {
      upgrade(db) {
        db.createObjectStore('session', { keyPath: 'id' });
        db.createObjectStore('assignment', { keyPath: 'id' });
        db.createObjectStore('catalog', { keyPath: 'id' });
        const q = db.createObjectStore('queue', { keyPath: 'idempotency_key' });
        q.createIndex('by_seq', 'seq');
        db.createObjectStore('shift_state', { keyPath: 'id' });
        const s = db.createObjectStore('sales_local', { keyPath: 'idempotency_key' });
        s.createIndex('by_shift', 'shift_local_id');
        const w = db.createObjectStore('waste_local', { keyPath: 'idempotency_key' });
        w.createIndex('by_shift', 'shift_local_id');
        db.createObjectStore('secrets', { keyPath: 'id' });
        db.createObjectStore('settings', { keyPath: 'id' });
      },
    });
  }
  return dbPromise;
}

/** Solo para pruebas: cierra y olvida la conexión. */
export async function resetDBForTests() {
  if (dbPromise) {
    const db = await dbPromise;
    db.close();
    dbPromise = null;
  }
  await new Promise<void>((resolve) => {
    const req = indexedDB.deleteDatabase(DB_NAME);
    req.onsuccess = () => resolve();
    req.onerror = () => resolve();
    req.onblocked = () => resolve();
  });
}

// ---- helpers por store ----
export const sessionStore = {
  get: async () => (await getDB()).get('session', 'current'),
  set: async (s: Omit<SessionRecord, 'id'>) => (await getDB()).put('session', { id: 'current', ...s }),
  update: async (patch: Partial<SessionRecord>) => {
    const db = await getDB();
    const cur = await db.get('session', 'current');
    if (!cur) return undefined;
    const next = { ...cur, ...patch, id: 'current' as const };
    await db.put('session', next);
    return next;
  },
  clear: async () => (await getDB()).delete('session', 'current'),
};

export const assignmentStore = {
  get: async () => (await getDB()).get('assignment', 'current'),
  set: async (data: AssignmentResponse) => (await getDB()).put('assignment', { id: 'current', fetched_at: new Date().toISOString(), data }),
  clear: async () => (await getDB()).delete('assignment', 'current'),
};

export const catalogStore = {
  get: async () => (await getDB()).get('catalog', 'current'),
  set: async (catalog: Catalog, config: OperatorConfig) =>
    (await getDB()).put('catalog', { id: 'current', fetched_at: new Date().toISOString(), catalog, config }),
};

export const shiftStore = {
  get: async () => (await getDB()).get('shift_state', 'current'),
  set: async (s: Omit<ShiftStateRecord, 'id'>) => (await getDB()).put('shift_state', { id: 'current', ...s }),
  update: async (patch: Partial<ShiftStateRecord>) => {
    const db = await getDB();
    const cur = await db.get('shift_state', 'current');
    if (!cur) return undefined;
    const next = { ...cur, ...patch, id: 'current' as const };
    await db.put('shift_state', next);
    return next;
  },
  clear: async () => (await getDB()).delete('shift_state', 'current'),
};

export const salesLocalStore = {
  put: async (s: SaleLocalRecord) => (await getDB()).put('sales_local', s),
  get: async (key: string) => (await getDB()).get('sales_local', key),
  byShift: async (shiftLocalId: string) => (await getDB()).getAllFromIndex('sales_local', 'by_shift', shiftLocalId),
  all: async () => (await getDB()).getAll('sales_local'),
  update: async (key: string, patch: Partial<SaleLocalRecord>) => {
    const db = await getDB();
    const cur = await db.get('sales_local', key);
    if (!cur) return undefined;
    const next = { ...cur, ...patch };
    await db.put('sales_local', next);
    return next;
  },
  clearShift: async (shiftLocalId: string) => {
    const db = await getDB();
    const keys = await db.getAllKeysFromIndex('sales_local', 'by_shift', shiftLocalId);
    const tx = db.transaction('sales_local', 'readwrite');
    await Promise.all(keys.map((k) => tx.store.delete(k)));
    await tx.done;
  },
};

export const wasteLocalStore = {
  put: async (w: WasteLocalRecord) => (await getDB()).put('waste_local', w),
  byShift: async (shiftLocalId: string) => (await getDB()).getAllFromIndex('waste_local', 'by_shift', shiftLocalId),
  clearShift: async (shiftLocalId: string) => {
    const db = await getDB();
    const keys = await db.getAllKeysFromIndex('waste_local', 'by_shift', shiftLocalId);
    const tx = db.transaction('waste_local', 'readwrite');
    await Promise.all(keys.map((k) => tx.store.delete(k)));
    await tx.done;
  },
};

export const settingsStore = {
  get: async () => (await getDB()).get('settings', 'current'),
  set: async (s: Omit<SettingsRecord, 'id'>) => (await getDB()).put('settings', { id: 'current', ...s }),
};

export const secretsStore = {
  get: async () => (await getDB()).get('secrets', 'queue_key'),
  set: async (raw: ArrayBuffer) => (await getDB()).put('secrets', { id: 'queue_key', raw }),
  clear: async () => (await getDB()).delete('secrets', 'queue_key'),
};

/** Borra todo lo local (cerrar sesión). La cola pendiente se conserva sólo si `keepQueue`. */
export async function wipeLocal(opts: { keepQueue?: boolean } = {}) {
  const db = await getDB();
  const stores: ('session' | 'assignment' | 'catalog' | 'shift_state' | 'sales_local' | 'waste_local' | 'queue' | 'secrets')[] = [
    'session',
    'assignment',
    'catalog',
    'shift_state',
    'sales_local',
    'waste_local',
  ];
  if (!opts.keepQueue) stores.push('queue', 'secrets');
  const tx = db.transaction(stores, 'readwrite');
  await Promise.all(stores.map((s) => tx.objectStore(s).clear()));
  await tx.done;
}
