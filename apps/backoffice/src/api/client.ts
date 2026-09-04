// Cliente HTTP mínimo: token bearer, device_id persistido, errores del backend con `message`.
// Sesión: refresh token rotativo (localStorage). Ante 401 AUTH_INVALID refresca una vez y reintenta;
// si el access token vence en <5 min refresca antes de la petición.
import { accessExpired, canRefresh, clearSession, getDeviceId, getSession, saveSession, sessionFromLogin, type Session } from '../state/session';
import type { LoginResponse } from '../types';

export class ApiError extends Error {
  code: string;
  status: number;
  details: unknown;
  /** Segundos a esperar (429 RATE_LIMITED): `details.retry_after_seconds` o header Retry-After. */
  retryAfterSeconds: number | null;
  constructor(status: number, code: string, message: string, details?: unknown, retryAfterSeconds: number | null = null) {
    super(message);
    this.code = code;
    this.status = status;
    this.details = details;
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

// Rutas relativas: en dev/preview Vite hace proxy de /v1 hacia VITE_API_URL; en prod el mismo host sirve /v1.
const BASE = '';

/** Refrescar proactivamente si el access token vence en menos de este margen. */
export const REFRESH_AHEAD_MS = 5 * 60_000;

type Listener = (err: ApiError) => void;
const unauthorizedListeners: Listener[] = [];
/** La sesión se cerró localmente (refresh inválido/expirado, dispositivo revocado). */
export function onUnauthorized(fn: Listener) {
  unauthorizedListeners.push(fn);
  return () => {
    const i = unauthorizedListeners.indexOf(fn);
    if (i >= 0) unauthorizedListeners.splice(i, 1);
  };
}

type SessionListener = (s: Session | null) => void;
const sessionListeners: SessionListener[] = [];
/** Cambió la sesión persistida (tokens rotados, must_change_password). */
export function onSessionChanged(fn: SessionListener) {
  sessionListeners.push(fn);
  return () => {
    const i = sessionListeners.indexOf(fn);
    if (i >= 0) sessionListeners.splice(i, 1);
  };
}

function notifySession(s: Session | null) {
  sessionListeners.forEach((fn) => fn(s));
}

/** Guarda la sesión y avisa a la UI. */
export function commitSession(s: Session) {
  saveSession(s);
  notifySession(s);
}

function dropSession(err: ApiError) {
  clearSession();
  notifySession(null);
  unauthorizedListeners.forEach((fn) => fn(err));
}

/** Marca la sesión actual como "debe cambiar contraseña" (403 PASSWORD_CHANGE_REQUIRED). */
function markPasswordChangeRequired() {
  const s = getSession();
  if (s && !s.mustChangePassword) commitSession({ ...s, mustChangePassword: true });
}

let refreshing: Promise<LoginResponse | null> | null = null;

/**
 * Rota el refresh token (`POST /v1/auth/refresh`) con el device_id persistido y reemplaza ambos tokens.
 * Con lock: llamadas simultáneas comparten la petición. Devuelve null si no hay refresh token utilizable.
 * Si el servidor responde 401 la sesión local se cierra y se relanza el error.
 */
export function refreshSession(): Promise<LoginResponse | null> {
  if (refreshing) return refreshing;
  const cur = getSession();
  if (!cur || !canRefresh(cur)) return Promise.resolve(null);
  refreshing = (async () => {
    let res: LoginResponse;
    try {
      res = await rawRequest<LoginResponse>('POST', '/v1/auth/refresh', { refresh_token: cur.refreshToken, device_id: getDeviceId() }, { auth: false });
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) dropSession(e);
      throw e;
    }
    commitSession(sessionFromLogin(res));
    return res;
  })().finally(() => {
    refreshing = null;
  });
  return refreshing;
}

interface ReqOpts {
  auth?: boolean;
}

async function rawRequest<T>(method: string, path: string, body: unknown, opts: ReqOpts): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  const session = getSession();
  if (opts.auth !== false && session?.token) headers.Authorization = `Bearer ${session.token}`;
  let res: Response;
  try {
    res = await fetch(BASE + path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch {
    throw new ApiError(0, 'NETWORK', 'Sin conexión con el servidor');
  }
  let data: unknown = null;
  const text = await res.text();
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null;
    }
  }
  if (!res.ok) {
    const e = (data as { error?: { code?: string; message?: string; details?: unknown } } | null)?.error;
    const details = e?.details as { retry_after_seconds?: unknown } | undefined;
    let retryAfter: number | null = null;
    if (typeof details?.retry_after_seconds === 'number') retryAfter = details.retry_after_seconds;
    else {
      const h = typeof res.headers?.get === 'function' ? res.headers.get('Retry-After') : null;
      if (h && /^\d+$/.test(h)) retryAfter = Number(h);
    }
    throw new ApiError(res.status, e?.code || `HTTP_${res.status}`, e?.message || `Error ${res.status}`, e?.details, retryAfter);
  }
  return data as T;
}

export async function request<T>(method: string, path: string, body?: unknown, opts: ReqOpts = {}): Promise<T> {
  if (opts.auth !== false) {
    const s = getSession();
    if (s && canRefresh(s) && accessExpired(s, REFRESH_AHEAD_MS)) {
      // Refresco proactivo; si falla por red/5xx seguimos con el token actual (el 401 posterior reintenta).
      try {
        await refreshSession();
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) throw e;
      }
    }
  }
  try {
    return await rawRequest<T>(method, path, body, opts);
  } catch (e) {
    if (!(e instanceof ApiError) || opts.auth === false) throw e;
    if (e.status === 403 && e.code === 'PASSWORD_CHANGE_REQUIRED') {
      markPasswordChangeRequired();
      throw e;
    }
    if (e.status !== 401) throw e;
    const s = getSession();
    if (e.code === 'DEVICE_REVOKED' || !s || !canRefresh(s)) {
      dropSession(e);
      throw e;
    }
    // AUTH_INVALID con refresh token: rotar y reintentar una sola vez.
    await refreshSession(); // 401 aquí ya cerró la sesión local
    return rawRequest<T>(method, path, body, opts);
  }
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body ?? {}),
  put: <T>(path: string, body?: unknown) => request<T>('PUT', path, body),
  patch: <T>(path: string, body?: unknown) => request<T>('PATCH', path, body),
  del: <T>(path: string) => request<T>('DELETE', path),
};

export function qs(params: Record<string, string | number | undefined | null>): string {
  const parts = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
  return parts.length ? `?${parts.join('&')}` : '';
}
