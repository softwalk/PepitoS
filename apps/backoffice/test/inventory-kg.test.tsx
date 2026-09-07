// Inventario en kilogramos y fotos de conteo/recepción con sello; ubicación del incidente en el detalle de caso.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { AuthProvider } from '../src/state/auth';
import { ToastProvider } from '../src/components/Toast';
import { InventoryPage } from '../src/pages/Inventory';
import { CaseDetailPage } from '../src/pages/CaseDetail';
import { fmtKg } from '../src/lib/format';

vi.mock('react-leaflet', () => ({
  MapContainer: ({ children }: { children?: unknown }) => <div data-testid="leaflet-map">{children as never}</div>,
  TileLayer: () => null,
  Marker: ({ children }: { children?: unknown }) => <div>{children as never}</div>,
  Popup: ({ children }: { children?: unknown }) => <span>{children as never}</span>,
  Polyline: () => null,
}));

const EVID = { id: 'e1', kind: 'inventory_count', entity: 'inventory_count', entity_id: 'c1', content_type: 'image/jpeg', size_bytes: 12345, sha256: 'abcdef0123456789', taken_at: '2026-09-07T14:05:09Z', url: 'https://files.local/e1.jpg' };

function mount(path: string, element: JSX.Element, role = 'ops') {
  localStorage.setItem('pepito.backoffice.session', JSON.stringify({ token: 't', user: { id: 'u', name: 'Ops', role, zone_id: null }, expiresAt: Date.now() + 100000 }));
  render(
    <MemoryRouter initialEntries={[path]}>
      <ToastProvider>
        <AuthProvider>
          <Routes>
            <Route path="/inventario" element={element} />
            <Route path="/excepciones/:id" element={element} />
          </Routes>
        </AuthProvider>
      </ToastProvider>
    </MemoryRouter>,
  );
}

describe('Inventario en kg y fotos', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      const u = String(url);
      const json = (b: unknown) => new Response(JSON.stringify(b), { status: 200, headers: { 'Content-Type': 'application/json' } });
      if (u.startsWith('/v1/inventory/status')) {
        return json({ min_units: 10, total_units: 108, total_kg: 8.03, points: [{ point: { id: 'p1', name: 'Metro Insurgentes' }, stock_risk: 'ok', total_units: 108, total_kg: 8.03,
          items: [{ presentation_id: 'a', name: '50 g', grams: 50, balance: 37, theoretical: 37, min_units: 10, kg: 1.85 }, { presentation_id: 'b', name: '75 g', grams: 75, balance: 37, theoretical: 37, min_units: 10, kg: 2.78 }, { presentation_id: 'c', name: '100 g', grams: 100, balance: 34, theoretical: 34, min_units: 10, kg: 3.4 }] }] });
      }
      if (u.startsWith('/v1/inventory/counts')) {
        return json({ days: 7, counts: [{ id: 'c1', occurred_at: '2026-09-07T14:05:09Z', kind: 'manual', shift_id: 's1', point: { id: 'p1', name: 'Metro Insurgentes' }, actor: { id: 'u1', name: 'Juan Operador' },
          counts: { a: 36, b: 37, c: 34 }, theoretical: { a: 37, b: 37, c: 34 }, differences: { a: -1, b: 0, c: 0 }, counted_units: 107, counted_kg: 7.98, expected_kg: 8.03, diff_units: 1, diff_kg: -0.05, evidence: [EVID] }] });
      }
      if (u.startsWith('/v1/inventory/receipts')) return json({ days: 7, receipts: [{ id: 'r1', occurred_at: '2026-09-07T09:00:00Z', shift_id: 's1', qr_code: 'ENT-1', point: { id: 'p1', name: 'Metro Insurgentes' }, actor: { id: 'u1', name: 'Juan Operador' }, lines: [{ presentation_id: 'a', qty: 4, lot_code: null }], units: 4, kg: 0.2, evidence: [] }] });
      if (u.startsWith('/v1/admin/presentations')) return json([{ id: 'a', name: '50 g', grams: 50, sort: 1, is_active: true, product_id: null }, { id: 'b', name: '75 g', grams: 75, sort: 2, is_active: true, product_id: null }, { id: 'c', name: '100 g', grams: 100, sort: 3, is_active: true, product_id: null }]);
      if (u.startsWith('/v1/cases/k1')) {
        return json({ id: 'k1', category: 'security', severity: 'urgent', status: 'open', title: 'Seguridad', description: 'Intento de robo', source: 'operator', point: { id: 'p1', name: 'Metro Insurgentes', lat: 19.4235, lng: -99.163 }, shift: null, operator: { id: 'u1', name: 'Juan' },
          opened_at: '2026-09-07T14:05:09Z', age_minutes: 5, priority_score: 90, impact_score: 40, assignee: null, actions: [], timeline: [], evidence: [{ ...EVID, id: 'e2', kind: 'help_case', entity: 'case', entity_id: 'k1' }], ai: null, resolution: null, tags: [],
          sla: { remaining_min: 10, breached: false, taken: false, minutes: 15 }, payload: { gps: { lat: 19.4231, lng: -99.1628, accuracy_m: 12.4, at: '2026-09-07T14:05:00Z' }, has_photo: true } });
      }
      return new Response(JSON.stringify({ error: { code: 'NOT_FOUND', message: 'no' } }), { status: 404 });
    }));
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it('fmtKg', () => {
    expect(fmtKg(8.03)).toBe('8.03 kg');
    expect(fmtKg(2)).toBe('2.00 kg');
    expect(fmtKg(0.2)).toBe('0.20 kg');
    expect(fmtKg(null)).toBe('—');
  });

  it('muestra kg por punto y total, conteos con kg/fotos y el detalle con la foto', async () => {
    mount('/inventario', <InventoryPage />);
    expect((await screen.findByTestId('kg-p1')).textContent).toBe('8.03 kg');
    expect(screen.getByTestId('kg-total').textContent).toBe('8.03 kg');
    expect(screen.getByText(/108 piezas = 8.03 kg en total/)).toBeTruthy();
    const row = await screen.findByTestId('count-row-c1');
    expect(row.textContent).toContain('7.98 kg');
    expect(row.textContent).toContain('📷 1');
    fireEvent.click(screen.getByTestId('count-open-c1'));
    const detail = await screen.findByTestId('count-detail');
    expect(detail.textContent).toContain('107 u. · 7.98 kg');
    expect(detail.textContent).toContain('-1');
    expect(screen.getByTestId('evidence-gallery')).toBeTruthy();
    expect(screen.getByTestId('evidence-thumb-e1')).toBeTruthy();
    expect(screen.getByTestId('receipts-card').textContent).toContain('0.20 kg');
  });

  it('abre el conteo indicado en ?count= (enlace desde el reporte)', async () => {
    mount('/inventario?count=c1', <InventoryPage />);
    expect((await screen.findByTestId('count-detail')).textContent).toContain('Juan Operador');
  });

  it('detalle de caso: ubicación del incidente con GPS y foto de AYUDA', async () => {
    mount('/excepciones/k1', <CaseDetailPage />);
    const loc = await screen.findByTestId('incident-location');
    expect(loc.textContent).toContain('GPS 19.42310, -99.16280 ±12 m');
    expect(screen.getByTestId('leaflet-map')).toBeTruthy();
    expect(screen.getByTestId('evidence-thumb-e2')).toBeTruthy();
  });
});
