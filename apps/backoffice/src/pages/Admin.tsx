import { useMemo, useState, type FormEvent, type ReactNode } from 'react';
import { api } from '../api/client';
import { useFetch } from '../lib/useFetch';
import { useAuth } from '../state/auth';
import { useToast } from '../components/Toast';
import { SettingsTab } from './SettingsTab';
import { Badge, Card, Empty, Field, Loading, Modal, PageTitle, StatusBadge } from '../components/ui';
import type { Assignment, Cart, Device, Point, Presentation, PriceVersion, ResetPasswordResponse, Setting, User, Zone } from '../types';
import { fmtDateTime, fmtTime, money, todayLocalISO } from '../lib/format';
import { ROLE_LABEL } from '../components/Layout';
import { ReopenShiftButton } from '../components/ReopenShift';

type Tab = 'users' | 'points' | 'carts' | 'assignments' | 'presentations' | 'prices' | 'devices' | 'zones' | 'settings';
/** ops/finance sólo ven Parámetros y Precios (lectura). */
const TABS: { key: Tab; label: string; adminOnly?: boolean }[] = [
  { key: 'users', label: 'Usuarios', adminOnly: true },
  { key: 'points', label: 'Puntos', adminOnly: true },
  { key: 'carts', label: 'Carritos', adminOnly: true },
  { key: 'assignments', label: 'Asignaciones', adminOnly: true },
  { key: 'presentations', label: 'Presentaciones', adminOnly: true },
  { key: 'prices', label: 'Precios' },
  { key: 'devices', label: 'Dispositivos', adminOnly: true },
  { key: 'zones', label: 'Zonas', adminOnly: true },
  { key: 'settings', label: 'Parámetros' },
];
/** Horas de gracia en las que el servidor sigue aceptando ventas offline con una versión desactivada (B8). */
export const PRICE_OFFLINE_GRACE_HOURS = 72;

type FieldDef = { key: string; label: string; type?: 'text' | 'number' | 'select' | 'checkbox' | 'password' | 'date' | 'datetime'; options?: { value: string; label: string }[]; required?: boolean; createOnly?: boolean };

