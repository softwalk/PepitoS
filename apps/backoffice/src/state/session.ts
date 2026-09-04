// Sesión persistida en localStorage (access + refresh token) + device_id UUID estable por navegador.
import type { AuthUser, LoginResponse } from '../types';

const KEY = 'pepito.backoffice.session';
const DEVICE_KEY = 'pepito.device_id';

export interface Session {
  token: string;
  user: AuthUser;
  /** Vencimiento del access token (ms epoch). */
  expiresAt: number;
  /** Refresh token rotativo (ausente en sesiones guardadas por versiones anteriores). */
  refreshToken?: string | null;
  /** Vencimiento del refresh token (ms epoch). */
  refreshExpiresAt?: number | null;
  /** El servidor exige cambiar la contraseña antes de usar el resto de la API. */
  mustChangePassword?: boolean;
}

function uuid(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID();
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16);
  });
}

export function getDeviceId(): string {
  try {
    let id = localStorage.getItem(DEVICE_KEY);
    if (!id) {
      id = uuid();
      localStorage.setItem(DEVICE_KEY, id);
    }
    return id;
  } catch {
    return uuid();
  }
}

/** true si el refresh token existe y no ha vencido. */
export function canRefresh(s: Session | null): boolean {
  return !!s?.refreshToken && (!s.refreshExpiresAt || s.refreshExpiresAt > Date.now());
}

/** true si el access token ya venció (o vence en `aheadMs`). */
export function accessExpired(s: Session, aheadMs = 0): boolean {
  return !!s.expiresAt && s.expiresAt - aheadMs < Date.now();
}

/**
 * Sesión guardada. Devuelve null si no hay o si ya no sirve: access token vencido sin refresh token
 * utilizable. Con refresh token vigente se devuelve aunque el access token haya vencido (se renueva solo).
 */
export function getSession(): Session | null {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    const s = JSON.parse(raw) as Session;
    if (!s.token) return null;
    if (accessExpired(s) && !canRefresh(s)) return null;
    return s;
  } catch {
    return null;
  }
}

export function sessionFromLogin(res: LoginResponse): Session {
  return {
    token: res.access_token,
    user: res.user,
    expiresAt: Date.now() + res.expires_in * 1000,
    refreshToken: res.refresh_token ?? null,
    refreshExpiresAt: res.refresh_expires_at ? Date.parse(res.refresh_expires_at) : null,
    mustChangePassword: !!res.must_change_password,
  };
}

export function saveSession(s: Session) {
  try {
    localStorage.setItem(KEY, JSON.stringify(s));
  } catch {
    /* ignore */
  }
}

export function clearSession() {
  try {
    localStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
}
