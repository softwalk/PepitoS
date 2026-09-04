import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { countsAsSale } from '../offline/expected';
import { speak } from '../offline/speech';
import { cancelSale, recordSale, recordWaste, undoSale, UNDO_WINDOW_MS } from '../state/actions';
import { money, useApp } from '../state/store';
import type { PaymentMethod, Presentation, WasteReason } from '../types';

type Toast = { key: string; text: string; method: PaymentMethod; until: number } | null;

const CANCEL_REASONS: { code: string; icon: string; label: string }[] = [
  { code: 'mistake', icon: '🤦', label: 'Me equivoqué' },
  { code: 'customer_left', icon: '🚶', label: 'Cliente se fue' },
  { code: 'wrong_item', icon: '🔁', label: 'Cambio de tamaño' },
];

const WASTE_ICONS: Record<WasteReason, string> = { spill: '💧', quality: '👎', expired: '📅', sample: '🍽️', other: '❓' };

export default function Sell() {
  const nav = useNavigate();
  const { catalog, sales, shift, reload } = useApp();
  const [method, setMethod] = useState<PaymentMethod>('cash');
  const [showFlavors, setShowFlavors] = useState(false);
  const [flavor, setFlavor] = useState<string | null>(null);
  const [toast, setToast] = useState<Toast>(null);
  const [cancelFor, setCancelFor] = useState<string | null>(null);
  const [waste, setWaste] = useState<{ step: 'pres' | 'qty' | 'reason'; presentation?: Presentation; qty?: number } | null>(null);
  const [wasteDone, setWasteDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const undoTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const presentations = (catalog?.presentations ?? []).filter((p) => p.price_cents != null).sort((a, b) => a.sort - b.sort);
  const active = sales.filter(countsAsSale);
  const total = active.reduce((a, s) => a + s.total_cents, 0);

  useEffect(() => () => {
    if (toastTimer.current) clearTimeout(toastTimer.current);
    if (undoTimer.current) clearTimeout(undoTimer.current);
  }, []);

  const sell = async (p: Presentation) => {
    if (busy) return;
    setBusy(true);
    try {
      const rec = await recordSale(p, method, flavor);
      await reload();
      const text = `${p.grams} g · ${money(p.price_cents ?? 0)}`;
      setToast({ key: rec.idempotency_key, text, method, until: Date.now() + UNDO_WINDOW_MS });
      if (toastTimer.current) clearTimeout(toastTimer.current);
      // La confirmación grande dura 1.5 s; "Deshacer" sigue disponible hasta 60 s en la última venta.
      toastTimer.current = setTimeout(() => setToast((t) => (t && t.key === rec.idempotency_key ? { ...t, text: '' } : t)), 1500);
      if (undoTimer.current) clearTimeout(undoTimer.current);
      undoTimer.current = setTimeout(() => setToast((t) => (t && t.key === rec.idempotency_key ? null : t)), UNDO_WINDOW_MS);
      speak(`Venta ${p.grams} gramos, ${money(p.price_cents ?? 0)}`);
      if (method !== 'cash') setMethod('cash');
      setFlavor(null);
    } catch (e) {
      speak('No se pudo registrar la venta', true);
    } finally {
      setBusy(false);
    }
  };

  const undo = async () => {
    if (!toast) return;
    const out = await undoSale(toast.key);
    if (out === 'removed') {
      setToast(null);
      await reload();
      speak('Venta eliminada');
    } else if (out === 'needs_reason') {
      setCancelFor(toast.key);
      setToast(null);
    } else {
      setToast(null);
    }
  };

  const confirmCancel = async (code: string) => {
    if (!cancelFor) return;
    await cancelSale(cancelFor, code);
    setCancelFor(null);
    await reload();
  };

  const lastSale = toast ? sales.find((s) => s.idempotency_key === toast.key) : null;
  const showUndo = toast && Date.now() < toast.until && lastSale && (lastSale.status === 'pending' || lastSale.status === 'synced');

  if (cancelFor) {
    return (
      <div className="stack">
        <h1 className="h1">¿Por qué se cancela?</h1>
        <p className="muted">La venta ya se envió. Elige un motivo:</p>
        {CANCEL_REASONS.map((r) => (
          <button key={r.code} className="btn btn-outline" onClick={() => confirmCancel(r.code)}>
            <span className="ico" aria-hidden>
              {r.icon}
            </span>
            {r.label}
          </button>
        ))}
        <button className="btn btn-ghost" onClick={() => setCancelFor(null)}>
          No cancelar
        </button>
      </div>
    );
  }

  if (wasteDone) {
    return (
      <div className="result result-blue" role="status">
        <div className="ico" aria-hidden>
          🗑️
        </div>
        <p className="h1">Merma registrada</p>
        <button className="btn" onClick={() => setWasteDone(false)}>
          Volver a vender
        </button>
      </div>
    );
  }

  if (waste) {
    if (waste.step === 'pres') {
      return (
        <div className="stack">
          <h1 className="h1">Merma: ¿qué tamaño?</h1>
          <div className="grid3">
            {presentations.map((p) => (
              <button key={p.id} className="sale-btn" onClick={() => setWaste({ step: 'qty', presentation: p })}>
                <span className="g">{p.grams}</span>
                <span className="p">g</span>
              </button>
            ))}
          </div>
          <button className="btn btn-ghost" onClick={() => setWaste(null)}>
            Cancelar
          </button>
        </div>
      );
    }
    if (waste.step === 'qty') {
      return (
        <div className="stack">
          <h1 className="h1">¿Cuántas?</h1>
          <div className="grid2">
            {[1, 2, 3].map((n) => (
              <button key={n} className="btn btn-outline btn-huge" onClick={() => setWaste({ ...waste, step: 'reason', qty: n })}>
                {n}
              </button>
            ))}
            <button className="btn btn-outline btn-huge" onClick={() => setWaste({ ...waste, qty: (waste.qty ?? 3) + 1 })}>
              + {waste.qty && waste.qty > 3 ? `(${waste.qty})` : ''}
            </button>
          </div>
          {waste.qty && waste.qty > 3 && (
            <button className="btn btn-primary" onClick={() => setWaste({ ...waste, step: 'reason' })}>
              Continuar con {waste.qty}
            </button>
          )}
          <button className="btn btn-ghost" onClick={() => setWaste(null)}>
            Cancelar
          </button>
        </div>
      );
    }
    return (
      <div className="stack">
        <h1 className="h1">¿Por qué?</h1>
        {(catalog?.waste_reasons ?? []).map((r) => (
          <button
            key={r.code}
            className="btn btn-outline"
            onClick={async () => {
              await recordWaste(waste.presentation!.id, waste.qty ?? 1, r.code);
              setWaste(null);
              setWasteDone(true);
              await reload();
            }}
          >
            <span className="ico" aria-hidden>
              {WASTE_ICONS[r.code] ?? '❓'}
            </span>
            {r.label}
          </button>
        ))}
        <button className="btn btn-ghost" onClick={() => setWaste(null)}>
          Cancelar
        </button>
      </div>
    );
  }

  const flavorName = flavor ? catalog?.flavors.find((f) => f.id === flavor)?.name ?? '' : null;

  return (
    <div className="stack" style={{ paddingBottom: toast ? 130 : 0 }}>
      <div className="counter" aria-live="polite">
        <div>
          <div className="muted">Ventas del turno</div>
          <div className="n">{active.length}</div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div className="muted">Total</div>
          <div className="n">{money(total)}</div>
        </div>
      </div>

      {shift?.ready === false && (
        <div className="exception">
          <span className="ico" aria-hidden>
            ⚠️
          </span>
          <div>
            <b>Puesto abierto con pendientes</b>
            Puedes vender; el supervisor ya está avisado.
          </div>
        </div>
      )}

      {/* Forma de pago: control segmentado, siempre visible. Vuelve a efectivo tras cada venta digital. */}
      <div className="segmented" role="group" aria-label="Forma de pago">
        <button type="button" className={`cash ${method === 'cash' ? 'active' : ''}`} aria-pressed={method === 'cash'} onClick={() => setMethod('cash')}>
          <span aria-hidden>💵</span> Efectivo
        </button>
        <button type="button" className={`qr method-toggle-seg ${method !== 'cash' ? 'active' : ''}`} aria-pressed={method !== 'cash'} onClick={() => setMethod('qr')}>
          <span aria-hidden>📱</span> QR / Tarjeta
        </button>
      </div>

      <div className="stack" role="group" aria-label="Registrar venta">
        {presentations.map((p) => (
          <button key={p.id} className={`sale-btn ${method !== 'cash' ? 'qr' : ''}`} disabled={busy} onClick={() => sell(p)}>
            <span className="g">{p.grams} g</span>
            <span className="p">{money(p.price_cents ?? 0)}</span>
            <span className="btn-sub">{method === 'cash' ? '💵 Efectivo' : '📱 QR / Tarjeta'}{flavorName ? ` · ${flavorName}` : ''}</span>
          </button>
        ))}
      </div>

      <button type="button" className="disclosure" onClick={() => setShowFlavors((v) => !v)} aria-expanded={showFlavors}>
        <span>
          <span aria-hidden>🌶️</span> Sabor{flavorName ? `: ${flavorName}` : ' (opcional)'}
        </span>
        <span className="chev" aria-hidden>
          ▼
        </span>
      </button>
      {showFlavors && (
        <div className="flavor-chips" role="group" aria-label="Sabor">
          <button className={`chip ${flavor === null ? 'active' : ''}`} onClick={() => setFlavor(null)}>
            Sin sabor
          </button>
          {(catalog?.flavors ?? []).map((f) => (
            <button key={f.id} className={`chip ${flavor === f.id ? 'active' : ''}`} onClick={() => setFlavor(f.id)}>
              {f.name}
            </button>
          ))}
        </div>
      )}

      <div className="btn-row">
        <button className="btn btn-outline" onClick={() => setWaste({ step: 'pres' })}>
          <span className="ico" aria-hidden>
            🗑️
          </span>
          MERMA
        </button>
        <button className="btn btn-outline" onClick={() => nav('/')}>
          <span className="ico" aria-hidden>
            🏠
          </span>
          Inicio
        </button>
      </div>

      {toast && (toast.text || showUndo) && (
        <div className="toast" role="status" aria-live="assertive">
          <div className={`toast-inner ${toast.method !== 'cash' ? 'blue' : ''}`}>
            <div>
              <div className="t">{toast.text ? '✓ Venta registrada' : 'Última venta'}</div>
              <div>{toast.text || `${lastSale?.grams} g · ${money(lastSale?.total_cents ?? 0)}`}</div>
            </div>
            {showUndo && (
              <button className="undo" onClick={undo}>
                ↩ Deshacer
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
