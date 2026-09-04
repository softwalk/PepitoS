import { useNavigate } from 'react-router-dom';
import { shiftIsOpen, useApp } from '../state/store';

export default function Home() {
  const nav = useNavigate();
  const { shift, assignment } = useApp();
  const open = shiftIsOpen(shift);
  const closing = shift?.status === 'closing' || shift?.status === 'closed';
  const hasAssignment = !!assignment?.assignment;
  const assignmentDone = assignment?.assignment?.status === 'done';
  const canOpen = !open && !closing && hasAssignment && !assignmentDone;

  return (
    <>
      {!hasAssignment && !open && (
        <div className="exception" role="status">
          <span className="ico" aria-hidden>
            📅
          </span>
          <div>
            <b>No tienes punto asignado hoy</b>
            Avisa a tu supervisor.
          </div>
        </div>
      )}
      {assignmentDone && !open && (
        <div className="card center">
          <p className="h2">
            <span aria-hidden>✅</span> Turno de hoy terminado
          </p>
        </div>
      )}
      {shift?.status === 'open_pending' && (
        <div className="exception" role="status">
          <span className="ico" aria-hidden>
            ⏳
          </span>
          <div>
            <b>Puesto abierto, pendiente de enviar</b>
            Puedes vender. Se enviará cuando haya señal.
          </div>
        </div>
      )}
      <div className="home-grid">
        <button className="btn btn-green btn-huge" disabled={!canOpen} onClick={() => nav('/abrir')}>
          <span className="ico" aria-hidden>
            🔓
          </span>
          ABRIR PUESTO
        </button>
        <button className="btn btn-primary btn-huge" disabled={!open} onClick={() => nav('/vender')}>
          <span className="ico" aria-hidden>
            🛍️
          </span>
          VENDER
        </button>
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
    </>
  );
}
