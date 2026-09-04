import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '../state/auth';
import type { Role } from '../types';

interface NavItem { to: string; label: string; icon: string; roles: Role[]; mobile?: boolean }

const NAV: NavItem[] = [
  { to: '/ct', label: 'Control Tower', icon: '◎', roles: ['ops', 'finance', 'admin'] },
  { to: '/ct/briefing', label: 'Briefing', icon: '☰', roles: ['ops', 'finance', 'admin'] },
  { to: '/excepciones', label: 'Excepciones', icon: '⚑', roles: ['ops', 'finance', 'admin', 'supervisor'], mobile: true },
  { to: '/supervisor', label: 'Supervisor', icon: '⚡', roles: ['supervisor', 'ops', 'admin'], mobile: true },
  { to: '/supervisor/ruta', label: 'Ruta', icon: '➜', roles: ['supervisor', 'ops', 'admin'], mobile: true },
  { to: '/ventas', label: 'Ventas', icon: '$', roles: ['ops', 'finance', 'admin', 'supervisor'] },
  { to: '/inventario', label: 'Inventario', icon: '▤', roles: ['ops', 'admin', 'supervisor'], mobile: true },
  { to: '/personas', label: 'Personas', icon: '☺', roles: ['ops', 'admin', 'supervisor'] },
  { to: '/activos', label: 'Activos', icon: '⚙', roles: ['ops', 'admin'] },
  { to: '/reglas', label: 'Reglas', icon: '⚖', roles: ['ops', 'admin'] },
  { to: '/aprobaciones', label: 'Aprobaciones', icon: '✓', roles: ['ops', 'finance', 'admin'] },
  { to: '/auditoria', label: 'Audit log', icon: '≡', roles: ['ops', 'finance', 'admin'] },
  { to: '/admin', label: 'Administración', icon: '⚒', roles: ['admin'] },
];

export const ROLE_LABEL: Record<Role, string> = { operator: 'Operador', supervisor: 'Supervisor', ops: 'Operaciones', finance: 'Finanzas', admin: 'Administrador' };

export function Layout() {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  if (!user) return null;
  const items = NAV.filter((n) => n.roles.includes(user.role));
  const mobileItems = user.role === 'supervisor' ? items.filter((n) => n.mobile) : items.slice(0, 5);
  const doLogout = async () => {
    await logout();
    nav('/login');
  };
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">P</span>
          <div>
            <div className="brand-name">PEPITO OS</div>
            <div className="brand-sub">Backoffice</div>
          </div>
        </div>
        <nav className="side-nav">
          {items.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.to === '/ct' || n.to === '/supervisor'} className={({ isActive }) => (isActive ? 'active' : '')}>
              <span className="nav-icon" aria-hidden>{n.icon}</span>
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="side-user">
          <div className="side-user-name">{user.name}</div>
          <div className="muted small">{ROLE_LABEL[user.role]}</div>
          <Link to="/cambiar-contrasena" className="btn btn-ghost small">
            Cambiar contraseña
          </Link>
          <button type="button" className="btn btn-ghost small" onClick={doLogout}>
            Cerrar sesión
          </button>
        </div>
      </aside>
      <div className="content">
        <header className="topbar">
          <span className="brand-name">PEPITO OS</span>
          <span className="muted small">
            {user.name} · {ROLE_LABEL[user.role]}
          </span>
          <button type="button" className="btn btn-ghost small" onClick={doLogout}>
            Salir
          </button>
        </header>
        <main className="main">
          <Outlet />
        </main>
        <nav className="bottom-nav">
          {mobileItems.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.to === '/supervisor' || n.to === '/ct'} className={({ isActive }) => (isActive ? 'active' : '')}>
              <span className="nav-icon" aria-hidden>{n.icon}</span>
              <span>{n.label}</span>
            </NavLink>
          ))}
        </nav>
      </div>
    </div>
  );
}
