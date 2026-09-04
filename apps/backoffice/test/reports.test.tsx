// Módulo de Reportes: formato/semaforos/filtros en URL, Centro de Reportes por rol y página de reporte con filtros en la URL.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { ReportsPage } from '../src/pages/Reports';
import { ReportViewPage } from '../src/pages/ReportView';
import { AuthProvider } from '../src/state/auth';
import { ToastProvider } from '../src/components/Toast';
import { columnLight, filtersFrom, filtersToQuery, fmtValue } from '../src/lib/reports';
import type { ReportCatalog, ReportPayload } from '../src/types';

vi.mock('recharts', async () => {
  const actual = await vi.importActual<typeof import('recharts')>('recharts');
  return { ...actual, ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div data-testid="chart">{children}</div> };
});

describe('lib/reports', () => {
  it('formatea valores según el formato declarado', () => {
    expect(fmtValue(490000, 'money')).toBe('$4,900');
    expect(fmtValue(3500, 'money')).toBe('$35.00');
    expect(fmtValue(12345678, 'money')).toBe('$123,457');
    expect(fmtValue(85.7, 'pct')).toBe('85.7%');
    expect(fmtValue(-18, 'delta')).toBe('-18 %');
    expect(fmtValue(3.4, 'delta')).toBe('+3.4 %');
    expect(fmtValue(null, 'int')).toBe('—');
  });
  it('semáforos por columna', () => {
    expect(columnLight('target', 100)).toBe('green');
    expect(columnLight('target', 74.9)).toBe('red');
    expect(columnLight('ticket', 3700)).toBe('amber');
    expect(columnLight('waste', 5)).toBe('red');
    expect(columnLight('diff', -5000)).toBe('red');
    expect(columnLight('avail', 96)).toBe('green');
    expect(columnLight('target', null)).toBeNull();
  });
  it('filtros ↔ URL', () => {
    const f = filtersFrom(new URLSearchParams('period=last7&point_id=p1&foo=bar'));
    expect(f).toEqual({ period: 'last7', point_id: 'p1' });
    expect(filtersToQuery(f)).toBe('?period=last7&point_id=p1');
    expect(filtersToQuery({})).toBe('');
  });
});

const catalog: ReportCatalog = {
  categories: [
    { name: 'Comercial', reports: [{ key: 'sales', title: 'Ventas y desempeño comercial', description: 'd', decision: 'x', frequency: 'Diaria', orientation: 'landscape', scope: 'zone' }] },
    { name: 'Finanzas', reports: [{ key: 'cash', title: 'Caja y conciliación', description: 'd', decision: 'x', frequency: 'Diaria', orientation: 'landscape', scope: 'zone' }] },
  ],
  presets: [],
};

function payload(period: string, pointId: string | null): ReportPayload {
  return {
    key: 'sales', title: 'Ventas y desempeño comercial', category: 'Comercial', description: 'desc', decision: 'x', frequency: 'Diaria', orientation: 'landscape', generated_at: '2026-09-04T20:00:00Z',
    period: { preset: period, preset_label: period === 'last7' ? 'Últimos 7 días' : 'Hoy', from: '2026-09-04', to: '2026-09-04', label: '04/09/2026', days: 1, start: '', end: '' },
    compare: { preset: 'previous', preset_label: '', from: '2026-09-03', to: '2026-09-03', label: '03/09/2026', days: 1, start: '', end: '' },
    filters: pointId ? { point_id: pointId } : {},
    scope: { role: 'supervisor', zone_id: 'z1', operator_id: null, point_id: pointId, cart_id: null, presentation_id: null, method: null, zone_locked: true, operator_locked: false },
    kpis: [
      { key: 'sales', label: 'Ventas', value: pointId ? 49000 : 123400, format: 'money', prev: 100000, delta_pct: 23.4, delta_abs: 23400, trend: 'up', tone: 'ok', hint: null },
      { key: 'ticket', label: 'Ticket promedio', value: 3500, format: 'money', prev: null, delta_pct: null, delta_abs: null, trend: 'flat', tone: 'bad', hint: 'bajo' },
    ],
    charts: [{ key: 'trend', title: 'Ventas por día', type: 'bar', x: 'label', data: [{ label: '04/09', sales_cents: 49000 }], series: [{ key: 'sales_cents', label: 'Ventas', format: 'money' }] }],
    tables: [{ key: 'points', title: 'Por punto', columns: [{ key: 'point', label: 'Punto', format: 'text', link: '/reportes/points?point_id={point_id}' }, { key: 'target_pct', label: 'vs meta', format: 'pct', tone: 'target' }], rows: [{ point_id: 'p1', point: 'Metro Insurgentes - 90', target_pct: 120 }] }],
    insights: [{ kind: 'alert', text: 'Ticket promedio $35 por debajo de $36 (rojo).', link: null }, { kind: 'recommendation', text: 'Empujar 75 g.', link: '/reportes/points' }],
    hidden: [],
  };
}

function LocationProbe() {
  const loc = useLocation();
  return <div data-testid="loc">{loc.pathname + loc.search}</div>;
}

