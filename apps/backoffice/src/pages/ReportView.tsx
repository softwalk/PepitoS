/** Página de un reporte: filtros en la URL (periodo + dimensiones), KPIs, hallazgos, gráficas y tablas.
 *  El alcance real lo fija la API (`scope`): el supervisor ve su zona aunque cambie la URL. */
import { useMemo, useState } from 'react';
import { Link, Navigate, useParams, useSearchParams } from 'react-router-dom';
import { api, qs } from '../api/client';
import { Badge, Card, Loading, Modal, PageTitle } from '../components/ui';
import { useToast } from '../components/Toast';
import { StateBox, stateFromError } from '../components/State';
import { ChartBlock, Insights, KpiGrid, TableBlock } from '../components/ReportBlocks';
import { useFetch } from '../lib/useFetch';
import { useAuth } from '../state/auth';
import { fmtDateTime } from '../lib/format';
import { PRESETS, downloadText, filtersFrom, filtersToQuery, type Filters } from '../lib/reports';
import type { ReportInsight, ReportKey, ReportOptions, ReportPayload } from '../types';

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

export function ReportBody({ r, print = false, onExport, onCreateCase }: { r: ReportPayload; print?: boolean; onExport?: (tableKey: string) => void; onCreateCase?: (i: ReportInsight) => void }) {
  const charts = r.charts;
  return (
    <>
      <CoverageNote r={r} />
      <KpiGrid kpis={r.kpis} compareLabel={r.compare.label} />
      <Insights items={r.insights} onCreateCase={print ? undefined : onCreateCase} />
      {charts.length > 0 && (
        <div className={`report-charts ${print ? 'print' : ''}`}>
          {charts.map((c) => (
            <ChartBlock key={c.key} chart={c} />
          ))}
        </div>
      )}
      {r.tables.map((t) => (
        <TableBlock key={t.key} table={t} pageSize={print ? Math.max(t.rows.length, 1) : 25} onExport={onExport} print={print} />
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
  const toast = useToast();
  const [sendOpen, setSendOpen] = useState(false);
  const [emails, setEmails] = useState('');
  const [caseFrom, setCaseFrom] = useState<ReportInsight | null>(null);
  const exportCsv = async (tableKey?: string) => {
    try {
      const q = qs({ ...filters, table: tableKey });
      const text = await api.text(`/v1/reports/bi/${rk}/export.csv${q}`);
      downloadText(`pepito-${rk}${tableKey ? '-' + tableKey : ''}.csv`, text);
    } catch (e) {
      toast.error(e, 'No se pudo exportar');
    }
  };
  const sendMail = async () => {
    try {
      const r = await api.post<{ status: string; channel: string; path?: string; error?: string }>(`/v1/reports/bi/${rk}/send`, { to: emails.split(/[,;\s]+/).filter(Boolean), period: filters.period ?? 'today', from: filters.from, to_date: filters.to, zone_id: filters.zone_id, point_id: filters.point_id, operator_id: filters.operator_id });
      toast.toast(r.status === 'sent' ? 'Reporte enviado por correo' : r.path ? `Sin SMTP configurado: se guardó en el servidor (${r.path})` : `No se envió: ${r.error ?? r.status}`, r.status === 'sent' ? 'success' : 'info');
      setSendOpen(false);
    } catch (e) {
      toast.error(e, 'No se pudo enviar');
    }
  };
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
          <>
            <button type="button" className="btn" onClick={() => exportCsv()} data-testid="export-csv">
              ⬇ CSV
            </button>
            <button type="button" className="btn" onClick={() => setSendOpen(true)} data-testid="send-mail">
              ✉ Enviar
            </button>
            <a className="btn btn-primary" href={printHref} target="_blank" rel="noopener" data-testid="export-pdf">
              Exportar PDF
            </a>
          </>
        }
      />
      <ReportFilters reportKey={rk} filters={filters} onChange={onChange} options={options} />
      {data && <ReportHeaderMeta r={data} />}
      {loading && !data && <Loading />}
      {error && !data && (
        <Card>
          <div data-testid="report-error">
            <StateBox kind={stateFromError(new Error(error))} error={error} />
          </div>
        </Card>
      )}
      {data && <ReportBody r={data} onExport={(k) => void exportCsv(k)} onCreateCase={(i) => setCaseFrom(i)} />}
      {sendOpen && (
        <Modal title="Enviar reporte por correo" onClose={() => setSendOpen(false)}>
          <p className="muted small">Se envía con los filtros actuales y tu misma autorización (PDF si el servidor tiene WeasyPrint; si no, HTML). Queda en el audit log.</p>
          <label className="field">
            <span className="field-label">Destinatarios (separados por coma)</span>
            <input value={emails} onChange={(e) => setEmails(e.target.value)} placeholder="direccion@pepito.mx, finanzas@pepito.mx" data-testid="send-to" />
          </label>
          <div className="modal-actions" style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 12 }}>
            <button className="btn" onClick={() => setSendOpen(false)}>Cancelar</button>
            <button className="btn btn-primary" onClick={sendMail} data-testid="send-confirm">Enviar</button>
          </div>
        </Modal>
      )}
      {caseFrom && data && <CreateCaseModal insight={caseFrom} report={data} onClose={() => setCaseFrom(null)} />}
    </>
  );
}


