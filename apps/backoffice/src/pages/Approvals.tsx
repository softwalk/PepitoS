import { useState } from 'react';
import { api, qs } from '../api/client';
import { useFetch } from '../lib/useFetch';
import { useAuth } from '../state/auth';
import { useToast } from '../components/Toast';
import { Card, Empty, Field, Loading, Modal, PageTitle, StatusBadge } from '../components/ui';
import type { Approval, User } from '../types';
import { fmtDateTime, money } from '../lib/format';

const TYPE_LABEL: Record<string, string> = { payment: 'Pago', purchase: 'Compra', adjustment: 'Ajuste' };

export function ApprovalsPage() {
  const toast = useToast();
  const { hasRole } = useAuth();
  const canDecide = hasRole('finance', 'admin');
  const [status, setStatus] = useState('pending');
  const { data, loading, reload } = useFetch<Approval[]>(() => api.get(`/v1/approvals${qs({ status })}`), [status], { every: 60_000 });
  const users = useFetch<User[]>(() => api.get('/v1/admin/users'), [], { silent: true, enabled: hasRole('ops', 'admin') });
  const [deciding, setDeciding] = useState<{ a: Approval; decision: 'approve' | 'reject' } | null>(null);
  const [note, setNote] = useState('');
  const userName = (id: string | null) => users.data?.find((u) => u.id === id)?.name ?? (id ? id.slice(0, 8) : '—');

  const decide = async () => {
    if (!deciding) return;
    try {
      await api.post(`/v1/approvals/${deciding.a.id}/decision`, { decision: deciding.decision, note: note || null });
      toast.toast(deciding.decision === 'approve' ? 'Aprobada' : 'Rechazada', 'success');
      setDeciding(null);
      setNote('');
      void reload(true);
    } catch (e) {
      toast.error(e);
    }
  };

  return (
    <div>
      <PageTitle
        title="Aprobaciones"
        subtitle="Human-in-the-loop: pagos, compras y ajustes materiales requieren decisión humana. Quien solicita no puede aprobar."
        actions={
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="pending">Pendientes</option>
            <option value="approved">Aprobadas</option>
            <option value="rejected">Rechazadas</option>
            <option value="cancelled">Canceladas (turno reabierto)</option>
            <option value="">Todas</option>
          </select>
        }
      />
      <Card>
        {loading && !data && <Loading />}
        {data && data.length === 0 && <Empty text="Sin aprobaciones" />}
        {data && data.length > 0 && (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Solicitada</th>
                  <th>Tipo</th>
                  <th>Título</th>
                  <th className="num">Monto</th>
                  <th>Solicitó</th>
                  <th>Nota</th>
                  <th>Estado</th>
                  <th>Decisión</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {data.map((a) => (
                  <tr key={a.id}>
                    <td className="nowrap">{fmtDateTime(a.created_at)}</td>
                    <td>{TYPE_LABEL[a.approval_type] ?? a.approval_type}</td>
                    <td>
                      <b>{a.title}</b>
                    </td>
                    <td className="num">{a.amount_cents === null ? '—' : money(a.amount_cents)}</td>
                    <td>{userName(a.requested_by)}</td>
                    <td>{a.note ?? '—'}</td>
                    <td>
                      <StatusBadge status={a.status} />
                    </td>
                    <td className="small">
                      {a.decided_at ? (
                        <>
                          {userName(a.decided_by)} · {fmtDateTime(a.decided_at)}
                          {a.decision_note && <div className="muted">{a.decision_note}</div>}
                        </>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td className="nowrap">
                      {a.status === 'pending' && canDecide && (
                        <>
                          <button type="button" className="btn small btn-success" onClick={() => setDeciding({ a, decision: 'approve' })}>
                            Aprobar
                          </button>{' '}
                          <button type="button" className="btn small btn-danger" onClick={() => setDeciding({ a, decision: 'reject' })}>
                            Rechazar
                          </button>
                        </>
                      )}
                      {a.status === 'pending' && !canDecide && <span className="muted small">Decide Finanzas</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      {deciding && (
        <Modal title={`${deciding.decision === 'approve' ? 'Aprobar' : 'Rechazar'} · ${deciding.a.title}`} onClose={() => setDeciding(null)}>
          <p>
            Monto: <b>{deciding.a.amount_cents === null ? '—' : money(deciding.a.amount_cents)}</b>
          </p>
          <Field label="Nota">
            <textarea value={note} onChange={(e) => setNote(e.target.value)} autoFocus placeholder="Motivo o referencia" />
          </Field>
          <div className="row" style={{ justifyContent: 'flex-end', marginTop: 10 }}>
            <button type="button" className="btn" onClick={() => setDeciding(null)}>
              Cancelar
            </button>
            <button type="button" className={`btn ${deciding.decision === 'approve' ? 'btn-success' : 'btn-danger'}`} onClick={decide}>
              Confirmar
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