function EntityForm<T extends { id: string }>({ title, fields, initial, onSubmit, onClose }: { title: string; fields: FieldDef[]; initial: Partial<T> | null; onSubmit: (values: Record<string, unknown>) => Promise<void>; onClose: () => void }) {
  const [values, setValues] = useState<Record<string, unknown>>(() => {
    const v: Record<string, unknown> = {};
    for (const f of fields) v[f.key] = initial ? (initial as Record<string, unknown>)[f.key] ?? (f.type === 'checkbox' ? true : '') : f.type === 'checkbox' ? true : '';
    return v;
  });
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const out: Record<string, unknown> = {};
      for (const f of fields) {
        if (initial && f.createOnly) continue;
        let v = values[f.key];
        if (f.type === 'number') v = v === '' || v === null ? null : Number(v);
        if ((f.type === 'text' || f.type === 'select' || f.type === 'password') && v === '') v = null;
        if (f.type === 'password' && !v) continue;
        if (v === null && !initial && !f.required) continue;
        out[f.key] = v;
      }
      await onSubmit(out);
      onClose();
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal title={title} onClose={onClose}>
      <form onSubmit={submit} className="stack">
        <div className="form-grid">
          {fields
            .filter((f) => !(initial && f.createOnly))
            .map((f) => (
              <Field key={f.key} label={f.label}>
                {f.type === 'select' ? (
                  <select value={String(values[f.key] ?? '')} onChange={(e) => setValues({ ...values, [f.key]: e.target.value })} required={f.required}>
                    <option value="">—</option>
                    {(f.options ?? []).map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                ) : f.type === 'checkbox' ? (
                  <input type="checkbox" checked={!!values[f.key]} onChange={(e) => setValues({ ...values, [f.key]: e.target.checked })} style={{ width: 20, minHeight: 20 }} />
                ) : (
                  <input
                    type={f.type === 'number' ? 'number' : f.type === 'password' ? 'password' : f.type === 'date' ? 'date' : f.type === 'datetime' ? 'datetime-local' : 'text'}
                    step={f.type === 'number' ? 'any' : undefined}
                    value={String(values[f.key] ?? '')}
                    onChange={(e) => setValues({ ...values, [f.key]: e.target.value })}
                    required={f.required && !(initial && f.type === 'password')}
                  />
                )}
              </Field>
            ))}
        </div>
        <div className="row" style={{ justifyContent: 'flex-end' }}>
          <button type="button" className="btn" onClick={onClose}>
            Cancelar
          </button>
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {initial ? 'Guardar' : 'Crear'}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function Crud<T extends { id: string; is_active?: boolean }>({ path, label: entityLabel, fields, columns, data, reload, extra }: { path: string; label: string; fields: FieldDef[]; columns: { h: string; r: (x: T) => ReactNode }[]; data: T[] | null; reload: () => Promise<void>; extra?: (x: T) => ReactNode }) {
  const toast = useToast();
  const [editing, setEditing] = useState<Partial<T> | null | 'new'>(null);
  const save = async (values: Record<string, unknown>) => {
    try {
      if (editing === 'new') await api.post(`/v1/admin/${path}`, values);
      else if (editing) await api.patch(`/v1/admin/${path}/${editing.id}`, values);
      toast.toast('Guardado', 'success');
      await reload();
    } catch (e) {
      toast.error(e);
      throw e;
    }
  };
  const deactivate = async (x: T) => {
    if (!confirm(`¿Dar de baja ${entityLabel.toLowerCase()}?`)) return;
    try {
      await api.del(`/v1/admin/${path}/${x.id}`);
      toast.toast('Baja registrada', 'success');
      await reload();
    } catch (e) {
      toast.error(e);
    }
  };
  return (
    <Card title={`${entityLabel} (${data?.length ?? 0})`} actions={<button type="button" className="btn btn-primary small" onClick={() => setEditing('new')}>+ Nuevo</button>}>
      {!data && <Loading />}
      {data && data.length === 0 && <Empty />}
      {data && data.length > 0 && (
        <div className="table-wrap">
          <table className="table compact">
            <thead>
              <tr>
                {columns.map((c) => (
                  <th key={c.h}>{c.h}</th>
                ))}
                <th></th>
              </tr>
            </thead>
            <tbody>
              {data.map((x) => (
                <tr key={x.id} style={{ opacity: x.is_active === false ? 0.55 : 1 }}>
                  {columns.map((c) => (
                    <td key={c.h}>{c.r(x)}</td>
                  ))}
                  <td className="nowrap">
                    <button type="button" className="btn small" onClick={() => setEditing(x)}>
                      Editar
                    </button>{' '}
                    {x.is_active !== false && (
                      <button type="button" className="btn small btn-ghost" onClick={() => deactivate(x)}>
                        Baja
                      </button>
                    )}{' '}
                    {extra?.(x)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {editing && <EntityForm<T> title={editing === 'new' ? `Nuevo · ${entityLabel}` : `Editar · ${entityLabel}`} fields={fields} initial={editing === 'new' ? null : editing} onSubmit={save} onClose={() => setEditing(null)} />}
    </Card>
  );
}

/** Restablece la contraseña de un usuario y muestra la temporal generada (una sola vez) con botón copiar. */
function ResetPasswordModal({ user, onClose, onDone }: { user: User; onClose: () => void; onDone: () => Promise<void> }) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ResetPasswordResponse | null>(null);
  const [copied, setCopied] = useState(false);
  const run = async () => {
    setBusy(true);
    try {
      const r = await api.post<ResetPasswordResponse>(`/v1/admin/users/${user.id}/reset-password`, {});
      setResult(r);
      await onDone();
    } catch (e) {
      toast.error(e);
    } finally {
      setBusy(false);
    }
  };
  const copy = async () => {
    if (!result?.temporary_password) return;
    try {
      await navigator.clipboard.writeText(result.temporary_password);
      setCopied(true);
      toast.toast('Contraseña copiada', 'success');
    } catch {
      toast.toast('No se pudo copiar; selecciona el texto manualmente', 'error');
    }
  };
  return (
    <Modal title={`Restablecer contraseña · ${user.name}`} onClose={onClose}>
      {!result ? (
        <div className="stack">
          <p>
            Se generará una contraseña temporal para <b className="mono">{user.username}</b>, se cerrarán sus sesiones y deberá cambiarla al entrar.
          </p>
          <div className="row" style={{ justifyContent: 'flex-end' }}>
            <button type="button" className="btn" onClick={onClose} disabled={busy}>
              Cancelar
            </button>
            <button type="button" className="btn btn-danger" onClick={run} disabled={busy} data-testid="reset-password-confirm">
              {busy ? 'Restableciendo…' : 'Restablecer'}
            </button>
          </div>
        </div>
      ) : (
        <div className="stack">
          <p>Contraseña temporal (se muestra una sola vez; compártela por un canal seguro):</p>
          <div className="row">
            <code className="mono" data-testid="temporary-password" style={{ fontSize: 18, padding: '8px 12px', background: 'var(--bg)', borderRadius: 8, userSelect: 'all' }}>
              {result.temporary_password ?? '—'}
            </code>
            <button type="button" className="btn btn-primary small" onClick={copy} disabled={!result.temporary_password}>
              {copied ? 'Copiada ✓' : 'Copiar'}
            </button>
          </div>
          <p className="muted small">El usuario verá "Debe cambiar contraseña" hasta que la cambie desde su app.</p>
          <div className="row" style={{ justifyContent: 'flex-end' }}>
            <button type="button" className="btn btn-primary" onClick={onClose}>
              Listo
            </button>
          </div>
        </div>
      )}
    </Modal>
  );
}

export function AdminPage() {
  const toast = useToast();
  const { hasRole } = useAuth();
  const isAdmin = hasRole('admin');
  const tabs = TABS.filter((t) => isAdmin || !t.adminOnly);
  const [tab, setTab] = useState<Tab>(isAdmin ? 'users' : 'settings');
  const [resetting, setResetting] = useState<User | null>(null);
  const zones = useFetch<Zone[]>(() => api.get('/v1/admin/zones'), [], { enabled: isAdmin });
  const users = useFetch<User[]>(() => api.get('/v1/admin/users'), [], { enabled: isAdmin });
  const points = useFetch<Point[]>(() => api.get('/v1/admin/points'), [], { enabled: isAdmin });
  const carts = useFetch<Cart[]>(() => api.get('/v1/admin/carts'), [], { enabled: isAdmin });
  const assignments = useFetch<Assignment[]>(() => api.get('/v1/admin/assignments'), [], { enabled: isAdmin });
  const [pointSheet, setPointSheet] = useState<Point | null>(null);
  const [verifying, setVerifying] = useState<Point | null>(null);
  const [importing, setImporting] = useState(false);
  const settingsAll = useFetch<Setting[]>(() => api.get('/v1/admin/settings'), []);
  const openMaxDistance = Number(settingsAll.data?.find((s) => s.key === 'open_max_distance_m')?.value ?? 50);
  const reimportPoints = async () => {
    setImporting(true);
    try {
      const r = await api.post<{ created: number; updated: number; zones_created: number }>('/v1/admin/points/import-authorized');
      toast.toast(`Catálogo importado: ${r.created} nuevos, ${r.updated} actualizados, ${r.zones_created} zonas nuevas`, 'success');
      await points.reload(true);
      await zones.reload(true);
    } catch (e) {
      toast.error(e);
    } finally {
      setImporting(false);
    }
  };
  const presentations = useFetch<Presentation[]>(() => api.get('/v1/admin/presentations'), [], { silent: !isAdmin });
  const priceVersions = useFetch<PriceVersion[]>(() => api.get('/v1/admin/price-versions'), []);
  const devices = useFetch<Device[]>(() => api.get('/v1/admin/devices'), [], { enabled: isAdmin });

  const zoneOpts = useMemo(() => (zones.data ?? []).map((z) => ({ value: z.id, label: z.name })), [zones.data]);
  const zoneName = (id: string | null) => zones.data?.find((z) => z.id === id)?.name ?? '—';
  const userName = (id: string | null) => users.data?.find((u) => u.id === id)?.name ?? '—';
  const pointName = (id: string) => points.data?.find((p) => p.id === id)?.name ?? id.slice(0, 8);
  const cartCode = (id: string) => carts.data?.find((c) => c.id === id)?.code ?? id.slice(0, 8);
  const operators = (users.data ?? []).filter((u) => u.role === 'operator' && u.is_active);

  // Precios
  const [newPrice, setNewPrice] = useState<{ name: string; prices: Record<string, string> } | null>(null);
  const createPrice = async (e: FormEvent) => {
    e.preventDefault();
    if (!newPrice) return;
    try {
      const prices: Record<string, number> = {};
      for (const [k, v] of Object.entries(newPrice.prices)) if (v !== '') prices[k] = Math.round(parseFloat(v) * 100);
      await api.post('/v1/admin/price-versions', { name: newPrice.name, prices });
      toast.toast('Versión de precio creada', 'success');
      setNewPrice(null);
      await priceVersions.reload(true);
    } catch (err) {
      toast.error(err);
    }
  };

  /** Desactivar / reactivar una versión (PATCH). Aviso: gracia de 72 h para ventas offline con la versión desactivada. */
  const togglePriceVersion = async (v: PriceVersion) => {
    const question = v.is_active
      ? `¿Desactivar la versión "${v.name}"?\n\nLos operadores sin señal seguirán vendiendo con estos precios hasta sincronizar: el servidor acepta esas ventas durante ${PRICE_OFFLINE_GRACE_HOURS} h de gracia y las marca como "precio vencido" en el reporte diario. Asegúrate de que exista otra versión activa.`
      : `¿Reactivar la versión "${v.name}"? Volverá a ser una versión vigente.`;
    if (!confirm(question)) return;
    try {
      await api.patch<PriceVersion>(`/v1/admin/price-versions/${v.id}`, { is_active: !v.is_active });
      toast.toast(v.is_active ? 'Versión desactivada' : 'Versión reactivada', 'success');
      await priceVersions.reload(true);
    } catch (e) {
      toast.error(e);
    }
  };

  const revoke = async (d: Device) => {
    const reason = prompt(`Motivo para revocar ${d.name ?? d.device_id}:`, 'Dispositivo perdido');
    if (reason === null) return;
    try {
      await api.post(`/v1/admin/devices/${d.device_id}/revoke`, { reason });
      toast.toast('Dispositivo revocado', 'success');
      await devices.reload(true);
    } catch (e) {
      toast.error(e);
    }
  };
  const unrevoke = async (d: Device) => {
    try {
      await api.post(`/v1/admin/devices/${d.device_id}/unrevoke`);
      toast.toast('Dispositivo reactivado', 'success');
      await devices.reload(true);
    } catch (e) {
      toast.error(e);
    }
  };

  return (
    <div>
      <PageTitle title="Administración" subtitle="Altas y cambios quedan en el audit log. Las bajas son lógicas: el ledger nunca pierde referencias." />
      <div className="tabs">
        {tabs.map((t) => (
          <button key={t.key} type="button" className={tab === t.key ? 'active' : ''} onClick={() => setTab(t.key)}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'users' && (
        <Crud<User>
          path="users"
          label="Usuarios"
          data={users.data}
          reload={() => users.reload(true)}
          fields={[
            { key: 'username', label: 'Usuario', required: true, createOnly: true },
            { key: 'name', label: 'Nombre', required: true },
            { key: 'role', label: 'Rol', type: 'select', required: true, options: (['operator', 'supervisor', 'ops', 'finance', 'admin'] as const).map((r) => ({ value: r, label: ROLE_LABEL[r] })) },
            { key: 'password', label: 'Contraseña', type: 'password', required: true },
            { key: 'zone_id', label: 'Zona', type: 'select', options: zoneOpts },
            { key: 'phone', label: 'Teléfono' },
            { key: 'is_active', label: 'Activo', type: 'checkbox' },
          ]}
          columns={[
            { h: 'Usuario', r: (u) => <span className="mono">{u.username}</span> },
            { h: 'Nombre', r: (u) => <b>{u.name}</b> },
            { h: 'Rol', r: (u) => <Badge tone="blue">{ROLE_LABEL[u.role]}</Badge> },
            { h: 'Zona', r: (u) => zoneName(u.zone_id) },
            { h: 'Teléfono', r: (u) => u.phone ?? '—' },
            { h: 'Activo', r: (u) => <StatusBadge status={u.is_active ? 'active' : 'blocked'} /> },
            { h: 'Contraseña', r: (u) => (u.must_change_password ? <Badge tone="amber" title="Debe cambiar su contraseña al entrar">Debe cambiar contraseña</Badge> : <span className="muted">—</span>) },
          ]}
          extra={(u) => (
            <button type="button" className="btn small btn-ghost" onClick={() => setResetting(u)} data-testid={`reset-password-${u.username}`}>
              Restablecer contraseña
            </button>
          )}
        />
      )}
      {resetting && <ResetPasswordModal user={resetting} onClose={() => setResetting(null)} onDone={() => users.reload(true)} />}

      {tab === 'points' && (
        <Crud<Point>
          path="points"
          label="Puntos"
          data={points.data ? [...points.data].sort((a, b) => (a.meta?.ranking ?? 0) - (b.meta?.ranking ?? 0) || a.name.localeCompare(b.name)) : null}
          reload={() => points.reload(true)}
          fields={[
            { key: 'name', label: 'Nombre', required: true },
            { key: 'address', label: 'Dirección' },
            { key: 'lat', label: 'Latitud', type: 'number', required: true },
            { key: 'lng', label: 'Longitud', type: 'number', required: true },
            { key: 'geofence_radius_m', label: 'Geocerca (m)', type: 'number' },
            { key: 'zone_id', label: 'Zona', type: 'select', options: zoneOpts },
            { key: 'open_time', label: 'Apertura (HH:MM)' },
            { key: 'close_time', label: 'Cierre (HH:MM)' },
            { key: 'daily_target_cents', label: 'Meta diaria (centavos)', type: 'number' },
            { key: 'daily_target_tx', label: 'Meta ventas/día', type: 'number' },
            { key: 'is_active', label: 'Activo', type: 'checkbox' },
            { key: 'geo_verified', label: 'Coordenadas verificadas en campo', type: 'checkbox' },
          ]}
          columns={[
            { h: '#', r: (p) => (p.meta?.ranking ? <span className="mono">{p.meta.ranking}</span> : <span className="muted">—</span>) },
            { h: 'Punto', r: (p) => (
              <>
                <b>{p.name}</b>
                {p.meta?.node_type && <div className="muted small">{p.meta.node_type}{p.meta.score ? ` · score ${p.meta.score}` : ''}</div>}
              </>
            ) },
            { h: 'Alcaldía / zona', r: (p) => zoneName(p.zone_id) },
            { h: 'GPS', r: (p) => (
              <>
                <span className="mono">{p.lat.toFixed(4)}, {p.lng.toFixed(4)}</span>{' '}
                {p.geo_verified === false ? <Badge tone="amber" title={p.meta?.geo_source ?? 'Coordenadas aproximadas'}>Por validar · tolerancia {p.geofence_radius_m} m</Badge> : <Badge tone="green">Verificado · apertura ≤ {openMaxDistance} m</Badge>}
              </>
            ) },
            { h: 'Horario', r: (p) => `${p.open_time ?? '—'}–${p.close_time ?? '—'}` },
            { h: 'Meta', r: (p) => `${money(p.daily_target_cents, { decimals: 0 })} · ${p.daily_target_tx} tx` },
            { h: 'Activo', r: (p) => <StatusBadge status={p.is_active ? 'active' : 'blocked'} /> },
          ]}
          extra={(p) => (
            <>
              {p.meta?.ranking && (
                <button type="button" className="btn small btn-ghost" onClick={() => setPointSheet(p)}>
                  Ficha
                </button>
              )}{' '}
              {p.geo_verified === false && isAdmin && (
                <button type="button" className="btn small btn-accent" data-testid={`verify-point-${p.id}`} onClick={() => setVerifying(p)}>
                  Validar GPS
                </button>
              )}
            </>
          )}
        />
      )}
      {tab === 'points' && (
        <p className="muted small">
          Sólo los puntos activos pueden asignarse a carritos. Los 100 del catálogo <i>Pepito · mejores ubicaciones CDMX</i> entran con coordenadas aproximadas (<b>Por validar</b>): al abrir se tolera la geocerca del punto. Tras validarlas en campo (<b>Validar GPS</b>) aplica la regla estricta: abrir a más de {openMaxDistance} m avisa al operador y abre caso urgente.{' '}
          {isAdmin && (
            <button type="button" className="btn small" onClick={reimportPoints} disabled={importing}>
              {importing ? 'Importando…' : 'Reimportar catálogo'}
            </button>
          )}
        </p>
      )}
      {pointSheet && <PointSheetModal point={pointSheet} onClose={() => setPointSheet(null)} />}
      {verifying && (
        <VerifyPointModal
          point={verifying}
          onClose={() => setVerifying(null)}
          onDone={async () => {
            setVerifying(null);
            await points.reload(true);
          }}
        />
      )}

      {tab === 'carts' && (
        <Crud<Cart>
          path="carts"
          label="Carritos"
          data={carts.data}
          reload={() => carts.reload(true)}
          fields={[
            { key: 'code', label: 'Código', required: true },
            { key: 'description', label: 'Descripción' },
            { key: 'is_active', label: 'Activo', type: 'checkbox' },
          ]}
          columns={[
            { h: 'Código', r: (c) => <b className="mono">{c.code}</b> },
            { h: 'Descripción', r: (c) => c.description ?? '—' },
            { h: 'Activo', r: (c) => <StatusBadge status={c.is_active ? 'active' : 'blocked'} /> },
          ]}
        />
      )}

      {tab === 'assignments' && (
        <Crud<Assignment>
          path="assignments"
          label="Asignaciones"
          data={assignments.data ? [...assignments.data].sort((a, b) => b.shift_date.localeCompare(a.shift_date)).slice(0, 200) : null}
          reload={() => assignments.reload(true)}
          fields={[
            { key: 'operator_id', label: 'Operador', type: 'select', required: true, options: operators.map((u) => ({ value: u.id, label: u.name })) },
            { key: 'point_id', label: 'Punto', type: 'select', required: true, options: (points.data ?? []).filter((p) => p.is_active).map((p) => ({ value: p.id, label: p.name })) },
            { key: 'cart_id', label: 'Carrito', type: 'select', required: true, options: (carts.data ?? []).filter((c) => c.is_active).map((c) => ({ value: c.id, label: c.code })) },
            { key: 'shift_date', label: 'Fecha', type: 'date', required: true, createOnly: true },
            { key: 'status', label: 'Estado', type: 'select', options: ['planned', 'started', 'done', 'absent'].map((s) => ({ value: s, label: s })) },
          ]}
          columns={[
            { h: 'Fecha', r: (a) => <b>{a.shift_date}</b> },
            { h: 'Operador', r: (a) => userName(a.operator_id) },
            { h: 'Punto', r: (a) => pointName(a.point_id) },
            { h: 'Carrito', r: (a) => <span className="mono">{cartCode(a.cart_id)}</span> },
            { h: 'Horario', r: (a) => `${fmtTime(a.planned_start)}–${fmtTime(a.planned_end)}` },
            { h: 'Estado', r: (a) => <StatusBadge status={a.status} /> },
            { h: 'Turno', r: (a) => (a.shift_status ? <StatusBadge status={a.shift_status} /> : <span className="muted">—</span>) },
          ]}
          extra={(a) => (a.shift_id && a.shift_status === 'closed' ? <ReopenShiftButton shiftId={a.shift_id} label={`${userName(a.operator_id)} · ${pointName(a.point_id)}`} onDone={() => assignments.reload(true)} /> : null)}
        />
      )}
      {tab === 'assignments' && <p className="muted small">Al crear sin horario, se usa el horario de apertura/cierre del punto. Fecha sugerida: {todayLocalISO()}.</p>}

      {tab === 'presentations' && (
        <Crud<Presentation>
          path="presentations"
          label="Presentaciones"
          data={presentations.data}
          reload={() => presentations.reload(true)}
          fields={[
            { key: 'name', label: 'Nombre', required: true },
            { key: 'grams', label: 'Gramos', type: 'number', required: true },
            { key: 'sort', label: 'Orden', type: 'number' },
            { key: 'is_active', label: 'Activa', type: 'checkbox' },
          ]}
          columns={[
            { h: 'Nombre', r: (p) => <b>{p.name}</b> },
            { h: 'Gramos', r: (p) => `${p.grams} g` },
            { h: 'Orden', r: (p) => p.sort },
            { h: 'Precio vigente', r: (p) => money(priceVersions.data?.find((v) => v.is_active)?.prices[p.id] ?? null) },
            { h: 'Activa', r: (p) => <StatusBadge status={p.is_active ? 'active' : 'blocked'} /> },
          ]}
        />
      )}

      {tab === 'settings' && <SettingsTab canEdit={isAdmin} />}

      {tab === 'prices' && (
        <Card title="Versiones de precio" actions={isAdmin ? <button type="button" className="btn btn-primary small" onClick={() => setNewPrice({ name: `Precios ${todayLocalISO()}`, prices: Object.fromEntries((presentations.data ?? []).map((p) => [p.id, String(((priceVersions.data?.[0]?.prices[p.id] ?? 0) / 100).toFixed(2))])) })}>+ Nueva versión</button> : undefined}>
          <p className="muted small">
            Los precios nunca se editan in-place: cada cambio es una nueva versión con vigencia; las ventas guardan la versión usada. Al desactivar una versión, las ventas offline con ella se aceptan {PRICE_OFFLINE_GRACE_HOURS} h más y quedan marcadas como "precio vencido".
          </p>
          {!priceVersions.data && <Loading />}
          {priceVersions.data && (
            <div className="table-wrap">
              <table className="table compact">
                <thead>
                  <tr>
                    <th>Nombre</th>
                    <th>Vigente desde</th>
                    <th>Hasta</th>
                    {(presentations.data ?? []).map((p) => (
                      <th key={p.id} className="num">
                        {p.name}
                      </th>
                    ))}
                    <th className="num">Ventas</th>
                    <th>Activa</th>
                    <th>Desactivada</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {priceVersions.data.map((v) => (
                    <tr key={v.id} data-testid={`price-version-${v.id}`} style={{ opacity: v.is_active ? 1 : 0.7 }}>
                      <td>
                        <b>{v.name}</b>
                      </td>
                      <td className="nowrap">{fmtDateTime(v.valid_from)}</td>
                      <td className="nowrap">{fmtDateTime(v.valid_to)}</td>
                      {(presentations.data ?? []).map((p) => (
                        <td key={p.id} className="num">
                          {money(v.prices[p.id] ?? null)}
                        </td>
                      ))}
                      <td className="num">{v.sales_count ?? '—'}</td>
                      <td>{v.is_active ? <Badge tone="green">Sí</Badge> : <Badge tone="gray">No</Badge>}</td>
                      <td className="nowrap small muted">{fmtDateTime(v.deactivated_at)}</td>
                      <td className="nowrap">
                        {isAdmin && (
                          <button type="button" className={`btn small ${v.is_active ? 'btn-danger' : ''}`} onClick={() => togglePriceVersion(v)} data-testid={`toggle-price-version-${v.id}`}>
                            {v.is_active ? 'Desactivar' : 'Reactivar'}
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {newPrice && (
            <Modal title="Nueva versión de precio" onClose={() => setNewPrice(null)}>
              <form onSubmit={createPrice} className="stack">
                <Field label="Nombre">
                  <input value={newPrice.name} onChange={(e) => setNewPrice({ ...newPrice, name: e.target.value })} required />
                </Field>
                {(presentations.data ?? []).map((p) => (
                  <Field key={p.id} label={`${p.name} (MXN)`}>
                    <input type="number" step="0.01" min="0" value={newPrice.prices[p.id] ?? ''} onChange={(e) => setNewPrice({ ...newPrice, prices: { ...newPrice.prices, [p.id]: e.target.value } })} required />
                  </Field>
                ))}
                <div className="row" style={{ justifyContent: 'flex-end' }}>
                  <button type="button" className="btn" onClick={() => setNewPrice(null)}>
                    Cancelar
                  </button>
                  <button type="submit" className="btn btn-primary">
                    Crear versión (vigente ahora)
                  </button>
                </div>
              </form>
            </Modal>
          )}
        </Card>
      )}

      {tab === 'devices' && (
        <Card title={`Dispositivos (${devices.data?.length ?? 0})`}>
          <p className="muted small">Revocar un dispositivo invalida su sesión de inmediato (401 DEVICE_REVOKED) sin tocar ledger ni turnos históricos.</p>
          {!devices.data && <Loading />}
          {devices.data && (
            <div className="table-wrap">
              <table className="table compact">
                <thead>
                  <tr>
                    <th>Dispositivo</th>
                    <th>Usuario</th>
                    <th>Plataforma</th>
                    <th>Último login</th>
                    <th>Visto</th>
                    <th>Estado</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {devices.data.map((d) => (
                    <tr key={d.id}>
                      <td>
                        {d.name ?? <span className="muted">sin nombre</span>}
                        <div className="mono muted">{d.device_id}</div>
                      </td>
                      <td>{userName(d.user_id)}</td>
                      <td>{d.platform ?? '—'}</td>
                      <td className="nowrap">{fmtDateTime(d.last_login_at)}</td>
                      <td className="nowrap">{fmtDateTime(d.last_seen_at)}</td>
                      <td>
                        {d.revoked ? (
                          <>
                            <Badge tone="red">Revocado</Badge> <span className="small muted">{d.revoked_reason}</span>
                          </>
                        ) : (
                          <Badge tone="green">Activo</Badge>
                        )}
                      </td>
                      <td>
                        {d.revoked ? (
                          <button type="button" className="btn small" onClick={() => unrevoke(d)}>
                            Reactivar
                          </button>
                        ) : (
                          <button type="button" className="btn small btn-danger" onClick={() => revoke(d)}>
                            Revocar
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      {tab === 'zones' && (
        <Crud<Zone>
          path="zones"
          label="Zonas"
          data={zones.data}
          reload={() => zones.reload(true)}
          fields={[
            { key: 'name', label: 'Nombre', required: true },
            { key: 'is_active', label: 'Activa', type: 'checkbox' },
          ]}
          columns={[
            { h: 'Zona', r: (z) => <b>{z.name}</b> },
            { h: 'Supervisores', r: (z) => (users.data ?? []).filter((u) => u.zone_id === z.id && u.role === 'supervisor').map((u) => u.name).join(', ') || '—' },
            { h: 'Puntos', r: (z) => (points.data ?? []).filter((p) => p.zone_id === z.id).length },
            { h: 'Activa', r: (z) => <StatusBadge status={z.is_active ? 'active' : 'blocked'} /> },
          ]}
        />
      )}
    </div>
  );
}


/** Ficha del punto autorizado (datos del catálogo de ubicaciones). */
function PointSheetModal({ point, onClose }: { point: Point; onClose: () => void }) {
  const m = point.meta ?? {};
  const row = (k: string, v?: string | number | null) => (v ? (
    <tr>
      <th style={{ width: 180 }}>{k}</th>
      <td>{v}</td>
    </tr>
  ) : null);
  return (
    <Modal title={`#${m.ranking} · ${point.name}`} onClose={onClose} className="wide">
      <table className="table compact">
        <tbody>
          {row('Alcaldía', m.alcaldia)}
          {row('Tipo de nodo', m.node_type)}
          {row('Score /100', m.score)}
          {row('Afluencia estimada', m.afluencia)}
          {row('Riesgo permiso/operación', m.riesgo)}
          {row('Factibilidad resguardo + carga', m.resguardo)}
          {row('Horario sugerido', m.horario_sugerido)}
          {row('Justificación', m.justificacion)}
          {row('Estrategia resguardo/recarga', m.estrategia)}
          {row('Validación antes de abrir', m.validacion)}
          {row('Coordenadas', `${point.lat.toFixed(5)}, ${point.lng.toFixed(5)} · ${point.geo_verified === false ? 'por validar' : 'verificadas'}${m.geo_source ? ` (${m.geo_source})` : ''}`)}
          {row('Fuente', m.fuente)}
        </tbody>
      </table>
      <p className="muted small" style={{ marginTop: 8 }}>{m.source}</p>
    </Modal>
  );
}

/** Valida las coordenadas de un punto: a mano (lat/lng) o adoptando el GPS de la última apertura registrada en ese punto. */
function VerifyPointModal({ point, onClose, onDone }: { point: Point; onClose: () => void; onDone: () => Promise<void> }) {
  const toast = useToast();
  const [lat, setLat] = useState(String(point.lat));
  const [lng, setLng] = useState(String(point.lng));
  const [source, setSource] = useState('Validado en campo');
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post(`/v1/admin/points/${point.id}/verify-location`, { verified: true, lat: Number(lat), lng: Number(lng), source });
      toast.toast(`Coordenadas de ${point.name} verificadas`, 'success');
      await onDone();
    } catch (err) {
      toast.error(err);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal title={`Validar GPS · ${point.name}`} onClose={onClose}>
      <form className="stack" onSubmit={submit} data-testid="verify-point-form">
        <p className="small muted">
          Escribe las coordenadas reales del lugar exacto donde se coloca el carrito (por ejemplo, las que marca el teléfono del supervisor parado en el punto). A partir de ahora la apertura exigirá estar a no más de la distancia máxima configurada.
        </p>
        <div className="form-grid">
          <Field label="Latitud">
            <input value={lat} onChange={(e) => setLat(e.target.value)} required inputMode="decimal" />
          </Field>
          <Field label="Longitud">
            <input value={lng} onChange={(e) => setLng(e.target.value)} required inputMode="decimal" />
          </Field>
        </div>
        <Field label="Fuente / nota" hint="Queda en el audit log.">
          <input value={source} onChange={(e) => setSource(e.target.value)} maxLength={120} />
        </Field>
        <div className="row" style={{ justifyContent: 'flex-end' }}>
          <button type="button" className="btn" onClick={onClose} disabled={busy}>
            Cancelar
          </button>
          <button type="submit" className="btn btn-accent" disabled={busy} data-testid="verify-point-confirm">
            {busy ? 'Guardando…' : 'Marcar verificado'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
