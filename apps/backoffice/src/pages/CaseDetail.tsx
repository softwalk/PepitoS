import { useMemo, useState, type FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../api/client';
import { useFetch } from '../lib/useFetch';
import { useAuth } from '../state/auth';
import { useToast } from '../components/Toast';
import { EvidenceGallery } from '../components/EvidenceGallery';
import { Badge, Card, Empty, Field, Loading, PageTitle, SeverityBadge, StatusBadge } from '../components/ui';
import type { Action, Audit, AuditLogRow, Case, CaseStatus, Severity, User } from '../types';
import { CATEGORY_LABEL, ageLabel, fmtDate, fmtDateTime, label, todayLocalISO } from '../lib/format';

const CATEGORIES = ['cart', 'battery', 'product', 'payment', 'security', 'other'];

export function CaseDetailPage() {
  const { id = '' } = useParams();
  const toast = useToast();
  const { user, hasRole } = useAuth();
  const canEdit = hasRole('supervisor', 'ops', 'admin');
  const { data: c, loading, reload, setData } = useFetch<Case>(() => api.get(`/v1/cases/${id}`), [id]);
  const users = useFetch<User[]>(() => api.get('/v1/admin/users'), [], { silent: true, enabled: hasRole('ops', 'admin') });
  const log = useFetch<AuditLogRow[]>(() => api.get(`/v1/audit-log?entity=case&entity_id=${id}&limit=100`), [id], { silent: true, enabled: hasRole('ops', 'admin', 'finance') });
  // Caso abierto por una auditoría: sus fotos también son evidencia del caso.
  const auditId = typeof c?.payload?.audit_id === 'string' ? (c.payload.audit_id as string) : null;
  const audit = useFetch<Audit>(() => api.get(`/v1/audits/${auditId}`), [auditId], { silent: true, enabled: !!auditId && hasRole('supervisor', 'ops', 'admin') });

  const [desc, setDesc] = useState('');
  const [owner, setOwner] = useState('');
  const [due, setDue] = useState(todayLocalISO());
  const [resolution, setResolution] = useState('');

  const patch = async (body: Partial<{ status: CaseStatus; assignee_id: string; severity: Severity; category: string; resolution: string }>) => {
    try {
      const updated = await api.patch<Case>(`/v1/cases/${id}`, body);
      setData(updated);
      toast.toast('Caso actualizado', 'success');
      void log.reload(true);
    } catch (e) {
      toast.error(e);
    }
  };

  const addAction = async (e: FormEvent) => {
    e.preventDefault();
    if (!desc.trim()) return;
    try {
      await api.post<Action>(`/v1/cases/${id}/actions`, { description: desc.trim(), owner_id: owner || null, due_date: due || null });
      setDesc('');
      toast.toast('Acción correctiva agregada', 'success');
      await reload(true);
    } catch (err) {
      toast.error(err);
    }
  };

  const markAction = async (a: Action, status: Action['status']) => {
    try {
      await api.patch(`/v1/actions/${a.id}`, { status });
      await reload(true);
    } catch (err) {
      toast.error(err);
    }
  };

  const timeline = useMemo(() => {
    if (!c) return [];
    const items: { at: string; what: string; detail?: string }[] = [{ at: c.opened_at, what: `Caso abierto (${c.source === 'rule' ? 'regla ' + (c.rule_key ?? '') : c.source})`, detail: c.description || undefined }];
    if (c.ai) items.push({ at: c.opened_at, what: `IA sugiere categoría "${label(CATEGORY_LABEL, c.ai.suggested_category)}"`, detail: `confianza ${Math.round(c.ai.confidence * 100)}% · sólo sugerencia, decide un humano` });
    for (const a of c.actions) {
      items.push({ at: a.done_at ?? a.due_date ?? c.opened_at, what: `Acción: ${a.description}`, detail: `${label({ pending: 'Pendiente', done: 'Hecha', overdue: 'Vencida' }, a.status)}${a.due_date ? ' · vence ' + fmtDate(a.due_date) : ''}` });
    }
    for (const r of log.data ?? []) {
      const before = (r.before ?? {}) as Record<string, unknown>;
      const after = (r.after ?? {}) as Record<string, unknown>;
      const changes = Object.keys(after)
        .filter((k) => JSON.stringify(before[k]) !== JSON.stringify(after[k]))
        .map((k) => `${k}: ${String(before[k] ?? '—')} → ${String(after[k] ?? '—')}`)
        .join('; ');
      items.push({ at: r.at, what: `${r.action} · ${r.actor_name ?? 'sistema'}`, detail: [changes, r.reason].filter(Boolean).join(' · ') || undefined });
    }
    if (c.resolved_at) items.push({ at: c.resolved_at, what: `Caso ${c.status === 'closed' ? 'cerrado' : 'resuelto'}`, detail: c.resolution ?? undefined });
    return items.sort((a, b) => a.at.localeCompare(b.at));
  }, [c, log.data]);

  if (loading && !c) return <Loading />;
  if (!c) return <Empty text="Caso no encontrado" />;

  return (
    <div>
      <PageTitle
        title={c.title}
        subtitle={
          <span className="tag-line">
            <SeverityBadge severity={c.severity} /> <StatusBadge status={c.status} /> {c.point && <span>{c.point.name}</span>} · abierto hace {ageLabel(c.age_minutes)} · prioridad {c.priority_score.toFixed(1)} · <Link to="/excepciones">← Excepciones</Link>
          </span>
        }
      />
      <div className="grid-2">
        <div>
          <Card title="Detalle">
            <p style={{ marginTop: 0 }}>{c.description || <span className="muted">Sin descripción</span>}</p>
            <div className="stat-inline">
              <span>
                Categoría: <b>{label(CATEGORY_LABEL, c.category)}</b>
              </span>
              <span>
                Origen: <b>{c.source}</b>
              </span>
              <span>
                Impacto: <b>{c.impact_score}</b>
              </span>
              <span>
                Responsable: <b>{c.assignee?.name ?? 'Sin asignar'}</b>
              </span>
              {c.shift_id && (
                <span>
                  Turno: <span className="mono">{c.shift_id.slice(0, 8)}</span>
                </span>
              )}
            </div>
            {c.ai && (
              <div className="rec" style={{ marginTop: 10, background: 'var(--amber-bg)', color: 'var(--amber)', padding: 8, borderRadius: 6 }}>
                Sugerencia IA: reclasificar como <b>{label(CATEGORY_LABEL, c.ai.suggested_category)}</b> (confianza {Math.round(c.ai.confidence * 100)}%).{' '}
                {canEdit && c.ai.suggested_category !== c.category && (
                  <button type="button" className="btn small" onClick={() => patch({ category: c.ai!.suggested_category })}>
                    Aceptar sugerencia
                  </button>
                )}
              </div>
            )}
          </Card>

          <Card title={`Evidencias (${(c.evidence?.length ?? 0) + (audit.data?.evidence.length ?? 0)})`} actions={auditId ? <Link to={`/auditorias/${auditId}`} className="btn small">Ver auditoría</Link> : undefined}>
            <EvidenceGallery items={c.evidence} emptyText={auditId ? 'Sin fotos propias del caso' : 'Sin fotos adjuntas'} />
            {audit.data && audit.data.evidence.length > 0 && (
              <div style={{ marginTop: 10 }}>
                <EvidenceGallery items={audit.data.evidence} title={`Fotos de la auditoría (${fmtDateTime(audit.data.performed_at)})`} />
              </div>
            )}
          </Card>

          {canEdit && (
            <Card title="Gestión">
              <div className="form-grid">
                <Field label="Estado">
                  <select value={c.status} onChange={(e) => patch({ status: e.target.value as CaseStatus })}>
                    <option value="open">Abierto</option>
                    <option value="in_progress">En proceso</option>
                    <option value="resolved">Resuelto</option>
                    <option value="closed">Cerrado</option>
                  </select>
                </Field>
                <Field label="Severidad">
                  <select value={c.severity} onChange={(e) => patch({ severity: e.target.value as Severity })}>
                    <option value="urgent">URGENTE</option>
                    <option value="review">REVISAR</option>
                    <option value="normal">NORMAL</option>
                  </select>
                </Field>
                <Field label="Categoría">
                  <select value={CATEGORIES.includes(c.category) ? c.category : ''} onChange={(e) => e.target.value && patch({ category: e.target.value })}>
                    {!CATEGORIES.includes(c.category) && <option value="">{label(CATEGORY_LABEL, c.category)}</option>}
                    {CATEGORIES.map((k) => (
                      <option key={k} value={k}>
                        {CATEGORY_LABEL[k]}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Asignar a">
                  {users.data ? (
                    <select value={c.assignee?.id ?? ''} onChange={(e) => e.target.value && patch({ assignee_id: e.target.value })}>
                      <option value="">Sin asignar</option>
                      {users.data
                        .filter((u) => u.is_active && u.role !== 'operator')
                        .map((u) => (
                          <option key={u.id} value={u.id}>
                            {u.name} ({u.role})
                          </option>
                        ))}
                    </select>
                  ) : (
                    <button type="button" className="btn" onClick={() => user && patch({ assignee_id: user.id })}>
                      Asignármelo
                    </button>
                  )}
                </Field>
              </div>
              <div className="row" style={{ marginTop: 10 }}>
                <input placeholder="Resolución / nota" value={resolution} onChange={(e) => setResolution(e.target.value)} style={{ flex: 1 }} />
                <button type="button" className="btn btn-success" onClick={() => patch({ status: 'resolved', resolution })} disabled={!resolution.trim()}>
                  Resolver con nota
                </button>
              </div>
            </Card>
          )}

          <Card title={`Acciones correctivas (${c.actions.length})`}>
            {c.actions.length === 0 && <Empty text="Sin acciones" />}
            {c.actions.length > 0 && (
              <table className="table compact">
                <thead>
                  <tr>
                    <th>Descripción</th>
                    <th>Responsable</th>
                    <th>Fecha</th>
                    <th>Estado</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {c.actions.map((a) => (
                    <tr key={a.id}>
                      <td>{a.description}</td>
                      <td>{users.data?.find((u) => u.id === a.owner_id)?.name ?? (a.owner_id ? a.owner_id.slice(0, 8) : '—')}</td>
                      <td className="nowrap">{fmtDate(a.due_date)}</td>
                      <td>
                        <StatusBadge status={a.status} />
                      </td>
                      <td className="nowrap">
                        {canEdit && a.status !== 'done' && (
                          <button type="button" className="btn small btn-success" onClick={() => markAction(a, 'done')}>
                            Marcar hecha
                          </button>
                        )}
                        {canEdit && a.status === 'done' && (
                          <button type="button" className="btn small" onClick={() => markAction(a, 'pending')}>
                            Reabrir
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {canEdit && (
              <form onSubmit={addAction} className="form-grid" style={{ marginTop: 12 }}>
                <Field label="Nueva acción">
                  <input value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="Qué se va a hacer" required />
                </Field>
                <Field label="Responsable">
                  {users.data ? (
                    <select value={owner} onChange={(e) => setOwner(e.target.value)}>
                      <option value="">{user?.name} (yo)</option>
                      {users.data
                        .filter((u) => u.is_active)
                        .map((u) => (
                          <option key={u.id} value={u.id}>
                            {u.name}
                          </option>
                        ))}
                    </select>
                  ) : (
                    <input value={user?.name ?? ''} disabled />
                  )}
                </Field>
                <Field label="Fecha objetivo">
                  <input type="date" value={due} onChange={(e) => setDue(e.target.value)} required />
                </Field>
                <button type="submit" className="btn btn-primary">
                  Agregar acción
                </button>
              </form>
            )}
          </Card>
        </div>
        <Card title="Línea de tiempo">
          <ul className="timeline">
            {timeline.map((t, i) => (
              <li key={i}>
                <div className="t-when">{fmtDateTime(t.at)}</div>
                <div className="t-what">{t.what}</div>
                {t.detail && <div className="t-detail">{t.detail}</div>}
              </li>
            ))}
          </ul>
          {c.payload && Object.keys(c.payload).length > 0 && (
            <details>
              <summary className="muted small">Payload técnico</summary>
              <pre className="json">{JSON.stringify(c.payload, null, 2)}</pre>
            </details>
          )}
          {c.resolution && (
            <p>
              <Badge tone="green">Resolución</Badge> {c.resolution}
            </p>
          )}
        </Card>
      </div>
    </div>
  );
}
