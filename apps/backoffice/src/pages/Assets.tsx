import { useState, type FormEvent } from 'react';
import { api, qs } from '../api/client';
import { useFetch } from '../lib/useFetch';
import { useToast } from '../components/Toast';
import { Badge, Card, Empty, Field, Loading, Modal, PageTitle, SeverityBadge, StatusBadge } from '../components/ui';
import type { Asset, CaseStatus, Severity, Ticket } from '../types';
import { fmtDate, fmtDateTime } from '../lib/format';

const TYPE_LABEL: Record<string, string> = { battery: 'Batería', charger: 'Cargador', pos: 'POS', cart: 'Carrito' };

export function AssetsPage() {
  const toast = useToast();
  const assets = useFetch<Asset[]>(() => api.get('/v1/assets'), [], { every: 60_000 });
  const [ticketStatus, setTicketStatus] = useState('');
  const tickets = useFetch<Ticket[]>(() => api.get(`/v1/maintenance/tickets${qs({ status: ticketStatus })}`), [ticketStatus]);
  const [creating, setCreating] = useState<Asset | null>(null);
  const [form, setForm] = useState({ title: '', description: '', severity: 'review' as Severity, kind: 'corrective' as 'corrective' | 'preventive' });
  const [resolving, setResolving] = useState<{ t: Ticket; status: CaseStatus } | null>(null);
  const [resolution, setResolution] = useState('');

  const assetOf = (id: string) => assets.data?.find((a) => a.id === id);

  const create = async (e: FormEvent) => {
    e.preventDefault();
    if (!creating) return;
    try {
      await api.post('/v1/maintenance/tickets', { asset_id: creating.id, ...form });
      toast.toast('Ticket creado', 'success');
      setCreating(null);
      setForm({ title: '', description: '', severity: 'review', kind: 'corrective' });
      void tickets.reload(true);
      void assets.reload(true);
    } catch (err) {
      toast.error(err);
    }
  };

  const changeStatus = async (t: Ticket, status: CaseStatus, res?: string) => {
    try {
      await api.patch(`/v1/maintenance/tickets/${t.id}`, { status, resolution: res || undefined });
      toast.toast('Ticket actualizado', 'success');
      setResolving(null);
      setResolution('');
      void tickets.reload(true);
      void assets.reload(true);
    } catch (err) {
      toast.error(err);
    }
  };

  return (
    <div>
      <PageTitle title="Activos y mantenimiento" subtitle="Carrito, batería, cargador y POS con historial; preventivos programados y tickets correctivos." />
      <Card title={`Activos (${assets.data?.length ?? 0})`}>
        {assets.loading && !assets.data && <Loading />}
        {assets.data && (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Código</th>
                  <th>Tipo</th>
                  <th>Carrito</th>
                  <th>Estado</th>
                  <th>Último preventivo</th>
                  <th>Próximo preventivo</th>
                  <th className="num">Tickets abiertos</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {assets.data.map((a) => (
                  <tr key={a.id}>
                    <td className="mono">{a.code}</td>
                    <td>{TYPE_LABEL[a.asset_type] ?? a.asset_type}</td>
                    <td>{a.cart_code ?? '—'}</td>
                    <td>
                      <StatusBadge status={a.status} />
                    </td>
                    <td>{fmtDate(a.last_maintenance_at)}</td>
                    <td>
                      {fmtDate(a.next_maintenance_at)} {a.overdue && <Badge tone="red">VENCIDO</Badge>}
                    </td>
                    <td className="num">{a.open_tickets.length ? <Badge tone="amber">{a.open_tickets.length}</Badge> : 0}</td>
                    <td>
                      <button type="button" className="btn small" onClick={() => setCreating(a)}>
                        + Ticket
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card
        title="Tickets de mantenimiento"
        actions={
          <select value={ticketStatus} onChange={(e) => setTicketStatus(e.target.value)}>
            <option value="">Todos</option>
            <option value="open">Abiertos</option>
            <option value="in_progress">En proceso</option>
            <option value="resolved">Resueltos</option>
            <option value="closed">Cerrados</option>
          </select>
        }
      >
        {tickets.loading && !tickets.data && <Loading />}
        {tickets.data && tickets.data.length === 0 && <Empty text="Sin tickets" />}
        {tickets.data && tickets.data.length > 0 && (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Creado</th>
                  <th>Activo</th>
                  <th>Título</th>
                  <th>Tipo</th>
                  <th>Severidad</th>
                  <th>Estado</th>
                  <th>Resolución</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {tickets.data.map((t) => (
                  <tr key={t.id}>
                    <td className="nowrap">{fmtDateTime(t.created_at)}</td>
                    <td className="mono">{assetOf(t.asset_id)?.code ?? t.asset_id.slice(0, 8)}</td>
                    <td>
                      <b>{t.title}</b>
                      {t.description && <div className="small muted">{t.description}</div>}
                    </td>
                    <td>{t.kind === 'preventive' ? 'Preventivo' : 'Correctivo'}</td>
                    <td>
                      <SeverityBadge severity={t.severity} />
                    </td>
                    <td>
                      <StatusBadge status={t.status} />
                    </td>
                    <td>{t.resolution ?? '—'}</td>
                    <td className="nowrap">
                      {t.status === 'open' && (
                        <button type="button" className="btn small" onClick={() => changeStatus(t, 'in_progress')}>
                          Iniciar
                        </button>
                      )}{' '}
                      {(t.status === 'open' || t.status === 'in_progress') && (
                        <button type="button" className="btn small btn-success" onClick={() => setResolving({ t, status: 'resolved' })}>
                          Resolver
                        </button>
                      )}{' '}
                      {t.status === 'resolved' && (
                        <button type="button" className="btn small" onClick={() => changeStatus(t, 'closed')}>
                          Cerrar
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {creating && (
        <Modal title={`Nuevo ticket · ${creating.code}`} onClose={() => setCreating(null)}>
          <form onSubmit={create} className="stack">
            <Field label="Título">
              <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required autoFocus />
            </Field>
            <Field label="Descripción / evidencia">
              <textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
            </Field>
            <div className="grid-2">
              <Field label="Severidad">
                <select value={form.severity} onChange={(e) => setForm({ ...form, severity: e.target.value as Severity })}>
                  <option value="urgent">URGENTE</option>
                  <option value="review">REVISAR</option>
                  <option value="normal">NORMAL</option>
                </select>
              </Field>
              <Field label="Tipo">
                <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value as 'corrective' | 'preventive' })}>
                  <option value="corrective">Correctivo</option>
                  <option value="preventive">Preventivo</option>
                </select>
              </Field>
            </div>
            <div className="row" style={{ justifyContent: 'flex-end' }}>
              <button type="button" className="btn" onClick={() => setCreating(null)}>
                Cancelar
              </button>
              <button type="submit" className="btn btn-primary">
                Crear ticket
              </button>
            </div>
          </form>
        </Modal>
      )}
      {resolving && (
        <Modal title={`Resolver · ${resolving.t.title}`} onClose={() => setResolving(null)}>
          <Field label="Resolución">
            <textarea value={resolution} onChange={(e) => setResolution(e.target.value)} autoFocus />
          </Field>
          <div className="row" style={{ justifyContent: 'flex-end', marginTop: 10 }}>
            <button type="button" className="btn" onClick={() => setResolving(null)}>
              Cancelar
            </button>
            <button type="button" className="btn btn-success" onClick={() => changeStatus(resolving.t, resolving.status, resolution)}>
              Marcar resuelto
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