function mount(path: string, role = 'supervisor') {
  localStorage.setItem('pepito.backoffice.session', JSON.stringify({ token: 't', user: { id: 'u', name: 'Sup', role, zone_id: 'z1' }, expiresAt: Date.now() + 100000 }));
  render(
    <MemoryRouter initialEntries={[path]}>
      <ToastProvider>
        <AuthProvider>
          <Routes>
            <Route path="/reportes" element={<ReportsPage />} />
            <Route path="/reportes/:key" element={<ReportViewPage />} />
          </Routes>
          <LocationProbe />
        </AuthProvider>
      </ToastProvider>
    </MemoryRouter>,
  );
}

describe('Centro de Reportes y página de reporte', () => {
  const calls: string[] = [];
  beforeEach(() => {
    calls.length = 0;
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      const u = String(url);
      calls.push(u);
      const json = (b: unknown) => new Response(JSON.stringify(b), { status: 200, headers: { 'Content-Type': 'application/json' } });
      if (u === '/v1/reports/bi') return json(catalog);
      if (u.startsWith('/v1/reports/bi/options')) return json({ zones: [{ id: 'z1', name: 'Centro' }], points: [{ id: 'p1', name: 'Metro Insurgentes - 90', zone_id: 'z1' }, { id: 'p2', name: 'Otro', zone_id: 'z2' }], operators: [], carts: [], presentations: [], methods: [] });
      if (u.startsWith('/v1/reports/bi/sales')) {
        const q = new URL(u, 'http://x').searchParams;
        return json(payload(q.get('period') ?? 'today', q.get('point_id')));
      }
      if (u.startsWith('/v1/reports/bi/cash')) return new Response(JSON.stringify({ error: { code: 'FORBIDDEN', message: 'No tienes permiso para esta acción' } }), { status: 403 });
      return new Response(JSON.stringify({ error: { code: 'NOT_FOUND', message: 'no' } }), { status: 404 });
    }));
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it('muestra sólo los reportes que devuelve la API, por categoría', async () => {
    mount('/reportes');
    await screen.findByTestId('report-tile-sales');
    expect(screen.getByTestId('report-tile-cash')).toBeTruthy();
    expect(screen.queryByTestId('report-tile-executive')).toBeNull();
    expect(screen.getByTestId('report-category-Comercial')).toBeTruthy();
    expect(screen.getAllByText('Tu zona', { selector: '.badge' })).toHaveLength(2);
  });

  it('renderiza KPIs, hallazgos, gráfica y tabla; los filtros cambian la URL y recargan', async () => {
    mount('/reportes/sales?period=today');
    await screen.findByTestId('report-kpis');
    expect(screen.getByText('$1,234')).toBeTruthy();
    expect(screen.getByText('↑ +23 %')).toBeTruthy();
    expect(screen.getByText('Alerta')).toBeTruthy();
    expect(screen.getByText('Recomendación')).toBeTruthy();
    expect(screen.getByTestId('chart')).toBeTruthy();
    expect(screen.getByText('Metro Insurgentes - 90', { selector: 'td a' }).closest('a')?.getAttribute('href')).toBe('/reportes/points?point_id=p1');
    expect(screen.getByText('Alcance: tu zona')).toBeTruthy();
    expect((screen.getByTestId('filter-zone_id') as HTMLSelectElement).disabled).toBe(true);
    expect(screen.getByTestId('export-pdf').getAttribute('href')).toBe('/reportes/sales/imprimir?period=today');

    fireEvent.click(screen.getByRole('tab', { name: 'Últimos 7 días' }));
    await waitFor(() => expect(screen.getByTestId('loc').textContent).toBe('/reportes/sales?period=last7'));
    await screen.findByText('Últimos 7 días: 04/09/2026');

    fireEvent.change(screen.getByTestId('filter-point_id'), { target: { value: 'p1' } });
    await waitFor(() => expect(screen.getByTestId('loc').textContent).toBe('/reportes/sales?period=last7&point_id=p1'));
    await screen.findByText('$490.00');
    expect(calls.some((c) => c.includes('/v1/reports/bi/sales?period=last7&point_id=p1'))).toBe(true);
    // Sólo puntos de la zona en el selector
    expect(Array.from((screen.getByTestId('filter-point_id') as HTMLSelectElement).options).map((o) => o.value)).toEqual(['', 'p1']);
    fireEvent.click(screen.getByText('Limpiar filtros'));
    await waitFor(() => expect(screen.getByTestId('loc').textContent).toBe('/reportes/sales?period=last7'));
  });

  it('un 403 de la API se muestra como mensaje, nunca datos', async () => {
    mount('/reportes/cash?period=today');
    await screen.findByText('No tienes permiso para esta acción', { selector: '.empty' });
    expect(screen.queryByTestId('report-kpis')).toBeNull();
  });

  it('clave desconocida → vuelve al centro', async () => {
    mount('/reportes/nada');
    await waitFor(() => expect(screen.getByTestId('loc').textContent).toBe('/reportes'));
  });
});
