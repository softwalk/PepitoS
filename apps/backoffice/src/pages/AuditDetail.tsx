import { Link, useParams } from 'react-router-dom';
import { api } from '../api/client';
import { useFetch } from '../lib/useFetch';
import { useAuth } from '../state/auth';
import { EvidenceGallery } from '../components/EvidenceGallery';
import { Badge, Card, Empty, Loading, PageTitle } from '../components/ui';
import type { Audit, Case, Point, User } from '../types';
import { fmtDateTime, money } from '../lib/format';

const CHECK_LABEL: Record<string, string> = {
  clean_ok: 'Limpieza del punto y carrito',
  uniform_ok: 'Uniforme completo',
  product_ok: 'Producto en buen estado',
  display_ok: 'Exhibición correcta',
  prices_visible: 'Precios visibles',
  cart_secure: 'Carrito seguro',
  pos_ok: 'POS / terminal funcionando',
};

export function AuditDetailPage() {
  const { id = '' } = useParams();
  const { hasRole } = useAuth();
  const { data: a, loading } = useFetch<Audit>(() => api.get(`/v1/audits/${id}`), [id]);
  const point = useFetch<Point>(() => api.get(`/v1/admin/points/${a!.point_id}`), [a?.point_id], { silent: true, enabled: !!a });
  const users = useFetch<User[]>(() => api.get('/v1/admin/users'), [], { silent: true, enabled: hasRole('ops', 'admin') });
  const cases = useFetch<Case[]>(() => api.get(`/v1/cases?status=open,in_progress,resolved,closed&point_id=${a!.point_id}`), [a?.point_id], { silent: true, enabled: !!a });
  const related = (cases.data ?? []).filter((c) => c.payload?.audit_id === id);

  if (loading && !a) return <Loading />;
  if (!a) return <Empty text="Auditoría no encontrada" />;
  const auditor = users.data?.find((u) => u.id === a.auditor_id)?.name ?? a.auditor_id.slice(0, 8);
  const diff = a.cash_counted_cents !== null && a.cash_expected_cents !== null ? a.cash_counted_cents - a.cash_expected_cents : null;

  return (
    <div>
      <PageTitle
        title={`Auditoría · ${point.data?.name ?? ''}`}
        subtitle={
          <span className="tag-line">
            {fmtDateTime(a.performed_at)} · auditor {auditor} · {a.non_conformities.length ? <Badge tone="red">{a.non_conformities.length} no conformidad(es)</Badge> : <Badge tone="green">Sin no conformidades</Badge>} · <Link to="/supervisor">← Mi día</Link>
          </span>
        }
      />
      <div className="grid-2">
        <div>
          <Card title="Checklist">
            <table className="table compact">
              <tbody>
                {Object.entries(a.checklist).map(([k, v]) => (
                  <tr key={k}>
                    <td>{CHECK_LABEL[k] ?? k}</td>
                    <td>{v ? <Badge tone="green">Sí</Badge> : <Badge tone="red">No</Badge>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
          <Card title="Arqueo sorpresa">
            {a.cash_counted_cents === null ? (
              <Empty text="Sin arqueo" />
            ) : (
              <div className="stat-inline">
                <span>
                  Contado: <b>{money(a.cash_counted_cents)}</b>
                </span>
                <span>
                  Esperado: <b>{money(a.cash_expected_cents)}</b>
                </span>
                <span style={{ color: diff ? 'var(--red)' : undefined }}>
                  Diferencia: <b>{diff === null ? '—' : money(diff)}</b>
                </span>
              </div>
            )}
          </Card>
          {a.notes && (
            <Card title="Notas">
              <p style={{ margin: 0 }}>{a.notes}</p>
            </Card>
          )}
          {related.length > 0 && (
            <Card title={`Casos abiertos por esta auditoría (${related.length})`}>
              <ul>
                {related.map((c) => (
                  <li key={c.id}>
                    <Link to={`/casos/${c.id}`}>{c.title}</Link>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
        <Card title={`Evidencias (${a.evidence.length})`}>
          <EvidenceGallery items={a.evidence} emptyText="La auditoría no adjuntó fotos" />
        </Card>
      </div>
    </div>
  );
}
