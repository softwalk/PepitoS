// Mejoras v2 del backoffice: dedupe de alertas, tabla ordenable con selector de columnas, chip de SLA, estados y tema.
import { describe, expect, it, afterEach } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { dedupeAlerts } from '../src/pages/ControlTower';
import { DataTable } from '../src/components/DataTable';
import { SlaChip } from '../src/components/ui';
import { StateBox, stateFromError } from '../src/components/State';
import { ApiError } from '../src/api/client';
import { applyTheme, setDensity, setTheme } from '../src/lib/theme';

afterEach(() => cleanup());

describe('dedupeAlerts', () => {
  it('agrupa alertas iguales y conserva la más reciente', () => {
    const rows = dedupeAlerts([
      { id: '1', rule_key: 'no_open', message: 'Punto sin abrir: A', raised_at: '2026-09-07T10:00:00Z' },
      { id: '2', rule_key: 'no_open', message: 'Punto sin abrir: A', raised_at: '2026-09-07T11:00:00Z' },
      { id: '3', rule_key: 'high_waste', message: 'Merma alta: B', raised_at: '2026-09-07T09:00:00Z' },
    ]);
    expect(rows).toHaveLength(2);
    expect(rows[0].a.id).toBe('2');
    expect(rows[0].n).toBe(2);
  });
});

describe('DataTable', () => {
  const rows = [
    { id: 'a', name: 'Alameda', sales: 100 },
    { id: 'b', name: 'Buenavista', sales: 300 },
    { id: 'c', name: 'Centro', sales: 200 },
  ];
  it('ordena por columna, oculta columnas y muestra detalle', () => {
    render(
      <MemoryRouter>
        <DataTable columns={[{ key: 'name', label: 'Punto' }, { key: 'sales', label: 'Ventas', numeric: true }]} rows={rows} rowKey={(r) => r.id} detail={(r) => <span>Detalle {r.name}</span>} testId="dt" />
      </MemoryRouter>,
    );
    const cells = () => screen.getAllByRole('row').slice(1).map((r) => r.querySelector('td')?.textContent);
    expect(cells()).toEqual(['Alameda', 'Buenavista', 'Centro']);
    fireEvent.click(screen.getByText('Ventas'));
    expect(cells()).toEqual(['Buenavista', 'Centro', 'Alameda']);
    fireEvent.click(screen.getByText('Ventas'));
    expect(cells()).toEqual(['Alameda', 'Centro', 'Buenavista']);
    fireEvent.click(screen.getByTestId('col-picker'));
    fireEvent.click(screen.getByLabelText('Ventas'));
    expect(screen.queryByText('300')).toBeNull();
    fireEvent.click(screen.getByText('Centro'));
    expect(screen.getByText('Detalle Centro')).toBeTruthy();
  });
});

describe('SlaChip y estados', () => {
  it('muestra restante, vencido y tomado', () => {
    render(<div><SlaChip sla={{ remaining_min: 90, breached: false, taken: false, minutes: 240 }} /><SlaChip sla={{ remaining_min: -5, breached: true, taken: false, minutes: 15 }} /><SlaChip sla={{ remaining_min: 3, breached: false, taken: true, minutes: 15 }} /></div>);
    expect(screen.getByText('SLA 1 h 30 min')).toBeTruthy();
    expect(screen.getByText('SLA vencido')).toBeTruthy();
    expect(screen.getByText('SLA ok')).toBeTruthy();
  });
  it('clasifica errores y renderiza el estado correcto', () => {
    expect(stateFromError(new ApiError(403, 'FORBIDDEN', 'No tienes permiso'))).toBe('forbidden');
    expect(stateFromError(new ApiError(0, 'NETWORK', 'Sin conexión con el servidor'))).toBe('offline');
    expect(stateFromError(new Error('Sin conexión con el servidor'))).toBe('offline');
    expect(stateFromError(new Error('boom'))).toBe('error');
    render(<StateBox kind="offline" />);
    expect(screen.getByTestId('state-offline').textContent).toContain('Sin conexión');
  });
  it('aplica tema y densidad al documento', () => {
    setTheme('dark');
    setDensity('compact');
    applyTheme();
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
    expect(document.documentElement.getAttribute('data-density')).toBe('compact');
    setTheme('light');
    setDensity('normal');
  });
});
