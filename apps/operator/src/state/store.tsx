// Estado global de la app: lee IndexedDB y se re-lee cuando la cola/sync cambian algo.
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { configureClient, setAuthToken } from '../api/client';
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
import { autoCleanup, refreshAssignment, resumeShift } from './actions';
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
    setAuthToken(session?.access_token ?? null);
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
    configureClient({
      onUnauthorized: (code) => {
        // Token expirado o dispositivo revocado: cerrar sesión localmente (la cola cifrada se conserva).
        if (code === 'DEVICE_REVOKED' || code === 'AUTH_INVALID') {
          void sessionStore.clear().then(reload);
        }
      },
    });
    (async () => {
      await reload();
      startSync();
      await resumeShift();
      if (navigator.onLine && (await sessionStore.get())) {
        try {
          await refreshAssignment();
          await reload();
        } catch {
          /* offline: se usa lo guardado */
        }
      }
    })();
    const unsubSync = subscribeSync((sync) => setState((s) => ({ ...s, sync })));
    const unsubDomain = subscribeDomain(() => void reload());
    const unsubBattery = watchBattery((battery) => setState((s) => ({ ...s, battery })));
    void readBattery().then((battery) => setState((s) => ({ ...s, battery })));
    return () => {
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
