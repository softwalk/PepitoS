import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ControlTowerPage } from '../src/pages/ControlTower';
import { AuthProvider } from '../src/state/auth';
import { ToastProvider } from '../src/components/Toast';
import type { Summary } from '../src/types';

// Leaflet necesita un DOM real con layout; en jsdom sustituimos el mapa por un marcador.
vi.mock('../src/components/PointsMap', () => ({
  PointsMap: ({ points }: { points: unknown[] }) => <div data-testid="map-mock">mapa {points.length} puntos</div>,
  RouteMap: () => <div />,
}));

const summary: Summary = {
  date: '2026-09-03',
  totals: { points: 3, open: 2, late: 1, closed: 0, offline: 0, sales_cents: 154000, target_cents: 702000, tx: 40, ticket_cents: 3850, forecast_close_cents: 420000 },
  exceptions: { urgent: 2, review: 3, normal: 0 },
  points: [
    {
      point: { id: 'p1', name: 'Metro Insurgentes', lat: 19.42, lng: -99.16, zone_id: 'z' },
      status: 'open', shift_id: 's1', operator: { id: 'u1', name: 'Operador Uno' }, opened_at: '2026-09-03T14:05:00Z', last_seen_at: '2026-09-03T15:00:00Z',
      last_gps: { lat: 19.42, lng: -99.16, at: '2026-09-03T15:00:00Z', in_geofence: true }, battery_pct: 80, sales_cents: 120000, target_cents: 234000, tx: 30, ticket_cents: 4000,
      cash_status: 'pending', stock_risk: 'ok', open_cases: { urgent: 0, review: 1 }, planned_start: '2026-09-03T14:00:00Z',
    },
    {
      point: { id: 'p2', name: 'Parque México', lat: 19.41, lng: -99.17, zone_id: 'z' },
      status: 'late', shift_id: null, operator: { id: 'u2', name: 'Operador Dos' }, opened_at: null, last_seen_at: null, last_gps: null, battery_pct: null,
      sales_cents: 0, target_cents: 234000, tx: 0, ticket_cents: 0, cash_status: 'pending', stock_risk: 'low', open_cases: { urgent: 1, review: 0 }, planned_start: '2026-09-03T14:00:00Z',
    },
  ],
  alerts_recent: [{ id: 'a1', rule_key: 'no_open', severity: 'urgent', status: 'open', message: 'Punto sin abrir: Parque México', point_id: 'p2', shift_id: null, case_id: 'c1', raised_at: '2026-09-03T14:25:00Z', resolved_at: null }],
};

describe('ControlTowerPage', () => {
  beforeEach(() => {
    localStorage.setItem('pepito.backoffice.session', JSON.stringify({ token: 't', user: { id: 'u', name: 'Ops', role: 'ops', zone_id: null }, expiresAt: Date.now() + 100000 }));
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (String(url).startsWith('/v1/control-tower/summary')) return new Response(JSON.stringify(summary), { status: 200, headers: { 'Content-Type': 'application/json' } });
      return new Response(JSON.stringify({ error: { code: 'NOT_FOUND', message: 'no' } }), { status: 404 });
    }));
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it('muestra KPIs, semáforos, excepciones y la tabla de puntos', async () => {
    render(
      <MemoryRouter>
        <ToastProvider>
          <AuthProvider>
            <ControlTowerPage />
          </AuthProvider>
        </ToastProvider>
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByTestId('points-table')).toBeInTheDocument());
    expect(screen.getByText('Metro Insurgentes')).toBeInTheDocument();
    expect(screen.getByText('Parque México')).toBeInTheDocument();
    expect(screen.getByText('$1,540')).toBeInTheDocument(); // ventas hoy
    expect(screen.getByText('$38.50')).toBeInTheDocument(); // ticket promedio (ámbar)
    expect(screen.getByTestId('kpi-Ticket promedio').className).toContain('tone-amber');
    expect(screen.getByTestId('kpi-Ventas hoy').className).toContain('tone-red');
    expect(screen.getByRole('link', { name: /2\s*URGENTE/ })).toBeInTheDocument();
    expect(screen.getByText('Punto sin abrir: Parque México')).toBeInTheDocument();
    expect(screen.getByTestId('map-mock')).toHaveTextContent('2 puntos');
    expect(screen.getByRole('button', { name: 'Ejecutar reglas ahora' })).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/v1/control-tower/summary?date='), expect.objectContaining({ headers: expect.objectContaining({ Authorization: 'Bearer t' }) }));
  });
});
