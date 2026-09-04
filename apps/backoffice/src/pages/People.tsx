import { useState } from 'react';
import { api, qs } from '../api/client';
import { useFetch } from '../lib/useFetch';
import { Badge, Card, Empty, Loading, PageTitle, StatusBadge } from '../components/ui';
import type { AttendanceRow } from '../types';
import { fmtTime, todayLocalISO } from '../lib/format';

const ATT_LABEL: Record<string, string> = { present: 'Presente', late: 'Tarde', absent: 'Ausente', pending: 'Pendiente', closed: 'Terminó', on_time: 'A tiempo' };

export function PeoplePage() {
  const [date, setDate] = useState(todayLocalISO());
  const { data, loading } = useFetch<{ date: string; rows: AttendanceRow[] }>(() => api.get(`/v1/people/attendance${qs({ date })}`), [date], { every: 60_000 });
  const rows = data?.rows ?? [];
  const count = (s: string) => rows.filter((r) => r.status === s).length;
  const late = rows.filter((r) => (r.late_minutes ?? 0) > 0).length;
  return (
    <div>
      <PageTitle title="Personas · asistencia" subtitle="Check-in/out por asignación, puntualidad y ausencias." actions={<input type="date" value={date} onChange={(e) => setDate(e.target.value)} />} />
      {loading && !data && <Loading />}
      {data && (
        <>
          <div className="kpis">
            <div className="kpi">
              <div className="kpi-label">Asignaciones</div>
              <div className="kpi-value">{rows.length}</div>
            </div>
            <div className="kpi tone-green">
              <div className="kpi-label">Con check-in</div>
              <div className="kpi-value">{rows.filter((r) => r.check_in_at).length}</div>
            </div>
            <div className={`kpi tone-${late ? 'amber' : 'green'}`}>
              <div className="kpi-label">Llegadas tarde</div>
              <div className="kpi-value">{late}</div>
            </div>
            <div className={`kpi tone-${count('absent') ? 'red' : 'green'}`}>
              <div className="kpi-label">Ausencias</div>
              <div className="kpi-value">{count('absent')}</div>
            </div>
            <div className="kpi">
              <div className="kpi-label">Pendientes de abrir</div>
              <div className="kpi-value">{count('pending')}</div>
            </div>
          </div>
          <Card title="Asistencia del día">
            {rows.length === 0 && <Empty text="Sin asignaciones en la fecha" />}
            {rows.length > 0 && (
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Operador</th>
                      <th>Punto</th>
                      <th>Planeado</th>
                      <th>Check-in</th>
                      <th>Check-out</th>
                      <th className="num">Retraso</th>
                      <th>Estado</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.assignment_id}>
                        <td>
                          <b>{r.operator.name}</b>
                        </td>
                        <td>{r.point.name}</td>
                        <td className="nowrap">
                          {fmtTime(r.planned_start)} – {fmtTime(r.planned_end)}
                        </td>
                        <td>{fmtTime(r.check_in_at)}</td>
                        <td>{fmtTime(r.check_out_at)}</td>
                        <td className="num">{r.late_minutes ? <Badge tone={r.late_minutes > 20 ? 'red' : 'amber'}>{r.late_minutes} min</Badge> : r.check_in_at ? <Badge tone="green">A tiempo</Badge> : '—'}</td>
                        <td>{ATT_LABEL[r.status] ? <Badge tone={r.status === 'absent' ? 'red' : r.status === 'pending' ? 'amber' : r.status === 'late' ? 'amber' : 'green'}>{ATT_LABEL[r.status]}</Badge> : <StatusBadge status={r.status} />}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
