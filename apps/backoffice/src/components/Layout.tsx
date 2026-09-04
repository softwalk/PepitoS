import { useEffect, useState } from 'react';
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../state/auth';
import type { Role } from '../types';
import { Icon, type IconName } from './icons';

interface NavItem { to: string; label: string; icon: IconName; roles: Role[]; mobile?: boolean; group: string }

/** Navegación agrupada por intención: monitorear → actuar en campo → negocio → sistema. */
const NAV: NavItem[] = [
  { group: 'Monitoreo', to: '/ct', label: 'Control Tower', icon: 'tower', roles: ['ops', 'finance', 'admin'] },
  { group: 'Monitoreo', to: '/ct/briefing', label: 'Briefing', icon: 'briefing', roles: ['ops', 'finance', 'admin'] },
  { group: 'Monitoreo', to: '/excepciones', label: 'Excepciones', icon: 'flag', roles: ['ops', 'finance', 'admin', 'supervisor'], mobile: true },
  { group: 'Campo', to: '/supervisor', label: 'Supervisor', icon: 'bolt', roles: ['supervisor', 'ops', 'admin'], mobile: true },
  { group: 'Campo', to: '/supervisor/ruta', label: 'Ruta', icon: 'route', roles: ['supervisor', 'ops', 'admin'], mobile: true },
  { group: 'Negocio', to: '/ventas', label: 'Ventas', icon: 'sales', roles: ['ops', 'finance', 'admin', 'supervisor'] },
  { group: 'Negocio', to: '/inventario', label: 'Inventario', icon: 'inventory', roles: ['ops', 'admin', 'supervisor'], mobile: true },
  { group: 'Negocio', to: '/personas', label: 'Personas', icon: 'people', roles: ['ops', 'admin', 'supervisor'] },
  { group: 'Negocio', to: '/activos', label: 'Activos', icon: 'assets', roles: ['ops', 'admin'] },
  { group: 'Sistema', to: '/reglas', label: 'Reglas', icon: 'rules', roles: ['ops', 'admin'] },
  { group: 'Sistema', to: '/aprobaciones', label: 'Aprobaciones', icon: 'approvals', roles: ['ops', 'finance', 'admin'] },
  { group: 'Sistema', to: '/auditoria', label: 'Audit log', icon: 'log', roles: ['ops', 'finance', 'admin'] },
  { group: 'Sistema', to: '/admin', label: 'Administración', icon: 'admin', roles: ['admin', 'ops', 'finance'] },
];

export const ROLE_LABEL: Record<Role, string> = { operator: 'Operador', supervisor: 'Supervisor', ops: 'Operaciones', finance: 'Finanzas', admin: 'Administrador' };

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? '')
    .join('');
}

export function Layout() {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const [drawer, setDrawer] = useState(false);
  useEffect(() => setDrawer(false), [loc.pathname]);
  useEffect(() => {
    if (!drawer) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setDrawer(false);
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [drawer]);
  // En móvil (≤768 px) el sidebar cerrado no debe ser alcanzable por teclado ni por lectores de pantalla.
  const [isMobile, setIsMobile] = useState(() => typeof window !== 'undefined' && window.matchMedia?.('(max-width: 768px)').matches);
  useEffect(() => {
    const mq = window.matchMedia?.('(max-width: 768px)');
    if (!mq) return;
    const onChange = () => setIsMobile(mq.matches);
    mq.addEventListener?.('change', onChange);
    return () => mq.removeEventListener?.('change', onChange);
  }, []);
  if (!user) return null;
  const items = NAV.filter((n) => n.roles.includes(user.role));
  const mobileItems = user.role === 'supervisor' ? items.filter((n) => n.mobile) : items.slice(0, 4);
  const groups = Array.from(new Set(items.map((n) => n.group)));
  const doLogout = async () => {
    await logout();
    nav('/login');
  };
  const isEnd = (to: string) => to === '/ct' || to === '/supervisor';

  return (
    <div className="shell">
      <aside id="sidebar" className={`sidebar ${drawer ? 'open' : ''}`} aria-hidden={isMobile && !drawer ? true : undefined} {...(isMobile && !drawer ? { inert: '' } : {})}>
        <div className="brand">
          <span className="brand-mark">P</span>
          <div>
            <div className="brand-name">PEPITO OS</div>
            <div className="brand-sub">Backoffice</div>
          </div>
        </div>
        <nav className="side-nav" aria-label="Principal">
          {groups.map((g) => (
            <div key={g} className="nav-group">
              <div className="nav-group-title">{g}</div>
              {items
                .filter((n) => n.group === g)
                .map((n) => (
                  <NavLink key={n.to} to={n.to} end={isEnd(n.to)} className={({ isActive }) => (isActive ? 'active' : '')}>
                    <span className="nav-icon">
                      <Icon name={n.icon} />
                    </span>
                    {n.label}
                  </NavLink>
                ))}
            </div>
          ))}
        </nav>
        <div className="side-user">
          <div className="side-user-row">
            <span className="avatar" aria-hidden>
              {initials(user.name)}
            </span>
            <div className="side-user-meta">
              <div className="side-user-name">{user.name}</div>
              <div className="muted small">{ROLE_LABEL[user.role]}</div>
            </div>
          </div>
          <div className="side-user-actions">
            <Link to="/cambiar-contrasena" className="btn btn-ghost small" title="Cambiar contraseña">
              <Icon name="key" size={15} /> Cambiar contraseña
            </Link>
            <button type="button" className="btn btn-ghost small" onClick={doLogout}>
              <Icon name="logout" size={15} /> Cerrar sesión
            </button>
          </div>
        </div>
      </aside>
      {drawer && <div className="drawer-backdrop" onClick={() => setDrawer(false)} aria-hidden />}
      <div className="content">
        <header className="topbar">
          <button type="button" className="btn btn-ghost icon-btn" aria-label="Menú" aria-expanded={drawer} aria-controls="sidebar" onClick={() => setDrawer((v) => !v)}>
            <Icon name="menu" />
          </button>
          <span className="brand-name">PEPITO OS</span>
          <span className="muted small topbar-user">
            {user.name} · {ROLE_LABEL[user.role]}
          </span>
          <button type="button" className="btn btn-ghost small" onClick={doLogout}>
            Salir
          </button>
        </header>
        <main className="main">
          <Outlet />
        </main>
        <nav className="bottom-nav" aria-label="Principal (móvil)">
          {mobileItems.map((n) => (
            <NavLink key={n.to} to={n.to} end={isEnd(n.to)} className={({ isActive }) => (isActive ? 'active' : '')}>
              <span className="nav-icon">
                <Icon name={n.icon} size={22} />
              </span>
              <span>{n.label}</span>
            </NavLink>
          ))}
        </nav>
      </div>
    </div>
  );
}
