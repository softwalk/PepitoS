/** Seguridad y notificaciones del usuario: MFA (TOTP), notificaciones push/WhatsApp, apariencia (tema y densidad). */
import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { Badge, Card, Empty, Loading, PageTitle } from '../components/ui';
import { useToast } from '../components/Toast';
import { useFetch } from '../lib/useFetch';
import { fmtDateTime } from '../lib/format';
import { currentSubscription, pushSupported, subscribePush, unsubscribePush } from '../lib/push';
import { getDensity, getTheme, setDensity, setTheme, type Density, type Theme } from '../lib/theme';
import { useAuth } from '../state/auth';
import type { MfaStatus, NotificationConfig, NotificationLogRow } from '../types';

function MfaCard() {
  const toast = useToast();
  const { data, reload } = useFetch<MfaStatus>(() => api.get('/v1/auth/mfa'), []);
  const [setup, setSetup] = useState<{ secret: string; otpauth_uri: string } | null>(null);
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const run = async (fn: () => Promise<unknown>, ok: string) => {
    setBusy(true);
    try {
      await fn();
      toast.toast(ok, 'success');
      setSetup(null);
      setCode('');
      await reload(true);
    } catch (e) {
      toast.error(e);
    } finally {
      setBusy(false);
    }
  };
  if (!data) return <Loading />;
  return (
    <Card title="Verificación en dos pasos (MFA)" testId="mfa-card">
      <p className="muted">
        Un código de 6 dígitos de una app autenticadora (Google Authenticator, Authy, 1Password…) además de tu contraseña.
        {data.required && ' Tu rol lo requiere.'}
        {data.enforced && !data.enabled && <b> Está exigido por configuración: actívalo para seguir usando el backoffice.</b>}
      </p>
      <p>
        Estado: {data.enabled ? <Badge tone="green">Activo desde {fmtDateTime(data.enabled_at)}</Badge> : <Badge tone="amber">Inactivo</Badge>}
      </p>
      {!data.enabled && !setup && (
        <button className="btn btn-primary" disabled={busy} data-testid="mfa-setup" onClick={async () => { setBusy(true); try { setSetup(await api.post('/v1/auth/mfa/setup')); } catch (e) { toast.error(e); } finally { setBusy(false); } }}>
          Activar MFA
        </button>
      )}
      {setup && (
        <div className="stack" style={{ display: 'grid', gap: 10 }}>
          <p>
            1. Abre tu app autenticadora y <b>agrega una cuenta con clave manual</b> (o usa el enlace en el teléfono):
          </p>
          <p>
            <code className="mfa-secret" data-testid="mfa-secret">{setup.secret.replace(/(.{4})/g, '$1 ').trim()}</code>
          </p>
          <p>
            <a href={setup.otpauth_uri}>Abrir en la app autenticadora</a> · Emisor: PEPITO OS
          </p>
          <p>2. Escribe el código que muestra la app para confirmar:</p>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <input inputMode="numeric" autoComplete="one-time-code" value={code} onChange={(e) => setCode(e.target.value)} placeholder="000000" style={{ width: 140, fontSize: 20, letterSpacing: 4, textAlign: 'center' }} data-testid="mfa-code" />
            <button className="btn btn-primary" disabled={busy || code.replace(/\s/g, '').length < 6} data-testid="mfa-enable" onClick={() => run(() => api.post('/v1/auth/mfa/enable', { code: code.replace(/\s/g, '') }), 'MFA activado')}>
              Confirmar
            </button>
            <button className="btn btn-ghost" onClick={() => setSetup(null)}>
              Cancelar
            </button>
          </div>
        </div>
      )}
      {data.enabled && (
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <input inputMode="numeric" value={code} onChange={(e) => setCode(e.target.value)} placeholder="Código actual" style={{ width: 140 }} />
          <button className="btn btn-danger" disabled={busy || code.replace(/\s/g, '').length < 6} onClick={() => run(() => api.post('/v1/auth/mfa/disable', { code: code.replace(/\s/g, '') }), 'MFA desactivado')}>
            Desactivar MFA
          </button>
        </div>
      )}
    </Card>
  );
}

