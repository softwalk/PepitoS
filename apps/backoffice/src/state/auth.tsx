import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { api, commitSession, onSessionChanged, onUnauthorized, refreshSession as clientRefreshSession } from '../api/client';
import type { AuthUser, LoginResponse, Role } from '../types';
import { clearSession, getDeviceId, getSession, sessionFromLogin, type Session } from './session';

interface AuthCtx {
  session: Session | null;
  user: AuthUser | null;
  /** El servidor exige cambiar la contraseña antes de seguir. */
  mustChangePassword: boolean;
  login: (username: string, password: string) => Promise<LoginResponse>;
  logout: () => Promise<void>;
  /** Rota el refresh token y reemplaza ambos tokens (lock en el cliente HTTP). */
  refresh: () => Promise<LoginResponse | null>;
  changePassword: (current_password: string, new_password: string) => Promise<void>;
  hasRole: (...roles: Role[]) => boolean;
}

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(() => getSession());

  useEffect(() => {
    const offUnauthorized = onUnauthorized(() => setSession(null));
    const offChanged = onSessionChanged((s) => setSession(s));
    return () => {
      offUnauthorized();
      offChanged();
    };
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const res = await api.post<LoginResponse>('/v1/auth/login', {
      username,
      password,
      device_id: getDeviceId(),
      device_name: navigator.userAgent.slice(0, 80),
      platform: 'web-backoffice',
    });
    commitSession(sessionFromLogin(res));
    return res;
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.post('/v1/auth/logout');
    } catch {
      /* el token puede haber expirado; limpiamos igual */
    }
    clearSession();
    setSession(null);
  }, []);

  const refresh = useCallback(() => clientRefreshSession(), []);

  const changePassword = useCallback(async (current_password: string, new_password: string) => {
    await api.post<{ ok: boolean }>('/v1/auth/change-password', { current_password, new_password });
    const s = getSession();
    if (s) commitSession({ ...s, mustChangePassword: false });
  }, []);

  const value = useMemo<AuthCtx>(
    () => ({
      session,
      user: session?.user ?? null,
      mustChangePassword: !!session?.mustChangePassword,
      login,
      logout,
      refresh,
      changePassword,
      hasRole: (...roles: Role[]) => !!session && roles.includes(session.user.role),
    }),
    [session, login, logout, refresh, changePassword],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthCtx {
  const v = useContext(Ctx);
  if (!v) throw new Error('useAuth fuera de AuthProvider');
  return v;
}
