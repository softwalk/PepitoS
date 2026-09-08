import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { LIGHT_LABEL, SEVERITY_LABEL, STATUS_LABEL, label, type Light } from '../lib/format';
import type { Severity } from '../types';

export function Badge({ tone, children, title }: { tone: string; children: ReactNode; title?: string }) {
  return (
    <span className={`badge badge-${tone}`} title={title}>
      {children}
    </span>
  );
}

const STATUS_TONE: Record<string, string> = {
  open: 'green',
  late: 'amber',
  offline: 'gray',
  closed: 'blue',
  not_scheduled: 'light',
  in_progress: 'blue',
  resolved: 'green',
  pending: 'amber',
  done: 'green',
  overdue: 'red',
  approved: 'green',
  rejected: 'red',
  cancelled: 'gray',
  started: 'blue',
  planned: 'light',
  reconciled: 'green',
  difference: 'red',
  ok: 'green',
  warn: 'amber',
  low: 'amber',
  critical: 'red',
  present: 'green',
  absent: 'red',
  active: 'green',
  blocked: 'red',
  transferred: 'blue',
};

export function StatusBadge({ status }: { status: string | null | undefined }) {
  if (!status) return <span className="muted">—</span>;
  return <Badge tone={STATUS_TONE[status] ?? 'gray'}>{label(STATUS_LABEL, status)}</Badge>;
}

const SEV_TONE: Record<Severity, string> = { urgent: 'red', review: 'amber', normal: 'green' };
export function SeverityBadge({ severity }: { severity: Severity }) {
  return <Badge tone={SEV_TONE[severity] ?? 'gray'}>{SEVERITY_LABEL[severity] ?? severity}</Badge>;
}

export function LightDot({ light, text }: { light: Light; text?: string }) {
  return (
    <span className={`light light-${light}`} title={LIGHT_LABEL[light]}>
      <span className="light-dot" />
      {text ?? LIGHT_LABEL[light]}
    </span>
  );
}

export function Card({ title, children, actions, className = '', testId }: { title?: ReactNode; children: ReactNode; actions?: ReactNode; className?: string; testId?: string }) {
  return (
    <section className={`card ${className}`} data-testid={testId}>
      {(title || actions) && (
        <header className="card-head">
          {title && <h2>{title}</h2>}
          {actions && <div className="card-actions">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

export function Empty({ text = 'Sin datos' }: { text?: string }) {
  return <p className="empty">{text}</p>;
}

export function Loading() {
  return <p className="loading">Cargando…</p>;
}

export function PageTitle({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="page-title">
      <div>
        <h1>{title}</h1>
        {subtitle && <p className="muted">{subtitle}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </div>
  );
}

export function CaseLink({ id, children }: { id: string; children: ReactNode }) {
  return <Link to={`/casos/${id}`}>{children}</Link>;
}

export function Modal({ title, onClose, children, className = '' }: { title: string; onClose: () => void; children: ReactNode; className?: string }) {
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className={`modal ${className}`} role="dialog" aria-modal="true" aria-label={title} onClick={(e) => e.stopPropagation()}>
        <header className="modal-head">
          <h3>{title}</h3>
          <button type="button" className="btn btn-ghost" onClick={onClose} aria-label="Cerrar">
            ×
          </button>
        </header>
        {children}
      </div>
    </div>
  );
}

export function Field({ label: text, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="field">
      <span className="field-label">{text}</span>
      {children}
      {hint && <span className="field-hint">{hint}</span>}
    </label>
  );
}


/** Tarjeta de indicador unificada: nombre · cifra · unidad · comparativo/sub · semáforo (misma en Control Tower,
 *  Ventas, Inventario y Reportes). */
export function Kpi({ label, value, unit, sub, tone, wide, children, testId }: { label: string; value?: ReactNode; unit?: string; sub?: ReactNode; tone?: Light | null; wide?: boolean; children?: ReactNode; testId?: string }) {
  return (
    <div className={`kpi ${tone ? `tone-${tone}` : ''} ${wide ? 'kpi-wide' : ''}`} data-testid={testId ?? `kpi-${label}`}>
      <div className="kpi-label">
        <span>{label}</span>
        {tone && <LightDot light={tone} text="" />}
      </div>
      {value !== undefined && (
        <div className="kpi-value">
          {value}
          {unit && <span className="kpi-unit"> {unit}</span>}
        </div>
      )}
      {sub && <div className="kpi-sub">{sub}</div>}
      {children}
    </div>
  );
}


/** SLA de un caso: tiempo restante para tomarlo o «vencido». */
export function SlaChip({ sla }: { sla?: { remaining_min: number | null; breached: boolean; taken: boolean; minutes: number | null } | null }) {
  if (!sla || sla.minutes == null) return null;
  if (sla.taken && !sla.breached) return <Badge tone="green" title="Caso tomado dentro del SLA">SLA ok</Badge>;
  if (sla.breached) return <Badge tone="red" title="SLA vencido: escalado a Operaciones">SLA vencido</Badge>;
  const m = sla.remaining_min ?? 0;
  const txt = m >= 60 ? `${Math.floor(m / 60)} h ${m % 60} min` : `${m} min`;
  return <Badge tone={m <= Math.max(5, sla.minutes * 0.25) ? 'amber' : 'blue'} title={`Tomar antes de ${sla.minutes} min`}><span className="sla-chip">SLA {txt}</span></Badge>;
}
