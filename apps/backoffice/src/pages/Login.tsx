import { useEffect, useState, type FormEvent } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { ApiError } from '../api/client';
import { useAuth } from '../state/auth';
import { useToast } from '../components/Toast';
import { homeFor } from '../App';

/** mm:ss para la cuenta regresiva de 429 RATE_LIMITED. */
export function formatWait(seconds: number): string {
  const s = Math.max(0, Math.ceil(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

export function LoginPage() {
  const { user, mustChangePassword, login } = useAuth();
  const nav = useNavigate();
  const loc = useLocation() as { state?: { from?: string } };
  const toast = useToast();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [lockedUntil, setLockedUntil] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());

  const remaining = lockedUntil ? Math.max(0, Math.ceil((lockedUntil - now) / 1000)) : 0;
  const locked = remaining > 0;

  useEffect(() => {
    if (!lockedUntil) return;
    const t = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(t);
  }, [lockedUntil]);
  useEffect(() => {
    if (lockedUntil && remaining === 0) setLockedUntil(null);
  }, [lockedUntil, remaining]);

  if (user && user.role !== 'operator') {
    if (mustChangePassword) return <Navigate to="/cambiar-contrasena" replace />;
    return <Navigate to={loc.state?.from || homeFor(user.role)} replace />;
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const res = await login(username.trim(), password);
      const u = res.user;
      if (u.role === 'operator') {
        toast.toast('Este acceso es para supervisores y backoffice. Usa la app de operador.', 'error');
        return;
      }
      if (res.must_change_password) {
        nav('/cambiar-contrasena', { replace: true, state: { from: loc.state?.from } });
        return;
      }
      nav(loc.state?.from || homeFor(u.role), { replace: true });
    } catch (err) {
      if (err instanceof ApiError && (err.status === 429 || err.code === 'RATE_LIMITED')) {
        setLockedUntil(Date.now() + (err.retryAfterSeconds ?? 60) * 1000);
        setNow(Date.now());
      } else if (err instanceof ApiError && err.code === 'AUTH_INVALID') toast.toast('Usuario o contraseña incorrectos', 'error');
      else toast.error(err, 'No se pudo iniciar sesión');
    } finally {
      setBusy(false);
    }
  };

  const minutes = Math.max(1, Math.ceil(remaining / 60));

  return (
    <div className="login-wrap">
      <form className="login-card" onSubmit={submit}>
        <div className="brand">
          <span className="brand-mark">P</span>
          <div>
            <div className="brand-name">PEPITO OS</div>
            <div className="brand-sub">Control Tower · Supervisor</div>
          </div>
        </div>
        <label className="field">
          <span className="field-label">Usuario</span>
          <input autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required autoFocus />
        </label>
        <label className="field">
          <span className="field-label">Contraseña</span>
          <input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </label>
        {locked && (
          <p className="badge badge-amber" role="alert" data-testid="rate-limited" style={{ display: 'block', textAlign: 'center' }}>
            Demasiados intentos. Espera {minutes} {minutes === 1 ? 'minuto' : 'minutos'} ({formatWait(remaining)})
          </p>
        )}
        <button type="submit" className="btn btn-primary btn-block" disabled={busy || locked}>
          {busy ? 'Entrando…' : locked ? `Espera ${formatWait(remaining)}` : 'Entrar'}
        </button>
        <p className="muted small">Demo: ops/ops123 · finanzas/fin123 · sup1/sup123 · admin/admin123</p>
      </form>
    </div>
  );
}
