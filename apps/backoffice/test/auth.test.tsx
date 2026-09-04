// Sesión del backoffice: refresh rotativo en localStorage, reintento único ante 401, cierre de sesión y 429.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { api, ApiError, onUnauthorized, refreshSession } from '../src/api/client';
import { getSession, saveSession, type Session } from '../src/state/session';
import { AuthProvider } from '../src/state/auth';
import { ToastProvider } from '../src/components/Toast';
import { LoginPage } from '../src/pages/Login';
import App from '../src/App';
import type { LoginResponse } from '../src/types';

const USER = { id: 'u1', name: 'Ops', role: 'ops' as const, zone_id: null, username: 'ops' };

function loginResponse(over: Partial<LoginResponse> = {}): LoginResponse {
  return { access_token: 'access-1', token_type: 'bearer', expires_in: 900, refresh_token: 'refresh-1', refresh_expires_at: '2030-01-01T00:00:00Z', user: USER, must_change_password: false, ...over };
}

function json(status: number, body: unknown, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json', ...headers } });
}
function apiError(status: number, code: string, details?: unknown, headers?: Record<string, string>) {
  return json(status, { error: { code, message: code, details } }, headers);
}

type Call = { path: string; auth: string | null; body: unknown };
const calls: Call[] = [];

function mockServer(opts: { valid?: Set<string>; refreshOk?: boolean } = {}) {
  const valid = opts.valid ?? new Set(['access-1']);
  let n = 1;
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init: RequestInit) => {
      const path = String(url);
      const headers = init.headers as Record<string, string>;
      const body = init.body ? JSON.parse(String(init.body)) : undefined;
      calls.push({ path, auth: headers.Authorization ?? null, body });
      if (path === '/v1/auth/refresh') {
        if (opts.refreshOk === false || body.refresh_token !== `refresh-${n}`) return apiError(401, 'AUTH_INVALID');
        n += 1;
        valid.add(`access-${n}`);
        return json(200, loginResponse({ access_token: `access-${n}`, refresh_token: `refresh-${n}` }));
      }
      const token = headers.Authorization?.replace('Bearer ', '') ?? '';
      if (!valid.has(token)) return apiError(401, 'AUTH_INVALID');
      return json(200, { ok: true, path });
    }),
  );
}

function seedSession(over: Partial<Session> = {}) {
  saveSession({ token: 'access-1', user: USER, expiresAt: Date.now() + 900_000, refreshToken: 'refresh-1', refreshExpiresAt: Date.parse('2030-01-01T00:00:00Z'), mustChangePassword: false, ...over });
}

beforeEach(() => {
  calls.length = 0;
  localStorage.clear();
  localStorage.setItem('pepito.device_id', 'dev-1');
  seedSession();
});
afterEach(() => vi.unstubAllGlobals());

