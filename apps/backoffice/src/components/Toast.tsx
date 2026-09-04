import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react';

type Kind = 'error' | 'success' | 'info';
interface Toast { id: number; kind: Kind; text: string }

interface ToastCtx {
  toast: (text: string, kind?: Kind) => void;
  error: (err: unknown, fallback?: string) => void;
}

const Ctx = createContext<ToastCtx | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const seq = useRef(0);
  const toast = useCallback((text: string, kind: Kind = 'info') => {
    const id = ++seq.current;
    setItems((xs) => [...xs, { id, kind, text }]);
    setTimeout(() => setItems((xs) => xs.filter((t) => t.id !== id)), kind === 'error' ? 6000 : 3500);
  }, []);
  const error = useCallback(
    (err: unknown, fallback = 'Ocurrió un error') => {
      const msg = err instanceof Error && err.message ? err.message : fallback;
      toast(msg, 'error');
    },
    [toast],
  );
  const value = useMemo(() => ({ toast, error }), [toast, error]);
  return (
    <Ctx.Provider value={value}>
      {children}
      <div className="toast-host" role="status" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={`toast toast-${t.kind}`}>
            {t.text}
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}

export function useToast(): ToastCtx {
  const v = useContext(Ctx);
  if (!v) throw new Error('useToast fuera de ToastProvider');
  return v;
}
