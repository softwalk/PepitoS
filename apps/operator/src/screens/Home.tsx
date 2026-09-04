import { useNavigate } from 'react-router-dom';
import { countsAsSale } from '../offline/expected';
import { money, shiftIsOpen, useApp } from '../state/store';

function fmtTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleTimeString('es-MX', { hour: 'numeric', minute: '2-digit' });
}

/** Tarjeta de estado del turno: qué está pasando ahora, en una línea. */
function ShiftCard() {
  const { shift, assignment, sales } = useApp();
  const open = shiftIsOpen(shift);
  const a = assignment?.assignment;
  if (open && shift) {
    const active = sales.filter(countsAsSale);
    const count = active.length + (shift.server_sales?.count ?? 0);
    const total = active.reduce((s, x) => s + x.total_cents, 0) + (shift.server_sales?.total_cents ?? 0);
    const pending = shift.status === 'open_pending';
    return (
      <div className={`shift-card ${pending ? 'is-pending' : 'is-open'}`} role="status">
        <div className="icon" aria-hidden>
          {pending ? '⏳' : '🟢'}
        </div>
        <div>
          <div className="t">{pending ? 'Abierto, pendiente de enviar' : 'Puesto abierto'}</div>
          <div className="s">Desde {fmtTime(shift.opened_at)}{pending ? ' · se enviará con señal' : ''}</div>
        </div>
        <div className="stat">
          <b>{money(total)}</b>
          <span>
            {count} {count === 1 ? 'venta' : 'ventas'}
          </span>
        </div>
      </div>
    );
  }
  if (a?.status === 'done') {
    return (
      <div className="shift-card" role="status">
        <div className="icon" aria-hidden>
          ✅
        </div>
        <div>
          <div className="t">Turno de hoy terminado</div>
          <div className="s">Buen trabajo. Hasta mañana.</div>
        </div>
      </div>
    );
  }
  if (!a) {
    return (
      <div className="exception" role="status">
        <span className="ico" aria-hidden>
          📅
        </span>
        <div>
          <b>No tienes punto asignado hoy</b>
          Avisa a tu supervisor.
        </div>
      </div>
    );
  }
  return (
    <div className="shift-card" role="status">
      <div className="icon" aria-hidden>
        🔒
      </div>
      <div>
        <div className="t">Puesto cerrado</div>
        <div className="s">
          Turno {fmtTime(a.planned_start)} – {fmtTime(a.planned_end)}
        </div>
      </div>
    </div>
  );
}

export default function Home() {
  const nav = useNavigate();
  const { shift, assignment } = useApp();
  const open = shiftIsOpen(shift);
  const closing = shift?.status === 'closing' || shift?.status === 'closed';
  const hasAssignment = !!assignment?.assignment;
  const assignmentDone = assignment?.assignment?.status === 'done';
  const canOpen = !open && !closing && hasAssignment && !assignmentDone;

  // Una acción principal por estado: cerrado → ABRIR; abierto → VENDER. El resto queda debajo, siempre visible.
  const openBtn = (
    <button className={`btn btn-green btn-huge ${!open ? 'home-hero' : ''}`} disabled={!canOpen} onClick={() => nav('/abrir')}>
      <span className="ico" aria-hidden>
        🔓
      </span>
      ABRIR PUESTO
      {!canOpen && !open && <span className="btn-hint">{assignmentDone ? 'Turno terminado' : 'Sin asignación'}</span>}
    </button>
  );
  const sellBtn = (
    <button className={`btn btn-primary btn-huge ${open ? 'home-hero' : ''}`} disabled={!open} onClick={() => nav('/vender')}>
      <span className="ico" aria-hidden>
        🛍️
      </span>
      VENDER
      {!open && <span className="btn-hint">Abre el puesto primero</span>}
    </button>
  );

  return (
    <>
      <ShiftCard />
      <div className="home-grid">
        {open ? sellBtn : openBtn}
        <div className="btn-row">
          <button className="btn btn-blue btn-huge" onClick={() => nav('/ayuda')}>
            <span className="ico" aria-hidden>
              🆘
            </span>
            NECESITO AYUDA
          </button>
          <button className="btn btn-amber btn-huge" disabled={!open} onClick={() => nav('/cerrar')}>
            <span className="ico" aria-hidden>
              🔒
            </span>
            CERRAR PUESTO
          </button>
        </div>
        {!open && sellBtn}
      </div>
    </>
  );
}
