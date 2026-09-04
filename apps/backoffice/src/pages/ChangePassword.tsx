import { useState, type FormEvent } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { ApiError } from '../api/client';
import { useAuth } from '../state/auth';
import { useToast } from '../components/Toast';
import { Card, Field, PageTitle } from '../components/ui';
import { homeFor } from '../App';

export const MIN_PASSWORD_LENGTH = 8;

/** Cambio de contraseña: obligatorio cuando `must_change_password` (Guard redirige aquí) o voluntario desde el menú de usuario. */
export function ChangePasswordPage() {
  const { user, mustChangePassword, changePassword, logout } = useAuth();
  const nav = useNavigate();
  const loc = useLocation() as { state?: { from?: string } };
  const toast = useToast();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const tooShort = next.length > 0 && next.length < MIN_PASSWORD_LENGTH;
  const mismatch = confirm.length > 0 && confirm !== next;
  const same = next.length > 0 && next === current;
  const canSubmit = !busy && current.length > 0 && next.length >= MIN_PASSWORD_LENGTH && confirm === next && !same;
  const localError = tooShort ? `La nueva contraseña debe tener al menos ${MIN_PASSWORD_LENGTH} caracteres` : same ? 'La nueva contraseña debe ser distinta a la actual' : mismatch ? 'Las contraseñas no coinciden' : null;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    try {
      await changePassword(current, next);
      toast.toast('Contraseña actualizada', 'success');
      if (user) nav(loc.state?.from || homeFor(user.role), { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.code === 'AUTH_INVALID') setError('La contraseña actual es incorrecta');
      else if (err instanceof ApiError && err.code === 'VALIDATION') setError(err.message || `Mínimo ${MIN_PASSWORD_LENGTH} caracteres y distinta a la actual`);
      else setError(err instanceof Error && err.message ? err.message : 'No se pudo cambiar la contraseña');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <PageTitle title="Cambiar contraseña" subtitle={mustChangePassword ? 'Tu contraseña fue restablecida: define una nueva antes de continuar.' : `Cambia la contraseña de ${user?.username ?? 'tu usuario'}.`} />
      <Card className="change-password">
        <form onSubmit={submit} className="stack" style={{ maxWidth: 420 }} data-testid="change-password-form">
          <Field label="Contraseña actual">
            <input type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} required autoFocus />
          </Field>
          <Field label="Contraseña nueva" hint={`Mínimo ${MIN_PASSWORD_LENGTH} caracteres`}>
            <input type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} required minLength={MIN_PASSWORD_LENGTH} />
          </Field>
          <Field label="Confirmar contraseña nueva">
            <input type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required />
          </Field>
          {(error || localError) && (
            <p className="badge badge-red" role="alert" style={{ display: 'block' }}>
              {error ?? localError}
            </p>
          )}
          <div className="row" style={{ justifyContent: 'flex-end' }}>
            {mustChangePassword ? (
              <button type="button" className="btn" disabled={busy} onClick={() => logout().then(() => nav('/login'))}>
                Cerrar sesión
              </button>
            ) : (
              <button type="button" className="btn" disabled={busy} onClick={() => nav(-1)}>
                Cancelar
              </button>
            )}
            <button type="submit" className="btn btn-primary" disabled={!canSubmit}>
              {busy ? 'Guardando…' : 'Guardar contraseña'}
            </button>
          </div>
        </form>
      </Card>
    </div>
  );
}
