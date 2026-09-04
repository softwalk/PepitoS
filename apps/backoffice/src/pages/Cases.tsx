import { useMemo } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api, qs } from '../api/client';
import { useFetch } from '../lib/useFetch';
import { Badge, Card, Empty, Field, Loading, PageTitle, SeverityBadge, StatusBadge } from '../components/ui';
import type { Case, Point } from '../types';
import { CATEGORY_LABEL, ageLabel, fmtDateTime, label } from '../lib/format';

const SOURCE_LABEL: Record<string, string> = { operator: 'Operador', rule: 'Regla', supervisor: 'Supervisor', system: 'Sistema' };

export function CasesPage() {
  const [params, setParams] = useSearchParams();
  const status = params.get('status') ?? 'open,in_progress';
  const severity = params.get('severity') ?? '';
  const pointId = params.get('point_id') ?? '';

  const { data, loading } = useFetch<Case[]>(() => api.get(`/v1/cases${qs({ status, severity, point_id: pointId })}`), [status, severity, pointId], { every: 60_000 });
  const points = useFetch<Point[]>(() => api.get('/v1/admin/points'), []);

  const sorted = useMemo(() => (data ? [...data].sort((a, b) => b.priority_score - a.priority_score) : []), [data]);
  const set = (k: string, v: string) => {
    const p = new URLSearchParams(params);
    if (v) p.set(k, v);
    else p.delete(k);
    setParams(p, { replace: true });
  };

  return (
    <div>
      <PageTitle title="Excepciones" subtitle="Casos ordenados por prioridad (severidad + impacto + antigüedad)." />
      <div className="filters">
        <Field label="Estado">
          <select value={status} onChange={(e) => set('status', e.target.value)}>
            <option value="open,in_progress">Abiertos y en proceso</option>
            <option value="open">Abiertos</option>
            <option value="in_progress">En proceso</option>
            <option value="resolved">Resueltos</option>
            <option value="closed">Cerrados</option>
            <option value="open,in_progress,resolved,closed">Todos</option>
          </select>
        </Field>
        <Field label="Severidad">
          <select value={severity} onChange={(e) => set('severity', e.target.value)}>
            <option value="">Todas</option>
            <option value="urgent">URGENTE</option>
            <option value="review">REVISAR</option>
            <option value="normal">NORMAL</option>
          </select>
        </Field>
        <Field label="Punto">
          <select value={pointId} onChange={(e) => set('point_id', e.target.value)}>
            <option value="">Todos</option>
            {(points.data ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <Card title={`Casos (${sorted.length})`}>
        {loading && !data && <Loading />}
        {data && sorted.length === 0 && <Empty text="Sin casos con estos filtros" />}
        {sorted.length > 0 && (
          <div className="table-wrap">
            <table className="table" data-testid="cases-table">
              <thead>
                <tr>
                  <th className="num">Prioridad</th>
                  <th>Severidad</th>
                  <th>Caso</th>
                  <th>Punto</th>
                  <th>Categoría</th>
                  <th>Origen</th>
                  <th>Estado</th>
                  <th>Responsable</th>
                  <th>Abierto</th>
                  <th className="num">Tiempo abierto</th>
                  <th className="num">Acciones</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((c) => (
                  <tr key={c.id}>
                    <td className="num mono">{c.priority_score.toFixed(1)}</td>
                    <td>
                      <SeverityBadge severity={c.severity} />
                    </td>
                    <td>
                      <Link to={`/casos/${c.id}`}>
                        <b>{c.title}</b>
                      </Link>
                      {c.ai && (
                        <div className="small muted">
                          IA sugiere: {label(CATEGORY_LABEL, c.ai.suggested_category)} ({Math.round(c.ai.confidence * 100)}%)
                        </div>
                      )}
                    </td>
                    <td>{c.point?.name ?? '—'}</td>
                    <td>{label(CATEGORY_LABEL, c.category)}</td>
                    <td>{SOURCE_LABEL[c.source] ?? c.source}</td>
                    <td>
                      <StatusBadge status={c.status} />
                    </td>
                    <td>{c.assignee?.name ?? <span className="muted">Sin asignar</span>}</td>
                    <td className="nowrap">{fmtDateTime(c.opened_at)}</td>
                    <td className="num">{ageLabel(c.age_minutes)}</td>
                    <td className="num">
                      {c.actions.length ? (
                        <Badge tone={c.actions.every((a) => a.status === 'done') ? 'green' : 'amber'}>
                          {c.actions.filter((a) => a.status === 'done').length}/{c.actions.length}
                        </Badge>
                      ) : (
                        <span className="muted">0</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
