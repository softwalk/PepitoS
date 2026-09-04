import { useState } from 'react';
import { api, qs } from '../api/client';
import { useFetch } from '../lib/useFetch';
import { Card, Empty, Field, Loading, PageTitle } from '../components/ui';
import type { AuditLogRow } from '../types';
import { fmtDateTime } from '../lib/format';

const ENTITIES = ['', 'case', 'action', 'audit', 'rule', 'approval', 'lot', 'device', 'users', 'points', 'carts', 'assignments', 'presentations', 'price_version', 'zones', 'maintenance_ticket', 'token'];

function Diff({ before, after }: { before: unknown; after: unknown }) {
  const b = (before ?? {}) as Record<string, unknown>;
  const a = (after ?? {}) as Record<string, unknown>;
  const keys = Array.from(new Set([...Object.keys(b), ...Object.keys(a)])).filter((k) => JSON.stringify(b[k]) !== JSON.stringify(a[k]));
  if (!keys.length) return <span className="muted">—</span>;
  return (
    <div className="small" style={{ maxWidth: 420 }}>
      {keys.slice(0, 6).map((k) => (
        <div key={k}>
          <span className="mono">{k}</span>: <span className="muted">{before && k in b ? JSON.stringify(b[k]) : '∅'}</span> → <b>{JSON.stringify(a[k])}</b>
        </div>
      ))}
      {keys.length > 6 && <span className="muted">+{keys.length - 6} campos</span>}
    </div>
  );
}

export function AuditLogPage() {
  const [entity, setEntity] = useState('');
  const [entityId, setEntityId] = useState('');
  const [action, setAction] = useState('');
  const [limit, setLimit] = useState(200);
  const { data, loading } = useFetch<AuditLogRow[]>(() => api.get(`/v1/audit-log${qs({ entity, entity_id: entityId.length === 36 ? entityId : undefined, limit })}`), [entity, entityId, limit]);
  const rows = (data ?? []).filter((r) => !action || r.action.includes(action));
  return (
    <div>
      <PageTitle title="Audit log" subtitle="Cambios críticos: actor, antes/después, motivo, IP y dispositivo." />
      <div className="filters">
        <Field label="Entidad">
          <select value={entity} onChange={(e) => setEntity(e.target.value)}>
            {ENTITIES.map((e) => (
              <option key={e} value={e}>
                {e || 'Todas'}
              </option>
            ))}
          </select>
        </Field>
        <Field label="ID de entidad">
          <input value={entityId} onChange={(e) => setEntityId(e.target.value.trim())} placeholder="UUID" style={{ width: 300 }} />
        </Field>
        <Field label="Acción contiene">
          <input value={action} onChange={(e) => setAction(e.target.value)} placeholder="p. ej. rule.update" />
        </Field>
        <Field label="Límite">
          <select value={limit} onChange={(e) => setLimit(Number(e.target.value))}>
            {[50, 100, 200, 500, 1000].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <Card title={`Registros (${rows.length})`}>
        {loading && !data && <Loading />}
        {data && rows.length === 0 && <Empty />}
        {rows.length > 0 && (
          <div className="table-wrap">
            <table className="table compact">
              <thead>
                <tr>
                  <th>Cuándo</th>
                  <th>Actor</th>
                  <th>Acción</th>
                  <th>Entidad</th>
                  <th>Cambios</th>
                  <th>Motivo</th>
                  <th>IP / dispositivo</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id}>
                    <td className="nowrap">{fmtDateTime(r.at)}</td>
                    <td>{r.actor_name ?? <span className="muted">sistema</span>}</td>
                    <td className="mono">{r.action}</td>
                    <td className="small">
                      {r.entity ?? '—'}
                      {r.entity_id && <div className="mono muted">{r.entity_id.slice(0, 8)}…</div>}
                    </td>
                    <td>
                      <Diff before={r.before} after={r.after} />
                    </td>
                    <td className="small">{r.reason ?? '—'}</td>
                    <td className="small muted">
                      {r.ip ?? '—'}
                      {r.device_id && <div className="mono">{r.device_id.slice(0, 12)}</div>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
