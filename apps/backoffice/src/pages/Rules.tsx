import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { useFetch } from '../lib/useFetch';
import { useAuth } from '../state/auth';
import { useToast } from '../components/Toast';
import { Card, Loading, PageTitle, SeverityBadge } from '../components/ui';
import type { Rule, Severity } from '../types';
import { fmtDateTime } from '../lib/format';

const RULE_HELP: Record<string, string> = {
  no_open: 'Asignación de hoy sin apertura pasados N min de la hora planeada',
  out_of_geofence: 'Último GPS fuera del radio del punto por más de N min',
  low_sales_trajectory: 'Ventas < X% de la meta prorrateada tras M horas abiertas',
  high_waste: 'Merma del día / (ventas+merma) > X%',
  cash_difference: '|contado − esperado| > umbral en cierre (grave → urgente)',
  inventory_inconsistent: '|conteo − teórico| > N unidades',
  low_battery: 'Último battery_pct < N con turno abierto (crítico → urgente)',
  anomalous_cancellations: 'Cancelaciones del turno > N o > X% de ventas',
  sync_stale: 'Turno abierto sin evento/ping en N min',
  maintenance_overdue: 'Activo con preventivo vencido',
  stock_critical: 'Balance de una presentación < mínimo',
};

function parseValue(raw: string, previous: unknown): unknown {
  if (typeof previous === 'number') {
    const n = Number(raw);
    return Number.isNaN(n) ? previous : n;
  }
  if (typeof previous === 'boolean') return raw === 'true';
  try {
    return JSON.parse(raw);
  } catch {
    return raw;
  }
}

function RuleRow({ rule, onSaved, canEdit }: { rule: Rule; onSaved: (r: Rule) => void; canEdit: boolean }) {
  const toast = useToast();
  const [params, setParams] = useState<Record<string, string>>({});
  const [severity, setSeverity] = useState<Severity>(rule.severity);
  const [newKey, setNewKey] = useState('');
  const [newVal, setNewVal] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setParams(Object.fromEntries(Object.entries(rule.params ?? {}).map(([k, v]) => [k, typeof v === 'string' ? v : JSON.stringify(v)])));
    setSeverity(rule.severity);
  }, [rule]);

  const dirty = severity !== rule.severity || Object.entries(params).some(([k, v]) => JSON.stringify(parseValue(v, rule.params[k])) !== JSON.stringify(rule.params[k])) || newKey.trim() !== '';

  const save = async (patch?: Partial<{ enabled: boolean }>) => {
    setBusy(true);
    try {
      const body: Record<string, unknown> = { ...patch };
      if (!patch) {
        const p: Record<string, unknown> = {};
        for (const [k, v] of Object.entries(params)) p[k] = parseValue(v, rule.params[k]);
        if (newKey.trim()) p[newKey.trim()] = parseValue(newVal, undefined);
        body.params = p;
        body.severity = severity;
      }
      const r = await api.put<Rule>(`/v1/rules/${rule.key}`, body);
      onSaved(r);
      setNewKey('');
      setNewVal('');
      toast.toast(`Regla ${rule.key} guardada`, 'success');
    } catch (e) {
      toast.error(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <tr>
      <td>
        <label className="switch">
          <input type="checkbox" checked={rule.enabled} disabled={!canEdit || busy} onChange={(e) => save({ enabled: e.target.checked })} aria-label={`Activar ${rule.key}`} />
        </label>
      </td>
      <td>
        <b>{rule.name}</b>
        <div className="mono muted">{rule.key}</div>
        <div className="small muted">{RULE_HELP[rule.key]}</div>
      </td>
      <td>
        <div className="stack" style={{ gap: 4 }}>
          {Object.keys(params).length === 0 && <span className="muted small">Sin parámetros</span>}
          {Object.entries(params).map(([k, v]) => (
            <label key={k} className="row" style={{ gap: 6 }}>
              <span className="mono" style={{ minWidth: 120 }}>
                {k}
              </span>
              <input value={v} disabled={!canEdit} onChange={(e) => setParams({ ...params, [k]: e.target.value })} style={{ width: 110, minHeight: 28, padding: '3px 6px' }} />
            </label>
          ))}
          {canEdit && (
            <div className="row" style={{ gap: 6 }}>
              <input placeholder="nuevo_param" value={newKey} onChange={(e) => setNewKey(e.target.value)} style={{ width: 120, minHeight: 28, padding: '3px 6px' }} />
              <input placeholder="valor" value={newVal} onChange={(e) => setNewVal(e.target.value)} style={{ width: 110, minHeight: 28, padding: '3px 6px' }} />
            </div>
          )}
        </div>
      </td>
      <td>
        {canEdit ? (
          <select value={severity} onChange={(e) => setSeverity(e.target.value as Severity)}>
            <option value="urgent">URGENTE</option>
            <option value="review">REVISAR</option>
            <option value="normal">NORMAL</option>
          </select>
        ) : (
          <SeverityBadge severity={rule.severity} />
        )}
      </td>
      <td className="nowrap small muted">{fmtDateTime(rule.updated_at)}</td>
      <td>
        {canEdit && (
          <button type="button" className="btn small btn-primary" disabled={!dirty || busy} onClick={() => save()}>
            Guardar
          </button>
        )}
      </td>
    </tr>
  );
}

export function RulesPage() {
  const toast = useToast();
  const { hasRole } = useAuth();
  const canEdit = hasRole('ops', 'admin');
  const { data, loading, setData, reload } = useFetch<Rule[]>(() => api.get('/v1/rules'), []);
  const [running, setRunning] = useState(false);
  const run = async () => {
    setRunning(true);
    try {
      const r = await api.post<{ alerts_created: number; cases_created: number }>('/v1/rules/run');
      toast.toast(`Motor ejecutado: ${r.alerts_created} alertas, ${r.cases_created} casos`, 'success');
    } catch (e) {
      toast.error(e);
    } finally {
      setRunning(false);
    }
  };
  return (
    <div>
      <PageTitle
        title="Reglas determinísticas"
        subtitle="Cada regla evalúa y, si dispara y no hay caso abierto igual (regla:punto:día), crea alerta + caso. Cambios quedan en audit log."
        actions={
          <>
            <button type="button" className="btn" onClick={() => reload()}>
              Actualizar
            </button>
            {canEdit && (
              <button type="button" className="btn btn-accent" onClick={run} disabled={running}>
                {running ? 'Ejecutando…' : 'Ejecutar reglas ahora'}
              </button>
            )}
          </>
        }
      />
      <Card>
        {loading && !data && <Loading />}
        {data && (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Activa</th>
                  <th>Regla</th>
                  <th>Parámetros</th>
                  <th>Severidad</th>
                  <th>Actualizada</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {data.map((r) => (
                  <RuleRow key={r.key} rule={r} canEdit={canEdit} onSaved={(nr) => setData(data.map((x) => (x.key === nr.key ? nr : x)))} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
