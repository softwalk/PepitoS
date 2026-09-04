import type { ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useApp } from '../state/store';

function SyncPill() {
  const { sync } = useApp();
  if (sync.visible === 'help') {
    return (
      <span className="pill pill-red" role="status">
        <span aria-hidden>⚠️</span> Requiere ayuda
      </span>
    );
  }
  if (sync.visible === 'pending') {
    return (
      <span className="pill pill-amber" role="status">
        <span aria-hidden>⏳</span> Pendiente de enviar ({sync.pending})
      </span>
    );
  }
  return (
    <span className="pill pill-green" role="status">
      <span aria-hidden>✓</span> Guardado
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
  return (
    <div className="app">
      <header className="topbar">
        <div className="topbar-row">
          <div className="point" title={point}>
            <span aria-hidden>📍</span> {point}
          </div>
          <div className="cart">
            {cart && (
              <>
                <img src="/icon-cart.png" alt="" aria-hidden className="icon-img icon-inline" /> {cart}
              </>
            )}
          </div>
        </div>
        <div className="topbar-row">
          <div className="row">
            <SyncPill />
            {!sync.online && (
              <span className="pill pill-gray">
                <span aria-hidden>📴</span> Sin señal
              </span>
            )}
          </div>
          <div className="row">
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
