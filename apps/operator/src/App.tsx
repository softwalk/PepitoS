import { HashRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AppProvider, useApp } from './state/store';
import Layout from './components/Layout';
import Login from './screens/Login';
import ChangePassword from './screens/ChangePassword';
import Home from './screens/Home';
import OpenShift from './screens/OpenShift';
import Sell from './screens/Sell';
import Help from './screens/Help';
import CloseShift from './screens/CloseShift';
import Settings from './screens/Settings';

function Gate() {
  const { booted, session } = useApp();
  if (!booted) {
    return (
      <div className="app">
        <div className="main center" style={{ justifyContent: 'center' }}>
          <p className="h2">Cargando…</p>
        </div>
      </div>
    );
  }
  if (!session) {
    return (
      <Routes>
        <Route path="*" element={<Login />} />
      </Routes>
    );
  }
  if (session.must_change_password) {
    return (
      <Routes>
        <Route path="*" element={<ChangePassword />} />
      </Routes>
    );
  }
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/abrir" element={<OpenShift />} />
        <Route path="/vender" element={<Sell />} />
        <Route path="/ayuda" element={<Help />} />
        <Route path="/cerrar" element={<CloseShift />} />
        <Route path="/ajustes" element={<Settings />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
}

export default function App() {
  return (
    <AppProvider>
      <HashRouter>
        <Gate />
      </HashRouter>
    </AppProvider>
  );
}
