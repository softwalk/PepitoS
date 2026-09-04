import { beforeEach, describe, expect, it } from 'vitest';
import { resetDBForTests } from '../src/offline/db';
import { counts, enqueue, flush, listAll, remove, retryFailed } from '../src/offline/queue';
import type { SyncCommand, SyncResult } from '../src/types';

beforeEach(async () => {
  await resetDBForTests();
});

function okAll(cmds: SyncCommand[]): SyncResult[] {
  return cmds.map((c) => ({ idempotency_key: c.idempotency_key, status: 'ok', result: { id: c.idempotency_key } }));
}

describe('cola offline', () => {
  it('encola cifrado y descifra el payload en orden de creación', async () => {
    await enqueue('sale', { shift_id: 's1', n: 1 }, 'k1');
    await enqueue('waste', { shift_id: 's1', n: 2 }, 'k2');
    await enqueue('sale', { shift_id: 's1', n: 3 }, 'k3');
    const all = await listAll();
    expect(all.map((c) => c.idempotency_key)).toEqual(['k1', 'k2', 'k3']);
    expect(all[1].payload).toMatchObject({ shift_id: 's1', n: 2, idempotency_key: 'k2' });
    // El registro almacenado no contiene el payload en claro
    const { getDB } = await import('../src/offline/db');
    const raw = await (await getDB()).get('queue', 'k2');
    expect(raw).toBeDefined();
    expect(JSON.stringify(raw)).not.toContain('"n":2');
    expect(raw!.cipher.data.byteLength).toBeGreaterThan(0);
  });

  it('es idempotente: la misma clave no se encola dos veces', async () => {
    await enqueue('sale', { a: 1 }, 'dup');
    await enqueue('sale', { a: 2 }, 'dup');
    const all = await listAll();
    expect(all).toHaveLength(1);
    expect(all[0].payload).toMatchObject({ a: 1 });
  });

  it('envía en orden, elimina ok y duplicate, y conserva la clave de idempotencia en el envío', async () => {
    await enqueue('shift_open', { assignment_id: 'a' }, 'k1');
    await enqueue('sale', { shift_id: 'srv-1' }, 'k2');
    await enqueue('sale', { shift_id: 'srv-1' }, 'k3');
    const sent: SyncCommand[][] = [];
    const out = await flush({
      device_id: 'd',
      send: async (_d, cmds) => {
        sent.push(cmds);
        return {
          results: cmds.map((c) => ({ idempotency_key: c.idempotency_key, status: c.idempotency_key === 'k2' ? 'duplicate' : 'ok' })),
        };
      },
    });
    expect(sent).toHaveLength(1);
    expect(sent[0].map((c) => c.idempotency_key)).toEqual(['k1', 'k2', 'k3']);
    expect(sent[0][1].payload.idempotency_key).toBe('k2');
    expect(out).toMatchObject({ sent: 3, ok: 2, duplicate: 1, error: 0, networkFailed: false });
    expect(await counts()).toEqual({ pending: 0, failed: 0 });
  });

  it('marca como fallido un error no reintentable y sigue con los demás', async () => {
    await enqueue('sale', { shift_id: 's' }, 'bad');
    await enqueue('sale', { shift_id: 's' }, 'good');
    const results: Array<[string, string]> = [];
    const out = await flush({
      device_id: 'd',
      send: async (_d, cmds) => ({
        results: cmds.map((c) =>
          c.idempotency_key === 'bad'
            ? { idempotency_key: c.idempotency_key, status: 'error' as const, code: 'VALIDATION', message: 'Datos inválidos' }
            : { idempotency_key: c.idempotency_key, status: 'ok' as const },
        ),
      }),
      onResult: (cmd, r) => {
        results.push([cmd.idempotency_key, r.status]);
      },
    });
    expect(out.error).toBe(1);
    expect(out.ok).toBe(1);
    expect(results).toEqual([
      ['bad', 'error'],
      ['good', 'ok'],
    ]);
    expect(await counts()).toEqual({ pending: 0, failed: 1 });
    const all = await listAll();
    expect(all[0].status).toBe('failed');
    expect(all[0].last_error?.code).toBe('VALIDATION');
    // Reintentar: vuelve a pendiente
    expect(await retryFailed()).toBe(1);
    expect(await counts()).toEqual({ pending: 1, failed: 0 });
  });

  it('ante fallo de red no borra nada y aumenta intentos', async () => {
    await enqueue('sale', { shift_id: 's' }, 'k1');
    const out = await flush({
      device_id: 'd',
      send: async () => {
        throw new Error('offline');
      },
    });
    expect(out.networkFailed).toBe(true);
    const all = await listAll();
    expect(all).toHaveLength(1);
    expect(all[0].attempts).toBe(1);
    expect(all[0].status).toBe('pending');
  });

  it('resuelve shift_id local tras confirmar shift_open en el mismo flush', async () => {
    await enqueue('shift_open', { assignment_id: 'a' }, 'open');
    await enqueue('sale', { shift_id: 'local:abc' }, 's1');
    await enqueue('gps_ping', { pings: [{ shift_id: 'local:abc', lat: 1, lng: 2 }] }, 'g1');
    let serverId: string | null = null;
    const batches: SyncCommand[][] = [];
    const out = await flush({
      device_id: 'd',
      send: async (_d, cmds) => {
        batches.push(cmds);
        return { results: cmds.map((c) => ({ idempotency_key: c.idempotency_key, status: 'ok' as const, result: c.type === 'shift_open' ? { shift_id: 'srv-9' } : {} })) };
      },
      resolveShiftId: (local) => (local === 'local:abc' ? serverId : null),
      onResult: (cmd, r) => {
        if (cmd.type === 'shift_open') serverId = String((r.result as { shift_id: string }).shift_id);
      },
    });
    expect(batches).toHaveLength(2);
    expect(batches[0].map((c) => c.type)).toEqual(['shift_open']);
    expect(batches[1].map((c) => c.type)).toEqual(['sale', 'gps_ping']);
    expect(batches[1][0].payload.shift_id).toBe('srv-9');
    expect((batches[1][1].payload.pings as { shift_id: string }[])[0].shift_id).toBe('srv-9');
    expect(out.ok).toBe(3);
    expect(await counts()).toEqual({ pending: 0, failed: 0 });
  });

  it('remove elimina de la cola (deshacer antes de sincronizar)', async () => {
    await enqueue('sale', { shift_id: 's' }, 'k1');
    await remove('k1');
    expect(await counts()).toEqual({ pending: 0, failed: 0 });
    const out = await flush({ device_id: 'd', send: async (_d, cmds) => ({ results: okAll(cmds) }) });
    expect(out.sent).toBe(0);
  });
});
