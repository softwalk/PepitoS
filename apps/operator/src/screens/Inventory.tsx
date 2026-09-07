/** Recibir producto (QR o cantidades) y contar producto: dos pantallas simples con +/− por presentación. */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { speak } from '../offline/speech';
import { getExpected, recordCount, recordReceipt } from '../state/actions';
import { useApp } from '../state/store';

function QtyRows({ values, onChange, base }: { values: Record<string, number>; onChange: (id: string, v: number) => void; base?: Record<string, number> }) {
  const { catalog } = useApp();
  const pres = (catalog?.presentations ?? []).slice().sort((a, b) => a.sort - b.sort);
  return (
    <div className="stack">
      {pres.map((p) => (
        <div className="qty-row" key={p.id} data-testid={`qty-${p.grams}`}>
          <div>
            <div style={{ fontWeight: 800 }}>{p.grams} g</div>
            {base && <div className="muted" style={{ fontSize: '0.8em' }}>Debería haber {base[p.id] ?? 0}</div>}
          </div>
          <button type="button" className="qty-btn" aria-label={`Menos ${p.grams} g`} onClick={() => onChange(p.id, Math.max(0, (values[p.id] ?? 0) - 1))}>
            −
          </button>
          <div className="qty-val" aria-live="polite">{values[p.id] ?? 0}</div>
          <button type="button" className="qty-btn" aria-label={`Más ${p.grams} g`} onClick={() => onChange(p.id, (values[p.id] ?? 0) + 1)}>
            +
          </button>
        </div>
      ))}
    </div>
  );
}

export function Receive() {
  const nav = useNavigate();
  const { shift, reload } = useApp();
  const [qty, setQty] = useState<Record<string, number>>({});
  const [qr, setQr] = useState('');
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const total = Object.values(qty).reduce((a, b) => a + b, 0);
  if (!shift || shift.status === 'closed') return <NoShift />;
  if (done) return <Done title="Producto recibido" sub="Ya cuenta en tu inventario. Se envía con señal." onBack={() => nav('/')} />;
  return (
    <div className="stack">
      <h1 className="h1">Recibir producto</h1>
      <p className="h2">Escanea el QR de la entrega o marca cuántas piezas recibiste.</p>
      <input className="input" placeholder="Código QR de la entrega (opcional)" value={qr} onChange={(e) => setQr(e.target.value)} inputMode="text" autoCapitalize="characters" />
      <QtyRows values={qty} onChange={(id, v) => setQty((s) => ({ ...s, [id]: v }))} />
      <button
        className="btn btn-green"
        disabled={!total || busy}
        data-testid="receive-confirm"
        onClick={async () => {
          setBusy(true);
          try {
            await recordReceipt(Object.entries(qty).map(([presentation_id, q]) => ({ presentation_id, qty: q })), qr.trim() || undefined);
            await reload();
            speak(`Recibiste ${total} piezas`);
            setDone(true);
          } finally {
            setBusy(false);
          }
        }}
      >
        <span className="ico" aria-hidden>
          📦
        </span>
        {busy ? 'Guardando…' : `RECIBÍ ${total} PIEZAS`}
      </button>
      <button className="btn btn-ghost" onClick={() => nav('/')}>
        Volver
      </button>
    </div>
  );
}

export function Count() {
  const nav = useNavigate();
  const { shift, reload } = useApp();
  const [qty, setQty] = useState<Record<string, number>>({});
  const [base, setBase] = useState<Record<string, number>>({});
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  useEffect(() => {
    getExpected()
      .then((e) => {
        setBase(e.product_expected);
        setQty(Object.fromEntries(Object.entries(e.product_expected).map(([k, v]) => [k, Math.max(0, v)])));
      })
      .catch(() => undefined);
  }, []);
  if (!shift || shift.status === 'closed') return <NoShift />;
  if (done) return <Done title="Conteo registrado" sub="Si hay diferencia, el supervisor la revisará contigo." onBack={() => nav('/')} />;
  const diff = Object.keys(base).reduce((a, k) => a + Math.abs((qty[k] ?? 0) - (base[k] ?? 0)), 0);
  return (
    <div className="stack">
      <h1 className="h1">Contar producto</h1>
      <p className="h2">Cuenta lo que tienes en el carrito y ajusta los números.</p>
      <QtyRows values={qty} onChange={(id, v) => setQty((s) => ({ ...s, [id]: v }))} base={base} />
      {diff > 0 && (
        <div className="cash-diff warn" data-testid="count-diff">
          Diferencia de {diff} pieza(s) contra lo esperado
        </div>
      )}
      <button
        className="btn btn-primary"
        disabled={busy}
        data-testid="count-confirm"
        onClick={async () => {
          setBusy(true);
          try {
            await recordCount(qty);
            await reload();
            speak('Conteo registrado');
            setDone(true);
          } finally {
            setBusy(false);
          }
        }}
      >
        <span className="ico" aria-hidden>
          🔢
        </span>
        {busy ? 'Guardando…' : 'REGISTRAR CONTEO'}
      </button>
      <button className="btn btn-ghost" onClick={() => nav('/')}>
        Volver
      </button>
    </div>
  );
}

function NoShift() {
  const nav = useNavigate();
  return (
    <div className="stack">
      <p className="h2">No hay puesto abierto.</p>
      <button className="btn btn-primary" onClick={() => nav('/')}>
        Inicio
      </button>
    </div>
  );
}

function Done({ title, sub, onBack }: { title: string; sub: string; onBack: () => void }) {
  return (
    <div className="result result-green" role="status">
      <div className="ico" aria-hidden>
        ✅
      </div>
      <p className="h1">{title}</p>
      <p className="h2">{sub}</p>
      <button className="btn" onClick={onBack}>
        Inicio
      </button>
    </div>
  );
}
