import { Link } from 'react-router-dom';
import { api } from '../api/client';
import { useFetch } from '../lib/useFetch';
import { RouteMap } from '../components/PointsMap';
import { Card, Empty, Loading, PageTitle, SeverityBadge } from '../components/ui';
import type { RouteStop } from '../types';
import { fmtDate } from '../lib/format';

export function SupervisorRoutePage() {
  const { data, loading } = useFetch<{ date: string; stops: RouteStop[] }>(() => api.get('/v1/supervisor/route'), [], { every: 120_000 });
  const total = (data?.stops ?? []).reduce((s, x) => s + x.distance_from_previous_m, 0);
  return (
    <div>
      <PageTitle title="Ruta de hoy" subtitle={data ? `${fmtDate(data.date)} · ${data.stops.length} paradas · ${(total / 1000).toFixed(1)} km aprox.` : ''} actions={<Link to="/supervisor" className="btn">← Mi día</Link>} />
      {loading && !data && <Loading />}
      {data && (
        <>
          <Card>
            <RouteMap stops={data.stops} />
          </Card>
          {data.stops.length === 0 && <Empty text="Sin paradas sugeridas: ningún punto de tu zona tiene casos abiertos." />}
          {data.stops.map((s) => (
            <div key={s.point.id} className="sev-card" style={{ marginBottom: 10 }}>
              <div className="row-between">
                <div className="title">
                  {s.order}. {s.point.name}
                </div>
                <SeverityBadge severity={s.severity} />
              </div>
              <div>{s.reason}</div>
              <div className="meta">
                <span>Prioridad {s.priority_score}</span>
                <span>{s.case_ids.length} caso(s)</span>
                {s.distance_from_previous_m > 0 && <span>{(s.distance_from_previous_m / 1000).toFixed(1)} km desde la anterior</span>}
              </div>
              <div className="row">
                <Link to={`/supervisor/auditoria/${s.point.id}`} className="btn btn-primary">
                  Auditar en sitio
                </Link>
                <Link to={`/excepciones?point_id=${s.point.id}`} className="btn">
                  Ver casos
                </Link>
                <a className="btn btn-ghost" href={`https://www.google.com/maps/dir/?api=1&destination=${s.point.lat},${s.point.lng}`} target="_blank" rel="noreferrer">
                  Navegar
                </a>
              </div>
            </div>
          ))}
        </>
      )}
    </div>
  );
}
