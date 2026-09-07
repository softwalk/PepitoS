// Mensajes de error para el vendedor: nunca se muestra texto técnico (TypeError, "importKey", "undefined"…).
// Cada causa conocida tiene una explicación en español y qué hacer; lo desconocido se resume en una frase neutra.
import { ApiError, NetworkError } from '../api/client';

/** Conexión no segura: sin https el navegador no da WebCrypto ni GPS y la cola cifrada no puede guardar nada. */
export class InsecureContextError extends Error {
  constructor() {
    super(INSECURE_MESSAGE);
    this.name = 'InsecureContextError';
  }
}

export const INSECURE_MESSAGE = 'La app se abrió sin conexión segura (la dirección debe empezar con https://). Así no se pueden guardar ventas ni avisos. Pide al supervisor la dirección correcta o vuelve a instalar la app desde ella.';

/** true cuando el navegador no expone cifrado (http:// en la red local, WebView antiguo). */
export function insecureContext(): boolean {
  if (typeof window === 'undefined') return false;
  return window.isSecureContext === false || typeof globalThis.crypto?.subtle?.importKey !== 'function';
}

const PATTERNS: [RegExp, string][] = [
  [/importKey|crypto\.subtle|subtle is undefined|SubtleCrypto|Do\(\) is undefined/i, INSECURE_MESSAGE],
  [/QuotaExceeded|quota|no space|espacio/i, 'El teléfono no tiene espacio para guardar. Libera espacio (fotos, apps) e inténtalo de nuevo.'],
  [/IndexedDB|IDB|transaction|database|objectStore|Blocked/i, 'La app no pudo guardar en el teléfono. Cierra la app por completo, vuelve a abrirla e inténtalo otra vez.'],
  [/NetworkError|Failed to fetch|Load failed|net::|fetch/i, 'No hay señal. Lo que registres se guarda en el teléfono y se envía cuando haya conexión.'],
  [/NotAllowedError|permission|permiso/i, 'El teléfono no dio permiso (cámara o ubicación). Revísalo en Ajustes del teléfono.'],
  [/timeout|timed out/i, 'Tardó demasiado en responder. Inténtalo de nuevo.'],
];

/** Texto entendible para cualquier error; `fallback` cuando no se reconoce la causa. */
export function friendlyError(err: unknown, fallback = 'Algo falló al guardar. Inténtalo de nuevo; si sigue igual, avisa al supervisor.'): string {
  if (err instanceof InsecureContextError) return err.message;
  if (err instanceof NetworkError) return PATTERNS[3][1];
  if (err instanceof ApiError) return err.message || fallback; // la API ya responde en español
  const raw = err instanceof Error ? `${err.name}: ${err.message}` : typeof err === 'string' ? err : '';
  if (insecureContext() && /TypeError|undefined/i.test(raw)) return INSECURE_MESSAGE;
  for (const [re, msg] of PATTERNS) if (re.test(raw)) return msg;
  return fallback;
}
