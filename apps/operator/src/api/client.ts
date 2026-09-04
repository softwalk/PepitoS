// Cliente HTTP tipado de la API del operador (CONTRATOS §3, §5).
// Gestiona la sesión: access token + refresh token rotativo. Ante 401 AUTH_INVALID refresca una vez y
// reintenta; si el access token está por vencer (<5 min) refresca antes de la petición.
import type {
  AssignmentResponse,
  Catalog,
  HelpCasePayload,
  HelpCaseResponse,
  InventoryCountPayload,
  InventoryReceiptPayload,
  LoginResponse,
  GpsPing,
  PricesCurrent,
  SaleCancelPayload,
  SalePayload,
  SaleResponse,
  ShiftClosePayload,
  ShiftCloseResponse,
  ShiftExpected,
  ShiftOpenPayload,
  ShiftOpenResponse,
  SyncBatchResponse,
  SyncCommand,
  WastePayload,
} from '../types';

export class ApiError extends Error {
  code: string;
  status: number;
  details: unknown;
  /** Segundos a esperar (429 RATE_LIMITED): de `details.retry_after_seconds` o del header Retry-After. */
  retryAfterSeconds: number | null;
  constructor(code: string, message: string, status: number, details?: unknown, retryAfterSeconds: number | null = null) {
    super(message);
    this.code = code;
    this.status = status;
    this.details = details;
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

/** Error de red (sin conexión / servidor caído): la UI lo trata como "pendiente", nunca como fallo. */
export class NetworkError extends Error {
  constructor(message = 'Sin conexión') {
    super(message);
  }
}

// En dev/preview, Vite hace proxy de /v1 → VITE_API_URL (peticiones relativas). En producción, si se define
// VITE_API_BASE al compilar, se usa esa URL absoluta; si no, las peticiones son relativas (/v1) y el servidor
// web (nginx, etc.) debe hacer proxy a la API.
const BASE = (import.meta.env.VITE_API_BASE || '').replace(/\/$/, '');

/** Refrescar proactivamente si el access token vence en menos de este margen. */
export const REFRESH_AHEAD_MS = 5 * 60_000;

/** Tokens en memoria (la copia persistente vive en IndexedDB; ver state/store y state/actions). */
export interface AuthSession {
  access_token: string;
  expires_at: string;
  refresh_token: string | null;
  refresh_expires_at: string | null;
  device_id: string;
}

export interface ClientHooks {
  /** La sesión ya no sirve (refresh inválido/expirado o dispositivo revocado): cerrar sesión local. */
  onSessionLost?: (code: string) => void | Promise<void>;
  /** Tokens rotados con éxito: persistir. */
  onSessionRefreshed?: (res: LoginResponse, session: AuthSession) => void | Promise<void>;
  /** El servidor exige cambiar la contraseña (403 PASSWORD_CHANGE_REQUIRED o must_change_password). */
  onPasswordChangeRequired?: () => void | Promise<void>;
}

let session: AuthSession | null = null;
let hooks: ClientHooks = {};
let refreshing: Promise<LoginResponse | null> | null = null;

export function setAuthSession(s: AuthSession | null) {
  session = s;
}

export function getAuthSession(): AuthSession | null {
  return session;
}

export function configureClient(h: ClientHooks) {
  hooks = h;
}

export function sessionFromLogin(res: LoginResponse, device_id: string): AuthSession {
  return {
    access_token: res.access_token,
    expires_at: new Date(Date.now() + res.expires_in * 1000).toISOString(),
    refresh_token: res.refresh_token ?? null,
    refresh_expires_at: res.refresh_expires_at ?? null,
    device_id,
  };
}

function accessTokenExpiringSoon(s: AuthSession): boolean {
  const exp = Date.parse(s.expires_at);
  return Number.isFinite(exp) && exp - Date.now() < REFRESH_AHEAD_MS;
}

async function sessionLost(code: string) {
  session = null;
  await hooks.onSessionLost?.(code);
}

/**
 * Rota el refresh token (`POST /v1/auth/refresh`) y reemplaza ambos tokens. Con lock: llamadas
 * simultáneas comparten la misma petición. Devuelve null si no hay sesión con refresh token.
 * Si el servidor responde 401 (token inválido/rotado/expirado o dispositivo revocado) cierra la
 * sesión local y relanza el error.
 */
export function refreshSession(): Promise<LoginResponse | null> {
  if (refreshing) return refreshing;
  const cur = session;
  if (!cur?.refresh_token) return Promise.resolve(null);
  refreshing = (async () => {
    let res: LoginResponse;
    try {
      res = await rawRequest<LoginResponse>('POST', '/v1/auth/refresh', { refresh_token: cur.refresh_token, device_id: cur.device_id }, { auth: false });
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) await sessionLost(e.code);
      throw e;
    }
    const next = sessionFromLogin(res, cur.device_id);
    session = next;
    await hooks.onSessionRefreshed?.(res, next);
    if (res.must_change_password) await hooks.onPasswordChangeRequired?.();
    return res;
  })().finally(() => {
    refreshing = null;
  });
  return refreshing;
}

interface ReqOpts {
  auth?: boolean;
  timeoutMs?: number;
}

/** Petición sin lógica de sesión (la usan login/refresh y el reintento). */
async function rawRequest<T>(method: string, path: string, body: unknown, opts: ReqOpts): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (opts.auth !== false && session) headers.Authorization = `Bearer ${session.access_token}`;
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), opts.timeoutMs ?? 20000);
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body), signal: ctrl.signal });
  } catch (e) {
    clearTimeout(timer);
    throw new NetworkError(e instanceof Error ? e.message : 'Sin conexión');
  }
  clearTimeout(timer);
  const text = await res.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null;
    }
  }
  if (!res.ok) {
    const err = (data as { error?: { code?: string; message?: string; details?: unknown } } | null)?.error;
    const code = err?.code ?? (res.status >= 500 ? 'SERVER' : 'HTTP_' + res.status);
    const details = err?.details as { retry_after_seconds?: unknown } | undefined;
    let retryAfter: number | null = null;
    if (typeof details?.retry_after_seconds === 'number') retryAfter = details.retry_after_seconds;
    else {
      const h = typeof res.headers?.get === 'function' ? res.headers.get('Retry-After') : null;
      if (h && /^\d+$/.test(h)) retryAfter = Number(h);
    }
    throw new ApiError(code, err?.message ?? `Error ${res.status}`, res.status, err?.details, retryAfter);
  }
  return data as T;
}

