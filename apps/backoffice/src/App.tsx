import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import type { ReactNode } from 'react';
import { Layout } from './components/Layout';
import { useAuth } from './state/auth';
import type { Role } from './types';
import { LoginPage } from './pages/Login';
import { ControlTowerPage } from './pages/ControlTower';
import { BriefingPage } from './pages/Briefing';
import { CasesPage } from './pages/Cases';
import { CaseDetailPage } from './pages/CaseDetail';
import { SupervisorPage } from './pages/Supervisor';
import { SupervisorRoutePage } from './pages/SupervisorRoute';
import { AuditFormPage } from './pages/AuditForm';
import { SalesPage } from './pages/Sales';
import { InventoryPage } from './pages/Inventory';
import { PeoplePage } from './pages/People';
import { AssetsPage } from './pages/Assets';
import { RulesPage } from './pages/Rules';
import { ApprovalsPage } from './pages/Approvals';
import { AuditLogPage } from './pages/AuditLog';
import { AdminPage } from './pages/Admin';
import { AuditDetailPage } from './pages/AuditDetail';
import { ChangePasswordPage } from './pages/ChangePassword';

const CT: Role[] = ['ops', 'finance', 'admin'];
const SUP: Role[] = ['supervisor', 'ops', 'admin'];
const CASES: Role[] = ['supervisor', 'ops', 'finance', 'admin'];
const OPS: Role[] = ['ops', 'admin'];
const STAFF: Role[] = ['supervisor', 'ops', 'finance', 'admin'];
export const CHANGE_PASSWORD_PATH = '/cambiar-contrasena';

export function homeFor(role: Role): string {
  if (role === 'supervisor') return '/supervisor';
  if (role === 'operator') return '/login';
  return '/ct';
}

function Guard({ roles, children }: { roles: Role[]; children: ReactNode }) {
  const { user, mustChangePassword } = useAuth();
  const loc = useLocation();
  if (!user) return <Navigate to="/login" replace state={{ from: loc.pathname }} />;
  // Contraseña restablecida: el resto de la API responde 403 PASSWORD_CHANGE_REQUIRED hasta cambiarla.
  if (mustChangePassword && loc.pathname !== CHANGE_PASSWORD_PATH) return <Navigate to={CHANGE_PASSWORD_PATH} replace state={{ from: loc.pathname }} />;
  if (!roles.includes(user.role)) return <Navigate to={homeFor(user.role)} replace />;
  return <>{children}</>;
}

function Home() {
  const { user, mustChangePassword } = useAuth();
  if (user && mustChangePassword) return <Navigate to={CHANGE_PASSWORD_PATH} replace />;
  return <Navigate to={user ? homeFor(user.role) : '/login'} replace />;
}

export default function App() {
  const { user } = useAuth();
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={user ? <Layout /> : <Navigate to="/login" replace />}>
        <Route path="/" element={<Home />} />
        <Route path="/ct" element={<Guard roles={CT}><ControlTowerPage /></Guard>} />
        <Route path="/ct/briefing" element={<Guard roles={CT}><BriefingPage /></Guard>} />
        <Route path="/excepciones" element={<Guard roles={CASES}><CasesPage /></Guard>} />
        <Route path="/casos/:id" element={<Guard roles={CASES}><CaseDetailPage /></Guard>} />
        <Route path="/supervisor" element={<Guard roles={SUP}><SupervisorPage /></Guard>} />
        <Route path="/supervisor/ruta" element={<Guard roles={SUP}><SupervisorRoutePage /></Guard>} />
        <Route path="/supervisor/auditoria/:pointId" element={<Guard roles={SUP}><AuditFormPage /></Guard>} />
        <Route path="/auditorias/:id" element={<Guard roles={SUP}><AuditDetailPage /></Guard>} />
        <Route path="/ventas" element={<Guard roles={CASES}><SalesPage /></Guard>} />
        <Route path="/inventario" element={<Guard roles={SUP}><InventoryPage /></Guard>} />
        <Route path="/personas" element={<Guard roles={SUP}><PeoplePage /></Guard>} />
        <Route path="/activos" element={<Guard roles={OPS}><AssetsPage /></Guard>} />
        <Route path="/reglas" element={<Guard roles={OPS}><RulesPage /></Guard>} />
        <Route path="/aprobaciones" element={<Guard roles={CT}><ApprovalsPage /></Guard>} />
        <Route path="/auditoria" element={<Guard roles={CT}><AuditLogPage /></Guard>} />
        <Route path="/admin" element={<Guard roles={CT}><AdminPage /></Guard>} />
        <Route path={CHANGE_PASSWORD_PATH} element={<Guard roles={STAFF}><ChangePasswordPage /></Guard>} />
      </Route>
      <Route path="*" element={<Home />} />
    </Routes>
  );
}
