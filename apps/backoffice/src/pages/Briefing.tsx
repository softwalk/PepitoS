import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api, qs } from '../api/client';
import { useFetch } from '../lib/useFetch';
import { Card, Loading, PageTitle, SeverityBadge } from '../components/ui';
import type { Briefing } from '../types';
import { money, todayLocalISO } from '../lib/format';

export function BriefingPage() {
  const [date, setDate] = useState(todayLocalISO());
  const { data, loading } = useFetch<Briefing>(() => api.get(`/v1/control-tower/briefing${qs({ date })}`), [date]);
  const n = data?.numbers ?? {};
  const num = (k: string) => (typeof n[k] === 'number' ? (n[k] as number) : 0);
  const exc = (n.exceptions ?? {}) as Record<string, number>;
  return (
    <div>
      <PageTitle title="Briefing diario" subtitle="Resumen de decisiones para dirección: qué pasó, qué requiere decisión y por qué." actions={<input type="date" value={date} onChange={(e) => setDate(e.target.value)} />} />
      {loading && !data && <Loading />}
      {data && (
        <>
          <Card>
            <p className="headline">{data.headline}</p>
          </Card>
          <div className="grid-2">
            <Card title={`Decisiones (${data.decisions.length})`}>
              {data.decisions.length === 0 && <p className="empty">Sin decisiones pendientes. Red dentro de parámetros.</p>}
              {data.decisions.map((d, i) => (
                <div className="decision" key={i}>
                  <div className="row-between">
                    <b>{d.title}</b>
                    {d.severity && <SeverityBadge severity={d.severity} />}
                  </div>
                  <div className="muted small" style={{ marginTop: 4 }}>
                    {d.why}
                  </div>
                  <div className="rec">Recomendación: {d.recommendation}</div>
                  {d.case_id && (
                    <div style={{ marginTop: 6 }}>
                      <Link to={`/casos/${d.case_id}`}>Abrir caso →</Link>
                    </div>
                  )}
                </div>
              ))}
            </Card>
            <Card title="Números">
              <table className="table compact">
                <tbody>
                  <tr><td>Puntos programados</td><td className="num">{num('points')}</td></tr>
                  <tr><td>Abiertos / tarde / cerrados / sin señal</td><td className="num">{num('open')} / {num('late')} / {num('closed')} / {num('offline')}</td></tr>
                  <tr><td>Ventas</td><td className="num">{money(num('sales_cents'), { decimals: 0 })}</td></tr>
                  <tr><td>Meta</td><td className="num">{money(num('target_cents'), { decimals: 0 })} ({num('target_pct')}%)</td></tr>
                  <tr><td>Transacciones</td><td className="num">{num('tx')}</td></tr>
                  <tr><td>Ticket promedio</td><td className="num">{money(num('ticket_cents'))}</td></tr>
                  <tr><td>Forecast de cierre</td><td className="num">{money(num('forecast_close_cents'), { decimals: 0 })}</td></tr>
                  <tr><td>Excepciones urgente / revisar / normal</td><td className="num">{exc.urgent ?? 0} / {exc.review ?? 0} / {exc.normal ?? 0}</td></tr>
                  <tr><td>Cierres con diferencia de caja</td><td className="num">{num('cash_differences')}</td></tr>
                </tbody>
              </table>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
