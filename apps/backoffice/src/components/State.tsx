/** Estados diferenciados: un espacio vacío no debe significar «sin registros», «sin permiso», «sin conexión» y
 *  «error» a la vez. `stateFromError` clasifica el mensaje/código de la API. */
import { useEffect, useState } from 'react';
import { ApiError } from '../api/client';

export type StateKind = 'empty' | 'pending' | 'forbidden' | 'offline' | 'error' | 'updated';

const PRESET: Record<StateKind, { icon: string; title: string; text: string; cls: string }> = {
  empty: { icon: '📭', title: 'Sin registros', text: 'No hay datos para este filtro o periodo.', cls: 'empty' },
  pending: { icon: '⏳', title: 'Información pendiente', text: 'Hay turnos abiertos o registros sin sincronizar; las cifras cambiarán.', cls: 'pending' },
  forbidden: { icon: '🔒', title: 'No tienes permiso', text: 'Tu rol no puede ver esta sección. Pide acceso a un administrador.', cls: 'forbidden' },
  offline: { icon: '📡', title: 'Sin conexión con el servidor', text: 'Revisa la red. Se mostrará lo último que se pudo cargar.', cls: 'offline' },
  error: { icon: '⚠️', title: 'No se pudo cargar', text: 'Ocurrió un error en el servidor. Intenta de nuevo.', cls: 'error' },
  updated: { icon: '✅', title: 'Datos actualizados', text: '', cls: 'updated' },
};

export function stateFromError(e: unknown): StateKind {
  if (e instanceof ApiError) return e.status === 403 ? 'forbidden' : e.status === 0 ? 'offline' : 'error';
  const msg = String((e as Error)?.message ?? e ?? '');
  if (/permiso|forbidden/i.test(msg)) return 'forbidden';
  if (/conexi|network|fetch|failed to/i.test(msg)) return 'offline';
  return 'error';
}

export function StateBox({ kind, title, text, error }: { kind: StateKind; title?: string; text?: string; error?: string | null }) {
  const p = PRESET[kind];
  return (
    <div className={`state-box ${p.cls}`} role={kind === 'forbidden' || kind === 'error' ? 'alert' : 'status'} data-testid={`state-${kind}`}>
      <span className="state-ico" aria-hidden>{p.icon}</span>
      <div>
        <b>{title ?? p.title}</b>
        <span>{text ?? p.text}{error ? ` (${error})` : ''}</span>
      </div>
    </div>
  );
}

/** Aviso flotante cuando el navegador pierde la red. */
export function OfflineBanner() {
  const [online, setOnline] = useState(typeof navigator === 'undefined' ? true : navigator.onLine);
  useEffect(() => {
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    window.addEventListener('online', on);
    window.addEventListener('offline', off);
    return () => {
      window.removeEventListener('online', on);
      window.removeEventListener('offline', off);
    };
  }, []);
  if (online) return null;
  return (
    <div className="offline-banner" role="status" data-testid="offline-banner">
      📡 Sin conexión · los datos pueden estar desactualizados
    </div>
  );
}
