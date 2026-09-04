import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { EvidenceGallery } from '../src/components/EvidenceGallery';
import type { Evidence } from '../src/types';

const relative: Evidence = { id: 'e1', kind: 'audit', entity: 'audit', entity_id: 'a1', content_type: 'image/jpeg', size_bytes: 123456, sha256: 'a'.repeat(64), taken_at: '2026-09-04T15:00:00Z', url: '/v1/evidence/e1/file' };
const absolute: Evidence = { id: 'e2', kind: 'shift_open', entity: 'shift', entity_id: 's1', content_type: 'image/png', size_bytes: 2048, sha256: 'b'.repeat(64), taken_at: '2026-09-04T14:00:00Z', url: 'https://bucket.example.com/e2.png?X-Amz-Signature=abc' };

describe('EvidenceGallery', () => {
  const createObjectURL = vi.fn(() => 'blob:mock-e1');
  const revokeObjectURL = vi.fn();
  beforeEach(() => {
    localStorage.setItem('pepito.backoffice.session', JSON.stringify({ token: 'tok-123', user: { id: 'u', name: 'Ops', role: 'ops', zone_id: null }, expiresAt: Date.now() + 100000 }));
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      if (String(url) === '/v1/evidence/e1/file') {
        const auth = (init?.headers as Record<string, string> | undefined)?.Authorization;
        if (auth !== 'Bearer tok-123') return new Response(JSON.stringify({ error: { code: 'AUTH_INVALID', message: 'sin token' } }), { status: 401 });
        return new Response(new Blob([new Uint8Array([0xff, 0xd8, 0xff])], { type: 'image/jpeg' }), { status: 200, headers: { 'Content-Type': 'image/jpeg' } });
      }
      return new Response(JSON.stringify({ error: { code: 'NOT_FOUND', message: 'no' } }), { status: 404 });
    }));
    Object.defineProperty(URL, 'createObjectURL', { value: createObjectURL, configurable: true });
    Object.defineProperty(URL, 'revokeObjectURL', { value: revokeObjectURL, configurable: true });
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    localStorage.clear();
    createObjectURL.mockClear();
    revokeObjectURL.mockClear();
  });

  it('resuelve URLs relativas con Bearer → blob, usa las absolutas directas y revoca al desmontar', async () => {
    const { unmount } = render(<EvidenceGallery items={[relative, absolute]} />);
    await waitFor(() => expect(screen.getByTestId('evidence-thumb-e1').querySelector('img')).toHaveAttribute('src', 'blob:mock-e1'));
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('evidence-thumb-e2').querySelector('img')).toHaveAttribute('src', absolute.url);
    expect(screen.getByText('121 KB')).toBeInTheDocument();
    expect(screen.getByText('2 KB')).toBeInTheDocument();
    unmount();
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:mock-e1');
  });

  it('abre el visor modal con fecha y tamaño al hacer clic en la miniatura', async () => {
    render(<EvidenceGallery items={[relative]} />);
    const thumb = await screen.findByTestId('evidence-thumb-e1');
    await waitFor(() => expect(thumb).not.toBeDisabled());
    fireEvent.click(thumb);
    const viewer = screen.getByTestId('evidence-viewer');
    expect(viewer.querySelector('img')).toHaveAttribute('src', 'blob:mock-e1');
    expect(viewer).toHaveTextContent('Tamaño: 121 KB');
    expect(viewer).toHaveTextContent('Tomada:');
    expect(viewer).toHaveTextContent('image/jpeg');
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('Cerrar'));
    expect(screen.queryByTestId('evidence-viewer')).not.toBeInTheDocument();
  });

  it('muestra error cuando el archivo no se puede descargar y vacío sin evidencias', async () => {
    render(<EvidenceGallery items={[{ ...relative, id: 'e3', url: '/v1/evidence/e3/file' }]} />);
    await waitFor(() => expect(screen.getByTestId('evidence-thumb-e3')).toBeDisabled());
    expect(screen.getByTestId('evidence-thumb-e3')).toHaveTextContent('⚠︎');
    render(<EvidenceGallery items={[]} emptyText="Nada" />);
    expect(screen.getByText('Nada')).toBeInTheDocument();
  });
});
