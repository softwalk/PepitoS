/** Página de un reporte: filtros en la URL (periodo + dimensiones), KPIs, hallazgos, gráficas y tablas.
 *  El alcance real lo fija la API (`scope`): el supervisor ve su zona aunque cambie la URL. */
import { useMemo } from 'react';
import { Link, Navigate, useParams, useSearchParams } from 'react-router-dom';
import { api, qs } from '../api/client';
import { Badge, Card, Loading, PageTitle } from '../components/ui';
import { ChartBlock, Insights, KpiGrid, TableBlock } from '../components/ReportBlocks';
import { useFetch } from '../lib/useFetch';
import { fmtDateTime } from '../lib/format';
import { PRESETS, filtersFrom, filtersToQuery, type Filters } from '../lib/reports';
import type { ReportKey, ReportOptions, ReportPayload } from '../types';

const KEYS: ReportKey[] = ['executive', 'sales', 'cash', 'points', 'people', 'inventory', 'quality', 'maintenance', 'compliance', 'expansion'];

/** Dimensiones aplicables por reporte (el resto de la URL se ignora). */
const DIMENSIONS: Record<ReportKey, string[]> = {
  executive: ['zone_id', 'point_id'],
  sales: ['zone_id', 'point_id', 'operator_id', 'cart_id', 'presentation_id', 'method'],
  cash: ['zone_id', 'point_id', 'operator_id'],
  points: ['zone_id', 'point_id'],
  people: ['zone_id', 'operator_id', 'point_id'],
  inventory: ['zone_id', 'point_id', 'presentation_id'],
  quality: ['zone_id', 'point_id'],
  maintenance: ['zone_id', 'cart_id'],
  compliance: ['zone_id', 'point_id', 'operator_id', 'cart_id'],
  expansion: ['zone_id'],
};
const DIM_LABEL: Record<string, string> = { zone_id: 'Zona', point_id: 'Punto', operator_id: 'Vendedor', cart_id: 'Carrito', presentation_id: 'Presentación', method: 'Medio de pago' };
const DIM_SOURCE: Record<string, keyof ReportOptions> = { zone_id: 'zones', point_id: 'points', operator_id: 'operators', cart_id: 'carts', presentation_id: 'presentations', method: 'methods' };

export function useReport(key: string | undefined, filters: Filters) {
  const query = useMemo(() => qs({ ...filters }), [filters]);
  return useFetch<ReportPayload>(() => api.get(`/v1/reports/bi/${key}${query}`), [key, query], { enabled: !!key });
}

export function ReportFilters({ reportKey, filters, onChange, options }: { reportKey: ReportKey; filters: Filters; onChange: (f: Filters) => void; options: ReportOptions | null }) {
  const set = (k: keyof Filters, v: string) => {
    const next = { ...filters, [k]: v || undefined };
    if (k === 'period' && v !== 'custom') {
      delete next.from;
      delete next.to;
    }
    if (k === 'zone_id') {
      // Cambiar de zona invalida punto/vendedor de otra zona.
      if (next.point_id && options && !options.points.some((p) => p.id === next.point_id && p.zone_id === v)) delete next.point_id;
      if (next.operator_id && options && !options.operators.some((p) => p.id === next.operator_id && p.zone_id === v)) delete next.operator_id;
    }
    onChange(next);
  };
  const period = filters.period ?? 'today';
  return (
    <div className="filters report-filters" data-testid="report-filters">
      <div className="field">
        <span className="field-label">Periodo</span>
        <div className="seg" role="tablist" aria-label="Periodo">
          {PRESETS.map((p) => (
            <button key={p.key} type="button" role="tab" aria-selected={period === p.key} className={period === p.key ? 'active' : ''} onClick={() => set('period', p.key)}>
              {p.label}
            </button>
          ))}
        </div>
      </div>
      {period === 'custom' && (
        <>
          <label className="field">
            <span className="field-label">Desde</span>
            <input type="date" value={filters.from ?? ''} onChange={(e) => set('from', e.target.value)} />
          </label>
          <label className="field">
            <span className="field-label">Hasta</span>
            <input type="date" value={filters.to ?? ''} onChange={(e) => set('to', e.target.value)} />
          </label>
        </>
      )}
      {DIMENSIONS[reportKey].map((dim) => {
        const src = options?.[DIM_SOURCE[dim]] ?? [];
        const zoneLocked = options?.zones.length === 1;
        const zone = filters.zone_id ?? (zoneLocked ? options!.zones[0].id : undefined);
        const list = dim === 'point_id' && zone ? (src as ReportOptions['points']).filter((p) => p.zone_id === zone) : dim === 'operator_id' && zone ? (src as ReportOptions['operators']).filter((p) => p.zone_id === zone) : src;
        const locked = dim === 'zone_id' && zoneLocked;
        return (
          <label key={dim} className="field">
            <span className="field-label">{DIM_LABEL[dim]}</span>
            <select value={filters[dim as keyof Filters] ?? (locked ? options!.zones[0].id : '')} onChange={(e) => set(dim as keyof Filters, e.target.value)} disabled={locked} data-testid={`filter-${dim}`}>
              {!locked && <option value="">{dim === 'zone_id' ? 'Toda la red' : 'Todos'}</option>}
              {list.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.name}
                </option>
              ))}
            </select>
          </label>
        );
      })}
      {Object.keys(filters).some((k) => k !== 'period') && (
        <button type="button" className="btn btn-ghost" onClick={() => onChange({ period: filters.period })}>
          Limpiar filtros
        </button>
      )}
    </div>
  );
}

