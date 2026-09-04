// Fotos de evidencia: reducción en el cliente (≤ maxPx, JPEG) y validación de tamaño antes de encolar.
// Las fotos viajan en base64 dentro del comando (shift_open / shift_close / help_case), así que el tamaño importa
// tanto para la cola cifrada en IndexedDB como para el límite del servidor (`config.evidence_max_bytes`, 3 MB).

export const DEFAULT_MAX_PX = 1280;
export const DEFAULT_QUALITY = 0.8;
/** Límite por defecto si la config aún no se descargó (igual al del servidor). */
export const DEFAULT_MAX_BYTES = 3 * 1024 * 1024;

export interface CompressOptions {
  maxPx?: number;
  quality?: number;
  maxBytes?: number;
}

export class ImageTooLargeError extends Error {
  bytes: number;
  maxBytes: number;
  constructor(bytes: number, maxBytes: number) {
    super(`La foto pesa ${(bytes / (1024 * 1024)).toFixed(1)} MB; máximo ${Math.round(maxBytes / (1024 * 1024))} MB`);
    this.name = 'ImageTooLargeError';
    this.bytes = bytes;
    this.maxBytes = maxBytes;
  }
}

/** Bytes reales que representa una cadena base64 (sin prefijo data:). */
export function base64Bytes(b64: string): number {
  const clean = b64.replace(/\s+/g, '');
  const pad = clean.endsWith('==') ? 2 : clean.endsWith('=') ? 1 : 0;
  return Math.floor((clean.length * 3) / 4) - pad;
}

/** Quita el prefijo `data:image/...;base64,` si existe. */
export function stripDataUrl(s: string): string {
  const i = s.indexOf(',');
  return s.startsWith('data:') && i >= 0 ? s.slice(i + 1) : s;
}

async function readAsBase64(file: Blob): Promise<string> {
  if (typeof FileReader === 'undefined') {
    const bytes = new Uint8Array(await file.arrayBuffer());
    let bin = '';
    for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
    return btoa(bin);
  }
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(stripDataUrl(String(r.result ?? '')));
    r.onerror = () => reject(r.error ?? new Error('No se pudo leer la foto'));
    r.readAsDataURL(file);
  });
}

interface Drawable {
  width: number;
  height: number;
}

async function loadBitmap(file: Blob): Promise<(Drawable & { close?: () => void }) | null> {
  if (typeof createImageBitmap === 'function') {
    try {
      return await createImageBitmap(file);
    } catch {
      /* formato no soportado por createImageBitmap: intentamos con <img> */
    }
  }
  if (typeof Image === 'undefined' || typeof URL === 'undefined' || typeof URL.createObjectURL !== 'function') return null;
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      resolve(img);
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      resolve(null);
    };
    img.src = url;
  });
}

function drawScaled(source: Drawable, maxPx: number): HTMLCanvasElement | null {
  if (typeof document === 'undefined') return null;
  const scale = Math.min(1, maxPx / Math.max(source.width, source.height, 1));
  const canvas = document.createElement('canvas');
  canvas.width = Math.max(1, Math.round(source.width * scale));
  canvas.height = Math.max(1, Math.round(source.height * scale));
  const ctx = canvas.getContext('2d');
  if (!ctx) return null;
  ctx.drawImage(source as unknown as CanvasImageSource, 0, 0, canvas.width, canvas.height);
  return canvas;
}

/**
 * Reduce la imagen a ≤ `maxPx` por lado y la codifica como JPEG (`quality`). Devuelve base64 puro (sin `data:`).
 * Si aun así excede `maxBytes`, baja la calidad y el tamaño escalonadamente; si no hay forma, lanza ImageTooLargeError.
 * Sin canvas (navegador raro) devuelve el archivo original en base64, validando el tamaño.
 */
export async function compressImage(file: Blob, opts: CompressOptions = {}): Promise<string> {
  const maxPx = opts.maxPx ?? DEFAULT_MAX_PX;
  const quality = opts.quality ?? DEFAULT_QUALITY;
  const maxBytes = opts.maxBytes ?? DEFAULT_MAX_BYTES;
  const bitmap = await loadBitmap(file).catch(() => null);
  let canvas = bitmap ? drawScaled(bitmap, maxPx) : null;
  if (!canvas) {
    const raw = await readAsBase64(file);
    return ensureSize(raw, maxBytes);
  }
  // Intentos: calidad 0.8 → 0.6 → 0.45 y luego mitad de tamaño con 0.6.
  const attempts: { px: number; q: number }[] = [
    { px: maxPx, q: quality },
    { px: maxPx, q: Math.min(quality, 0.6) },
    { px: maxPx, q: 0.45 },
    { px: Math.round(maxPx / 2), q: 0.6 },
  ];
  let last = '';
  for (const a of attempts) {
    if (a.px !== canvas.width && a.px !== canvas.height && bitmap) canvas = drawScaled(bitmap, a.px) ?? canvas;
    last = stripDataUrl(canvas.toDataURL('image/jpeg', a.q));
    if (base64Bytes(last) <= maxBytes) {
      bitmap?.close?.();
      return last;
    }
  }
  bitmap?.close?.();
  throw new ImageTooLargeError(base64Bytes(last), maxBytes);
}

export function ensureSize(b64: string, maxBytes: number): string {
  const bytes = base64Bytes(b64);
  if (bytes > maxBytes) throw new ImageTooLargeError(bytes, maxBytes);
  return b64;
}

/** Valida en el cliente el tipo del archivo antes de intentar comprimirlo (el servidor acepta JPEG/PNG/WebP). */
export function isSupportedImage(file: Blob): boolean {
  const t = (file as File).type || '';
  return t === '' || /^image\/(jpeg|png|webp|heic|heif|gif|bmp)$/.test(t);
}
