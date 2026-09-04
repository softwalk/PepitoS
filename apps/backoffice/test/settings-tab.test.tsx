import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { SettingsTab, parseSettingValue } from '../src/pages/SettingsTab';
import { ToastProvider } from '../src/components/Toast';
import type { Setting } from '../src/types';

const settings: Setting[] = [
  { key: 'cash_difference_threshold_cents', value: 2000, type: 'int', default: 2000, description: 'Diferencia de caja (centavos) a partir de la cual se abre un caso', updated_at: '2026-09-04T05:22:05Z', updated_by: null },
  { key: 'photo_sampling_pct', value: 25, type: 'int', default: 10, description: 'Porcentaje de aperturas con foto', updated_at: '2026-09-04T06:00:00Z', updated_by: 'aaaaaaaa-0000-0000-0000-000000000000' },
];

function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

describe('SettingsTab (Parámetros)', () => {
  const puts: { path: string; body: unknown }[] = [];
  beforeEach(() => {
    puts.length = 0;
    localStorage.setItem('pepito.backoffice.session', JSON.stringify({ token: 't', user: { id: 'u', name: 'Admin', role: 'admin', zone_id: null }, expiresAt: Date.now() + 100000 }));
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      const path = String(url);
      if (path === '/v1/admin/settings' && (init?.method ?? 'GET') === 'GET') return json(200, settings);
      if (path.startsWith('/v1/admin/settings/') && init?.method === 'PUT') {
        const body = JSON.parse(String(init.body)) as { value: unknown };
        const key = path.split('/').pop()!;
        puts.push({ path, body });
        if (key === 'photo_sampling_pct' && typeof body.value === 'number' && body.value > 100) return json(422, { error: { code: 'VALIDATION', message: 'photo_sampling_pct debe ser ≤ 100', details: { key, max: 100 } } });
        const s = settings.find((x) => x.key === key)!;
        return json(200, { ...s, value: body.value, updated_at: '2026-09-04T07:00:00Z', updated_by: 'u' });
      }
      return json(404, { error: { code: 'NOT_FOUND', message: 'no' } });
    }));
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  const mount = (canEdit: boolean) =>
    render(
      <MemoryRouter>
        <ToastProvider>
          <SettingsTab canEdit={canEdit} />
        </ToastProvider>
      </MemoryRouter>,
    );

  it('renderiza descripción, valor, default y última actualización', async () => {
    mount(true);
    await waitFor(() => expect(screen.getByTestId('settings-table')).toBeInTheDocument());
    const row = screen.getByTestId('setting-photo_sampling_pct');
    expect(row).toHaveTextContent('Porcentaje de aperturas con foto');
    expect(within(row).getByLabelText('Valor de photo_sampling_pct')).toHaveValue(25);
    expect(within(row).getByText('10')).toBeInTheDocument(); // default
    expect(row).toHaveTextContent('aaaaaaaa');
    expect(screen.getByTestId('setting-cash_difference_threshold_cents')).toHaveTextContent('por defecto');
  });

  it('guarda por fila con PUT y refleja el valor devuelto', async () => {
    mount(true);
    const row = await screen.findByTestId('setting-cash_difference_threshold_cents');
    const input = within(row).getByLabelText('Valor de cash_difference_threshold_cents');
    const save = within(row).getByTestId('save-cash_difference_threshold_cents');
    expect(save).toBeDisabled();
    fireEvent.change(input, { target: { value: '3000' } });
    expect(save).toBeEnabled();
    fireEvent.click(save);
    await waitFor(() => expect(puts).toHaveLength(1));
    expect(puts[0]).toEqual({ path: '/v1/admin/settings/cash_difference_threshold_cents', body: { value: 3000 } });
    await waitFor(() => expect(screen.getByText('Parámetro cash_difference_threshold_cents guardado')).toBeInTheDocument());
    expect(input).toHaveValue(3000);
    expect(save).toBeDisabled();
    expect(row).not.toHaveTextContent('por defecto');
  });

  it('muestra el 422 del servidor como toast y no acepta valores no enteros', async () => {
    mount(true);
    const row = await screen.findByTestId('setting-photo_sampling_pct');
    const input = within(row).getByLabelText('Valor de photo_sampling_pct');
    fireEvent.change(input, { target: { value: '150' } });
    fireEvent.click(within(row).getByTestId('save-photo_sampling_pct'));
    await waitFor(() => expect(screen.getByText('photo_sampling_pct debe ser ≤ 100')).toBeInTheDocument());
    expect(input).toHaveValue(150);
    fireEvent.change(input, { target: { value: '12.5' } });
    expect(within(row).getByTestId('save-photo_sampling_pct')).toBeDisabled();
    expect(input).toHaveAttribute('aria-invalid', 'true');
  });

  it('sólo lectura para ops/finance', async () => {
    mount(false);
    const row = await screen.findByTestId('setting-photo_sampling_pct');
    expect(within(row).queryByLabelText('Valor de photo_sampling_pct')).not.toBeInTheDocument();
    expect(within(row).queryByTestId('save-photo_sampling_pct')).not.toBeInTheDocument();
    expect(row).toHaveTextContent('25');
    expect(screen.getByText(/Sólo lectura para tu rol/)).toBeInTheDocument();
  });

  it('parseSettingValue respeta el tipo', () => {
    expect(parseSettingValue('int', '42')).toBe(42);
    expect(parseSettingValue('int', '4.2')).toBeUndefined();
    expect(parseSettingValue('int', 'abc')).toBeUndefined();
    expect(parseSettingValue('float', '4.2')).toBe(4.2);
    expect(parseSettingValue('bool', 'true')).toBe(true);
    expect(parseSettingValue('bool', 'false')).toBe(false);
    expect(parseSettingValue('str', 'x')).toBe('x');
  });
});
