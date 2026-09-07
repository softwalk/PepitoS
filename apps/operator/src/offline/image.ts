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

// ───────────── Sello (fecha/hora/punto/ubicación) sobre la foto ─────────────

export interface StampInfo {
  /** Momento de la toma (por defecto ahora). */
  at?: Date;
  /** Nombre del punto o carrito. */
  place?: string | null;
  /** Coordenadas GPS; se imprimen con 5 decimales y la precisión en metros. */
  gps?: { lat: number; lng: number; accuracy_m?: number | null } | null;
  /** Etiqueta del tipo de foto (Conteo, Recepción, Incidente). */
  label?: string | null;
}

function pad2(n: number): string {
  return String(n).padStart(2, '0');
}

/** Texto del sello, una línea por elemento; es lo que se dibuja y lo que se prueba. */
export function stampLines(info: StampInfo): string[] {
  const at = info.at ?? new Date();
  const date = `${pad2(at.getDate())}/${pad2(at.getMonth() + 1)}/${at.getFullYear()} ${pad2(at.getHours())}:${pad2(at.getMinutes())}:${pad2(at.getSeconds())}`;
  const lines = [info.label ? `${info.label} · ${date}` : date];
  if (info.place) lines.push(info.place);
  if (info.gps) {
    const acc = info.gps.accuracy_m != null ? ` ±${Math.round(info.gps.accuracy_m)} m` : '';
    lines.push(`GPS ${info.gps.lat.toFixed(5)}, ${info.gps.lng.toFixed(5)}${acc}`);
  }
  return lines;
}

/**
 * Dibuja el sello en la esquina inferior de la imagen (banda semitransparente + texto) y devuelve base64 JPEG.
 * El sello queda dentro de los píxeles: no se puede quitar editando metadatos. Sin canvas devuelve la foto tal cual.
 */
export async function stampImage(b64: string, info: StampInfo, opts: { maxBytes?: number; quality?: number } = {}): Promise<string> {
  if (typeof document === 'undefined' || typeof Image === 'undefined') return b64;
  const img = await new Promise<HTMLImageElement | null>((resolve) => {
    const i = new Image();
    i.onload = () => resolve(i);
    i.onerror = () => resolve(null);
    i.src = `data:image/jpeg;base64,${b64}`;
  });
  if (!img || !img.width) return b64;
  const canvas = document.createElement('canvas');
  canvas.width = img.width;
  canvas.height = img.height;
  const ctx = canvas.getContext('2d');
  if (!ctx) return b64;
  ctx.drawImage(img, 0, 0);
  const lines = stampLines(info);
  const fs = Math.max(14, Math.round(Math.min(canvas.width, canvas.height) / 28));
  const lh = Math.round(fs * 1.35);
  const padX = Math.round(fs * 0.7);
  const bandH = lh * lines.length + padX;
  ctx.fillStyle = 'rgba(0,0,0,0.55)';
  ctx.fillRect(0, canvas.height - bandH, canvas.width, bandH);
  ctx.font = `bold ${fs}px system-ui, -apple-system, Roboto, Arial, sans-serif`;
  ctx.textBaseline = 'alphabetic';
  ctx.fillStyle = '#ffffff';
  ctx.shadowColor = 'rgba(0,0,0,0.8)';
  ctx.shadowBlur = 3;
  lines.forEach((t, i) => ctx.fillText(t, padX, canvas.height - bandH + padX / 2 + lh * (i + 1) - Math.round(fs * 0.3), canvas.width - padX * 2));
  const quality = opts.quality ?? DEFAULT_QUALITY;
  let out = stripDataUrl(canvas.toDataURL('image/jpeg', quality));
  const maxBytes = opts.maxBytes ?? DEFAULT_MAX_BYTES;
  if (base64Bytes(out) > maxBytes) out = stripDataUrl(canvas.toDataURL('image/jpeg', 0.5));
  return ensureSize(out, maxBytes);
}

/** Kilogramos teóricos de un mapa {presentation_id: piezas} según los gramos del catálogo. */
export function kilograms(counts: Record<string, number>, presentations: { id: string; grams: number }[]): number {
  const g = new Map(presentations.map((p) => [p.id, p.grams]));
  const totalGrams = Object.entries(counts).reduce((a, [id, q]) => a + (q || 0) * (g.get(id) ?? 0), 0);
  return gramsToKg(totalGrams);
}

/** Gramos → kg con exactamente 2 decimales, mitad hacia arriba (misma regla que la API `kg2`). */
export function gramsToKg(grams: number): number {
  return Math.round(grams / 10 + Number.EPSILON) / 100;
}

/** Siempre 2 decimales: "8.02 kg", "2.00 kg". */
export function fmtKg(kg: number): string {
  return `${kg.toLocaleString('es-MX', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} kg`;
}
