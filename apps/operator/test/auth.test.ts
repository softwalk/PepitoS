// Sesión: refresh rotativo, reintento único ante 401 y cierre de sesión local conservando la cola cifrada.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api, ApiError, getAuthSession, NetworkError, refreshSession, setAuthSession } from '../src/api/client';
import { resetDBForTests, sessionStore } from '../src/offline/db';
import { counts, enqueue, listAll } from '../src/offline/queue';
import { syncNow } from '../src/offline/sync';
import { installSessionHooks, persistSession } from '../src/state/actions';
import type { LoginResponse } from '../src/types';

const USER = { id: 'u1', name: 'Op 1', role: 'operator' as const, zone_id: null, username: 'op1' };

function loginResponse(over: Partial<LoginResponse> = {}): LoginResponse {
  return {
    access_token: 'access-1',
    token_type: 'bearer',
    expires_in: 12 * 3600,
    refresh_token: 'refresh-1',
    refresh_expires_at: '2030-01-01T00:00:00Z',
    user: USER,
    must_change_password: false,
    ...over,
  };
}

type Call = { path: string; auth: string | null; body: unknown };
const calls: Call[] = [];

function jsonResponse(status: number, body: unknown, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json', ...headers } });
}

function apiError(status: number, code: string, details?: unknown, headers?: Record<string, string>) {
  return jsonResponse(status, { error: { code, message: code, details } }, headers);
}

/** Servidor falso: responde según el token presentado y rota el refresh token. */
function mockServer(opts: { valid?: Set<string>; refreshOk?: boolean; refreshError?: Response | (() => Response) } = {}) {
  const valid = opts.valid ?? new Set(['access-1']);
  let n = 1;
  const fetchMock = vi.fn(async (url: string, init: RequestInit) => {
    const path = String(url);
    const headers = init.headers as Record<string, string>;
    const body = init.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ path, auth: headers.Authorization ?? null, body });
    if (path.endsWith('/v1/auth/refresh')) {
      if (opts.refreshError) return typeof opts.refreshError === 'function' ? opts.refreshError() : opts.refreshError.clone();
      if (opts.refreshOk === false || body.refresh_token !== `refresh-${n}`) return apiError(401, 'AUTH_INVALID');
      n += 1;
      valid.add(`access-${n}`);
      return jsonResponse(200, loginResponse({ access_token: `access-${n}`, refresh_token: `refresh-${n}` }));
    }
    const token = headers.Authorization?.replace('Bearer ', '') ?? '';
    if (!valid.has(token)) return apiError(401, 'AUTH_INVALID');
    if (path.endsWith('/v1/sync/batch')) {
      return jsonResponse(200, { results: (body.commands as { idempotency_key: string }[]).map((c) => ({ idempotency_key: c.idempotency_key, status: 'ok', result: {} })) });
    }
    if (path.endsWith('/v1/me/assignment')) return jsonResponse(200, { assignment: null, active_shift: null, catalog: { presentations: [], flavors: [], price_version_id: 'pv' }, config: {} });
    return jsonResponse(200, { ok: true });
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

let changes = 0;

beforeEach(async () => {
  calls.length = 0;
  changes = 0;
  await resetDBForTests();
  setAuthSession(null);
  installSessionHooks({ onChange: () => changes++ });
  await persistSession(loginResponse(), 'dev-1');
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('refresh de sesión', () => {
  it('reemplaza ambos tokens en memoria y en IndexedDB usando el device_id persistido', async () => {
    mockServer();
    const res = await refreshSession();
    expect(res?.access_token).toBe('access-2');
    expect(calls[0].path).toContain('/v1/auth/refresh');
    expect(calls[0].body).toEqual({ refresh_token: 'refresh-1', device_id: 'dev-1' });
    expect(calls[0].auth).toBeNull();
    expect(getAuthSession()).toMatchObject({ access_token: 'access-2', refresh_token: 'refresh-2', device_id: 'dev-1' });
    const stored = await sessionStore.get();
    expect(stored).toMatchObject({ access_token: 'access-2', refresh_token: 'refresh-2', refresh_expires_at: '2030-01-01T00:00:00Z', device_id: 'dev-1' });
    expect(Date.parse(stored!.expires_at)).toBeGreaterThan(Date.now() + 11 * 3600_000);
  });

  it('con lock: dos refresh simultáneos comparten una sola petición', async () => {
    mockServer();
    const [a, b] = await Promise.all([refreshSession(), refreshSession()]);
    expect(a?.access_token).toBe('access-2');
    expect(b?.access_token).toBe('access-2');
    expect(calls.filter((c) => c.path.includes('/v1/auth/refresh'))).toHaveLength(1);
  });

  it('sin refresh token no hace nada', async () => {
    mockServer();
    setAuthSession({ ...getAuthSession()!, refresh_token: null });
    expect(await refreshSession()).toBeNull();
    expect(calls).toHaveLength(0);
  });
});

describe('401 → refresh → reintento', () => {
  it('reintenta una sola vez la petición con el token nuevo', async () => {
    mockServer({ valid: new Set(['access-0']) }); // access-1 (actual) ya no vale
    const r = await api.myAssignment();
    expect(r).toMatchObject({ assignment: null });
    expect(calls.map((c) => c.path.replace(/^.*\/v1/, '/v1'))).toEqual(['/v1/me/assignment', '/v1/auth/refresh', '/v1/me/assignment']);
    expect(calls[0].auth).toBe('Bearer access-1');
    expect(calls[2].auth).toBe('Bearer access-2');
    expect((await sessionStore.get())?.access_token).toBe('access-2');
    expect(changes).toBe(0);
  });

  it('refresca proactivamente si el access token vence en menos de 5 minutos', async () => {
    mockServer();
    setAuthSession({ ...getAuthSession()!, expires_at: new Date(Date.now() + 60_000).toISOString() });
    await api.myAssignment();
    expect(calls.map((c) => c.path.replace(/^.*\/v1/, '/v1'))).toEqual(['/v1/auth/refresh', '/v1/me/assignment']);
    expect(calls[1].auth).toBe('Bearer access-2');
  });

  it('la cola offline sincroniza tras refrescar sin pedir login', async () => {
    mockServer({ valid: new Set(['access-0']) });
    await enqueue('sale', { shift_id: 'srv-1' }, 'k1');
    await syncNow();
    expect(await counts()).toEqual({ pending: 0, failed: 0 });
    const paths = calls.map((c) => c.path.replace(/^.*\/v1/, '/v1'));
    expect(paths).toEqual(['/v1/sync/batch', '/v1/auth/refresh', '/v1/sync/batch']);
    expect(calls[2].auth).toBe('Bearer access-2');
    expect(await sessionStore.get()).toMatchObject({ access_token: 'access-2' });
  });

  it('403 PASSWORD_CHANGE_REQUIRED marca la sesión para cambiar contraseña', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => apiError(403, 'PASSWORD_CHANGE_REQUIRED')),
    );
    await expect(api.myAssignment()).rejects.toMatchObject({ code: 'PASSWORD_CHANGE_REQUIRED' });
    expect((await sessionStore.get())?.must_change_password).toBe(true);
    expect(changes).toBe(1);
  });
});