function NotificationsCard() {
  const toast = useToast();
  const { data, reload } = useFetch<NotificationConfig>(() => api.get('/v1/notifications/config'), []);
  const [subscribed, setSubscribed] = useState<boolean | null>(null);
  const [phone, setPhone] = useState('');
  useEffect(() => {
    void currentSubscription().then((s) => setSubscribed(!!s));
  }, []);
  useEffect(() => {
    if (data) setPhone(data.phone ?? '');
  }, [data]);
  if (!data) return <Loading />;
  const savePrefs = async (patch: Record<string, unknown>) => {
    try {
      await api.put('/v1/notifications/prefs', patch);
      await reload(true);
      toast.toast('Preferencias guardadas', 'success');
    } catch (e) {
      toast.error(e);
    }
  };
  return (
    <Card title="Notificaciones" testId="notifications-card">
      <p className="muted">Casos urgentes y de revisión de tu zona, SLA vencidos y avisos de sistema. Push en este navegador; WhatsApp de respaldo cuando el push no llega.</p>
      <div style={{ display: 'grid', gap: 10 }}>
        <div>
          <b>Push en este navegador:</b> {!pushSupported() ? <Badge tone="gray">No soportado</Badge> : !data.push_enabled ? <Badge tone="gray">Servidor sin claves VAPID</Badge> : subscribed ? <Badge tone="green">Activo</Badge> : <Badge tone="amber">Inactivo</Badge>}
          {' '}
          {pushSupported() && data.push_enabled && !subscribed && (
            <button className="btn btn-primary small" data-testid="push-subscribe" onClick={async () => {
              const r = await subscribePush(data);
              if (r === 'subscribed') { setSubscribed(true); toast.toast('Notificaciones activadas', 'success'); await reload(true); }
              else toast.toast(r === 'denied' ? 'El navegador bloqueó las notificaciones' : 'No disponible', 'error');
            }}>
              Activar en este navegador
            </button>
          )}
          {subscribed && (
            <button className="btn small" onClick={async () => { await unsubscribePush(); setSubscribed(false); await reload(true); }}>
              Desactivar aquí
            </button>
          )}
          <span className="muted small"> · {data.subscriptions} navegador(es) suscritos</span>
        </div>
        <label style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <input type="checkbox" checked={data.prefs.push} onChange={(e) => savePrefs({ push: e.target.checked })} /> Recibir push
        </label>
        <label style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <input type="checkbox" checked={data.prefs.whatsapp} onChange={(e) => savePrefs({ whatsapp: e.target.checked })} /> Recibir WhatsApp de respaldo {data.whatsapp_enabled ? '' : <Badge tone="gray">servidor sin Twilio</Badge>}
        </label>
        <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <label className="field">
            <span className="field-label">Teléfono WhatsApp (E.164)</span>
            <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+5215512345678" />
          </label>
          <button className="btn" onClick={() => savePrefs({ phone })}>
            Guardar teléfono
          </button>
          <button className="btn" data-testid="notify-test" onClick={async () => { const r = await api.post<Record<string, unknown>>('/v1/notifications/test'); toast.toast(`Prueba enviada: ${JSON.stringify(r)}`, 'success'); }}>
            Enviar prueba
          </button>
        </div>
      </div>
    </Card>
  );
}

function AppearanceCard() {
  const [theme, setT] = useState<Theme>(getTheme());
  const [density, setD] = useState<Density>(getDensity());
  return (
    <Card title="Apariencia" testId="appearance-card">
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
        <label className="field">
          <span className="field-label">Tema</span>
          <select value={theme} onChange={(e) => { const v = e.target.value as Theme; setT(v); setTheme(v); }} data-testid="theme-select">
            <option value="system">Según el sistema</option>
            <option value="light">Claro</option>
            <option value="dark">Oscuro</option>
          </select>
        </label>
        <label className="field">
          <span className="field-label">Densidad</span>
          <select value={density} onChange={(e) => { const v = e.target.value as Density; setD(v); setDensity(v); }} data-testid="density-select">
            <option value="normal">Normal</option>
            <option value="compact">Compacta (monitores grandes)</option>
          </select>
        </label>
      </div>
    </Card>
  );
}

function LogCard() {
  const { data } = useFetch<NotificationLogRow[]>(() => api.get('/v1/notifications/log?limit=30'), [], { silent: true });
  return (
    <Card title="Últimas notificaciones">
      {!data ? <Loading /> : data.length === 0 ? <Empty text="Aún no se ha enviado ninguna notificación." /> : (
        <div className="table-wrap">
          <table className="table compact">
            <thead><tr><th>Cuándo</th><th>Canal</th><th>Título</th><th>Estado</th></tr></thead>
            <tbody>
              {data.map((r) => (
                <tr key={r.id}><td className="nowrap">{fmtDateTime(r.sent_at)}</td><td>{r.channel}</td><td>{r.title}</td><td><Badge tone={r.status === 'sent' ? 'green' : r.status === 'failed' ? 'red' : 'gray'}>{r.status}</Badge>{r.error && <span className="muted small"> {r.error}</span>}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

export function SecurityPage() {
  const { user } = useAuth();
  return (
    <>
      <PageTitle title="Seguridad y notificaciones" subtitle={`${user?.name} · ${user?.role}`} />
      <div className="grid-2">
        <div>
          <MfaCard />
          <AppearanceCard />
        </div>
        <div>
          <NotificationsCard />
          <LogCard />
        </div>
      </div>
    </>
  );
}
