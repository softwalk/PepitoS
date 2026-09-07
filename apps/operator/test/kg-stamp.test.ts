import { describe, expect, it } from 'vitest';
import { fmtKg, kilograms, stampLines } from '../src/offline/image';

const PRES = [
  { id: 'a', grams: 50 },
  { id: 'b', grams: 75 },
  { id: 'c', grams: 100 },
];

describe('kilogramos', () => {
  it('suma piezas × gramos del catálogo', () => {
    expect(kilograms({ a: 4, b: 2, c: 3 }, PRES)).toBe(0.65);
    expect(kilograms({}, PRES)).toBe(0);
    expect(kilograms({ zzz: 10 }, PRES)).toBe(0); // presentación desconocida no suma
  });
  it('siempre 2 decimales, mitad hacia arriba (misma regla que la API)', () => {
    expect(kilograms({ a: 37, b: 37, c: 34 }, PRES)).toBe(8.03); // 8025 g
    expect(kilograms({ a: 1 }, PRES)).toBe(0.05);
    expect(kilograms({ b: 1 }, PRES)).toBe(0.08); // 75 g
    expect(fmtKg(2)).toBe('2.00 kg');
    expect(fmtKg(0.65)).toBe('0.65 kg');
    expect(fmtKg(8.03)).toBe('8.03 kg');
  });
});

describe('sello de foto', () => {
  it('incluye etiqueta, fecha/hora local, punto y GPS con precisión', () => {
    const at = new Date(2026, 8, 7, 14, 5, 9);
    expect(stampLines({ at, label: 'Conteo', place: 'Metro Insurgentes', gps: { lat: 19.4235, lng: -99.163, accuracy_m: 12.4 } })).toEqual([
      'Conteo · 07/09/2026 14:05:09',
      'Metro Insurgentes',
      'GPS 19.42350, -99.16300 ±12 m',
    ]);
  });
  it('omite lo que no hay', () => {
    const at = new Date(2026, 0, 1, 8, 0, 0);
    expect(stampLines({ at })).toEqual(['01/01/2026 08:00:00']);
    expect(stampLines({ at, gps: { lat: 1, lng: 2 } })).toEqual(['01/01/2026 08:00:00', 'GPS 1.00000, 2.00000']);
  });
});
