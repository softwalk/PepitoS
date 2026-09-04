// device_id UUID persistido (localStorage + respaldo en IndexedDB vía session).
import { v4 as uuidv4 } from 'uuid';

const KEY = 'pepito.device_id';

export function getDeviceId(): string {
  try {
    const cur = localStorage.getItem(KEY);
    if (cur) return cur;
    const id = uuidv4();
    localStorage.setItem(KEY, id);
    return id;
  } catch {
    return uuidv4();
  }
}

export function deviceName(): string {
  const ua = typeof navigator !== 'undefined' ? navigator.userAgent : '';
  if (/android/i.test(ua)) return 'Android';
  if (/iphone|ipad/i.test(ua)) return 'iOS';
  return 'Navegador';
}
