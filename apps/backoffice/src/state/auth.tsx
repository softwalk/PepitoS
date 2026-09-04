import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { api, onUnauthorized } from '../api/client';
import type { AuthUser, LoginResponse, Role } from '../types';
import { clearSession, getDeviceId, getSession, saveSession, type Session } from './session';

interface AuthCtx {
  session: Session | null;
  user: AuthUser | null;
  login: (username: string, password: string) => Promise<AuthUser>;
  logout: () => Promise<void>;
  hasRole: (...roles: Role[]) => boolean;
}

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(() => getSession());

  useEffect(() => onUnauthorized(() => setSession(null)), []);

  const login = useCallback(async (username: string, password: string) => {
    const res = await api.post<LoginResponse>('/v1/auth/login', {
      username,
      password,
      device_id: getDeviceId(),
      device_name: navigator.userAgent.slice(0, 80),
      platform: 'web-backoffice',
    });
    const s: Session = { token: res.access_token, user: res.user, expiresAt: Date.now() + res.expires_in * 1000 };
    saveSession(s);
    setSession(s);
    return res.user;
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

  const value = useMemo<AuthCtx>(
    () => ({
      session,
      user: session?.user ?? null,
      login,
      logout,
      hasRole: (...roles: Role[]) => !!session && roles.includes(session.user.role),
    }),
    [session, login, logout],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthCtx {
  const v = useContext(Ctx);
  if (!v) throw new Error('useAuth fuera de AuthProvider');
  return v;
}
