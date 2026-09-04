// /admin → Parámetros (B6): tabla editable por fila de `GET /v1/admin/settings`; `PUT /v1/admin/settings/{key}` (sólo admin).
import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { useFetch } from '../lib/useFetch';
import { useToast } from '../components/Toast';
import { Badge, Card, Loading } from '../components/ui';
import type { Setting } from '../types';
import { fmtDateTime } from '../lib/format';

const UNIT: Record<string, string> = {
  cash_difference_threshold_cents: 'centavos',
  cash_difference_severe_cents: 'centavos',
  daily_sales_target_default_cents: 'centavos',
  cancel_window_minutes: 'min',
  gps_interval_seconds: 's',
  photo_sampling_pct: '%',
  evidence_retention_days: 'días',
  gps_retention_days: 'días',
  inventory_count_tolerance_units: 'unidades',
};

function toInput(s: Setting): string {
  if (s.type === 'bool') return s.value ? 'true' : 'false';
  return s.value === null || s.value === undefined ? '' : String(s.value);
}

/** Convierte el texto del input al tipo declarado; devuelve undefined si no es válido (el servidor valida rango → 422). */
export function parseSettingValue(type: Setting['type'], raw: string): unknown {
  if (type === 'bool') return raw === 'true';
  if (type === 'int') {
    if (!/^-?\d+$/.test(raw.trim())) return undefined;
    return Number(raw);
  }
  if (type === 'float') {
    const n = Number(raw);
    return raw.trim() === '' || Number.isNaN(n) ? undefined : n;
  }
  return raw;
}

function SettingRow({ s, canEdit, onSaved }: { s: Setting; canEdit: boolean; onSaved: (s: Setting) => void }) {
  const toast = useToast();
  const [raw, setRaw] = useState(toInput(s));
  const [busy, setBusy] = useState(false);
  useEffect(() => setRaw(toInput(s)), [s.key, s.value]);
  const parsed = parseSettingValue(s.type, raw);
  const dirty = raw !== toInput(s);
  const invalid = parsed === undefined;
  const isDefault = JSON.stringify(s.value) === JSON.stringify(s.default);

  const save = async () => {
    if (invalid || !dirty) return;
    setBusy(true);
    try {
      const out = await api.put<Setting>(`/v1/admin/settings/${s.key}`, { value: parsed });
      onSaved(out);
      toast.toast(`Parámetro ${s.key} guardado`, 'success');
    } catch (e) {
      // 422 VALIDATION (tipo/rango) llega con el mensaje del servidor
      toast.error(e);
    } finally {
      setBusy(false);
    }
  };

  const restore = () => setRaw(s.type === 'bool' ? (s.default ? 'true' : 'false') : String(s.default));

  return (
    <tr data-testid={`setting-${s.key}`}>
      <td>
        <b className="mono">{s.key}</b>
        <div className="small muted">{s.description}</div>
      </td>
      <td className="nowrap">
        {canEdit ? (
          s.type === 'bool' ? (
            <select value={raw} onChange={(e) => setRaw(e.target.value)} disabled={busy} aria-label={`Valor de ${s.key}`}>
              <option value="true">Sí</option>
              <option value="false">No</option>
            </select>
          ) : (
            <input type={s.type === 'str' ? 'text' : 'number'} step={s.type === 'float' ? 'any' : 1} value={raw} onChange={(e) => setRaw(e.target.value)} disabled={busy} aria-label={`Valor de ${s.key}`} aria-invalid={invalid} style={invalid ? { borderColor: 'var(--red)' } : undefined} />
          )
        ) : (
          <b>{s.type === 'bool' ? (s.value ? 'Sí' : 'No') : String(s.value)}</b>
        )}{' '}
        <span className="small muted">{UNIT[s.key]}</span>
        {isDefault && !dirty && (
          <div>
            <Badge tone="light">por defecto</Badge>
          </div>
        )}
      </td>
      <td className="nowrap">
        <span className="default">{s.type === 'bool' ? (s.default ? 'Sí' : 'No') : String(s.default)}</span>{' '}
        {canEdit && !isDefault && (
          <button type="button" className="btn small btn-ghost" onClick={restore} disabled={busy}>
            Restaurar
          </button>
        )}
      </td>
      <td className="nowrap small muted">
        {fmtDateTime(s.updated_at)}
        {s.updated_by && <div className="mono">{s.updated_by.slice(0, 8)}</div>}
      </td>
      <td className="nowrap">
        {canEdit && (
          <button type="button" className="btn small btn-primary" onClick={save} disabled={!dirty || invalid || busy} data-testid={`save-${s.key}`}>
            {busy ? 'Guardando…' : 'Guardar'}
          </button>
        )}
      </td>
    </tr>
  );
}

export function SettingsTab({ canEdit }: { canEdit: boolean }) {
  const { data, loading, setData, reload } = useFetch<Setting[]>(() => api.get('/v1/admin/settings'), []);
  return (
    <Card
      title="Parámetros operativos"
      actions={
        <button type="button" className="btn small" onClick={() => reload()}>
          Actualizar
        </button>
      }
    >
      <p className="muted small">
        Umbrales y tiempos que usan las reglas, la PWA del operador y las tareas de retención. Cambios auditados. Precedencia: override en <b>Reglas</b> (params) &gt; Parámetros &gt; valor por defecto.
        {!canEdit && ' Sólo lectura para tu rol; edita un administrador.'}
      </p>
      {loading && !data && <Loading />}
      {data && (
        <div className="table-wrap">
          <table className="table compact settings-table" data-testid="settings-table">
            <thead>
              <tr>
                <th>Parámetro</th>
                <th>Valor</th>
                <th>Por defecto</th>
                <th>Última actualización</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {data.map((s) => (
                <SettingRow key={s.key} s={s} canEdit={canEdit} onSaved={(ns) => setData(data.map((x) => (x.key === ns.key ? ns : x)))} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
