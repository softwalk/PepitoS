import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api, qs } from '../api/client';
import { useFetch } from '../lib/useFetch';
import { useAuth } from '../state/auth';
import { useToast } from '../components/Toast';
import { PointsMap } from '../components/PointsMap';
import { Badge, Card, Empty, LightDot, Loading, PageTitle, SeverityBadge, StatusBadge } from '../components/ui';
import type { PointStatus, Summary } from '../types';
import { fmtDateTime, fmtTime, money, ratioPct, salesLight, targetLight, ticketLight, todayLocalISO, type Light } from '../lib/format';
import { Icon } from '../components/icons';
import { ReopenShiftButton } from '../components/ReopenShift';

function Kpi({ label, value, sub, tone, wide, children }: { label: string; value?: string; sub?: string; tone?: Light; wide?: boolean; children?: React.ReactNode }) {
  return (
    <div className={`kpi ${tone ? `tone-${tone}` : ''} ${wide ? 'kpi-wide' : ''}`} data-testid={`kpi-${label}`}>
      <div className="kpi-label">
        <span>{label}</span>
        {tone && <LightDot light={tone} text="" />}
      </div>
      {value !== undefined && <div className="kpi-value">{value}</div>}
      {sub && <div className="kpi-sub">{sub}</div>}
      {children}
    </div>
  );
}

function PointRow({ p, onChanged }: { p: PointStatus; onChanged: () => Promise<void> }) {
  const progress = ratioPct(p.sales_cents, p.target_cents);
  const tLight = targetLight(progress);
  return (
    <tr>
      <td>
        <b>{p.point.name}</b>
      </td>
      <td>
        <StatusBadge status={p.status} />
      </td>
      <td>{p.operator?.name ?? <span className="muted">—</span>}</td>
      <td className="nowrap">{fmtTime(p.opened_at)}</td>
      <td className="nowrap">
        {p.last_gps ? (
          <>
            {fmtTime(p.last_gps.at)}{' '}
            <Badge tone={p.last_gps.in_geofence ? 'green' : 'red'}>{p.last_gps.in_geofence ? 'En geocerca' : 'Fuera'}</Badge>
          </>
        ) : (
          <span className="muted">—</span>
        )}
      </td>
      <td className="num">
        {p.battery_pct === null ? <span className="muted">—</span> : <Badge tone={p.battery_pct < 10 ? 'red' : p.battery_pct < 25 ? 'amber' : 'green'}>{p.battery_pct}%</Badge>}
      </td>
      <td className="num nowrap">
        {money(p.sales_cents, { decimals: 0 })} <span className="muted">/ {money(p.target_cents, { decimals: 0 })}</span>
        <div className={`bar tone-${tLight}`}>
          <div style={{ width: `${Math.min(100, progress)}%` }} />
        </div>
      </td>
      <td className="num">
        {p.tx} <LightDot light={salesLight(p.tx)} text="" />
      </td>
      <td className="num">
        {p.tx ? money(p.ticket_cents) : '—'} {p.tx ? <LightDot light={ticketLight(p.ticket_cents)} text="" /> : null}
      </td>
      <td>
        <StatusBadge status={p.cash_status} />
      </td>
      <td>
        <StatusBadge status={p.stock_risk} />
      </td>
      <td className="nowrap">
        {p.open_cases.urgent > 0 && <Badge tone="red">{p.open_cases.urgent} URG</Badge>} {p.open_cases.review > 0 && <Badge tone="amber">{p.open_cases.review} REV</Badge>}
        {p.open_cases.urgent + p.open_cases.review === 0 && <span className="muted">0</span>}
      </td>
      <td className="nowrap">
        <span className="row-actions">
          <Link to={`/excepciones?point_id=${p.point.id}`}>
            <Icon name="flag" size={13} /> Casos
          </Link>
          <Link to={`/supervisor/auditoria/${p.point.id}`}>
            <Icon name="search" size={13} /> Auditar
          </Link>
          {p.status === 'closed' && p.shift_id && <ReopenShiftButton shiftId={p.shift_id} label={p.point.name} onDone={onChanged} />}
        </span>
      </td>
    </tr>
  );
}

