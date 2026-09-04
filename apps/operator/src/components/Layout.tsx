import type { ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useApp } from '../state/store';

/** Estado de sincronía: texto + color; el fondo de la tira de estado sigue este mismo estado. */
function SyncPill() {
  const { sync } = useApp();
  if (sync.visible === 'help') {
    return (
      <span className="pill pill-red" role="status">
        <span className="dot" aria-hidden /> Requiere ayuda
      </span>
    );
  }
  if (sync.visible === 'pending') {
    return (
      <span className="pill pill-amber" role="status">
        <span className="dot" aria-hidden /> Pendiente de enviar ({sync.pending})
      </span>
    );
  }
  return (
    <span className="pill pill-green" role="status">
      <span aria-hidden>✓</span> Guardado
    </span>
  );
}

/** GPS: verde con fix reciente, rojo con motivo si falló (toca para ver qué hacer en Ajustes). */
function GpsPill() {
  const { gps, shift } = useApp();
  const open = shift?.status === 'open' || shift?.status === 'open_pending';
  if (!open && !gps.reason) return null;
  if (gps.reason) {
    return (
      <Link to="/ajustes" className="pill pill-red" aria-label="Problema con la ubicación: ver Ajustes" title={gps.reason}>
        <span aria-hidden>📡</span> Sin GPS
      </Link>
    );
  }
  const fresh = gps.last && Date.now() - new Date(gps.last.at).getTime() < 5 * 60_000;
  return (
    <span className={`pill ${fresh ? 'pill-green' : 'pill-gray'}`} aria-label={fresh ? 'Ubicación activa' : 'Ubicación pendiente'}>
      <span aria-hidden>📡</span>
    </span>
  );
}

function BatteryPill() {
  const { battery } = useApp();
  if (!battery) return null;
  const cls = battery.pct <= 10 ? 'pill-red' : battery.pct <= 25 ? 'pill-amber' : 'pill-gray';
  return (
    <span className={`pill ${cls}`} aria-label={`Batería ${battery.pct}%`}>
      <span aria-hidden>{battery.charging ? '🔌' : '🔋'}</span> {battery.pct}%
    </span>
  );
}

export default function Layout({ children }: { children: ReactNode }) {
  const { assignment, shift, sync } = useApp();
  const loc = useLocation();
  const point = shift?.point_name || assignment?.assignment?.point.name || 'Sin punto asignado';
  const cart = shift?.cart_code || assignment?.assignment?.cart.code || '';
  const stripState = !sync.online ? 'is-offline' : sync.visible === 'help' ? 'is-help' : sync.visible === 'pending' ? 'is-pending' : '';
  return (
    <div className="app">
      <header className="topbar">
        <div className="topbar-row">
          <img src="/mark.png" alt="PEPITO" className="topbar-logo" width={36} height={36} />
          <div className="point" title={point}>
            <span aria-hidden>📍</span>
            <span>{point}</span>
          </div>
          {cart && (
            <div className="cart">
              <img src="/icon-cart.png" alt="" aria-hidden className="icon-img icon-inline" /> {cart}
            </div>
          )}
        </div>
        <div className={`status-strip ${stripState}`}>
          <div className="row">
            <SyncPill />
            {!sync.online && (
              <span className="pill pill-gray">
                <span aria-hidden>📴</span> Sin señal
              </span>
            )}
          </div>
          <div className="row">
            <GpsPill />
            <BatteryPill />
            {loc.pathname !== '/ajustes' ? (
              <Link to="/ajustes" className="pill pill-gray" aria-label="Ajustes">
                <span aria-hidden>⚙️</span>
              </Link>
            ) : (
              <Link to="/" className="pill pill-gray" aria-label="Inicio">
                <span aria-hidden>🏠</span>
              </Link>
            )}
          </div>
        </div>
      </header>
      <main className="main">{children}</main>
    </div>
  );
}
