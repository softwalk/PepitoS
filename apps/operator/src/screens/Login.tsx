import InsecureBanner from '../components/InsecureBanner';
import { useEffect, useState, type FormEvent } from 'react';
import { ApiError, NetworkError } from '../api/client';
import { GPS_REASON_TEXT, getPositionDetailed } from '../offline/gps';
import { speak } from '../offline/speech';
import { login } from '../state/actions';
import { useApp } from '../state/store';

/** "N minutos" / "mm:ss" para la cuenta regresiva de 429 RATE_LIMITED. */
export function formatWait(seconds: number): string {
  const s = Math.max(0, Math.ceil(seconds));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${String(r).padStart(2, '0')}`;
}

export default function Login() {
  const { reload } = useApp();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lockedUntil, setLockedUntil] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [welcome, setWelcome] = useState<{ name: string; point: string; cart: string; hours: string } | null>(null);
  const [gpsTest, setGpsTest] = useState<'idle' | 'testing' | 'ok' | string>('idle');

  const remaining = lockedUntil ? Math.max(0, Math.ceil((lockedUntil - now) / 1000)) : 0;

  useEffect(() => {
    if (!lockedUntil) return;
    const t = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(t);
  }, [lockedUntil]);

  useEffect(() => {
    if (lockedUntil && remaining === 0) {
      setLockedUntil(null);
      setError(null);
    }
  }, [lockedUntil, remaining]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await login(username.trim(), password);
      if (r.must_change_password) {
        // El servidor exige cambiar la contraseña: la puerta de la app muestra esa pantalla.
        await reload();
        return;
      }
      const a = r.assignment;
      const f = (iso?: string) => (iso ? new Date(iso).toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit', hour12: false }) : '');
      setWelcome({
        name: a?.assignment ? 'Bienvenido' : 'Hola',
        point: a?.assignment?.point.name ?? 'Sin punto asignado hoy',
        cart: a?.assignment?.cart.code ?? '',
        hours: a?.assignment ? `${f(a.assignment.planned_start)}–${f(a.assignment.planned_end)}` : '',
      });
      // Bienvenida con «Probar GPS»: la pantalla se queda hasta que el operador toque Continuar (o 6 s).
      setTimeout(() => void reload(), 6000);
    } catch (err) {
      if (err instanceof NetworkError) setError('No hay señal. Conéctate para iniciar sesión.');
      else if (err instanceof ApiError) {
        if (err.status === 429 || err.code === 'RATE_LIMITED') {
          const secs = err.retryAfterSeconds ?? 60;
          setLockedUntil(Date.now() + secs * 1000);
          setNow(Date.now());
          setError(null);
        } else if (err.code === 'AUTH_INVALID') setError('Usuario o contraseña incorrectos');
        else if (err.code === 'DEVICE_REVOKED') setError('Este teléfono fue dado de baja. Avisa a tu supervisor.');
        else setError(err.message);
      } else setError('No se pudo entrar. Intenta de nuevo.');
    } finally {
      setBusy(false);
    }
  };

  if (welcome) {
    return (
      <div className="app">
        <div className="main">
          <div className="result result-green" role="status">
            <img src="/mark.png" alt="" aria-hidden className="mascot" width={120} height={120} />
            <p className="h1">{welcome.name}</p>
            <p className="h2">
              <span aria-hidden>📍</span> {welcome.point}
            </p>
            {welcome.cart && (
              <div className="welcome-facts" data-testid="welcome-facts">
                <div className="fact"><div className="k">Punto</div><div className="v">{welcome.point}</div></div>
                <div className="fact"><div className="k">Carrito</div><div className="v">{welcome.cart}</div></div>
                <div className="fact"><div className="k">Horario</div><div className="v">{welcome.hours}</div></div>
              </div>
            )}
            <button
              type="button"
              className="btn btn-outline"
              data-testid="welcome-gps"
              disabled={gpsTest === 'testing'}
              onClick={async () => {
                setGpsTest('testing');
                const g = await getPositionDetailed(15000);
                const text = g.gps ? 'ok' : GPS_REASON_TEXT[g.reason ?? 'unavailable'].title;
                setGpsTest(text);
                speak(g.gps ? 'Ubicación correcta' : text, true);
              }}
            >
              <span className="ico" aria-hidden>
                📡
              </span>
              {gpsTest === 'testing' ? 'Probando GPS…' : gpsTest === 'ok' ? '✓ GPS listo' : gpsTest === 'idle' ? 'Probar GPS' : `⚠️ ${gpsTest}`}
            </button>
            <button type="button" className="btn btn-primary" onClick={() => void reload()}>
              Continuar
            </button>
          </div>
        </div>
      </div>
    );
  }

  const locked = remaining > 0;
  const minutes = Math.max(1, Math.ceil(remaining / 60));

  return (
    <div className="app">
      <InsecureBanner />
      <div className="main" style={{ justifyContent: 'center' }}>
        <div className="login-brand">
          <img src="/logo.png" alt="PEPITO · Pepitas recién doradas al comal" className="logo" width={220} height={240} />
          <h1 className="sr">PEPITO OS</h1>
          <span className="tag">Operador</span>
        </div>
        <form className="stack" onSubmit={submit}>
          <label className="stack" style={{ gap: 6 }}>
            <span className="field-label">Usuario</span>
            <input className="input" autoComplete="username" autoCapitalize="none" value={username} onChange={(e) => setUsername(e.target.value)} required />
          </label>
          <label className="stack" style={{ gap: 6 }}>
            <span className="field-label">Contraseña</span>
            <input className="input" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </label>
          {locked && (
            <div className="error" role="alert" data-testid="rate-limited">
              <span aria-hidden>⏳</span> Demasiados intentos. Espera {minutes} {minutes === 1 ? 'minuto' : 'minutos'} ({formatWait(remaining)})
            </div>
          )}
          {error && !locked && (
            <div className="error" role="alert">
              <span aria-hidden>⚠️</span> {error}
            </div>
          )}
          <button className="btn btn-primary" type="submit" disabled={busy || locked || !username || !password}>
            <span className="ico" aria-hidden>
              🔑
            </span>
            {busy ? 'Entrando…' : locked ? `Espera ${formatWait(remaining)}` : 'ENTRAR'}
          </button>
        </form>
      </div>
    </div>
  );
}
