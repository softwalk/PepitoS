import { useState, type FormEvent } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../state/auth';
import { useToast } from '../components/Toast';
import { homeFor } from '../App';

export function LoginPage() {
  const { user, login } = useAuth();
  const nav = useNavigate();
  const loc = useLocation() as { state?: { from?: string } };
  const toast = useToast();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);

  if (user && user.role !== 'operator') return <Navigate to={loc.state?.from || homeFor(user.role)} replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const u = await login(username.trim(), password);
      if (u.role === 'operator') {
        toast.toast('Este acceso es para supervisores y backoffice. Usa la app de operador.', 'error');
        return;
      }
      nav(loc.state?.from || homeFor(u.role), { replace: true });
    } catch (err) {
      toast.error(err, 'No se pudo iniciar sesión');
    } finally {
      setBusy(false);
    }
  };

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
        <button type="submit" className="btn btn-primary btn-block" disabled={busy}>
          {busy ? 'Entrando…' : 'Entrar'}
        </button>
        <p className="muted small">Demo: ops/ops123 · finanzas/fin123 · sup1/sup123 · admin/admin123</p>
      </form>
    </div>
  );
}
