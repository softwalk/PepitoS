import { useState } from 'react';
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { api, qs } from '../api/client';
import { useFetch } from '../lib/useFetch';
import { Card, Empty, LightDot, Loading, PageTitle, StatusBadge } from '../components/ui';
import type { DailyReport } from '../types';
import { fmtTime, money, salesLight, ticketLight, todayLocalISO, wasteLight } from '../lib/format';

export function SalesPage() {
  const [date, setDate] = useState(todayLocalISO());
  const { data, loading } = useFetch<DailyReport>(() => api.get(`/v1/reports/daily${qs({ date })}`), [date]);
  const rows = data?.rows ?? [];
  const byPoint = new Map<string, { name: string; Ventas: number; Tx: number }>();
  for (const r of rows) {
    const cur = byPoint.get(r.point.id) ?? { name: r.point.name, Ventas: 0, Tx: 0 };
    cur.Ventas += r.sales_cents / 100;
    cur.Tx += r.tx;
    byPoint.set(r.point.id, cur);
  }
  const chart = Array.from(byPoint.values());
  const totalWaste = data ? data.totals.waste_units : 0;
  const totalUnitsApprox = rows.reduce((s, r) => s + (r.waste_pct ? (r.waste_units * 100) / r.waste_pct - r.waste_units : 0), 0);
  const wastePctTotal = totalWaste + totalUnitsApprox > 0 ? (totalWaste * 100) / (totalWaste + totalUnitsApprox) : 0;
  const ticket = data && data.totals.tx ? data.totals.sales_cents / data.totals.tx : 0;

  return (
    <div>
      <PageTitle title="Ventas · reporte diario" subtitle="Ventas, caja esperada vs contada, merma y estado de cierre por turno." actions={<input type="date" value={date} onChange={(e) => setDate(e.target.value)} aria-label="Fecha" />} />
      {loading && !data && <Loading />}
      {data && (
        <>
          <div className="kpis">
            <div className="kpi">
              <div className="kpi-label">Ventas totales</div>
              <div className="kpi-value">{money(data.totals.sales_cents, { decimals: 0 })}</div>
            </div>
            <div className={`kpi tone-${salesLight(rows.length ? data.totals.tx / rows.length : 0)}`}>
              <div className="kpi-label">Transacciones</div>
              <div className="kpi-value">{data.totals.tx}</div>
              <div className="kpi-sub">{rows.length ? (data.totals.tx / rows.length).toFixed(1) : 0} por turno</div>
            </div>
            <div className={`kpi ${data.totals.tx ? `tone-${ticketLight(ticket)}` : ''}`}>
              <div className="kpi-label">Ticket promedio</div>
              <div className="kpi-value">{data.totals.tx ? money(ticket) : '—'}</div>
            </div>
            <div className={`kpi tone-${data.totals.difference_cents === 0 ? 'green' : 'red'}`}>
              <div className="kpi-label">Diferencia de caja</div>
              <div className="kpi-value">{money(data.totals.difference_cents)}</div>
            </div>
            <div className={`kpi tone-${wasteLight(wastePctTotal)}`}>
              <div className="kpi-label">Merma</div>
              <div className="kpi-value">{totalWaste} u</div>
              <div className="kpi-sub">{wastePctTotal.toFixed(1)}% de unidades</div>
            </div>
          </div>
          <Card title="Ventas por punto">
            {rows.length === 0 ? (
              <Empty text="Sin turnos en la fecha" />
            ) : (
              <div className="chart-box">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chart} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e6ebf0" />
                    <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                    <YAxis tick={{ fontSize: 12 }} tickFormatter={(v: number) => `$${v}`} />
                    <Tooltip formatter={(v: number, name: string) => (name === 'Ventas' ? money(v * 100) : v)} />
                    <Legend />
                    <Bar dataKey="Ventas" fill="#1f4e79" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="Tx" fill="#e8590c" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </Card>
          <Card title={`Turnos (${rows.length})`}>
            {rows.length === 0 && <Empty text="Sin turnos" />}
            {rows.length > 0 && (
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Punto</th>
                      <th>Operador</th>
                      <th>Apertura</th>
                      <th>Cierre</th>
                      <th className="num">Ventas</th>
                      <th className="num">Tx</th>
                      <th className="num">Ticket</th>
                      <th className="num">Digital</th>
                      <th className="num">Efectivo esperado</th>
                      <th className="num">Contado</th>
                      <th className="num">Diferencia</th>
                      <th className="num">Cancel.</th>
                      <th className="num">Merma</th>
                      <th>Estado</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => {
                      const ticketRow = r.tx ? r.sales_cents / r.tx : 0;
                      return (
                        <tr key={r.shift_id}>
                          <td>
                            <b>{r.point.name}</b>
                          </td>
                          <td>{r.operator.name}</td>
                          <td>{fmtTime(r.opened_at)}</td>
                          <td>{fmtTime(r.closed_at)}</td>
                          <td className="num">{money(r.sales_cents)}</td>
                          <td className="num">
                            {r.tx} <LightDot light={salesLight(r.tx)} text="" />
                          </td>
                          <td className="num">
                            {r.tx ? money(ticketRow) : '—'} {r.tx ? <LightDot light={ticketLight(ticketRow)} text="" /> : null}
                          </td>
                          <td className="num">{money(r.digital_cents)}</td>
                          <td className="num">{money(r.cash_expected_cents)}</td>
                          <td className="num">{money(r.cash_counted_cents)}</td>
                          <td className="num" style={{ color: r.difference_cents ? 'var(--red)' : undefined }}>
                            {r.difference_cents === null ? '—' : money(r.difference_cents)}
                          </td>
                          <td className="num">{r.cancelled_count}</td>
                          <td className="num">
                            {r.waste_units} u · {r.waste_pct}% <LightDot light={wasteLight(r.waste_pct)} text="" />
                          </td>
                          <td>
                            <StatusBadge status={r.status} />
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                  <tfoot>
                    <tr>
                      <td colSpan={4}>Totales</td>
                      <td className="num">{money(data.totals.sales_cents)}</td>
                      <td className="num">{data.totals.tx}</td>
                      <td className="num">{data.totals.tx ? money(ticket) : '—'}</td>
                      <td className="num">{money(rows.reduce((s, r) => s + r.digital_cents, 0))}</td>
                      <td className="num">{money(rows.reduce((s, r) => s + (r.cash_expected_cents ?? 0), 0))}</td>
                      <td className="num">{money(rows.reduce((s, r) => s + (r.cash_counted_cents ?? 0), 0))}</td>
                      <td className="num">{money(data.totals.difference_cents)}</td>
                      <td className="num">{rows.reduce((s, r) => s + r.cancelled_count, 0)}</td>
                      <td className="num">{data.totals.waste_units} u</td>
                      <td></td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
