// Utilidades de formato (dinero en centavos, fechas, porcentajes) y semáforos PRD §15.
export type Light = 'green' | 'amber' | 'red';

export function money(cents: number | null | undefined, opts: { decimals?: number } = {}): string {
  if (cents === null || cents === undefined || Number.isNaN(cents)) return '—';
  const decimals = opts.decimals ?? 2;
  const value = cents / 100;
  const sign = value < 0 ? '-' : '';
  const abs = Math.abs(value).toLocaleString('es-MX', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  return `${sign}$${abs}`;
}

export function pct(value: number | null | undefined, decimals = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return `${value.toFixed(decimals)}%`;
}

export function ratioPct(part: number, total: number): number {
  if (!total) return 0;
  return Math.round((part * 100) / total);
}

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit', timeZone: 'America/Mexico_City' });
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString('es-MX', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'America/Mexico_City' });
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = iso.length === 10 ? new Date(iso + 'T12:00:00') : new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleDateString('es-MX', { day: '2-digit', month: 'short', year: 'numeric' });
}

export function ageLabel(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined) return '—';
  if (minutes < 60) return `${Math.round(minutes)} min`;
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  if (h < 24) return m ? `${h} h ${m} min` : `${h} h`;
  return `${Math.floor(h / 24)} d ${h % 24} h`;
}

export function todayLocalISO(): string {
  // Fecha operativa en America/Mexico_City (YYYY-MM-DD)
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Mexico_City', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date());
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? '';
  return `${get('year')}-${get('month')}-${get('day')}`;
}

// ---- Semáforos (PRD §15) ----
/** Ventas/día por punto: ≥60 verde, 45–59 ámbar, <45 rojo. */
export function salesLight(txPerDay: number): Light {
  if (txPerDay >= 60) return 'green';
  if (txPerDay >= 45) return 'amber';
  return 'red';
}

/** Ticket promedio: ≥$39 verde, $36–38.99 ámbar, <$36 rojo. */
export function ticketLight(ticketCents: number): Light {
  if (ticketCents >= 3900) return 'green';
  if (ticketCents >= 3600) return 'amber';
  return 'red';
}

/** Merma: ≤2% verde, 2–4% ámbar, >4% rojo. */
export function wasteLight(wastePct: number): Light {
  if (wastePct <= 2) return 'green';
  if (wastePct <= 4) return 'amber';
  return 'red';
}

/** Avance vs meta (%): ≥100 verde, 75–99 ámbar, <75 rojo. */
export function targetLight(progressPct: number): Light {
  if (progressPct >= 100) return 'green';
  if (progressPct >= 75) return 'amber';
  return 'red';
}

export const LIGHT_LABEL: Record<Light, string> = { green: 'Verde', amber: 'Ámbar', red: 'Rojo' };

export const STATUS_LABEL: Record<string, string> = {
  open: 'Abierto',
  closed: 'Cerrado',
  late: 'Tarde',
  offline: 'Sin señal',
  not_scheduled: 'No programado',
  in_progress: 'En proceso',
  resolved: 'Resuelto',
  pending: 'Pendiente',
  done: 'Hecha',
  overdue: 'Vencida',
  approved: 'Aprobada',
  rejected: 'Rechazada',
  reconciled: 'Conciliado',
  difference: 'Diferencia',
  transferred: 'Transferido',
  ok: 'OK',
  low: 'Bajo',
  critical: 'Crítico',
  present: 'Presente',
  absent: 'Ausente',
  active: 'Activo',
  blocked: 'Bloqueado',
};

export const SEVERITY_LABEL: Record<string, string> = { urgent: 'URGENTE', review: 'REVISAR', normal: 'NORMAL' };

export const CATEGORY_LABEL: Record<string, string> = {
  cart: 'Carrito',
  battery: 'Batería',
  product: 'Producto',
  payment: 'Cobro',
  security: 'Seguridad',
  other: 'Otro',
  audit: 'Auditoría',
  cash: 'Caja',
  no_open: 'No apertura',
  out_of_geofence: 'Fuera de geocerca',
  low_sales_trajectory: 'Ventas bajas',
  high_waste: 'Merma alta',
  cash_difference: 'Diferencia de caja',
  inventory_inconsistent: 'Inventario inconsistente',
  low_battery: 'Batería baja',
  anomalous_cancellations: 'Cancelaciones anómalas',
  sync_stale: 'Sin sincronizar',
  maintenance_overdue: 'Mantenimiento vencido',
  stock_critical: 'Stock crítico',
  opening: 'Apertura',
};

export function label(map: Record<string, string>, key: string | null | undefined): string {
  if (!key) return '—';
  return map[key] ?? key;
}

export function fmtBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined || Number.isNaN(bytes)) return '—';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
