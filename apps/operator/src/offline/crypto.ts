// Cifrado de la cola local: AES-GCM 256 con WebCrypto. La clave (bytes crudos) se guarda por sesión en IndexedDB.
// Limitación conocida (CONTRATOS §9): el navegador no ofrece keystore de hardware; la clave vive junto a los datos.
import { secretsStore } from './db';

let cachedKey: CryptoKey | null = null;

const subtle = () => globalThis.crypto.subtle;

async function importKey(raw: ArrayBuffer): Promise<CryptoKey> {
  return subtle().importKey('raw', raw, { name: 'AES-GCM' }, false, ['encrypt', 'decrypt']);
}

/** Obtiene (o crea) la clave de la sesión. */
export async function getQueueKey(): Promise<CryptoKey> {
  if (cachedKey) return cachedKey;
  const stored = await secretsStore.get();
  if (stored) {
    cachedKey = await importKey(stored.raw);
    return cachedKey;
  }
  const raw = globalThis.crypto.getRandomValues(new Uint8Array(32)).buffer;
  await secretsStore.set(raw);
  cachedKey = await importKey(raw);
  return cachedKey;
}

/** Rota la clave (al cerrar sesión). Sólo debe llamarse con la cola vacía. */
export async function dropQueueKey() {
  cachedKey = null;
  await secretsStore.clear();
}

export async function encryptJSON(value: unknown): Promise<{ iv: ArrayBuffer; data: ArrayBuffer }> {
  const key = await getQueueKey();
  const iv = globalThis.crypto.getRandomValues(new Uint8Array(12));
  const plain = new TextEncoder().encode(JSON.stringify(value));
  const data = await subtle().encrypt({ name: 'AES-GCM', iv }, key, plain);
  return { iv: iv.buffer, data };
}

export async function decryptJSON<T = unknown>(cipher: { iv: ArrayBuffer; data: ArrayBuffer }): Promise<T> {
  const key = await getQueueKey();
  const plain = await subtle().decrypt({ name: 'AES-GCM', iv: new Uint8Array(cipher.iv) }, key, cipher.data);
  return JSON.parse(new TextDecoder().decode(plain)) as T;
}
