// Cliente HTTP mínimo: token bearer, device_id persistido, errores del backend con `message`.
import { getSession, clearSession } from '../state/session';

export class ApiError extends Error {
  code: string;
  status: number;
  details: unknown;
  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

// Rutas relativas: en dev/preview Vite hace proxy de /v1 hacia VITE_API_URL; en prod el mismo host sirve /v1.
const BASE = '';

type Listener = (err: ApiError) => void;
const unauthorizedListeners: Listener[] = [];
export function onUnauthorized(fn: Listener) {
  unauthorizedListeners.push(fn);
  return () => {
    const i = unauthorizedListeners.indexOf(fn);
    if (i >= 0) unauthorizedListeners.splice(i, 1);
  };
}

export async function request<T>(method: string, path: string, body?: unknown, opts: { auth?: boolean } = {}): Promise<T> {
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
    const err = new ApiError(res.status, e?.code || `HTTP_${res.status}`, e?.message || `Error ${res.status}`, e?.details);
    if (res.status === 401 && opts.auth !== false) {
      clearSession();
      unauthorizedListeners.forEach((fn) => fn(err));
    }
    throw err;
  }
  return data as T;
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
