// Fotos de auditoría: reducción en el cliente (≤1280 px, JPEG 0.8) y validación de tamaño antes de enviar en `photos`.
export const MAX_PX = 1280;
export const QUALITY = 0.8;
export const DEFAULT_MAX_BYTES = 3 * 1024 * 1024;

export function base64Bytes(b64: string): number {
  const clean = b64.replace(/\s+/g, '');
  const pad = clean.endsWith('==') ? 2 : clean.endsWith('=') ? 1 : 0;
  return Math.floor((clean.length * 3) / 4) - pad;
}

export function stripDataUrl(s: string): string {
  const i = s.indexOf(',');
  return s.startsWith('data:') && i >= 0 ? s.slice(i + 1) : s;
}

function readAsBase64(file: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(stripDataUrl(String(r.result ?? '')));
    r.onerror = () => reject(r.error ?? new Error('No se pudo leer la foto'));
    r.readAsDataURL(file);
  });
}

async function loadBitmap(file: Blob): Promise<ImageBitmap | HTMLImageElement | null> {
  if (typeof createImageBitmap === 'function') {
    try {
      return await createImageBitmap(file);
    } catch {
      /* fallback <img> */
    }
  }
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

/** Devuelve base64 puro (sin `data:`) de un JPEG ≤ maxPx; baja calidad/tamaño hasta caber en maxBytes o lanza Error. */
export async function compressImage(file: Blob, opts: { maxPx?: number; quality?: number; maxBytes?: number } = {}): Promise<string> {
  const maxPx = opts.maxPx ?? MAX_PX;
  const quality = opts.quality ?? QUALITY;
  const maxBytes = opts.maxBytes ?? DEFAULT_MAX_BYTES;
  const bitmap = await loadBitmap(file).catch(() => null);
  if (!bitmap) {
    const raw = await readAsBase64(file);
    if (base64Bytes(raw) > maxBytes) throw new Error(`La foto excede el máximo de ${Math.round(maxBytes / (1024 * 1024))} MB`);
    return raw;
  }
  const draw = (px: number) => {
    const scale = Math.min(1, px / Math.max(bitmap.width, bitmap.height, 1));
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(bitmap.width * scale));
    canvas.height = Math.max(1, Math.round(bitmap.height * scale));
    canvas.getContext('2d')?.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    return canvas;
  };
  const attempts = [
    { px: maxPx, q: quality },
    { px: maxPx, q: Math.min(quality, 0.6) },
    { px: Math.round(maxPx / 2), q: 0.6 },
  ];
  let canvas = draw(maxPx);
  let last = '';
  for (const a of attempts) {
    if (a.px !== maxPx) canvas = draw(a.px);
    last = stripDataUrl(canvas.toDataURL('image/jpeg', a.q));
    if (base64Bytes(last) <= maxBytes) return last;
  }
  throw new Error(`La foto excede el máximo de ${Math.round(maxBytes / (1024 * 1024))} MB`);
}
