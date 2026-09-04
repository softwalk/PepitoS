import { useState, type FormEvent } from 'react';
import { ApiError, NetworkError } from '../api/client';
import { login } from '../state/actions';
import { useApp } from '../state/store';

export default function Login() {
  const { reload } = useApp();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [welcome, setWelcome] = useState<{ name: string; point: string; cart: string } | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const a = await login(username.trim(), password);
      setWelcome({
        name: a.assignment ? 'Bienvenido' : 'Hola',
        point: a.assignment?.point.name ?? 'Sin punto asignado hoy',
        cart: a.assignment?.cart.code ?? '',
      });
      setTimeout(() => void reload(), 1500);
    } catch (err) {
      if (err instanceof NetworkError) setError('No hay señal. Conéctate para iniciar sesión.');
      else if (err instanceof ApiError) setError(err.code === 'AUTH_INVALID' ? 'Usuario o contraseña incorrectos' : err.message);
      else setError('No se pudo entrar. Intenta de nuevo.');
    } finally {
      setBusy(false);
    }
  };

  if (welcome) {
    return (
      <div className="app">
        <div className="main">
          <div className="result result-green" role="status">
            <div className="ico" aria-hidden>
              👋
            </div>
            <p className="h1">{welcome.name}</p>
            <p className="h2">
              <span aria-hidden>📍</span> {welcome.point}
            </p>
            {welcome.cart && (
              <p className="h2">
                <span aria-hidden>🛒</span> Carrito {welcome.cart}
              </p>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="app">
      <div className="main" style={{ justifyContent: 'center' }}>
        <div className="center">
          <img src="/icons/icon-192.png" alt="" width={88} height={88} style={{ borderRadius: 22 }} />
          <h1 className="h1" style={{ marginTop: 8 }}>
            PEPITO OS
          </h1>
          <p className="muted">Operador</p>
        </div>
        <form className="stack" onSubmit={submit}>
          <label className="stack" style={{ gap: 6 }}>
            <span className="h2">Usuario</span>
            <input className="input" autoComplete="username" autoCapitalize="none" value={username} onChange={(e) => setUsername(e.target.value)} required />
          </label>
          <label className="stack" style={{ gap: 6 }}>
            <span className="h2">Contraseña</span>
            <input className="input" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </label>
          {error && (
            <div className="error" role="alert">
              <span aria-hidden>⚠️</span> {error}
            </div>
          )}
          <button className="btn btn-primary" type="submit" disabled={busy || !username || !password}>
            <span className="ico" aria-hidden>
              🔑
            </span>
            {busy ? 'Entrando…' : 'ENTRAR'}
          </button>
        </form>
      </div>
    </div>
  );
}
