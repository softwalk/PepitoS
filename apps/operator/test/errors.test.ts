import { describe, expect, it } from 'vitest';
import { ApiError, NetworkError } from '../src/api/client';
import { INSECURE_MESSAGE, friendlyError } from '../src/offline/errors';

describe('friendlyError: nunca texto técnico', () => {
  it('WebCrypto ausente (http://) → explicación en español', () => {
    expect(friendlyError(new TypeError(`can't access property "importKey", Do() is undefined`))).toBe(INSECURE_MESSAGE);
    expect(friendlyError(new TypeError("Cannot read properties of undefined (reading 'importKey')"))).toBe(INSECURE_MESSAGE);
    expect(friendlyError(new TypeError('crypto.subtle is undefined'))).toBe(INSECURE_MESSAGE);
  });
  it('sin señal, permisos, espacio', () => {
    expect(friendlyError(new NetworkError('Failed to fetch'))).toMatch(/No hay señal/);
    expect(friendlyError(new Error('QuotaExceededError: The quota has been exceeded.'))).toMatch(/espacio/);
    expect(friendlyError(new DOMException('denied', 'NotAllowedError'))).toMatch(/permiso/);
  });
  it('la API ya habla español; lo desconocido usa el texto neutro', () => {
    expect(friendlyError(new ApiError('SHIFT_NOT_OPEN', 'No hay turno abierto', 409))).toBe('No hay turno abierto');
    expect(friendlyError(new Error('boom xyz'))).toMatch(/Inténtalo de nuevo/);
    expect(friendlyError(new Error('boom xyz'), 'Otro texto')).toBe('Otro texto');
    expect(friendlyError(new Error('boom xyz'))).not.toMatch(/boom/);
  });
});
