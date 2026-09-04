import { Link, useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { useFetch } from '../lib/useFetch';
import { Badge, Empty, Loading, PageTitle, StatusBadge } from '../components/ui';
import type { Case, PointStatus, SupervisorExceptions } from '../types';
import { CATEGORY_LABEL, ageLabel, label, money, ratioPct } from '../lib/format';

function CaseCard({ c }: { c: Case }) {
  const nav = useNavigate();
  return (
    <div className="sev-card" data-testid="sev-card">
      <div className="title">{c.title}</div>
      <div className="meta">
        {c.point && <span>📍 {c.point.name}</span>}
        <span>⏱ {ageLabel(c.age_minutes)}</span>
        <span>{label(CATEGORY_LABEL, c.category)}</span>
        {c.status === 'in_progress' && <Badge tone="blue">En proceso</Badge>}
        {c.assignee && <span>👤 {c.assignee.name}</span>}
      </div>
      {c.description && <div className="small muted">{c.description.slice(0, 140)}</div>}
      <button type="button" className="btn btn-primary btn-big" onClick={() => nav(`/casos/${c.id}`)}>
        Atender
      </button>
    </div>
  );
}

function PointCard({ p }: { p: PointStatus }) {
  const progress = ratioPct(p.sales_cents, p.target_cents);
  return (
    <div className="point-card">
      <div className="row-between">
        <b>{p.point.name}</b>
        <StatusBadge status={p.status} />
      </div>
      <div className="small muted">
        {p.operator?.name ?? 'Sin operador'} · {money(p.sales_cents, { decimals: 0 })} ({progress}% de meta) · {p.tx} tx
      </div>
      <div className="bar">
        <div style={{ width: `${Math.min(100, progress)}%` }} />
      </div>
      <div className="row" style={{ marginTop: 4 }}>
        <Link to={`/supervisor/auditoria/${p.point.id}`} className="btn small">
          Auditar (muestreo)
        </Link>
        <Link to={`/excepciones?point_id=${p.point.id}`} className="btn small btn-ghost">
          Casos
        </Link>
      </div>
    </div>
  );
}

export function SupervisorPage() {
  const { data, loading, reload } = useFetch<SupervisorExceptions>(() => api.get('/v1/supervisor/exceptions'), [], { every: 60_000 });
  const normalCases = data?.normal_cases ?? [];
  const pointsWithoutCases = (data?.normal ?? []).filter((p) => p.open_cases.urgent + p.open_cases.review === 0);
  return (
    <div>
      <PageTitle
        title="Mi día"
        subtitle="Las reglas ordenan tu día: atiende URGENTE ahora, REVISAR en la ruta de hoy, NORMAL sólo por muestreo."
        actions={
          <>
            <button type="button" className="btn" onClick={() => reload()}>
              Actualizar
            </button>
            <Link to="/supervisor/ruta" className="btn btn-primary">
              Ver ruta
            </Link>
          </>
        }
      />
      {loading && !data && <Loading />}
      {data && (
        <>
          <section className="sev-block urgent" data-testid="block-urgent">
            <div className="sev-block-head">
              <h2>URGENTE · Atender ahora</h2>
              <Badge tone="red">{data.urgent.length}</Badge>
            </div>
            {data.urgent.length === 0 ? <Empty text="Nada urgente. Bien." /> : <div className="sev-cards">{data.urgent.map((c) => <CaseCard key={c.id} c={c} />)}</div>}
          </section>
          <section className="sev-block review" data-testid="block-review">
            <div className="sev-block-head">
              <h2>REVISAR · Visita o ruta de hoy</h2>
              <Badge tone="amber">{data.review.length}</Badge>
            </div>
            {data.review.length === 0 ? <Empty text="Nada por revisar." /> : <div className="sev-cards">{data.review.map((c) => <CaseCard key={c.id} c={c} />)}</div>}
          </section>
          <section className="sev-block normal" data-testid="block-normal">
            <div className="sev-block-head">
              <h2>NORMAL · Dentro de parámetros</h2>
              <Badge tone="green">{normalCases.length + pointsWithoutCases.length}</Badge>
            </div>
            {normalCases.length > 0 && <div className="sev-cards" style={{ marginBottom: 10 }}>{normalCases.map((c) => <CaseCard key={c.id} c={c} />)}</div>}
            {pointsWithoutCases.length === 0 && normalCases.length === 0 && <Empty text="Todos los puntos tienen algún caso abierto." />}
            {pointsWithoutCases.length > 0 && (
              <div className="sev-cards">
                {pointsWithoutCases.map((p) => (
                  <PointCard key={p.point.id} p={p} />
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}
