import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api } from '../api/client';
import { useFetch } from '../lib/useFetch';
import { useAuth } from '../state/auth';
import { useToast } from '../components/Toast';
import { EvidenceGallery } from '../components/EvidenceGallery';
import { Badge, Card, Empty, Field, Loading, Modal, PageTitle, StatusBadge } from '../components/ui';
import type { InventoryCountRow, InventoryReceiptRow, InventoryStatus, Lot, Presentation } from '../types';
import { fmtDateTime, fmtKg } from '../lib/format';

const KIND_LABEL: Record<string, string> = { manual: 'Manual', close: 'Cierre', transfer: 'Transferencia' };

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
  const [params] = useSearchParams();
  const focusCount = params.get('count');
  const [days, setDays] = useState(7);
  const counts = useFetch<{ counts: InventoryCountRow[] }>(() => api.get(`/v1/inventory/counts?days=${days}`), [days], { silent: true });
  const receipts = useFetch<{ receipts: InventoryReceiptRow[] }>(() => api.get(`/v1/inventory/receipts?days=${days}`), [days], { silent: true });
  const [openCount, setOpenCount] = useState<InventoryCountRow | null>(null);
  useEffect(() => {
    if (focusCount && counts.data) {
      const c = counts.data.counts.find((x) => x.id === focusCount);
      if (c) setOpenCount(c);
      else if (days < 90) setDays(90);
    }
  }, [focusCount, counts.data, days]);
  return (
    <div>
      <PageTitle
        title="Inventario"
        subtitle={status.data ? `Balance por punto reconstruido desde movimientos · mínimo ${status.data.min_units} u por presentación · ${status.data.total_units} piezas = ${fmtKg(status.data.total_kg)} en total` : ''}
      />
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
                    <th className="num">Total (u.)</th>
                    <th className="num">Total (kg)</th>
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
                      <td className="num" data-testid={`kg-${p.point.id}`}>
                        <b>{fmtKg(p.total_kg)}</b>
                      </td>
                    </tr>
                  ))}
                  <tr className="total-row">
                    <td colSpan={2 + presentations.length}>
                      <b>Total</b>
                    </td>
                    <td className="num">
                      <b>{status.data.total_units}</b>
                    </td>
                    <td className="num" data-testid="kg-total">
                      <b>{fmtKg(status.data.total_kg)}</b>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          )}
          <p className="muted small">Rojo: bajo el mínimo (quiebre). Ámbar: menos del doble del mínimo (programar reposición). Kilogramos = piezas × gramos nominales de cada presentación.</p>
        </Card>
      )}

      <Card
        title={`Conteos físicos (${counts.data?.counts.length ?? 0})`}
        actions={
          <select value={days} onChange={(e) => setDays(Number(e.target.value))} aria-label="Periodo">
            <option value={1}>Hoy</option>
            <option value={7}>7 días</option>
            <option value={30}>30 días</option>
            <option value={90}>90 días</option>
          </select>
        }
        testId="counts-card"
      >
        {!counts.data && <Loading />}
        {counts.data && counts.data.counts.length === 0 && <Empty text="Sin conteos en el periodo" />}
        {counts.data && counts.data.counts.length > 0 && (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Fecha</th>
                  <th>Punto</th>
                  <th>Operador</th>
                  <th>Tipo</th>
                  <th className="num">Contado (u.)</th>
                  <th className="num">Contado (kg)</th>
                  <th className="num">Esperado (kg)</th>
                  <th className="num">Dif. (u.)</th>
                  <th className="num">Fotos</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {counts.data.counts.map((c) => (
                  <tr key={c.id} data-testid={`count-row-${c.id}`}>
                    <td>{fmtDateTime(c.occurred_at)}</td>
                    <td>{c.point.name}</td>
                    <td>{c.actor.name}</td>
                    <td>{KIND_LABEL[c.kind] ?? c.kind}</td>
                    <td className="num">{c.counted_units}</td>
                    <td className="num">
                      <b>{fmtKg(c.counted_kg)}</b>
                    </td>
                    <td className="num">{fmtKg(c.expected_kg)}</td>
                    <td className="num">{c.diff_units > 0 ? <Badge tone="amber">{c.diff_units}</Badge> : '0'}</td>
                    <td className="num">{c.evidence.length > 0 ? <Badge tone="blue">📷 {c.evidence.length}</Badge> : <span className="muted">—</span>}</td>
                    <td>
                      <button type="button" className="btn small" onClick={() => setOpenCount(c)} data-testid={`count-open-${c.id}`}>
                        Ver
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title={`Recepciones de producto (${receipts.data?.receipts.length ?? 0})`} testId="receipts-card">
        {!receipts.data && <Loading />}
        {receipts.data && receipts.data.receipts.length === 0 && <Empty text="Sin recepciones en el periodo" />}
        {receipts.data && receipts.data.receipts.length > 0 && (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Fecha</th>
                  <th>Punto</th>
                  <th>Operador</th>
                  <th>QR</th>
                  <th className="num">Piezas</th>
                  <th className="num">kg</th>
                  <th>Fotos</th>
                </tr>
              </thead>
              <tbody>
                {receipts.data.receipts.map((r) => (
                  <tr key={r.id}>
                    <td>{fmtDateTime(r.occurred_at)}</td>
                    <td>{r.point.name}</td>
                    <td>{r.actor.name}</td>
                    <td className="mono">{r.qr_code ?? '—'}</td>
                    <td className="num">{r.units}</td>
                    <td className="num">
                      <b>{fmtKg(r.kg)}</b>
                    </td>
                    <td style={{ minWidth: 140 }}>{r.evidence.length > 0 ? <EvidenceGallery items={r.evidence} /> : <span className="muted">—</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {openCount && (
        <Modal className="wide" title={`Conteo ${KIND_LABEL[openCount.kind] ?? openCount.kind} · ${openCount.point.name} · ${fmtDateTime(openCount.occurred_at)}`} onClose={() => setOpenCount(null)}>
          <div data-testid="count-detail">
            <p className="muted small">Registrado por {openCount.actor.name}. Kilogramos = piezas × gramos nominales.</p>
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Presentación</th>
                    <th className="num">Contado</th>
                    <th className="num">Teórico</th>
                    <th className="num">Diferencia</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.keys({ ...openCount.theoretical, ...openCount.counts }).map((pid) => (
                    <tr key={pid}>
                      <td>{pres.data?.find((p) => p.id === pid)?.name ?? pid.slice(0, 8)}</td>
                      <td className="num">{openCount.counts[pid] ?? 0}</td>
                      <td className="num">{openCount.theoretical[pid] ?? 0}</td>
                      <td className="num">{(openCount.differences[pid] ?? 0) !== 0 ? <Badge tone="amber">{openCount.differences[pid] > 0 ? '+' : ''}{openCount.differences[pid]}</Badge> : '0'}</td>
                    </tr>
                  ))}
                  <tr className="total-row">
                    <td>
                      <b>Total</b>
                    </td>
                    <td className="num">
                      <b>{openCount.counted_units} u. · {fmtKg(openCount.counted_kg)}</b>
                    </td>
                    <td className="num">{fmtKg(openCount.expected_kg)}</td>
                    <td className="num">{openCount.diff_kg !== 0 ? `${openCount.diff_kg > 0 ? '+' : ''}${fmtKg(openCount.diff_kg)}` : '0'}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <h4 style={{ margin: '12px 0 6px' }}>Fotos del producto ({openCount.evidence.length})</h4>
            <EvidenceGallery items={openCount.evidence} emptyText="El operador no adjuntó foto en este conteo" />
          </div>
        </Modal>
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
