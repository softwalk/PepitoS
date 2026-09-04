import { useCallback, useEffect, useRef, useState } from 'react';
import { useToast } from '../components/Toast';

interface Options {
  /** ms entre refrescos automáticos (0 = sin auto-refresh) */
  every?: number;
  /** si es false no se ejecuta (p. ej. hasta tener un id) */
  enabled?: boolean;
  /** no mostrar toast en error (datos opcionales) */
  silent?: boolean;
}

/** Fetch declarativo con recarga manual y auto-refresh. Los errores se muestran como toast. */
export function useFetch<T>(fn: () => Promise<T>, deps: unknown[], opts: Options = {}) {
  const { every = 0, enabled = true, silent: quiet = false } = opts;
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(enabled);
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const toast = useToast();
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const alive = useRef(true);

  const reload = useCallback(
    async (silent = false) => {
      if (!enabled) return;
      if (!silent) setLoading(true);
      try {
        const d = await fnRef.current();
        if (!alive.current) return;
        setData(d);
        setError(null);
        setUpdatedAt(new Date());
      } catch (e) {
        if (!alive.current) return;
        const msg = e instanceof Error ? e.message : 'Error';
        setError(msg);
        if (!quiet && !(e instanceof Error && 'status' in e && (e as { status: number }).status === 401)) toast.error(e);
      } finally {
        if (alive.current) setLoading(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [enabled, ...deps],
  );

  useEffect(() => {
    alive.current = true;
    void reload();
    let timer: ReturnType<typeof setInterval> | undefined;
    if (every > 0) timer = setInterval(() => void reload(true), every);
    return () => {
      alive.current = false;
      if (timer) clearInterval(timer);
    };
  }, [reload, every]);

  return { data, loading, error, reload, updatedAt, setData };
}
