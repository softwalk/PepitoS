// Estado global de la app: lee IndexedDB y se re-lee cuando la cola/sync cambian algo.
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { getAuthSession, setAuthSession } from '../api/client';
import { readBattery, watchBattery, type BatteryInfo } from '../offline/battery';
import {
  assignmentStore,
  catalogStore,
  salesLocalStore,
  sessionStore,
  settingsStore,
  shiftStore,
  type SaleLocalRecord,
  type SessionRecord,
  type ShiftStateRecord,
} from '../offline/db';
import { setSpeechEnabled } from '../offline/speech';
import { getSyncStatus, startSync, subscribeDomain, subscribeSync, type SyncStatus } from '../offline/sync';
import { autoCleanup, installSessionHooks, refreshAssignment, resumeShift } from './actions';
import type { AssignmentResponse, Catalog, OperatorConfig } from '../types';

export interface Settings {
  audio: boolean;
  large_text: boolean;
}

export interface AppState {
  booted: boolean;
  session: SessionRecord | null;
  assignment: AssignmentResponse | null;
  catalog: Catalog | null;
  config: OperatorConfig | null;
  shift: ShiftStateRecord | null;
  sales: SaleLocalRecord[];
  sync: SyncStatus;
  battery: BatteryInfo | null;
  settings: Settings;
}

interface Ctx extends AppState {
  reload: () => Promise<void>;
  setSettings: (s: Partial<Settings>) => Promise<void>;
  clearSession: () => Promise<void>;
}

const AppContext = createContext<Ctx | null>(null);

const DEFAULT_SETTINGS: Settings = { audio: false, large_text: false };

export function AppProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AppState>({
    booted: false,
    session: null,
    assignment: null,
    catalog: null,
    config: null,
    shift: null,
    sales: [],
    sync: getSyncStatus(),
    battery: null,
    settings: DEFAULT_SETTINGS,
  });

  const reload = useCallback(async () => {
    const [session, assignment, catalog, shiftRaw, settings] = await Promise.all([
      sessionStore.get(),
      assignmentStore.get(),
      catalogStore.get(),
      shiftStore.get(),
      settingsStore.get(),
    ]);
    let shift = shiftRaw ?? null;
    if (shift && shift.status === 'closed' && (await autoCleanup())) shift = null;
    const sales = shift ? await salesLocalStore.byShift(shift.local_id) : [];
    // Activar la sesión persistida en el cliente HTTP (sin pisar un refresh más reciente en memoria).
    const cur = getAuthSession();
    if (!session) setAuthSession(null);
    else if (!cur || Date.parse(session.expires_at) >= Date.parse(cur.expires_at)) {
      setAuthSession({
        access_token: session.access_token,
        expires_at: session.expires_at,
        refresh_token: session.refresh_token ?? null,
        refresh_expires_at: session.refresh_expires_at ?? null,
        device_id: session.device_id,
      });
    }
    setState((s) => ({
      ...s,
      booted: true,
      session: session ?? null,
      assignment: assignment?.data ?? null,
      catalog: catalog?.catalog ?? assignment?.data.catalog ?? null,
      config: catalog?.config ?? assignment?.data.config ?? null,
      shift,
      sales,
      settings: settings ? { audio: settings.audio, large_text: settings.large_text } : DEFAULT_SETTINGS,
    }));
  }, []);

  useEffect(() => {
    installSessionHooks({ onChange: () => void reload() });
    (async () => {
      await reload();
      startSync();
      await resumeShift();
      const boot = await sessionStore.get();
      if (navigator.onLine && boot && !boot.must_change_password) {
        try {
          await refreshAssignment();
          await reload();
        } catch {
          /* offline: se usa lo guardado */
        }
      }
    })();
    // Cambios hechos desde el backoffice (p. ej. admin "Continuar turno" sobre un turno cerrado) llegan al
    // volver a la app o, si no hay turno abierto localmente, en el siguiente sondeo de 60 s.
    let refreshing = false;
    const refreshFromServer = async () => {
      if (refreshing || !navigator.onLine) return;
      const sess = await sessionStore.get();
      if (!sess || sess.must_change_password) return;
      // Sólo cuando no hay turno abierto en el teléfono: no re-descargar catálogo/config a mitad de una venta.
      const st = await shiftStore.get();
      if (st && st.status !== 'closed') return;
      refreshing = true;
      try {
        await refreshAssignment();
        await reload();
      } catch {
        /* sin red: se usa lo guardado */
      } finally {
        refreshing = false;
      }
    };
    const onVisible = () => {
      if (document.visibilityState === 'visible') void refreshFromServer();
    };
    document.addEventListener('visibilitychange', onVisible);
    const poll = setInterval(() => void refreshFromServer(), 60_000);
    const unsubSync = subscribeSync((sync) => setState((s) => ({ ...s, sync })));
    const unsubDomain = subscribeDomain(() => void reload());
    const unsubBattery = watchBattery((battery) => setState((s) => ({ ...s, battery })));
    void readBattery().then((battery) => setState((s) => ({ ...s, battery })));
    return () => {
      document.removeEventListener('visibilitychange', onVisible);
      clearInterval(poll);
      unsubSync();
      unsubDomain();
      unsubBattery();
    };
  }, [reload]);

  useEffect(() => {
    setSpeechEnabled(state.settings.audio);
    document.documentElement.classList.toggle('large-text', state.settings.large_text);
  }, [state.settings]);

  const setSettings = useCallback(
    async (patch: Partial<Settings>) => {
      const next = { ...state.settings, ...patch };
      await settingsStore.set(next);
      setState((s) => ({ ...s, settings: next }));
    },
    [state.settings],
  );

  const clearSession = useCallback(async () => {
    await reload();
  }, [reload]);

  const value = useMemo<Ctx>(() => ({ ...state, reload, setSettings, clearSession }), [state, reload, setSettings, clearSession]);
  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): Ctx {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp fuera de AppProvider');
  return ctx;
}

export function shiftIsOpen(shift: ShiftStateRecord | null): boolean {
  return !!shift && (shift.status === 'open' || shift.status === 'open_pending');
}

export function money(cents: number): string {
  const v = cents / 100;
  return '$' + v.toLocaleString('es-MX', { minimumFractionDigits: v % 1 === 0 ? 0 : 2, maximumFractionDigits: 2 });
}
