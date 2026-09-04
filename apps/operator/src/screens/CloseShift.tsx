import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Numpad, { pesosToCents } from '../components/Numpad';
import YesNo from '../components/YesNo';
import { getPosition } from '../offline/gps';
import { speak } from '../offline/speech';
import { closeShift, finishClosedShift, getExpected, type ExpectedView } from '../state/actions';
import { money, useApp } from '../state/store';
import type { CloseChecklist } from '../types';

const CHECKS: { key: keyof CloseChecklist; icon: string; label: string }[] = [
  { key: 'off_ok', icon: '🔌', label: 'Apagar equipo' },
  { key: 'clean_ok', icon: '🧽', label: 'Limpiar carrito' },
  { key: 'secured_ok', icon: '🔐', label: 'Asegurar con candado' },
  { key: 'stored_ok', icon: '🏠', label: 'Resguardar producto' },
  { key: 'charging_ok', icon: '🔋', label: 'Poner a cargar batería' },
];

type Result = { status: 'reconciled' | 'difference'; difference_cents: number; pending: boolean };

export default function CloseShift() {
  const nav = useNavigate();
  const { catalog, config, shift, reload } = useApp();
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [expected, setExpected] = useState<ExpectedView | null>(null);
  const [cash, setCash] = useState('');
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [checks, setChecks] = useState<Partial<Record<keyof CloseChecklist, boolean>>>({});
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Result | null>(null);

  useEffect(() => {
    let alive = true;
    getExpected()
      .then((e) => {
        if (!alive) return;
        setExpected(e);
        const init: Record<string, number> = {};
        for (const p of catalog?.presentations ?? []) init[p.id] = Math.max(0, e.product_expected[p.id] ?? 0);
        setCounts(init);
        speak(`Debes tener ${money(e.cash_expected_cents)}`);
      })
      .catch(() => {
        if (!alive) return;
        setExpected({ source: 'local', cash_expected_cents: 0, sales_count: 0, sales_total_cents: 0, digital_total_cents: 0, product_expected: {} });
      });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const labels = new Map((catalog?.checklist_close ?? []).map((c) => [c.key, c.label]));
  const checksComplete = CHECKS.every((c) => typeof checks[c.key] === 'boolean');
  const cashCents = pesosToCents(cash);
  const threshold = config?.cash_difference_threshold_cents ?? 2000;

  const finish = async () => {
    if (!expected || !checksComplete || busy) return;
    setBusy(true);
    try {
      const gps = await getPosition(6000);
      const checklist = Object.fromEntries(CHECKS.map((c) => [c.key, checks[c.key] === true])) as unknown as CloseChecklist;
      const r = await closeShift({ cash_counted_cents: cashCents, product_counts: counts, checklist, gps, expected_cash_cents: expected.cash_expected_cents });
      const pending = r.status === 'pending';
      const status: Result['status'] = r.status === 'pending' ? (Math.abs(r.difference_cents) <= threshold ? 'reconciled' : 'difference') : r.status;
      setResult({ status, difference_cents: r.difference_cents, pending });
      speak(status === 'reconciled' ? 'Cierre conciliado. Buen trabajo.' : 'Se registró una diferencia. El supervisor la revisará.');
    } finally {
      setBusy(false);
    }
  };

  const done = async () => {
    await finishClosedShift();
    await reload();
    nav('/', { replace: true });
  };

  if (result) {
    const ok = result.status === 'reconciled';
    return (
      <div className={`result ${ok ? 'result-green' : 'result-amber'}`} role="status">
        <div className="ico" aria-hidden>
          {ok ? '✅' : '📋'}
        </div>
        <p className="h1">{ok ? 'Cierre conciliado' : 'Se registró una diferencia'}</p>
        {!ok && <p className="h2">El supervisor la revisará. No necesitas hacer nada más.</p>}
        {!ok && <p>Diferencia: {result.difference_cents > 0 ? '+' : ''}{money(result.difference_cents)}</p>}
        {result.pending && <p>Se enviará cuando haya señal.</p>}
        <button className="btn" onClick={done}>
          Terminar
        </button>
      </div>
    );
  }

  if (!shift) {
    return (
      <div className="stack">
        <p className="h2">No hay puesto abierto.</p>
        <button className="btn btn-primary" onClick={() => nav('/')}>
          Inicio
        </button>
      </div>
    );
  }

  return (
    <div className="stack">
      <div className="steps" aria-label={`Paso ${step} de 3`}>
        {[1, 2, 3].map((n) => (
          <span key={n} className={n <= step ? 'on' : ''} />
        ))}
      </div>

      {step === 1 && (
        <>
          <h1 className="h1 center">Cerrar puesto</h1>
          <div className="card center">
            <div className="muted">Debes tener</div>
            <div className="big-money">{expected ? money(expected.cash_expected_cents) : '…'}</div>
            {expected && (
              <div className="muted">
                {expected.sales_count} ventas · efectivo{expected.source === 'local' ? ' (calculado en el teléfono)' : ''}
              </div>
            )}
          </div>
          <p className="h2 center">Tengo:</p>
          <div className={`amount-display ${cash ? '' : 'empty'}`} aria-live="polite">
            {cash ? money(cashCents) : '$ ___'}
          </div>
          <Numpad value={cash} onChange={setCash} />
          <button className="btn btn-primary" disabled={!expected || cash === ''} onClick={() => setStep(2)}>
            <span className="ico" aria-hidden>
              ➡️
            </span>
            CONTINUAR
          </button>
          <button className="btn btn-ghost" onClick={() => nav('/')}>
            Cancelar
          </button>
        </>
      )}

      {step === 2 && (
        <>
          <h1 className="h1">¿Cuánto producto queda?</h1>
          {(catalog?.presentations ?? []).map((p) => (
            <div className="stepper" key={p.id}>
              <div className="name">{p.grams} g</div>
              <div className="ctl">
                <button aria-label={`Menos ${p.grams} g`} onClick={() => setCounts((c) => ({ ...c, [p.id]: Math.max(0, (c[p.id] ?? 0) - 1) }))}>
                  −
                </button>
                <div className="v" aria-live="polite">
                  {counts[p.id] ?? 0}
                </div>
                <button aria-label={`Más ${p.grams} g`} onClick={() => setCounts((c) => ({ ...c, [p.id]: (c[p.id] ?? 0) + 1 }))}>
                  +
                </button>
              </div>
            </div>
          ))}
          <button className="btn btn-primary" onClick={() => setStep(3)}>
            <span className="ico" aria-hidden>
              ➡️
            </span>
            CONTINUAR
          </button>
          <button className="btn btn-ghost" onClick={() => setStep(1)}>
            Atrás
          </button>
        </>
      )}

      {step === 3 && (
        <>
          <h1 className="h1">Antes de irte</h1>
          {CHECKS.map((c) => (
            <YesNo key={c.key} icon={c.icon} label={labels.get(c.key) ?? c.label} value={checks[c.key] ?? null} onChange={(v) => setChecks((s) => ({ ...s, [c.key]: v }))} />
          ))}
          <button className="btn btn-amber" disabled={!checksComplete || busy} onClick={finish}>
            <span className="ico" aria-hidden>
              🔒
            </span>
            {busy ? 'Cerrando…' : 'CERRAR PUESTO'}
          </button>
          <button className="btn btn-ghost" onClick={() => setStep(2)}>
            Atrás
          </button>
        </>
      )}
    </div>
  );
}
