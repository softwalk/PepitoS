import { useState, type FormEvent } from 'react';
import { api } from '../api/client';
import { useAuth } from '../state/auth';
import { useToast } from './Toast';
import { Field, Modal } from './ui';
import { Icon } from './icons';

/**
 * "Continuar turno": sólo administrador. Reabre un turno cerrado (POST /v1/shifts/{id}/reopen) con motivo obligatorio.
 * El operador ve el mismo turno abierto al refrescar la app y puede seguir vendiendo; el siguiente cierre concilia todo.
 */
export function ReopenShiftButton({ shiftId, label, onDone, small = true }: { shiftId: string; label: string; onDone: () => void | Promise<void>; small?: boolean }) {
  const { hasRole } = useAuth();
  const [open, setOpen] = useState(false);
  if (!hasRole('admin')) return null;
  return (
    <>
      <button type="button" className={`btn btn-accent ${small ? 'small' : ''}`} onClick={() => setOpen(true)} data-testid={`reopen-shift-${shiftId}`}>
        <Icon name="play" size={13} /> Continuar turno
      </button>
      {open && (
        <ReopenShiftModal
          shiftId={shiftId}
          label={label}
          onClose={() => setOpen(false)}
          onDone={async () => {
            setOpen(false);
            await onDone();
          }}
        />
      )}
    </>
  );
}

export function ReopenShiftModal({ shiftId, label, onClose, onDone }: { shiftId: string; label: string; onClose: () => void; onDone: () => void | Promise<void> }) {
  const toast = useToast();
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (reason.trim().length < 5) return;
    setBusy(true);
    try {
      await api.post(`/v1/shifts/${shiftId}/reopen`, { reason: reason.trim() });
      toast.toast(`Turno reabierto: ${label}. El operador puede seguir vendiendo.`, 'success');
      await onDone();
    } catch (err) {
      toast.error(err, 'No se pudo reabrir el turno');
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal title="Continuar turno terminado" onClose={onClose}>
      <form className="stack" onSubmit={submit} data-testid="reopen-shift-form">
        <p>
          Vas a reabrir el turno de <b>{label}</b>. Se conservan las ventas y el cierre anterior queda en el audit log; el operador verá el puesto abierto y deberá
          volver a cerrar caja al terminar.
        </p>
        <Field label="Motivo (obligatorio)" hint="Queda registrado en el audit log con tu usuario.">
          <textarea value={reason} onChange={(e) => setReason(e.target.value)} minLength={5} maxLength={280} required autoFocus placeholder="Ej. El operador cerró por error a media jornada" />
        </Field>
        <div className="row" style={{ justifyContent: 'flex-end' }}>
          <button type="button" className="btn" onClick={onClose} disabled={busy}>
            Cancelar
          </button>
          <button type="submit" className="btn btn-accent" disabled={busy || reason.trim().length < 5} data-testid="reopen-shift-confirm">
            {busy ? 'Reabriendo…' : 'Reabrir turno'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
