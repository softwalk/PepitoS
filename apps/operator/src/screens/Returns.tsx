/** Devoluciones y movimientos de efectivo: el cliente devolvió producto (cancela la venta con motivo «return» y avisa al
 *  supervisor) o hubo un retiro/gasto/fondo en caja. Todo entra en el efectivo esperado del cierre. */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Numpad, { pesosToCents } from '../components/Numpad';
import { countsAsSale } from '../offline/expected';
import { speak } from '../offline/speech';
import { recordCashMovement, returnSale } from '../state/actions';
import { money, useApp } from '../state/store';
import type { CashMovementKind } from '../types';

const KINDS: { kind: CashMovementKind; label: string; icon: string; reasons: string[] }[] = [
  { kind: 'expense', label: 'Gasto', icon: '🧾', reasons: ['Hielo', 'Bolsas / servilletas', 'Transporte', 'Otro'] },
  { kind: 'withdrawal', label: 'Retiro', icon: '🏦', reasons: ['Entrega al supervisor', 'Depósito', 'Otro'] },
  { kind: 'deposit', label: 'Entrada', icon: '💵', reasons: ['Fondo adicional', 'Cambio recibido', 'Otro'] },
];

export default function Returns() {
  const nav = useNavigate();
  const { sales, catalog, shift, reload } = useApp();
  const [tab, setTab] = useState<'return' | 'cash'>('return');
  const [picked, setPicked] = useState<string | null>(null);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const [kind, setKind] = useState<CashMovementKind>('expense');
  const [reason, setReason] = useState('');
  const [amount, setAmount] = useState('');
  const pres = new Map((catalog?.presentations ?? []).map((p) => [p.id, p]));
  const list = sales.filter(countsAsSale).sort((a, b) => b.occurred_at.localeCompare(a.occurred_at)).slice(0, 30);

  if (!shift || shift.status === 'closed') {
    return (
      <div className="stack">
        <p className="h2">No hay puesto abierto.</p>
        <button className="btn btn-primary" onClick={() => nav('/')}>
          Inicio
        </button>
      </div>
    );
  }
  if (done) {
    return (
      <div className="result result-green" role="status">
        <div className="ico" aria-hidden>
          ✅
        </div>
        <p className="h1">{done}</p>
        <p className="h2">Se envía con señal. El supervisor lo verá en sus casos.</p>
        <button className="btn" onClick={() => nav('/vender', { replace: true })}>
          Seguir vendiendo
        </button>
      </div>
    );
  }

  const doReturn = async () => {
    if (!picked || busy) return;
    setBusy(true);
    try {
      const r = await returnSale(picked, note.trim() || undefined);
      if (r === 'not_synced') {
        speak('Esa venta aún no llega al servidor. Espera señal y vuelve a intentar.', true);
        setBusy(false);
        return;
      }
      await reload();
      speak('Devolución registrada');
      setDone('Devolución registrada');
    } finally {
      setBusy(false);
    }
  };
  const doCash = async () => {
    const cents = pesosToCents(amount || '0');
    if (!cents || !reason || busy) return;
    setBusy(true);
    try {
      await recordCashMovement(kind, cents, reason);
      await reload();
      speak('Movimiento de caja registrado');
      setDone(`${KINDS.find((k) => k.kind === kind)?.label} registrado: ${money(cents)}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="stack">
      <div className="segmented" role="tablist" aria-label="Tipo">
        <button type="button" role="tab" className={`cash ${tab === 'return' ? 'active' : ''}`} aria-selected={tab === 'return'} onClick={() => setTab('return')}>
          <span aria-hidden>↩️</span> Devolución
        </button>
        <button type="button" role="tab" className={`qr ${tab === 'cash' ? 'active' : ''}`} aria-selected={tab === 'cash'} onClick={() => setTab('cash')}>
          <span aria-hidden>💵</span> Caja
        </button>
      </div>

      {tab === 'return' && (
        <>
          <h1 className="h1">¿Qué venta devolvió el cliente?</h1>
          {list.length === 0 && <p className="muted">No hay ventas en este turno.</p>}
          <div className="sale-list" role="radiogroup" aria-label="Ventas del turno">
            {list.map((s) => {
              const p = pres.get(s.presentation_id);
              const active = picked === s.idempotency_key;
              return (
                <button key={s.idempotency_key} type="button" role="radio" aria-checked={active} className={`sale-row ${active ? 'active' : ''}`} style={active ? { borderColor: 'var(--brand)', borderWidth: 2 } : undefined} onClick={() => setPicked(s.idempotency_key)} data-testid="return-sale">
                  <div>
                    <div className="t">
                      {p ? `${p.grams} g` : 'Venta'} · {money(s.total_cents)} {s.method === 'cash' ? '💵' : '📱'}
                    </div>
                    <div className="s">
                      {new Date(s.occurred_at).toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' })}
                      {s.status === 'pending' ? ' · pendiente de enviar' : s.folio ? ` · ${s.folio}` : ''}
                    </div>
                  </div>
                  <span aria-hidden>{active ? '◉' : '○'}</span>
                </button>
              );
            })}
          </div>
          <textarea placeholder="¿Por qué? (opcional)" value={note} maxLength={200} onChange={(e) => setNote(e.target.value)} />
          <button className="btn btn-amber" disabled={!picked || busy} onClick={doReturn} data-testid="return-confirm">
            <span className="ico" aria-hidden>
              ↩️
            </span>
            {busy ? 'Registrando…' : 'REGISTRAR DEVOLUCIÓN'}
          </button>
        </>
      )}

      {tab === 'cash' && (
        <>
          <h1 className="h1">Movimiento de caja</h1>
          <div className="flavor-chips" role="group" aria-label="Tipo de movimiento">
            {KINDS.map((k) => (
              <button key={k.kind} type="button" className={`chip ${kind === k.kind ? 'active' : ''}`} aria-pressed={kind === k.kind} onClick={() => { setKind(k.kind); setReason(''); }}>
                {k.icon} {k.label}
              </button>
            ))}
          </div>
          <div className="flavor-chips" role="group" aria-label="Motivo">
            {KINDS.find((k) => k.kind === kind)!.reasons.map((r) => (
              <button key={r} type="button" className={`chip ${reason === r ? 'active' : ''}`} aria-pressed={reason === r} onClick={() => setReason(r)}>
                {r}
              </button>
            ))}
          </div>
          <div className={`amount-display ${amount ? '' : 'empty'}`} aria-live="polite">
            {amount ? money(pesosToCents(amount)) : '$ ___'}
          </div>
          <Numpad value={amount} onChange={setAmount} />
          <button className="btn btn-primary" disabled={!amount || !reason || busy} onClick={doCash} data-testid="cash-confirm">
            <span className="ico" aria-hidden>
              💵
            </span>
            {busy ? 'Registrando…' : 'REGISTRAR'}
          </button>
        </>
      )}
      <button className="btn btn-ghost" onClick={() => nav('/vender')}>
        Volver
      </button>
    </div>
  );
}
