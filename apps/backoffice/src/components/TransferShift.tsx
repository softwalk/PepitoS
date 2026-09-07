/** Transferencia de turno desde el teléfono del supervisor: elegir operador entrante, contar efectivo y producto del
 *  turno saliente (conteo intermedio guiado) → POST /v1/shifts/{id}/transfer. */
import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { Modal } from './ui';
import { useToast } from './Toast';
import { useFetch } from '../lib/useFetch';
import { money } from '../lib/format';

interface Expected { cash_expected_cents: number; product_expected: Record<string, number>; sales_count: number }
interface Pres { id: string; name: string; grams: number }

export function TransferShiftButton({ shiftId, pointName, onDone }: { shiftId: string; pointName: string; onDone: () => Promise<void> }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" className="btn small btn-ghost" onClick={() => setOpen(true)} data-testid="transfer-open">
        Transferir turno
      </button>
      {open && <TransferModal shiftId={shiftId} pointName={pointName} onClose={() => setOpen(false)} onDone={onDone} />}
    </>
  );
}

function TransferModal({ shiftId, pointName, onClose, onDone }: { shiftId: string; pointName: string; onClose: () => void; onDone: () => Promise<void> }) {
  const toast = useToast();
  const { data: exp } = useFetch<Expected>(() => api.get(`/v1/shifts/${shiftId}/expected`), [shiftId]);
  const { data: ops } = useFetch<{ operators: { id: string; name: string }[] }>(() => api.get('/v1/reports/bi/options'), [], { silent: true });
  const { data: catalog } = useFetch<{ presentations: Pres[] }>(() => api.get('/v1/catalog'), [], { silent: true });
  const [to, setTo] = useState('');
  const [cash, setCash] = useState('');
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (exp) setCounts(Object.fromEntries(Object.entries(exp.product_expected).map(([k, v]) => [k, Math.max(0, v)])));
  }, [exp]);
  const cents = Math.round(Number(cash || 0) * 100);
  const diff = exp ? cents - exp.cash_expected_cents : 0;
  const submit = async () => {
    setBusy(true);
    try {
      await api.post(`/v1/shifts/${shiftId}/transfer`, { idempotency_key: crypto.randomUUID(), to_operator_id: to, cash_counted_cents: cents, product_counts: counts });
      toast.toast('Turno transferido', 'success');
      await onDone();
      onClose();
    } catch (e) {
      toast.error(e, 'No se pudo transferir');
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal title={`Transferir turno · ${pointName}`} onClose={onClose}>
      <div style={{ display: 'grid', gap: 10 }} data-testid="transfer-modal">
        <p className="muted small">El turno saliente se cierra con este conteo intermedio y el entrante abre con el mismo carrito. La diferencia de caja del saliente queda registrada.</p>
        <label className="field">
          <span className="field-label">Operador entrante</span>
          <select value={to} onChange={(e) => setTo(e.target.value)} data-testid="transfer-to">
            <option value="">Elige…</option>
            {(ops?.operators ?? []).map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
          </select>
        </label>
        <label className="field">
          <span className="field-label">Efectivo contado {exp && <span className="muted">(esperado {money(exp.cash_expected_cents)})</span>}</span>
          <input inputMode="decimal" value={cash} onChange={(e) => setCash(e.target.value)} placeholder="0.00" data-testid="transfer-cash" />
        </label>
        {cash !== '' && exp && <div className={`cash-diff-line ${diff === 0 ? 'ok' : 'warn'}`} style={{ fontWeight: 700, color: diff === 0 ? 'var(--green)' : 'var(--amber)' }}>{diff === 0 ? '✓ Cuadra exacto' : `${diff > 0 ? 'Sobra' : 'Falta'} ${money(Math.abs(diff))}`}</div>}
        <div>
          <span className="field-label">Producto contado</span>
          {(catalog?.presentations ?? []).map((p) => (
            <div key={p.id} style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 6 }}>
              <span style={{ width: 70 }}>{p.grams} g</span>
              <button type="button" className="btn small" onClick={() => setCounts((c) => ({ ...c, [p.id]: Math.max(0, (c[p.id] ?? 0) - 1) }))}>−</button>
              <b style={{ minWidth: 32, textAlign: 'center' }}>{counts[p.id] ?? 0}</b>
              <button type="button" className="btn small" onClick={() => setCounts((c) => ({ ...c, [p.id]: (c[p.id] ?? 0) + 1 }))}>+</button>
              {exp && <span className="muted small">esperado {exp.product_expected[p.id] ?? 0}</span>}
            </div>
          ))}
        </div>
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <button className="btn" onClick={onClose}>Cancelar</button>
          <button className="btn btn-primary" disabled={busy || !to || cash === ''} onClick={submit} data-testid="transfer-confirm">{busy ? 'Transfiriendo…' : 'Transferir'}</button>
        </div>
      </div>
    </Modal>
  );
}
