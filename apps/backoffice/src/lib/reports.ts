// Módulo de Reportes: filtros en la URL, formato de valores y semáforos por columna (docs/REPORTES.md).
import { money, pct, targetLight, ticketLight, wasteLight, type Light } from './format';
import type { ReportPreset, Tone, ValueFormat } from '../types';

export const FILTER_KEYS = ['period', 'from', 'to', 'zone_id', 'point_id', 'operator_id', 'cart_id', 'presentation_id', 'method'] as const;
export type FilterKey = (typeof FILTER_KEYS)[number];
export type Filters = Partial<Record<FilterKey, string>>;

export const PRESETS: { key: ReportPreset; label: string }[] = [
  { key: 'today', label: 'Hoy' },
  { key: 'yesterday', label: 'Ayer' },
  { key: 'last7', label: 'Últimos 7 días' },
  { key: 'week', label: 'Semana actual' },
  { key: 'month', label: 'Mes actual' },
  { key: 'prev_month', label: 'Mes anterior' },
  { key: 'year', label: 'Año actual' },
  { key: 'custom', label: 'Rango' },
];

export function filtersFrom(params: URLSearchParams): Filters {
  const out: Filters = {};
  for (const k of FILTER_KEYS) {
    const v = params.get(k);
    if (v) out[k] = v;
  }
  return out;
}

export function filtersToQuery(f: Filters): string {
  const parts = FILTER_KEYS.filter((k) => f[k]).map((k) => `${k}=${encodeURIComponent(f[k] as string)}`);
  return parts.length ? `?${parts.join('&')}` : '';
}

/** Formato de un valor según el `format` declarado por la API. Dinero siempre en centavos. */
export function fmtValue(v: unknown, format: ValueFormat): string {
  if (v === null || v === undefined || v === '') return '—';
  switch (format) {
    case 'money':
      return money(Number(v), { decimals: Math.abs(Number(v)) >= 100000 ? 0 : 2 });
    case 'pct':
      return pct(Number(v), Number.isInteger(Number(v)) ? 0 : 1);
    case 'int':
      return Number(v).toLocaleString('es-MX', { maximumFractionDigits: 0 });
    case 'float':
      return Number(v).toLocaleString('es-MX', { maximumFractionDigits: 1 });
    case 'delta': {
      const n = Number(v);
      const sign = n > 0 ? '+' : '';
      return `${sign}${n.toFixed(Math.abs(n) >= 10 ? 0 : 1)} %`;
    }
    default:
      return String(v);
  }
}

export function toneToLight(t: Tone): Light | null {
  return t === 'ok' ? 'green' : t === 'warn' ? 'amber' : t === 'bad' ? 'red' : null;
}

/** Semáforo por columna (PRD §15 + reglas del módulo). */
export function columnLight(kind: string | undefined, v: unknown): Light | null {
  if (v === null || v === undefined || kind === undefined) return null;
  const n = Number(v);
  if (Number.isNaN(n)) return null;
  switch (kind) {
    case 'target':
      return targetLight(n);
    case 'ticket':
      return ticketLight(n);
    case 'waste':
      return wasteLight(n);
    case 'diff':
      return n === 0 ? 'green' : Math.abs(n) < 2000 ? 'amber' : 'red';
    case 'days':
      return n >= 3 ? 'green' : n >= 1.5 ? 'amber' : 'red';
    case 'avail':
      return n >= 95 ? 'green' : n >= 85 ? 'amber' : 'red';
    default:
      return null;
  }
}

export const INSIGHT_LABEL: Record<string, string> = { fact: 'Hecho', trend: 'Tendencia', alert: 'Alerta', hypothesis: 'Hipótesis', recommendation: 'Recomendación' };
export const INSIGHT_TONE: Record<string, string> = { fact: 'blue', trend: 'gray', alert: 'red', hypothesis: 'amber', recommendation: 'green' };

/** Sustituye `{campo}` en una plantilla de enlace con los valores de la fila. */
export function fillLink(template: string, row: Record<string, unknown>): string {
  return template.replace(/\{(\w+)\}/g, (_, k) => encodeURIComponent(String(row[k] ?? '')));
}

export const CHART_COLORS = ['#1f4e79', '#e8590c', '#1a7f46', '#e0951a', '#b3261e', '#1a56b3', '#6b4fbb', '#0f766e', '#a16207', '#7c3aed'];
export const TONE_COLORS: Record<string, string> = { ok: '#1a7f46', warn: '#e0951a', bad: '#b3261e', info: '#1f4e79', neutral: '#5b6b7d' };
