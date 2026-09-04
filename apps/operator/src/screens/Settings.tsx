import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { retryFailed } from '../offline/queue';
import { speak } from '../offline/speech';
import { refreshCounts, syncNow } from '../offline/sync';
import { logout } from '../state/actions';
import { useApp } from '../state/store';

export default function Settings() {
  const nav = useNavigate();
  const { session, sync, settings, setSettings, clearSession } = useApp();
  const [busy, setBusy] = useState(false);
  const [confirmForce, setConfirmForce] = useState(false);
  const total = sync.pending + sync.failed;

  const retry = async () => {
    setBusy(true);
    await retryFailed();
    await refreshCounts();
    await syncNow();
    setBusy(false);
  };

  const doLogout = async (force = false) => {
    setBusy(true);
    const r = await logout({ force });
    setBusy(false);
    if ('blocked' in r) {
      setConfirmForce(true);
      return;
    }
    await clearSession();
    nav('/', { replace: true });
  };

  return (
    <div className="stack">
      <h1 className="h1">Ajustes</h1>
      <div className="card settings-user">
        <div className="avatar" aria-hidden>
          {(session?.user.name ?? '?').trim().charAt(0).toUpperCase()}
        </div>
        <div>
          <p className="h2">{session?.user.name}</p>
          <p className="muted" style={{ margin: 0 }}>
            Usuario: {session?.user.username ?? '—'}
          </p>
        </div>
      </div>

      <div className="card stack">
        <div className="row between">
          <span className="h2">Por enviar</span>
          <span className={`pill ${sync.failed > 0 ? 'pill-red' : total > 0 ? 'pill-amber' : 'pill-green'}`}>{total === 0 ? 'Todo enviado ✓' : `${total} pendiente${total === 1 ? '' : 's'}`}</span>
        </div>
        {sync.failed > 0 && <p className="muted">Hay {sync.failed} que no se pudieron enviar. Avisa a tu supervisor si persiste.</p>}
        <button className="btn btn-outline" disabled={busy || total === 0} onClick={retry}>
          <span className="ico" aria-hidden>
            🔄
          </span>
          {sync.syncing ? 'Enviando…' : 'Reintentar enviar'}
        </button>
      </div>

      <div className="card stack">
        <button type="button" className="switch-row" onClick={() => setSettings({ audio: !settings.audio }).then(() => speak('Audio activado', !settings.audio))} aria-pressed={settings.audio}>
          <span className="h2">
            <span aria-hidden>🔊</span> Leer instrucciones en voz alta
          </span>
          <span className={`switch ${settings.audio ? 'on' : ''}`} aria-hidden />
        </button>
        <button type="button" className="switch-row" onClick={() => setSettings({ large_text: !settings.large_text })} aria-pressed={settings.large_text}>
          <span className="h2">
            <span aria-hidden>🔠</span> Texto más grande
          </span>
          <span className={`switch ${settings.large_text ? 'on' : ''}`} aria-hidden />
        </button>
      </div>

      {confirmForce ? (
        <div className="exception">
          <span className="ico" aria-hidden>
            ⚠️
          </span>
          <div className="stack">
            <b>Hay {total} registro(s) sin enviar. Si sales ahora se perderán.</b>
            <button className="btn btn-red" disabled={busy} onClick={() => doLogout(true)}>
              Salir de todos modos
            </button>
            <button className="btn btn-ghost" onClick={() => setConfirmForce(false)}>
              Mejor no
            </button>
          </div>
        </div>
      ) : (
        <button className="btn btn-outline" disabled={busy} onClick={() => doLogout(false)}>
          <span className="ico" aria-hidden>
            🚪
          </span>
          Cerrar sesión
        </button>
      )}
      <button className="btn btn-ghost" onClick={() => nav('/')}>
        Volver
      </button>
      <p className="muted center" style={{ fontSize: '0.8em' }}>
        PEPITO OS Operador v{__APP_VERSION__}
      </p>
    </div>
  );
}