describe('refresh', () => {
  it('reemplaza ambos tokens en localStorage usando el device_id persistido', async () => {
    mockServer();
    const res = await refreshSession();
    expect(res?.access_token).toBe('access-2');
    expect(calls[0]).toMatchObject({ path: '/v1/auth/refresh', auth: null, body: { refresh_token: 'refresh-1', device_id: 'dev-1' } });
    const s = getSession();
    expect(s).toMatchObject({ token: 'access-2', refreshToken: 'refresh-2', user: USER });
    expect(s!.expiresAt).toBeGreaterThan(Date.now() + 800_000);
  });

  it('con lock: dos refresh simultáneos comparten una petición', async () => {
    mockServer();
    const [a, b] = await Promise.all([refreshSession(), refreshSession()]);
    expect(a?.access_token).toBe('access-2');
    expect(b?.access_token).toBe('access-2');
    expect(calls.filter((c) => c.path === '/v1/auth/refresh')).toHaveLength(1);
  });

  it('401 → refresh → reintento único con el token nuevo', async () => {
    mockServer({ valid: new Set(['access-0']) });
    const r = await api.get<{ path: string }>('/v1/control-tower/summary');
    expect(r.path).toBe('/v1/control-tower/summary');
    expect(calls.map((c) => c.path)).toEqual(['/v1/control-tower/summary', '/v1/auth/refresh', '/v1/control-tower/summary']);
    expect(calls[2].auth).toBe('Bearer access-2');
  });

  it('refresca proactivamente si el access token vence en <5 min', async () => {
    mockServer();
    seedSession({ expiresAt: Date.now() + 60_000 });
    await api.get('/v1/x');
    expect(calls.map((c) => c.path)).toEqual(['/v1/auth/refresh', '/v1/x']);
    expect(calls[1].auth).toBe('Bearer access-2');
  });

  it('getSession conserva una sesión con access vencido pero refresh vigente', () => {
    seedSession({ expiresAt: Date.now() - 1000 });
    expect(getSession()?.token).toBe('access-1');
    seedSession({ expiresAt: Date.now() - 1000, refreshToken: null });
    expect(getSession()).toBeNull();
  });

  it('refresh fallido con 401 → sesión limpia y aviso a la UI', async () => {
    mockServer({ valid: new Set(['access-0']), refreshOk: false });
    const lost: string[] = [];
    const off = onUnauthorized((e) => lost.push(e.code));
    await expect(api.get('/v1/x')).rejects.toBeInstanceOf(ApiError);
    off();
    expect(calls.map((c) => c.path)).toEqual(['/v1/x', '/v1/auth/refresh']);
    expect(getSession()).toBeNull();
    expect(lost).toEqual(['AUTH_INVALID']);
  });

  it('DEVICE_REVOKED cierra sesión sin refresh', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => apiError(401, 'DEVICE_REVOKED')));
    await expect(api.get('/v1/x')).rejects.toMatchObject({ code: 'DEVICE_REVOKED' });
    expect(vi.mocked(fetch)).toHaveBeenCalledTimes(1);
    expect(getSession()).toBeNull();
  });

  it('403 PASSWORD_CHANGE_REQUIRED marca mustChangePassword', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => apiError(403, 'PASSWORD_CHANGE_REQUIRED')));
    await expect(api.get('/v1/x')).rejects.toMatchObject({ code: 'PASSWORD_CHANGE_REQUIRED' });
    expect(getSession()?.mustChangePassword).toBe(true);
  });
});

describe('LoginPage', () => {
  it('429 RATE_LIMITED muestra cuenta regresiva y deshabilita el botón', async () => {
    localStorage.clear();
    vi.stubGlobal('fetch', vi.fn(async () => apiError(429, 'RATE_LIMITED', { retry_after_seconds: 540 }, { 'Retry-After': '540' })));
    render(
      <MemoryRouter initialEntries={['/login']}>
        <ToastProvider>
          <AuthProvider>
            <LoginPage />
          </AuthProvider>
        </ToastProvider>
      </MemoryRouter>,
    );
    const { fireEvent } = await import('@testing-library/react');
    fireEvent.change(screen.getByLabelText('Usuario'), { target: { value: 'ops' } });
    fireEvent.change(screen.getByLabelText('Contraseña'), { target: { value: 'x' } });
    fireEvent.click(screen.getByRole('button', { name: 'Entrar' }));
    await waitFor(() => expect(screen.getByTestId('rate-limited')).toHaveTextContent('Demasiados intentos. Espera 9 minutos'));
    expect(screen.getByRole('button', { name: /Espera 9:00|Espera 8:59/ })).toBeDisabled();
  });
});

describe('Guard', () => {
  it('con must_change_password redirige a /cambiar-contrasena', async () => {
    seedSession({ mustChangePassword: true });
    vi.stubGlobal('fetch', vi.fn(async () => apiError(403, 'PASSWORD_CHANGE_REQUIRED')));
    render(
      <MemoryRouter initialEntries={['/ct']}>
        <ToastProvider>
          <AuthProvider>
            <App />
          </AuthProvider>
        </ToastProvider>
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByTestId('change-password-form')).toBeInTheDocument());
    expect(screen.getByRole('heading', { name: 'Cambiar contraseña' })).toBeInTheDocument();
  });
});
