/** Vista de impresión de un reporte: sin navegación ni botones; `@page` Carta con orientación según reporte.
 *  Consume el mismo endpoint con la misma autorización (auditado como `report.export`) y lanza `window.print()`. */
import { useEffect, useMemo, useState } from 'react';
import { Navigate, useParams, useSearchParams } from 'react-router-dom';
import { api, qs } from '../api/client';
import { Loading } from '../components/ui';
import { useFetch } from '../lib/useFetch';
import { fmtDateTime } from '../lib/format';
import { filtersFrom } from '../lib/reports';
import { useAuth } from '../state/auth';
import type { ReportOptions, ReportPayload } from '../types';
import { ReportBody } from './ReportView';

const FILTER_LABEL: Record<string, string> = { zone_id: 'Zona', point_id: 'Punto', operator_id: 'Vendedor', cart_id: 'Carrito', presentation_id: 'Presentación', method: 'Medio de pago' };

export function ReportPrintPage() {
  const { key } = useParams<{ key: string }>();
  const [params] = useSearchParams();
  const { user } = useAuth();
  const filters = useMemo(() => filtersFrom(params), [params]);
  const query = useMemo(() => qs({ ...filters, export: 'true' }), [filters]);
  const { data, error } = useFetch<ReportPayload>(() => api.get(`/v1/reports/bi/${key}${query}`), [key, query], { enabled: !!key, silent: true });
  const { data: options } = useFetch<ReportOptions>(() => api.get('/v1/reports/bi/options'), [], { silent: true });
  const [printed, setPrinted] = useState(false);

  useEffect(() => {
    if (!data) return;
    document.title = `${data.title} · ${data.period.label} · PEPITO OS`;
    const style = document.createElement('style');
    style.id = 'report-page-style';
    style.textContent = `@page { size: Letter ${data.orientation}; margin: 14mm 12mm 16mm 12mm; }`;
    document.head.appendChild(style);
    // Esperar a que recharts pinte los SVG antes de imprimir.
    const t = setTimeout(() => {
      if (!printed && !params.get('noprint')) {
        setPrinted(true);
        window.print();
      }
    }, 700);
    return () => {
      clearTimeout(t);
      style.remove();
    };
  }, [data, printed, params]);

  if (!key) return <Navigate to="/reportes" replace />;
  if (error) {
    return (
      <div className="print-page">
        <p className="empty">{error}</p>
      </div>
    );
  }
  if (!data) return <Loading />;
  const nameOf = (dim: string, id: string) => {
    const src = (options?.[{ zone_id: 'zones', point_id: 'points', operator_id: 'operators', cart_id: 'carts', presentation_id: 'presentations', method: 'methods' }[dim] as keyof ReportOptions] ?? []) as { id: string; name: string }[];
    return src.find((x) => x.id === id)?.name ?? id;
  };
  const applied = Object.entries(data.filters).filter(([k]) => FILTER_LABEL[k]);
  return (
    <div className={`print-page ${data.orientation}`} data-testid="report-print">
      <header className="print-head">
        <img src="/logo.png" alt="PEPITO" className="print-logo" />
        <div className="print-title">
          <h1>{data.title}</h1>
          <div className="muted">{data.category} · {data.description}</div>
        </div>
        <div className="print-meta">
          <div><b>Periodo:</b> {data.period.preset_label} — {data.period.label}</div>
          <div><b>Comparado con:</b> {data.compare.label}</div>
          <div><b>Generado:</b> {fmtDateTime(data.generated_at)} por {user?.name ?? '—'}</div>
          <div><b>Alcance:</b> {data.scope.zone_locked ? 'zona del supervisor' : data.scope.operator_locked ? 'desempeño propio' : 'toda la red'}</div>
          {applied.length > 0 && (
            <div>
              <b>Filtros:</b> {applied.map(([k, v]) => `${FILTER_LABEL[k]}: ${nameOf(k, v)}`).join(' · ')}
            </div>
          )}
        </div>
      </header>
      <ReportBody r={data} print />
      <footer className="print-foot">
        <span>PEPITO OS · {data.title} · {data.period.label}</span>
        <span>{['cash', 'executive', 'people', 'expansion'].includes(data.key) ? 'CONFIDENCIAL — uso interno' : 'Uso interno'}</span>
      </footer>
      <div className="print-actions no-print">
        <button type="button" className="btn btn-primary" onClick={() => window.print()}>
          Imprimir / Guardar PDF
        </button>
        <a className="btn" href={`/reportes/${data.key}${qs({ ...filters })}`}>
          Volver al reporte
        </a>
      </div>
    </div>
  );
}
