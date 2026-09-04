// Compresión de fotos en el cliente: reducción a ≤1280 px, JPEG y validación contra evidence_max_bytes (canvas simulado).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { base64Bytes, compressImage, ensureSize, ImageTooLargeError, stripDataUrl } from '../src/offline/image';

interface FakeCanvas {
  width: number;
  height: number;
  getContext: () => { drawImage: ReturnType<typeof vi.fn> };
  toDataURL: (type: string, quality: number) => string;
}

/** Canvas falso: el "JPEG" pesa proporcional a píxeles × calidad, para poder probar los reintentos de tamaño. */
function installFakeCanvas(opts: { bytesPerPixel: number }) {
  const canvases: FakeCanvas[] = [];
  const dataUrls: { w: number; h: number; q: number }[] = [];
  const drawImage = vi.fn();
  const doc = {
    createElement: (tag: string) => {
      if (tag !== 'canvas') throw new Error('sólo canvas');
      const c: FakeCanvas = {
        width: 0,
        height: 0,
        getContext: () => ({ drawImage }),
        toDataURL: (_type, q) => {
          dataUrls.push({ w: c.width, h: c.height, q });
          const bytes = Math.max(1, Math.round(c.width * c.height * opts.bytesPerPixel * q));
          return 'data:image/jpeg;base64,' + Buffer.alloc(bytes, 0xab).toString('base64');
        },
      };
      canvases.push(c);
      return c;
    },
  };
  vi.stubGlobal('document', doc);
  return { canvases, dataUrls, drawImage };
}

function fakeBitmap(width: number, height: number) {
  const close = vi.fn();
  vi.stubGlobal('createImageBitmap', vi.fn(async () => ({ width, height, close })));
  return { close };
}

beforeEach(() => {
  vi.stubGlobal('Blob', globalThis.Blob);
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe('base64 helpers', () => {
  it('calcula bytes reales y quita el prefijo data:', () => {
    const b64 = Buffer.alloc(100, 1).toString('base64');
    expect(base64Bytes(b64)).toBe(100);
    expect(base64Bytes(Buffer.alloc(101, 1).toString('base64'))).toBe(101);
    expect(stripDataUrl('data:image/png;base64,' + b64)).toBe(b64);
    expect(stripDataUrl(b64)).toBe(b64);
  });

  it('ensureSize lanza ImageTooLargeError si excede el máximo', () => {
    const b64 = Buffer.alloc(10, 1).toString('base64');
    expect(ensureSize(b64, 10)).toBe(b64);
    expect(() => ensureSize(b64, 9)).toThrow(ImageTooLargeError);
  });
});

describe('compressImage', () => {
  it('reduce a ≤1280 px manteniendo proporción y codifica JPEG 0.8', async () => {
    const { dataUrls, drawImage } = installFakeCanvas({ bytesPerPixel: 0.05 });
    const { close } = fakeBitmap(4000, 3000);
    const out = await compressImage(new Blob(['x'], { type: 'image/jpeg' }));
    expect(dataUrls[0]).toEqual({ w: 1280, h: 960, q: 0.8 });
    expect(drawImage).toHaveBeenCalledWith(expect.anything(), 0, 0, 1280, 960);
    expect(out).not.toContain('data:');
    expect(base64Bytes(out)).toBeGreaterThan(0);
    expect(close).toHaveBeenCalled();
  });

  it('no agranda imágenes pequeñas', async () => {
    const { dataUrls } = installFakeCanvas({ bytesPerPixel: 0.05 });
    fakeBitmap(640, 480);
    await compressImage(new Blob(['x'], { type: 'image/jpeg' }));
    expect(dataUrls[0]).toEqual({ w: 640, h: 480, q: 0.8 });
  });

  it('baja calidad/tamaño hasta caber en maxBytes', async () => {
    // 1280×960×2×0.8 ≈ 1.97 MB; con maxBytes 700 KB debe llegar a la mitad de tamaño (640×480×2×0.6 ≈ 369 KB).
    const { dataUrls } = installFakeCanvas({ bytesPerPixel: 2 });
    fakeBitmap(1280, 960);
    const out = await compressImage(new Blob(['x'], { type: 'image/jpeg' }), { maxBytes: 700 * 1024 });
    expect(base64Bytes(out)).toBeLessThanOrEqual(700 * 1024);
    expect(dataUrls.map((d) => d.q)).toEqual([0.8, 0.6, 0.45, 0.6]);
    expect(dataUrls.at(-1)).toEqual({ w: 640, h: 480, q: 0.6 });
  });

  it('lanza ImageTooLargeError si ni el último intento cabe', async () => {
    installFakeCanvas({ bytesPerPixel: 50 });
    fakeBitmap(200, 200);
    await expect(compressImage(new Blob(['x'], { type: 'image/jpeg' }), { maxBytes: 1024 })).rejects.toBeInstanceOf(ImageTooLargeError);
  });

  it('sin canvas devuelve el archivo original en base64 y valida el tamaño', async () => {
    vi.stubGlobal('createImageBitmap', undefined);
    vi.stubGlobal('document', undefined);
    vi.stubGlobal('Image', undefined);
    const bytes = new Uint8Array([0xff, 0xd8, 0xff, 1, 2, 3]);
    const out = await compressImage(new Blob([bytes], { type: 'image/jpeg' }), { maxBytes: 100 });
    expect(Buffer.from(out, 'base64')).toEqual(Buffer.from(bytes));
    await expect(compressImage(new Blob([bytes], { type: 'image/jpeg' }), { maxBytes: 3 })).rejects.toBeInstanceOf(ImageTooLargeError);
  });
});
