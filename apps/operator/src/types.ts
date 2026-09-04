// Tipos del contrato (docs/CONTRATOS.md §3, §5 Operador). Dinero en centavos enteros.

export type Role = 'operator' | 'supervisor' | 'ops' | 'finance' | 'admin';

export interface LoginResponse {
  access_token: string;
  token_type: 'bearer';
  expires_in: number;
  refresh_token: string;
  refresh_expires_at: string;
  user: { id: string; name: string; role: Role; zone_id: string | null; username?: string };
  must_change_password: boolean;
}

export interface GPS {
  lat: number;
  lng: number;
  accuracy_m: number | null;
  mocked: boolean;
  at: string;
}

export interface Presentation {
  id: string;
  name: string;
  grams: number;
  price_cents: number | null;
  sort: number;
}

export interface Flavor {
  id: string;
  name: string;
  sort: number;
}

export interface ChecklistItem {
  key: string;
  label: string;
  critical?: boolean;
}

export interface Catalog {
  presentations: Presentation[];
  flavors: Flavor[];
  price_version_id: string | null;
  waste_reasons: { code: WasteReason; label: string }[];
  help_categories: { code: HelpCategory; label: string; icon: string }[];
  checklist_open: ChecklistItem[];
  checklist_close: ChecklistItem[];
}

export interface OperatorConfig {
  cash_difference_threshold_cents: number;
  cancel_window_minutes: number;
  gps_interval_seconds: number;
  photo_sampling_pct: number;
}

export interface Point {
  id: string;
  name: string;
  address: string | null;
  lat: number;
  lng: number;
  geofence_radius_m: number;
}

export interface Assignment {
  id: string;
  shift_date: string;
  planned_start: string;
  planned_end: string;
  status?: string;
  point: Point;
  cart: { id: string; code: string };
}

export interface ActiveShift {
  id: string;
  opened_at: string;
  status: string;
  ready?: boolean;
  exceptions?: ShiftException[];
}

export interface AssignmentResponse {
  assignment: Assignment | null;
  active_shift: ActiveShift | null;
  catalog: Catalog;
  config: OperatorConfig;
}

export interface OpenChecklist {
  cart_secure: boolean;
  battery_ok: boolean;
  product_ok: boolean;
  clean_ok: boolean;
  pos_ok: boolean;
}

export interface CloseChecklist {
  off_ok: boolean;
  clean_ok: boolean;
  secured_ok: boolean;
  stored_ok: boolean;
  charging_ok: boolean;
}

export interface ShiftException {
  code: string;
  message: string;
}

export interface ShiftOpenPayload {
  idempotency_key: string;
  assignment_id: string;
  opened_at: string;
  checklist: OpenChecklist;
  gps: GPS | null;
  photos?: { key: string; base64: string }[];
}

export interface ShiftOpenResponse {
  shift_id: string;
  status: 'open' | 'open_with_exception';
  exceptions: ShiftException[];
  ready: boolean;
}

export interface ShiftExpected {
  sales_count: number;
  sales_total_cents: number;
  cash_expected_cents: number;
  digital_total_cents: number;
  product_expected: Record<string, number>;
  waste_units: number;
  cancelled_count?: number;
}

export interface ShiftClosePayload {
  idempotency_key: string;
  closed_at: string;
  cash_counted_cents: number;
  product_counts: Record<string, number>;
  checklist: CloseChecklist;
  gps: GPS | null;
}

export interface ShiftCloseResponse {
  shift_id: string;
  status: 'reconciled' | 'difference';
  cash_expected_cents: number;
  cash_counted_cents: number;
  difference_cents: number;
  product_diff: Record<string, number>;
  case_id: string | null;
}

export type PaymentMethod = 'cash' | 'qr' | 'card';

export interface SaleLine {
  presentation_id: string;
  qty: number;
  flavor_id?: string | null;
}

export interface SalePayload {
  idempotency_key: string;
  shift_id: string;
  occurred_at: string;
  price_version_id: string;
  lines: SaleLine[];
  payments: { method: PaymentMethod; amount_cents: number }[];
  offline_created: boolean;
  gps?: GPS | null;
}

export interface SaleResponse {
  sale_id: string;
  folio: string;
  total_cents: number;
  status: 'recorded';
  duplicate: boolean;
}

export interface SaleCancelPayload {
  idempotency_key: string;
  reason_code: string;
  note?: string;
}

export type WasteReason = 'spill' | 'quality' | 'expired' | 'sample' | 'other';

export interface WastePayload {
  idempotency_key: string;
  shift_id: string;
  occurred_at: string;
  presentation_id: string;
  qty: number;
  reason_code: WasteReason;
  note?: string;
}

export type HelpCategory = 'cart' | 'battery' | 'product' | 'payment' | 'security' | 'other';

export interface HelpCasePayload {
  idempotency_key: string;
  shift_id?: string | null;
  occurred_at: string;
  category: HelpCategory;
  note?: string;
  photo_base64?: string;
  gps?: GPS | null;
}

export interface HelpCaseResponse {
  case_id: string;
  severity: string;
  category: HelpCategory;
  status: 'open';
}

export interface GpsPing {
  shift_id: string;
  at: string;
  lat: number;
  lng: number;
  accuracy_m: number | null;
  mocked: boolean;
  battery_pct?: number | null;
}

export interface InventoryReceiptPayload {
  idempotency_key: string;
  shift_id: string;
  occurred_at: string;
  qr_code?: string;
  lines: { presentation_id: string; qty: number; lot_code?: string }[];
}

export interface InventoryCountPayload {
  idempotency_key: string;
  shift_id: string;
  occurred_at: string;
  counts: Record<string, number>;
}

export type SyncCommandType =
  | 'sale'
  | 'waste'
  | 'shift_open'
  | 'shift_close'
  | 'help_case'
  | 'gps_ping'
  | 'inventory_receipt'
  | 'inventory_count'
  | 'sale_cancel';

export interface SyncCommand {
  idempotency_key: string;
  type: SyncCommandType;
  created_at: string;
  payload: Record<string, unknown>;
}

export interface SyncResult {
  idempotency_key: string;
  status: 'ok' | 'duplicate' | 'error';
  code?: string;
  message?: string;
  result?: Record<string, unknown>;
}

export interface SyncBatchResponse {
  results: SyncResult[];
}

export interface PricesCurrent {
  price_version_id: string | null;
  valid_from: string | null;
  prices: Record<string, number>;
}

export interface ApiErrorBody {
  error: { code: string; message: string; details?: unknown };
}