async function request<T>(method: string, path: string, body?: unknown, opts: ReqOpts = {}): Promise<T> {
  if (opts.auth !== false && session?.refresh_token && accessTokenExpiringSoon(session)) {
    // Refresco proactivo: si falla por red o 5xx seguimos con el token actual (el 401 posterior reintenta).
    try {
      await refreshSession();
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) throw e;
    }
  }
  try {
    return await rawRequest<T>(method, path, body, opts);
  } catch (e) {
    if (!(e instanceof ApiError) || opts.auth === false) throw e;
    if (e.status === 403 && e.code === 'PASSWORD_CHANGE_REQUIRED') {
      await hooks.onPasswordChangeRequired?.();
      throw e;
    }
    if (e.status !== 401) throw e;
    if (e.code === 'DEVICE_REVOKED' || !session?.refresh_token) {
      await sessionLost(e.code);
      throw e;
    }
    // AUTH_INVALID (u otro 401) con refresh token: rotar y reintentar una sola vez.
    await refreshSession(); // si falla con 401 ya cerró la sesión local; si falla por red propaga NetworkError
    return rawRequest<T>(method, path, body, opts);
  }
}

export const api = {
  // §3
  login(body: { username: string; password: string; device_id: string; device_name?: string; platform?: string }) {
    return request<LoginResponse>('POST', '/v1/auth/login', body, { auth: false });
  },
  refresh(body: { refresh_token: string; device_id: string }) {
    return request<LoginResponse>('POST', '/v1/auth/refresh', body, { auth: false });
  },
  logout() {
    return request<{ ok: boolean }>('POST', '/v1/auth/logout');
  },
  changePassword(body: { current_password: string; new_password: string }) {
    return request<{ ok: boolean }>('POST', '/v1/auth/change-password', body);
  },
  // §5 Operador
  myAssignment() {
    return request<AssignmentResponse>('GET', '/v1/me/assignment');
  },
  openShift(body: ShiftOpenPayload) {
    return request<ShiftOpenResponse>('POST', '/v1/shifts/open', body);
  },
  shiftExpected(shiftId: string) {
    return request<ShiftExpected>('GET', `/v1/shifts/${shiftId}/expected`, undefined, { timeoutMs: 8000 });
  },
  closeShift(shiftId: string, body: ShiftClosePayload) {
    return request<ShiftCloseResponse>('POST', `/v1/shifts/${shiftId}/close`, body);
  },
  createSale(body: SalePayload) {
    return request<SaleResponse>('POST', '/v1/sales', body);
  },
  cancelSale(saleId: string, body: SaleCancelPayload) {
    return request<{ sale_id: string; status: 'cancelled' }>('POST', `/v1/sales/${saleId}/cancel`, body);
  },
  createWaste(body: WastePayload) {
    return request<{ waste_id: string }>('POST', '/v1/waste', body);
  },
  createHelpCase(body: HelpCasePayload) {
    return request<HelpCaseResponse>('POST', '/v1/help-cases', body);
  },
  inventoryReceipt(body: InventoryReceiptPayload) {
    return request<{ receipt_id: string }>('POST', '/v1/inventory/receipts', body);
  },
  inventoryCount(body: InventoryCountPayload) {
    return request<{ count_id: string; differences: Record<string, number> }>('POST', '/v1/inventory/counts', body);
  },
  gpsPings(pings: GpsPing[]) {
    return request<{ accepted: number }>('POST', '/v1/gps/pings', { pings });
  },
  syncBatch(device_id: string, commands: SyncCommand[]) {
    return request<SyncBatchResponse>('POST', '/v1/sync/batch', { device_id, commands }, { timeoutMs: 30000 });
  },
  catalog() {
    return request<Catalog>('GET', '/v1/catalog');
  },
  pricesCurrent() {
    return request<PricesCurrent>('GET', '/v1/prices/current');
  },
};
