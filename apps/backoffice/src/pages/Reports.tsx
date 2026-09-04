/** Centro de Reportes: catálogo por categorías con sólo los reportes permitidos al rol (lo decide la API). */
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import { Badge, Empty, Loading, PageTitle } from '../components/ui';
import { Icon } from '../components/icons';
import { useFetch } from '../lib/useFetch';
import { useAuth } from '../state/auth';
import type { ReportCatalog } from '../types';

const SCOPE_LABEL = { network: 'Toda la red', zone: 'Tu zona', self: 'Tu desempeño' };

export function ReportsPage() {
  const { user } = useAuth();
  const { data, loading } = useFetch<ReportCatalog>(() => api.get('/v1/reports/bi'), []);
  return (
    <>
      <PageTitle
        title="Centro de Reportes"
        subtitle={user?.role === 'supervisor' ? 'Reportes de tu zona. Cada reporte abre con el periodo «Hoy»; los filtros viven en la URL y se pueden compartir.' : 'Elige un reporte. Cada uno responde una decisión concreta: KPI → desviación → causa → acción.'}
      />
      {loading && !data && <Loading />}
      {data && data.categories.length === 0 && <Empty text="Tu rol no tiene reportes asignados." />}
      {data?.categories.map((cat) => (
        <section key={cat.name} className="report-category" data-testid={`report-category-${cat.name}`}>
          <h2 className="report-category-title">{cat.name}</h2>
          <div className="report-grid">
            {cat.reports.map((r) => (
              <Link key={r.key} to={`/reportes/${r.key}?period=today`} className="report-tile" data-testid={`report-tile-${r.key}`}>
                <div className="report-tile-head">
                  <span className="report-tile-icon">
                    <Icon name="reports" size={18} />
                  </span>
                  <h3>{r.title}</h3>
                </div>
                <p>{r.description}</p>
                <p className="report-tile-decision">
                  <b>Decide:</b> {r.decision}
                </p>
                <div className="report-tile-meta">
                  <Badge tone="gray">{r.frequency}</Badge>
                  <Badge tone={r.scope === 'network' ? 'blue' : 'amber'}>{SCOPE_LABEL[r.scope]}</Badge>
                </div>
              </Link>
            ))}
          </div>
        </section>
      ))}
    </>
  );
}
