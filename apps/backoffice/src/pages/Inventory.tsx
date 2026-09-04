import { useState } from 'react';
import { api } from '../api/client';
import { useFetch } from '../lib/useFetch';
import { useAuth } from '../state/auth';
import { useToast } from '../components/Toast';
import { Badge, Card, Empty, Field, Loading, Modal, PageTitle, StatusBadge } from '../components/ui';
import type { InventoryStatus, Lot, Presentation } from '../types';
import { fmtDateTime } from '../lib/format';

interface Affected { point_id: string; point_name: string | null; presentation_id: string; received_units: number }

export function InventoryPage() {
  const toast = useToast();
  const { hasRole } = useAuth();
  const canBlock = hasRole('ops', 'admin');
  const status = useFetch<InventoryStatus>(() => api.get('/v1/inventory/status'), [], { every: 60_000 });
  const lots = useFetch<Lot[]>(() => api.get('/v1/lots'), [], { enabled: canBlock, silent: true });
  const pres = useFetch<Presentation[]>(() => api.get('/v1/admin/presentations'), [], { silent: true });
  const [blocking, setBlocking] = useState<Lot | null>(null);
  const [reason, setReason] = useState('');
  const [result, setResult] = useState<{ lot: Lot; affected: Affected[] } | null>(null);
  const presName = (id: string | null) => pres.data?.find((p) => p.id === id)?.name ?? (id ? id.slice(0, 8) : 'Todas');

  const block = async () => {
    if (!blocking || !reason.trim()) return;
    try {
      const r = await api.post<{ affected_points: Affected[] }>(`/v1/lots/${blocking.id}/block`, { reason: reason.trim() });
      setResult({ lot: blocking, affected: r.affected_points });
      toast.toast(`Lote ${blocking.code} bloqueado. ${r.affected_points.length} punto(s) afectado(s).`, 'success');
      setBlocking(null);
      setReason('');
      void lots.reload(true);
      void status.reload(true);
    } catch (e) {
      toast.error(e);
    }
  };

  const presentations = status.data?.points[0]?.items.map((i) => i.name) ?? [];
  return (
    <div>
      <PageTitle title="Inventario" subtitle={status.data ? `Balance por punto reconstruido desde movimientos · mínimo ${status.data.min_units} u por presentación` : ''} />
      {status.loading && !status.data && <Loading />}
      {status.data && (
        <Card title="Stock por punto y presentación">
          {status.data.points.length === 0 && <Empty />}
          {status.data.points.length > 0 && (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Punto</th>
                    <th>Riesgo de quiebre</th>
                    {presentations.map((n) => (
                      <th key={n} className="num">
                        {n}
                      </th>
                    ))}
                    <th className="num">Total</th>
                  </tr>
                </thead>
                <tbody>
                  {status.data.points.map((p) => (
                    <tr key={p.point.id}>
                      <td>
                        <b>{p.point.name}</b>
                      </td>
                      <td>
                        <StatusBadge status={p.stock_risk} />
                      </td>
                      {p.items.map((i) => (
                        <td key={i.presentation_id} className="num">
                          <span style={{ color: i.balance < i.min_units ? 'var(--red)' : i.balance < i.min_units * 2 ? 'var(--amber)' : undefined, fontWeight: i.balance < i.min_units * 2 ? 700 : 400 }}>{i.balance}</span>
                          {i.theoretical !== i.balance && <span className="muted small"> (teórico {i.theoretical})</span>}
                        </td>
                      ))}
                      <td className="num">
                        <b>{p.total_units}</b>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="muted small">Rojo: bajo el mínimo (quiebre). Ámbar: menos del doble del mínimo (programar reposición).</p>
        </Card>
      )}

      {canBlock && (
        <Card title="Lotes">
          {!lots.data && <Loading />}
          {lots.data && lots.data.length === 0 && <Empty text="Sin lotes registrados" />}
          {lots.data && lots.data.length > 0 && (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Lote</th>
                    <th>Presentación</th>
                    <th>Estado</th>
                    <th>Motivo</th>
                    <th>Bloqueado</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {lots.data.map((l) => (
                    <tr key={l.id}>
                      <td className="mono">{l.code}</td>
                      <td>{presName(l.presentation_id)}</td>
                      <td>
                        <StatusBadge status={l.status} />
                      </td>
                      <td>{l.blocked_reason ?? '—'}</td>
                      <td>{fmtDateTime(l.blocked_at)}</td>
                      <td>
                        {l.status !== 'blocked' && (
                          <button type="button" className="btn small btn-danger" onClick={() => setBlocking(l)}>
                            Bloquear
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {result && (
            <div style={{ marginTop: 12 }}>
              <Badge tone="red">Lote {result.lot.code} bloqueado</Badge> Puntos afectados:
              {result.affected.length === 0 ? (
                <span className="muted"> ninguno (sin recepciones de este lote)</span>
              ) : (
                <ul>
                  {result.affected.map((a, i) => (
                    <li key={i}>
                      {a.point_name ?? a.point_id} · {presName(a.presentation_id)} · {a.received_units} u retiradas del balance
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </Card>
      )}

      {blocking && (
        <Modal title={`Bloquear lote ${blocking.code}`} onClose={() => setBlocking(null)}>
          <p className="muted small">Decisión humana: se retiran del balance las unidades recibidas de este lote en cada punto y se evita nuevas entregas.</p>
          <Field label="Motivo (obligatorio)">
            <textarea value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Ej. reporte de calidad del proveedor" />
          </Field>
          <div className="row" style={{ justifyContent: 'flex-end', marginTop: 10 }}>
            <button type="button" className="btn" onClick={() => setBlocking(null)}>
              Cancelar
            </button>
            <button type="button" className="btn btn-danger" onClick={block} disabled={!reason.trim()}>
              Bloquear lote
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
