// "Continuar turno": sólo admin, sólo turnos con shift_status=closed y sólo con la fecha de hoy seleccionada.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ControlTowerPage } from '../src/pages/ControlTower';
import { AuthProvider } from '../src/state/auth';
import { ToastProvider } from '../src/components/Toast';
import { todayLocalISO } from '../src/lib/format';
import type { PointStatus, Summary } from '../src/types';

vi.mock('../src/components/PointsMap', () => ({ PointsMap: () => <div data-testid="map-mock" />, RouteMap: () => <div /> }));

function point(id: string, name: string, status: PointStatus['status'], shift_status: PointStatus['shift_status']): PointStatus {
  return {
    point: { id, name, lat: 0, lng: 0, zone_id: null }, status, shift_id: `s-${id}`, shift_status, operator: { id: 'u', name: 'Op' }, opened_at: null, last_seen_at: null, last_gps: null,
    battery_pct: null, sales_cents: 0, target_cents: 1000, tx: 0, ticket_cents: 0, cash_status: 'ok', stock_risk: 'ok', open_cases: { urgent: 0, review: 0 }, planned_start: '2026-09-04T14:00:00Z',
  } as PointStatus;
}

function summaryFor(date: string): Summary {
  return {
    date,
    totals: { points: 2, open: 0, late: 0, closed: 2, offline: 0, sales_cents: 0, target_cents: 2000, tx: 0, ticket_cents: 0, forecast_close_cents: 0 },
    exceptions: { urgent: 0, review: 0, normal: 0 },
    points: [point('p1', 'Cerrado Hoy', 'closed', 'closed'), point('p2', 'Transferido', 'closed', 'transferred')],
    alerts_recent: [],
  } as Summary;
}

function mount(role: string) {
  localStorage.setItem('pepito.backoffice.session', JSON.stringify({ token: 't', user: { id: 'u', name: 'Admin', role, zone_id: null }, expiresAt: Date.now() + 100000 }));
  render(
    <MemoryRouter>
      <ToastProvider>
        <AuthProvider>
          <ControlTowerPage />
        </AuthProvider>
      </ToastProvider>
    </MemoryRouter>,
  );
}

describe('Continuar turno en Control Tower', () => {
  const posts: string[] = [];
  beforeEach(() => {
    posts.length = 0;
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      const u = String(url);
      if (u.startsWith('/v1/control-tower/summary')) return new Response(JSON.stringify(summaryFor(new URL(u, 'http://x').searchParams.get('date') ?? '')), { status: 200, headers: { 'Content-Type': 'application/json' } });
      if (u.match(/\/v1\/shifts\/.+\/reopen$/) && init?.method === 'POST') {
        posts.push(u + ' ' + String(init.body));
        return new Response(JSON.stringify({ id: 's-p1', status: 'open' }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      return new Response(JSON.stringify({ error: { code: 'NOT_FOUND', message: 'no' } }), { status: 404 });
    }));
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it('admin: botón sólo en el turno cerrado (no en el transferido) y envía el motivo', async () => {
    mount('admin');
    await waitFor(() => expect(screen.getByTestId('points-table')).toBeInTheDocument());
    expect(screen.getByTestId('reopen-shift-s-p1')).toBeInTheDocument();
    expect(screen.queryByTestId('reopen-shift-s-p2')).toBeNull();
    fireEvent.click(screen.getByTestId('reopen-shift-s-p1'));
    const confirm = screen.getByTestId('reopen-shift-confirm') as HTMLButtonElement;
    expect(confirm.disabled).toBe(true); // motivo obligatorio
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Cerró por error a media jornada' } });
    expect(confirm.disabled).toBe(false);
    fireEvent.click(confirm);
    await waitFor(() => expect(posts.length).toBe(1));
    expect(posts[0]).toContain('/v1/shifts/s-p1/reopen');
    expect(posts[0]).toContain('Cerró por error');
  });

  it('ops no ve el botón', async () => {
    mount('ops');
    await waitFor(() => expect(screen.getByTestId('points-table')).toBeInTheDocument());
    expect(screen.queryByTestId('reopen-shift-s-p1')).toBeNull();
  });

  it('con otra fecha seleccionada no se ofrece', async () => {
    mount('admin');
    await waitFor(() => expect(screen.getByTestId('reopen-shift-s-p1')).toBeInTheDocument());
    const yesterday = new Date(todayLocalISO() + 'T12:00:00');
    yesterday.setDate(yesterday.getDate() - 1);
    fireEvent.change(screen.getByLabelText('Fecha'), { target: { value: yesterday.toISOString().slice(0, 10) } });
    await waitFor(() => expect(screen.queryByTestId('reopen-shift-s-p1')).toBeNull());
  });
});