/** Alerta → trabajo: crea un caso con responsable, acción sugerida y fecha a partir de un hallazgo del reporte. */
function CreateCaseModal({ insight, report, onClose }: { insight: ReportInsight; report: ReportPayload; onClose: () => void }) {
  const toast = useToast();
  const { data: options } = useFetch<ReportOptions>(() => api.get('/v1/reports/bi/options'), [], { silent: true });
  const { data: users } = useFetch<{ id: string; name: string; role: string; is_active: boolean }[]>(() => api.get('/v1/admin/users'), [], { silent: true });
  const linkPoint = insight.link?.match(/point_id=([0-9a-f-]{36})/)?.[1];
  const [title, setTitle] = useState(insight.text.slice(0, 120));
  const [pointId, setPointId] = useState(linkPoint ?? report.filters.point_id ?? '');
  const [severity, setSeverity] = useState<'urgent' | 'review' | 'normal'>(insight.kind === 'alert' ? 'review' : 'normal');
  const [assignee, setAssignee] = useState('');
  const [action, setAction] = useState(insight.kind === 'recommendation' ? insight.text.slice(0, 200) : '');
  const [due, setDue] = useState('');
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    try {
      const c = await api.post<{ id: string }>('/v1/cases', {
        title, description: `${insight.text}\n\nOrigen: reporte «${report.title}» (${report.period.label}).`, point_id: pointId || null, severity, category: 'other',
        assignee_id: assignee || null, action: action || null, action_due_date: due || null, source_ref: `report:${report.key}${filtersToQuery(report.filters as Filters)}`,
      });
      toast.toast('Caso creado', 'success');
      onClose();
      window.location.assign(`/casos/${c.id}`);
    } catch (e) {
      toast.error(e, 'No se pudo crear el caso');
    } finally {
      setBusy(false);
    }
  };
  const { user: me } = useAuth();
  const supervisors = (users ?? []).filter((u) => u.is_active && (u.role === 'supervisor' || u.role === 'ops'));
  if (me && !supervisors.some((u) => u.id === me.id)) supervisors.unshift({ id: me.id, name: `${me.name} (yo)`, role: me.role, is_active: true });
  return (
    <Modal title="Crear caso desde el hallazgo" onClose={onClose}>
      <div style={{ display: 'grid', gap: 10 }} data-testid="create-case-modal">
        <label className="field"><span className="field-label">Título</span><input value={title} onChange={(e) => setTitle(e.target.value)} /></label>
        <label className="field"><span className="field-label">Punto</span>
          <select value={pointId} onChange={(e) => setPointId(e.target.value)}>
            <option value="">Sin punto</option>
            {(options?.points ?? []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </label>
        <div style={{ display: 'flex', gap: 10 }}>
          <label className="field" style={{ flex: 1 }}><span className="field-label">Severidad</span>
            <select value={severity} onChange={(e) => setSeverity(e.target.value as typeof severity)}><option value="urgent">Urgente</option><option value="review">Revisar</option><option value="normal">Normal</option></select>
          </label>
          <label className="field" style={{ flex: 1 }}><span className="field-label">Responsable</span>
            <select value={assignee} onChange={(e) => setAssignee(e.target.value)}><option value="">Sin asignar</option>{supervisors.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}</select>
          </label>
        </div>
        <label className="field"><span className="field-label">Acción sugerida</span><input value={action} onChange={(e) => setAction(e.target.value)} placeholder="Qué debe hacerse" /></label>
        <label className="field"><span className="field-label">Fecha objetivo</span><input type="date" value={due} onChange={(e) => setDue(e.target.value)} /></label>
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <button className="btn" onClick={onClose}>Cancelar</button>
          <button className="btn btn-primary" disabled={busy || title.length < 4} onClick={submit} data-testid="create-case-confirm">Crear caso</button>
        </div>
      </div>
    </Modal>
  );
}