export function CoverageNote({ r }: { r: ReportPayload }) {
  const c = r.coverage;
  if (!c || (c.open_shifts === 0 && c.sync_stale_open === 0)) return null;
  const parts: string[] = [];
  if (c.open_shifts) parts.push(`${c.open_shifts} turno(s) abiertos${c.close_overdue ? ` (${c.close_overdue} con cierre vencido)` : ''}: sus ventas y caja cambiarán al cerrar`);
  if (c.sync_stale_open) parts.push(`${c.sync_stale_open} dispositivo(s) sin sincronizar: puede haber registros pendientes de enviar`);
  return (
    <div className="coverage-note" role="status" data-testid="coverage-note">
      <b>Información pendiente ·</b> {parts.join(' · ')}.
    </div>
  );
}

export function ReportHeaderMeta({ r }: { r: ReportPayload }) {
  return (
    <div className="report-meta">
      <Badge tone="blue">{r.period.preset_label}: {r.period.label}</Badge>
      <Badge tone="gray">vs {r.compare.label}</Badge>
      {r.scope.zone_locked && <Badge tone="amber">Alcance: tu zona</Badge>}
      {r.scope.operator_locked && <Badge tone="amber">Alcance: tu desempeño</Badge>}
      <Badge tone={r.coverage?.status === 'pending' ? 'amber' : 'green'}>{r.coverage?.status === 'pending' ? 'Cifras preliminares' : r.partial ? 'Sin turnos abiertos' : 'Periodo cerrado'}</Badge>
      <span className="muted small">Corte de datos {fmtDateTime(r.data_as_of)} · generado {fmtDateTime(r.generated_at)} · v{r.version}</span>
    </div>
  );
}

export function ReportBody({ r, print = false }: { r: ReportPayload; print?: boolean }) {
  const charts = r.charts;
  return (
    <>
      <CoverageNote r={r} />
      <KpiGrid kpis={r.kpis} compareLabel={r.compare.label} />
      <Insights items={r.insights} />
      {charts.length > 0 && (
        <div className={`report-charts ${print ? 'print' : ''}`}>
          {charts.map((c) => (
            <ChartBlock key={c.key} chart={c} />
          ))}
        </div>
      )}
      {r.tables.map((t) => (
        <TableBlock key={t.key} table={t} pageSize={print ? Math.max(t.rows.length, 1) : 25} />
      ))}
      {r.hidden.length > 0 && !print && (
        <p className="muted small">Secciones no disponibles para tu rol: {r.hidden.join(', ')}.</p>
      )}
    </>
  );
}

export function ReportViewPage() {
  const { key } = useParams<{ key: string }>();
  const [params, setParams] = useSearchParams();
  const filters = useMemo(() => filtersFrom(params), [params]);
  const valid = KEYS.includes(key as ReportKey);
  const { data, loading, error } = useReport(valid ? key : undefined, filters);
  const { data: options } = useFetch<ReportOptions>(() => api.get('/v1/reports/bi/options'), [], { silent: true });
  if (!valid) return <Navigate to="/reportes" replace />;
  const rk = key as ReportKey;
  const onChange = (f: Filters) => setParams(new URLSearchParams(filtersToQuery(f).replace(/^\?/, '')), { replace: true });
  const printHref = `/reportes/${rk}/imprimir${filtersToQuery(filters)}`;
  return (
    <>
      <PageTitle
        title={data?.title ?? 'Reporte'}
        subtitle={
          <>
            <Link to="/reportes">← Centro de Reportes</Link>
            {data && <> · {data.description}</>}
          </>
        }
        actions={
          <a className="btn btn-primary" href={printHref} target="_blank" rel="noopener" data-testid="export-pdf">
            Exportar PDF
          </a>
        }
      />
      <ReportFilters reportKey={rk} filters={filters} onChange={onChange} options={options} />
      {data && <ReportHeaderMeta r={data} />}
      {loading && !data && <Loading />}
      {error && !data && (
        <Card>
          <p className="state-msg" data-testid="report-error">
            <b>{/permiso/i.test(error) ? 'Sin permiso' : /conexi|red|network|fetch/i.test(error) ? 'Error de conexión' : 'No se pudo generar el reporte'}</b> · {error}
          </p>
        </Card>
      )}
      {data && <ReportBody r={data} />}
    </>
  );
}
