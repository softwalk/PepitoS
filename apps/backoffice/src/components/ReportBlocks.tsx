/** Bloques genéricos del módulo de Reportes: KPIs con semáforo, gráficas (recharts), tablas ejecutivas y hallazgos.
 *  Renderizan el payload declarativo de `GET /v1/reports/bi/<clave>`; no conocen cada reporte en particular. */
import { Fragment } from 'react';
import { Link } from 'react-router-dom';
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis,
} from 'recharts';
import { Badge, Card, Empty, LightDot, StatusBadge } from './ui';
import { DataTable, type DTColumn } from './DataTable';
import { CHART_COLORS, INSIGHT_LABEL, INSIGHT_TONE, TONE_COLORS, columnLight, fillLink, fmtValue, toneToLight } from '../lib/reports';
import type { ReportChart, ReportColumn, ReportInsight, ReportKpi, ReportTable, ValueFormat } from '../types';

const TREND_ARROW: Record<string, string> = { up: '↑', down: '↓', flat: '→' };

export function KpiGrid({ kpis, compareLabel }: { kpis: ReportKpi[]; compareLabel?: string }) {
  if (!kpis.length) return null;
  return (
    <div className="kpis report-kpis" data-testid="report-kpis">
      {kpis.map((k) => {
        const light = toneToLight(k.tone);
        const deltaTone = k.delta_pct == null ? '' : k.trend === 'flat' ? 'gray' : (k.delta_pct > 0) === (k.trend === 'up') ? 'green' : 'red';
        return (
          <div key={k.key} className={`kpi ${light ? `tone-${light}` : ''}`}>
            <div className="kpi-label">
              <span>{k.label}</span>
              {light && <LightDot light={light} text="" />}
            </div>
            <div className="kpi-value">
              {fmtValue(k.value, k.format)}
              {k.unit && <span className="kpi-unit"> {k.unit}</span>}
            </div>
            <div className="kpi-sub">
              {k.delta_pct != null && (
                <span className={`kpi-delta ${deltaTone}`} title={compareLabel ? `vs ${compareLabel}` : undefined}>
                  {TREND_ARROW[k.trend]} {fmtValue(k.delta_pct, 'delta')}
                  {k.prev != null && <span className="muted"> · antes {fmtValue(k.prev, k.format)}</span>}
                </span>
              )}
              {k.delta_pct == null && k.compare === 'no_comparable' && (
                <span className="muted" title={`Sin base en ${compareLabel ?? 'el periodo anterior'}`}>
                  Sin base comparable
                </span>
              )}
              {k.hint && <span className="kpi-hint"> {k.hint}</span>}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function fmtTick(format: ValueFormat | undefined) {
  return (v: number) => (format === 'money' ? `$${Math.round(v / 100).toLocaleString('es-MX')}` : format === 'pct' ? `${v}%` : String(v));
}

function seriesColor(s: { color?: string }, i: number): string {
  return (s.color && TONE_COLORS[s.color]) || s.color || CHART_COLORS[i % CHART_COLORS.length];
}

export function ChartBlock({ chart }: { chart: ReportChart }) {
  const series = chart.series ?? [];
  const fmt = (v: unknown, name: string) => {
    const s = series.find((x) => x.label === name || x.key === name);
    return [fmtValue(v, s?.format ?? chart.format ?? 'int'), name] as [string, string];
  };
  if (!chart.data.length) {
    return (
      <Card title={chart.title} className="report-chart">
        <Empty text="Sin datos en el periodo" />
      </Card>
    );
  }
  let body: JSX.Element;
  const h = 260;
  switch (chart.type) {
    case 'line':
      body = (
        <ResponsiveContainer width="100%" height={h}>
          <LineChart data={chart.data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e9f0" />
            <XAxis dataKey={chart.x} tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} tickFormatter={fmtTick(series[0]?.format)} width={60} />
            <Tooltip formatter={fmt} />
            <Legend />
            {series.map((s, i) => (
              <Line key={s.key} type="monotone" dataKey={s.key} name={s.label} stroke={seriesColor(s, i)} strokeWidth={2} dot={chart.data.length <= 31} strokeDasharray={s.dashed ? '5 4' : undefined} isAnimationActive={false} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      );
      break;
    case 'bar':
    case 'stacked': {
      const vertical = chart.layout === 'vertical';
      body = (
        <ResponsiveContainer width="100%" height={vertical ? Math.max(h, 28 * chart.data.length + 40) : h}>
          <BarChart data={chart.data} layout={vertical ? 'vertical' : 'horizontal'} margin={{ top: 8, right: 16, left: vertical ? 8 : 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e9f0" />
            {vertical ? (
              <>
                <XAxis type="number" tick={{ fontSize: 11 }} tickFormatter={fmtTick(series[0]?.format)} domain={chart.domain} />
                <YAxis type="category" dataKey={chart.x} tick={{ fontSize: 11 }} width={150} />
              </>
            ) : (
              <>
                <XAxis dataKey={chart.x} tick={{ fontSize: 11 }} />
                <YAxis yAxisId="left" tick={{ fontSize: 11 }} tickFormatter={fmtTick(series[0]?.format)} width={60} domain={chart.domain} />
                {series.some((s) => s.axis === 'right') && <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11 }} width={40} />}
              </>
            )}
            <Tooltip formatter={fmt} />
            {series.length > 1 && <Legend />}
            {series.map((s, i) => (
              <Bar key={s.key} dataKey={s.key} name={s.label} fill={seriesColor(s, i)} stackId={chart.type === 'stacked' ? 'a' : undefined} yAxisId={vertical ? undefined : s.axis === 'right' ? 'right' : 'left'} radius={chart.type === 'stacked' ? 0 : 3} isAnimationActive={false} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      );
      break;
    }
    case 'donut': {
      const key = series[0]?.key ?? 'value';
      const total = chart.data.reduce((s, r) => s + Number(r[key] ?? 0), 0);
      body = (
        <div className="donut-wrap">
          <ResponsiveContainer width="100%" height={h}>
            <PieChart>
              <Pie data={chart.data} dataKey={key} nameKey={chart.x ?? 'label'} innerRadius={60} outerRadius={95} paddingAngle={2} isAnimationActive={false}>
                {chart.data.map((_, i) => (
                  <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip formatter={(v: unknown) => fmtValue(v, series[0]?.format ?? 'int')} />
            </PieChart>
          </ResponsiveContainer>
          <ul className="donut-legend">
            {chart.data.map((r, i) => (
              <li key={i}>
                <span className="swatch" style={{ background: CHART_COLORS[i % CHART_COLORS.length] }} />
                <span className="lbl">{String(r[chart.x ?? 'label'])}</span>
                <b>{fmtValue(r[key], series[0]?.format ?? 'int')}</b>
                <span className="muted">{total ? `${Math.round((Number(r[key]) * 100) / total)} %` : ''}</span>
              </li>
            ))}
          </ul>
        </div>
      );
      break;
    }
    case 'scatter':
      body = (
        <ResponsiveContainer width="100%" height={h}>
          <ScatterChart margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e9f0" />
            <XAxis type="number" dataKey={chart.x} name={chart.x_label} tick={{ fontSize: 11 }} label={{ value: chart.x_label, position: 'insideBottom', offset: -4, fontSize: 11 }} />
            <YAxis type="number" dataKey={chart.y} name={chart.y_label} tick={{ fontSize: 11 }} width={50} />
            <ZAxis range={[60, 60]} />
            <Tooltip cursor={{ strokeDasharray: '3 3' }} content={({ payload }) => (payload && payload.length ? <div className="chart-tip">{String(payload[0].payload.point)} · {chart.x_label}: {String(payload[0].payload[chart.x ?? ''])} · {chart.y_label}: {String(payload[0].payload[chart.y ?? ''])}</div> : null)} />
            <Scatter data={chart.data} fill="#1f4e79" isAnimationActive={false} />
          </ScatterChart>
        </ResponsiveContainer>
      );
      break;
    case 'heatmap': {
      const xs = chart.x_labels ?? [];
      const ys = chart.y_labels ?? [];
      const max = Math.max(1, ...chart.data.map((r) => Number(r.value ?? 0)));
      const grid = new Map<string, number>();
      chart.data.forEach((r) => grid.set(`${r.y}-${r.x}`, Number(r.value ?? 0)));
      body = (
        <div className="heatmap" style={{ gridTemplateColumns: `52px repeat(${xs.length}, minmax(14px, 1fr))` }} role="img" aria-label={chart.title}>
          <div />
          {xs.map((x, i) => (
            <div key={x} className="hm-x">{i % 3 === 0 ? x : ''}</div>
          ))}
          {ys.map((y, yi) => (
            <Fragment key={y}>
              <div className="hm-y">{y}</div>
              {xs.map((_, xi) => {
                const v = grid.get(`${yi}-${xi}`) ?? 0;
                return <div key={`${yi}-${xi}`} className="hm-cell" style={{ opacity: v ? 0.15 + (0.85 * v) / max : 0.04 }} title={`${y} ${xs[xi]}:00 · ${fmtValue(v, chart.format ?? 'int')}`} />;
              })}
            </Fragment>
          ))}
        </div>
      );
      break;
    }
    default:
      body = <Empty />;
  }
  return (
    <Card title={chart.title} className="report-chart">
      {body}
    </Card>
  );
}

function CellValue({ col, row }: { col: ReportColumn; row: Record<string, unknown> }) {
  const v = row[col.key];
  if (col.format === 'link') {
    if (!v) return <span className="muted">—</span>;
    return <Link to={fillLink(col.link ?? '', row)}>{col.label_text ?? 'Ver'}</Link>;
  }
  if (col.format === 'status') return <StatusBadge status={v as string} />;
  if (col.format === 'verdict') {
    const tone = v === 'GO' ? 'green' : v === 'AJUSTAR' ? 'amber' : v === 'NO GO' ? 'red' : 'gray';
    return <Badge tone={tone}>{String(v)}</Badge>;
  }
  if (col.format === 'delta' && v != null) {
    const n = Number(v);
    return <span className={`delta ${n > 0 ? 'up' : n < 0 ? 'down' : ''}`}>{fmtValue(v, 'delta')}</span>;
  }
  const text = fmtValue(v, col.format);
  const light = columnLight(col.tone, v);
  const content = col.link && v != null ? <Link to={fillLink(col.link, row)}>{text}</Link> : text;
  if (light) return <LightDot light={light} text={text} />;
  return <>{content}</>;
}

const NUMERIC: ValueFormat[] = ['money', 'int', 'pct', 'float', 'delta', 'kg'];

export function TableBlock({ table, pageSize = 25, onExport, print = false }: { table: ReportTable; pageSize?: number; onExport?: (tableKey: string) => void; print?: boolean }) {
  const rows = table.rows;
  const columns: DTColumn<Record<string, unknown>>[] = table.columns.map((c) => ({
    key: c.key,
    label: c.label || c.label_text || '',
    numeric: NUMERIC.includes(c.format),
    render: (row) => <CellValue col={c} row={row} />,
    sortValue: (row) => (c.format === 'link' ? null : (row[c.key] as number | string | null | undefined)),
  }));
  return (
    <Card title={table.title} className="report-table" testId={`table-${table.key}`} actions={onExport && rows.length > 0 && !print ? <button type="button" className="btn btn-ghost small" onClick={() => onExport(table.key)} data-testid={`csv-${table.key}`}>⬇ CSV</button> : undefined}>
      {rows.length === 0 ? (
        <Empty text="Sin registros en el periodo" />
      ) : print ? (
        <div className="table-wrap">
          <table className="table compact">
            <thead>
              <tr>
                {table.columns.map((c) => (
                  <th key={c.key} className={NUMERIC.includes(c.format) ? 'num' : ''}>{c.label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, pageSize).map((r, i) => (
                <tr key={i}>
                  {table.columns.map((c) => (
                    <td key={c.key} className={NUMERIC.includes(c.format) ? 'num' : ''}>
                      <CellValue col={c} row={r} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <DataTable
          columns={columns}
          rows={rows}
          rowKey={(r, i) => String(r.point_id ?? r.operator_id ?? r.shift_id ?? r.cart_id ?? r.id ?? i)}
          pageSize={pageSize}
          testId={`dt-${table.key}`}
          detail={(r) => (
            <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
              {table.columns.filter((c) => c.format !== 'link').map((c) => (
                <span key={c.key}><span className="muted">{c.label}:</span> <CellValue col={c} row={r} /></span>
              ))}
            </div>
          )}
        />
      )}
    </Card>
  );
}

export function Insights({ items, onCreateCase }: { items: ReportInsight[]; onCreateCase?: (i: ReportInsight) => void }) {
  return (
    <Card title="Hallazgos y alertas" className="report-insights" testId="report-insights">
      {items.length === 0 ? (
        <Empty text="Sin hallazgos: no hay suficientes datos en el periodo." />
      ) : (
        <ul className="insights">
          {items.map((i, n) => (
            <li key={n} className={`insight insight-${i.kind}`}>
              <Badge tone={INSIGHT_TONE[i.kind]}>{INSIGHT_LABEL[i.kind]}</Badge>
              <span>{i.text}</span>
              <span className="insight-link" style={{ display: 'flex', gap: 8 }}>
                {onCreateCase && (i.kind === 'alert' || i.kind === 'recommendation' || i.kind === 'hypothesis') && (
                  <button type="button" className="btn btn-ghost small" onClick={() => onCreateCase(i)} data-testid="insight-create-case">
                    + Crear caso
                  </button>
                )}
                {i.link && <Link to={i.link}>Ver →</Link>}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