describe('refresh fallido', () => {
  it('401 al refrescar → sesión local limpia y cola cifrada conservada', async () => {
    mockServer({ valid: new Set(['access-0']), refreshOk: false });
    await enqueue('sale', { shift_id: 'srv-1', n: 1 }, 'k1');
    await enqueue('waste', { shift_id: 'srv-1', n: 2 }, 'k2');
    await expect(api.myAssignment()).rejects.toBeInstanceOf(ApiError);
    expect(calls.map((c) => c.path.replace(/^.*\/v1/, '/v1'))).toEqual(['/v1/me/assignment', '/v1/auth/refresh']);
    expect(getAuthSession()).toBeNull();
    expect(await sessionStore.get()).toBeUndefined();
    expect(changes).toBe(1);
    expect(await counts()).toEqual({ pending: 2, failed: 0 });
    const all = await listAll(); // sigue descifrable: la clave no se borró
    expect(all.map((c) => c.payload.n)).toEqual([1, 2]);
  });

  it('DEVICE_REVOKED cierra sesión sin intentar refresh', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => apiError(401, 'DEVICE_REVOKED')),
    );
    await expect(api.myAssignment()).rejects.toMatchObject({ code: 'DEVICE_REVOKED' });
    expect(vi.mocked(fetch)).toHaveBeenCalledTimes(1);
    expect(getAuthSession()).toBeNull();
    expect(await sessionStore.get()).toBeUndefined();
  });

  it('sin red al refrescar: propaga NetworkError y conserva la sesión (se reintenta luego)', async () => {
    let first = true;
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (String(url).includes('/v1/auth/refresh')) throw new TypeError('Failed to fetch');
        if (first) {
          first = false;
          return apiError(401, 'AUTH_INVALID');
        }
        return jsonResponse(200, {});
      }),
    );
    await expect(api.myAssignment()).rejects.toBeInstanceOf(NetworkError);
    expect(getAuthSession()?.access_token).toBe('access-1');
    expect(await sessionStore.get()).toBeDefined();
  });

  it('429 RATE_LIMITED en login expone retry_after_seconds', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => apiError(429, 'RATE_LIMITED', { retry_after_seconds: 540 }, { 'Retry-After': '540' })),
    );
    const err = await api.login({ username: 'op1', password: 'x', device_id: 'dev-1' }).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(429);
    expect(err.retryAfterSeconds).toBe(540);
  });
});