export function ControlTowerPage() {
  const { hasRole } = useAuth();
  const toast = useToast();
  const [date, setDate] = useState(todayLocalISO());
  const [running, setRunning] = useState(false);
  const { data, loading, reload, updatedAt } = useFetch<Summary>(() => api.get(`/v1/control-tower/summary${qs({ date })}`), [date], { every: 60_000 });

  const runRules = async () => {
    setRunning(true);
    try {
      const r = await api.post<{ alerts_created: number; cases_created: number }>('/v1/rules/run');
      toast.toast(`Reglas ejecutadas: ${r.alerts_created} alertas, ${r.cases_created} casos nuevos`, 'success');
      await reload(true);
    } catch (e) {
      toast.error(e);
    } finally {
      setRunning(false);
    }
  };

  const t = data?.totals;
  const progress = t ? ratioPct(t.sales_cents, t.target_cents) : 0;
  const scheduled = t?.points || 0;
  const txPerPoint = scheduled ? (t?.tx || 0) / scheduled : 0;

  return (
    <div>
      <PageTitle
        title="Control Tower"
        subtitle={
          <>
            <span className="live-dot" aria-hidden />
            Estado de la red · {updatedAt ? `actualizado ${updatedAt.toLocaleTimeString('es-MX', { hour: 'numeric', minute: '2-digit' })}` : '…'} · se refresca cada 60 s
          </>
        }
        actions={
          <>
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)} aria-label="Fecha" />
            <button type="button" className="btn" onClick={() => reload()} disabled={loading} title="Actualizar ahora">
              <Icon name="refresh" size={15} /> Actualizar
            </button>
            <Link to="/ct/briefing" className="btn">
              <Icon name="briefing" size={15} /> Briefing
            </Link>
            {hasRole('admin', 'ops') && (
              <button type="button" className="btn btn-accent" onClick={runRules} disabled={running}>
                <Icon name="play" size={15} /> {running ? 'Ejecutando…' : 'Ejecutar reglas ahora'}
              </button>
            )}
          </>
        }
      />

      {!data && loading && <Loading />}
      {data && t && (
        <>
          <div className="kpis">
            <Kpi label="Puntos" value={`${t.points}`} sub="programados hoy">
              <div className="kpi-split">
                <div>
                  <b style={{ color: 'var(--green)' }}>{t.open}</b>
                  <span>abiertos</span>
                </div>
                <div>
                  <b style={{ color: 'var(--amber)' }}>{t.late}</b>
                  <span>tarde</span>
                </div>
                <div>
                  <b style={{ color: 'var(--blue)' }}>{t.closed}</b>
                  <span>cerrados</span>
                </div>
                <div>
                  <b style={{ color: 'var(--gray)' }}>{t.offline}</b>
                  <span>s/señal</span>
                </div>
              </div>
            </Kpi>
            <Kpi label="Ventas hoy" value={money(t.sales_cents, { decimals: 0 })} sub={`Meta ${money(t.target_cents, { decimals: 0 })} · ${progress}%`} tone={targetLight(progress)}>
              <div className={`bar tone-${targetLight(progress)}`}>
                <div style={{ width: `${Math.min(100, progress)}%` }} />
              </div>
            </Kpi>
            <Kpi label="Transacciones" value={`${t.tx}`} sub={`${txPerPoint.toFixed(1)} por punto (meta 60)`} tone={salesLight(txPerPoint)} />
            <Kpi label="Ticket promedio" value={t.tx ? money(t.ticket_cents) : '—'} sub="Verde ≥ $39 · Ámbar $36–38.99" tone={t.tx ? ticketLight(t.ticket_cents) : undefined} />
            <Kpi label="Forecast cierre" value={money(t.forecast_close_cents, { decimals: 0 })} sub={`${ratioPct(t.forecast_close_cents, t.target_cents)}% de la meta`} tone={targetLight(ratioPct(t.forecast_close_cents, t.target_cents))} />
            <div className="kpi">
              <div className="kpi-label">Excepciones abiertas</div>
              <div className="exc-counter" style={{ marginTop: 6 }}>
                <Link to="/excepciones?severity=urgent" className="exc-urgent">
                  <b>{data.exceptions.urgent}</b>
                  <span>URGENTE</span>
                </Link>
                <Link to="/excepciones?severity=review" className="exc-review">
                  <b>{data.exceptions.review}</b>
                  <span>REVISAR</span>
                </Link>
                <Link to="/excepciones?severity=normal" className="exc-normal">
                  <b>{data.exceptions.normal}</b>
                  <span>NORMAL</span>
                </Link>
              </div>
            </div>
          </div>

          <div className="grid-2" style={{ gridTemplateColumns: '3fr 2fr' }}>
            <Card title="Mapa de puntos">
              <PointsMap points={data.points} />
            </Card>
            <Card title="Alertas recientes">
              {data.alerts_recent.length === 0 && <Empty text="Sin alertas" />}
              <ul className="alert-list">
                {data.alerts_recent.slice(0, 12).map((a) => (
                  <li key={a.id}>
                    <SeverityBadge severity={a.severity} />
                    <span style={{ flex: 1, minWidth: 0 }}>{a.case_id ? <Link to={`/casos/${a.case_id}`}>{a.message}</Link> : a.message}</span>
                    {a.status === 'resolved' && <Badge tone="green">Resuelta</Badge>}
                    <span className="muted small nowrap">{fmtDateTime(a.raised_at)}</span>
                  </li>
                ))}
              </ul>
            </Card>
          </div>

          <Card title={`Puntos (${data.points.length})`}>
            <div className="table-wrap">
              <table className="table" data-testid="points-table">
                <thead>
                  <tr>
                    <th>Punto</th>
                    <th>Estado</th>
                    <th>Operador</th>
                    <th>Apertura</th>
                    <th>Último GPS</th>
                    <th className="num">Batería</th>
                    <th className="num">Ventas / meta</th>
                    <th className="num">Tx</th>
                    <th className="num">Ticket</th>
                    <th>Caja</th>
                    <th>Stock</th>
                    <th>Casos</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {data.points.map((p) => (
                    <PointRow key={p.point.id} p={p} onChanged={() => reload(true)} />
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
