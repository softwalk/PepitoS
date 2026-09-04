import { useState, type FormEvent } from 'react';
import { ApiError, NetworkError } from '../api/client';
import { changePassword, logout, refreshAssignment } from '../state/actions';
import { useApp } from '../state/store';

export const MIN_PASSWORD_LENGTH = 8;

/** Pantalla obligatoria cuando el servidor exige cambiar la contraseña (must_change_password / 403 PASSWORD_CHANGE_REQUIRED). */
export default function ChangePassword() {
  const { session, reload } = useApp();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const tooShort = next.length > 0 && next.length < MIN_PASSWORD_LENGTH;
  const mismatch = confirm.length > 0 && confirm !== next;
  const same = next.length > 0 && next === current;
  const canSubmit = !busy && current.length > 0 && next.length >= MIN_PASSWORD_LENGTH && confirm === next && !same;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    try {
      await changePassword(current, next);
      setDone(true);
      try {
        if (navigator.onLine) await refreshAssignment();
      } catch {
        /* sin red: se usa lo guardado */
      }
      setTimeout(() => void reload(), 1200);
    } catch (err) {
      if (err instanceof NetworkError) setError('No hay señal. Conéctate para cambiar la contraseña.');
      else if (err instanceof ApiError) {
        if (err.code === 'AUTH_INVALID') setError('La contraseña actual es incorrecta');
        else if (err.code === 'VALIDATION') setError(err.message || `La nueva contraseña debe tener al menos ${MIN_PASSWORD_LENGTH} caracteres y ser distinta`);
        else setError(err.message);
      } else setError('No se pudo cambiar. Intenta de nuevo.');
    } finally {
      setBusy(false);
    }
  };

  const exit = async () => {
    setBusy(true);
    await logout({ force: true });
    await reload();
  };

  if (done) {
    return (
      <div className="app">
        <div className="main">
          <div className="result result-green" role="status">
            <div className="ico" aria-hidden>
              ✅
            </div>
            <p className="h1">Contraseña cambiada</p>
            <p className="h2">Ya puedes trabajar</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="app">
      <div className="main" style={{ justifyContent: 'center' }}>
        <div className="center">
          <div className="ico" aria-hidden style={{ fontSize: 48 }}>
            🔒
          </div>
          <h1 className="h1" style={{ marginTop: 8 }}>
            Cambia tu contraseña
          </h1>
          <p className="muted">{session?.user.name ? `${session.user.name}, ` : ''}antes de continuar necesitas una contraseña nueva.</p>
        </div>
        <form className="stack" onSubmit={submit}>
          <label className="stack" style={{ gap: 6 }}>
            <span className="h2">Contraseña actual</span>
            <input className="input" type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} required />
          </label>
          <label className="stack" style={{ gap: 6 }}>
            <span className="h2">Contraseña nueva</span>
            <input className="input" type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} required minLength={MIN_PASSWORD_LENGTH} />
            <span className="muted" style={{ margin: 0 }}>
              Mínimo {MIN_PASSWORD_LENGTH} caracteres
            </span>
          </label>
          <label className="stack" style={{ gap: 6 }}>
            <span className="h2">Repite la nueva</span>
            <input className="input" type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required />
          </label>
          {(tooShort || mismatch || same || error) && (
            <div className="error" role="alert">
              <span aria-hidden>⚠️</span>{' '}
              {error ?? (tooShort ? `Debe tener al menos ${MIN_PASSWORD_LENGTH} caracteres` : same ? 'La nueva debe ser distinta a la actual' : 'Las contraseñas no coinciden')}
            </div>
          )}
          <button className="btn btn-primary" type="submit" disabled={!canSubmit}>
            <span className="ico" aria-hidden>
              🔑
            </span>
            {busy ? 'Guardando…' : 'GUARDAR CONTRASEÑA'}
          </button>
          <button className="btn btn-ghost" type="button" disabled={busy} onClick={exit}>
            Salir
          </button>
        </form>
      </div>
    </div>
  );
}
