import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import YesNo from '../components/YesNo';
import { getPosition } from '../offline/gps';
import { speak } from '../offline/speech';
import { openShift, suggestedAction } from '../state/actions';
import { useApp } from '../state/store';
import type { GPS, OpenChecklist, ShiftException } from '../types';

const ITEMS: { key: keyof OpenChecklist; icon: string; label: string }[] = [
  { key: 'cart_secure', icon: '🔐', label: 'Carrito seguro' },
  { key: 'battery_ok', icon: '🔋', label: 'Batería cargada' },
  { key: 'product_ok', icon: '🥜', label: 'Producto suficiente y en buen estado' },
  { key: 'clean_ok', icon: '🧽', label: 'Carrito limpio' },
  { key: 'pos_ok', icon: '💳', label: 'Terminal / POS funciona' },
];

export default function OpenShift() {
  const nav = useNavigate();
  const { catalog, reload } = useApp();
  const [gps, setGps] = useState<GPS | null | 'loading'>('loading');
  const [values, setValues] = useState<Partial<Record<keyof OpenChecklist, boolean>>>({});
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ ready: boolean; exceptions: ShiftException[]; pending: boolean } | null>(null);

  useEffect(() => {
    let alive = true;
    getPosition(8000).then((g) => alive && setGps(g));
    return () => {
      alive = false;
    };
  }, []);

  const labels = new Map((catalog?.checklist_open ?? []).map((c) => [c.key, c.label]));
  const complete = ITEMS.every((i) => typeof values[i.key] === 'boolean');

  const submit = async () => {
    if (!complete) return;
    setBusy(true);
    try {
      const checklist = Object.fromEntries(ITEMS.map((i) => [i.key, values[i.key] === true])) as unknown as OpenChecklist;
      const st = await openShift(checklist, gps === 'loading' ? null : gps);
      await reload();
      setResult({ ready: st.ready, exceptions: st.exceptions, pending: st.status === 'open_pending' });
      speak(st.ready ? 'Listo para vender' : 'Puesto abierto con excepciones. Revisa la lista.');
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'No se pudo abrir';
      setResult({ ready: false, exceptions: [{ code: 'error', message: msg }], pending: false });
    } finally {
      setBusy(false);
    }
  };

  if (result) {
    if (result.ready && result.exceptions.length === 0) {
      return (
        <div className="result result-green" role="status">
          <div className="ico" aria-hidden>
            ✅
          </div>
          <p className="h1">LISTO PARA VENDER</p>
          {result.pending && <p>Se enviará cuando haya señal.</p>}
          <button className="btn" onClick={() => nav('/vender', { replace: true })}>
            <span className="ico" aria-hidden>
              🛍️
            </span>
            VENDER
          </button>
        </div>
      );
    }
    return (
      <div className="stack">
        <div className={`result ${result.ready ? 'result-green' : 'result-amber'}`} style={{ minHeight: 'auto' }} role="status">
          <div className="ico" aria-hidden>
            {result.ready ? '✅' : '⚠️'}
          </div>
          <p className="h1">{result.ready ? 'PUESTO ABIERTO' : 'ABIERTO CON PENDIENTES'}</p>
          <p>Ya avisamos al supervisor.</p>
        </div>
        {result.exceptions.map((e) => (
          <div className="exception" key={e.code}>
            <span className="ico" aria-hidden>
              👉
            </span>
            <div>
              <b>{e.message}</b>
              {suggestedAction(e.code)}
            </div>
          </div>
        ))}
        <button className="btn btn-primary" onClick={() => nav(result.ready ? '/vender' : '/', { replace: true })}>
          {result.ready ? 'VENDER' : 'CONTINUAR'}
        </button>
      </div>
    );
  }

  return (
    <div className="stack">
      <h1 className="h1">Abrir puesto</h1>
      <div className="row muted">
        <span aria-hidden>📡</span>
        {gps === 'loading' ? 'Buscando ubicación…' : gps ? 'Ubicación lista' : 'Sin ubicación (continúa igual)'}
      </div>
      <p className="h2">Revisa y marca Sí o No:</p>
      {ITEMS.map((i) => (
        <YesNo key={i.key} icon={i.icon} label={labels.get(i.key) ?? i.label} value={values[i.key] ?? null} onChange={(v) => setValues((s) => ({ ...s, [i.key]: v }))} />
      ))}
      <button className="btn btn-green" disabled={!complete || busy} onClick={submit}>
        <span className="ico" aria-hidden>
          ✅
        </span>
        {busy ? 'Abriendo…' : 'LISTO'}
      </button>
      <button className="btn btn-ghost" onClick={() => nav('/')}>
        Volver
      </button>
    </div>
  );
}
