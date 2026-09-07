// Web Push en el backoffice: registra /sw.js y guarda la suscripción en la API (VAPID desde /v1/notifications/config).
import { api } from '../api/client';
import type { NotificationConfig } from '../types';

function b64uToBytes(s: string): ArrayBuffer {
  const pad = '='.repeat((4 - (s.length % 4)) % 4);
  const raw = atob((s + pad).replace(/-/g, '+').replace(/_/g, '/'));
  const buf = new ArrayBuffer(raw.length);
  const view = new Uint8Array(buf);
  for (let i = 0; i < raw.length; i++) view[i] = raw.charCodeAt(i);
  return buf;
}

export function pushSupported(): boolean {
  return typeof window !== 'undefined' && 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
}

export async function currentSubscription(): Promise<PushSubscription | null> {
  if (!pushSupported()) return null;
  const reg = await navigator.serviceWorker.getRegistration('/sw.js');
  return reg ? reg.pushManager.getSubscription() : null;
}

export async function subscribePush(cfg: NotificationConfig): Promise<'subscribed' | 'denied' | 'unsupported' | 'disabled'> {
  if (!pushSupported()) return 'unsupported';
  if (!cfg.push_enabled || !cfg.vapid_public_key) return 'disabled';
  const perm = await Notification.requestPermission();
  if (perm !== 'granted') return 'denied';
  const reg = await navigator.serviceWorker.register('/sw.js');
  const sub = (await reg.pushManager.getSubscription()) ?? (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64uToBytes(cfg.vapid_public_key) }));
  const json = sub.toJSON();
  await api.post('/v1/notifications/subscriptions', { endpoint: sub.endpoint, keys: json.keys, user_agent: navigator.userAgent.slice(0, 200) });
  return 'subscribed';
}

export async function unsubscribePush(): Promise<void> {
  const sub = await currentSubscription();
  if (!sub) return;
  await api.del(`/v1/notifications/subscriptions?endpoint=${encodeURIComponent(sub.endpoint)}`);
  await sub.unsubscribe();
}
