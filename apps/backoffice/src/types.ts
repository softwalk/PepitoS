// Shapes de respuesta del backend (apps/api). Ver docs/CONTRATOS.md §5.
export type Role = 'operator' | 'supervisor' | 'ops' | 'finance' | 'admin';
export type Severity = 'urgent' | 'review' | 'normal';
export type CaseStatus = 'open' | 'in_progress' | 'resolved' | 'closed';
export type PointState = 'open' | 'closed' | 'late' | 'offline' | 'not_scheduled';

export interface AuthUser {
  id: string;
  name: string;
  role: Role;
  zone_id: string | null;
  username?: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  refresh_token: string;
  refresh_expires_at: string;
  user: AuthUser;
  must_change_password: boolean;
}

export interface Ref {
  id: string;
  name: string;
}

export interface Action {
  id: string;
  case_id: string | null;
  audit_id: string | null;
  description: string;
  owner_id: string | null;
  due_date: string | null;
  status: 'pending' | 'done' | 'overdue';
  done_at: string | null;
}

export interface Case {
  id: string;
  category: string;
  severity: Severity;
  status: CaseStatus;
  title: string;
  description: string;
  source: 'operator' | 'rule' | 'supervisor' | 'system';
  rule_key: string | null;
  point: Ref | null;
  shift_id: string | null;
  shift_status: 'open' | 'closed' | 'transferred' | null;
  opened_at: string;
  resolved_at: string | null;
  age_minutes: number;
  impact_score: number;
  priority_score: number;
  assignee: Ref | null;
  actions: Action[];
  ai: { suggested_category: string; confidence: number } | null;
  resolution: string | null;
  payload: Record<string, unknown>;
  /** Fotos asociadas (B4). `url` puede ser presignada (absoluta) o `/v1/evidence/{id}/file` (requiere Bearer). */
  evidence?: Evidence[];
}

export interface Evidence {
  id: string;
  kind: 'help_case' | 'shift_open' | 'shift_close' | 'audit' | 'case_note' | string;
  entity: 'case' | 'shift' | 'audit';
  entity_id: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  taken_at: string | null;
  url: string | null;
}

export interface Audit {
  id: string;
  point_id: string;
  shift_id: string | null;
  auditor_id: string;
  checklist: Record<string, boolean>;
  non_conformities: string[];
  cash_counted_cents: number | null;
  cash_expected_cents: number | null;
  notes: string | null;
  performed_at: string;
  photos: { evidence_id: string; key: string | null }[];
  evidence: Evidence[];
}

export interface PointStatus {
  point: { id: string; name: string; lat: number; lng: number; zone_id: string | null };
  status: PointState;
  shift_id: string | null;
  shift_status: 'open' | 'closed' | 'transferred' | null;
  operator: Ref | null;
  opened_at: string | null;
  last_seen_at: string | null;
  last_gps: { lat: number; lng: number; at: string; in_geofence: boolean } | null;
  battery_pct: number | null;
  sales_cents: number;
  target_cents: number;
  tx: number;
  ticket_cents: number;
  cash_status: 'ok' | 'difference' | 'pending';
  stock_risk: 'ok' | 'low' | 'critical';
  open_cases: { urgent: number; review: number };
  planned_start: string | null;
}

export interface Alert {
  id: string;
  rule_key: string;
  severity: Severity;
  status: string;
  message: string;
  point_id: string | null;
  shift_id: string | null;
  case_id: string | null;
  raised_at: string;
  resolved_at: string | null;
}

export interface Summary {
  date: string;
  totals: {
    points: number;
    open: number;
    late: number;
    closed: number;
    offline: number;
    sales_cents: number;
    target_cents: number;
    tx: number;
    ticket_cents: number;
    forecast_close_cents: number;
  };
  exceptions: { urgent: number; review: number; normal: number };
  points: PointStatus[];
  alerts_recent: Alert[];
}

export interface Briefing {
  date: string;
  headline: string;
  decisions: { title: string; why: string; recommendation: string; case_id?: string; severity?: Severity; priority_score?: number }[];
  numbers: Record<string, number | Record<string, number>>;
}

export interface SupervisorExceptions {
  urgent: Case[];
  review: Case[];
  normal: PointStatus[];
  normal_cases?: Case[];
}

export interface RouteStop {
  order: number;
  point: { id: string; name: string; lat: number; lng: number };
  reason: string;
  severity: Severity;
  priority_score: number;
  case_ids: string[];
  distance_from_previous_m: number;
}

export interface DailyRow {
  point: Ref;
  shift_id: string;
  operator: Ref;
  opened_at: string | null;
  closed_at: string | null;
  sales_cents: number;
  tx: number;
  cash_expected_cents: number | null;
  cash_counted_cents: number | null;
  difference_cents: number | null;
  digital_cents: number;
  cancelled_count: number;
  waste_units: number;
  waste_pct: number;
  status: string;
  /** Ventas registradas con una versión de precio ya desactivada (gracia offline de 72 h). */
  stale_price_sales: number;
}

export interface DailyReport {
  date: string;
  rows: DailyRow[];
  totals: { sales_cents: number; tx: number; difference_cents: number; waste_units: number; stale_price_sales: number };
}

export interface Rule {
  key: string;
  name: string;
  enabled: boolean;
  params: Record<string, unknown>;
  severity: Severity;
  updated_at: string | null;
}

export interface Approval {
  id: string;
  approval_type: string;
  entity: string | null;
  entity_id: string | null;
  title: string;
  amount_cents: number | null;
  status: 'pending' | 'approved' | 'rejected';
  requested_by: string | null;
  decided_by: string | null;
  decided_at: string | null;
  note: string | null;
  decision_note: string | null;
  created_at: string;
}

export interface AuditLogRow {
  id: string;
  at: string;
  actor_id: string | null;
  actor_name: string | null;
  action: string;
  entity: string | null;
  entity_id: string | null;
  before: unknown;
  after: unknown;
  reason: string | null;
  ip: string | null;
  device_id: string | null;
}

export interface InventoryStatus {
  points: {
    point: Ref;
    stock_risk: 'ok' | 'low' | 'critical';
    items: { presentation_id: string; name: string; balance: number; theoretical: number; min_units: number }[];
    total_units: number;
  }[];
  min_units: number;
}

export interface Lot {
  id: string;
  code: string;
  presentation_id: string | null;
  status: 'active' | 'blocked';
  blocked_reason: string | null;
  blocked_at: string | null;
}

export interface AttendanceRow {
  assignment_id: string;
  operator: Ref;
  point: Ref;
  planned_start: string | null;
  planned_end: string | null;
  check_in_at: string | null;
  check_out_at: string | null;
  late_minutes: number | null;
  status: string;
}

export interface Ticket {
  id: string;
  asset_id: string;
  severity: Severity;
  status: CaseStatus;
  title: string;
  description: string | null;
  kind: 'corrective' | 'preventive';
  evidence: string[] | null;
  resolution: string | null;
  created_at: string;
  resolved_at: string | null;
}

export interface Asset {
  id: string;
  code: string;
  asset_type: string;
  cart_id: string | null;
  cart_code: string | null;
  status: string;
  maintenance_interval_days: number | null;
  last_maintenance_at: string | null;
  next_maintenance_at: string | null;
  overdue: boolean;
  open_tickets: Ticket[];
}

// Admin
export interface Zone { id: string; name: string; is_active: boolean }
export interface User { id: string; username: string; name: string; role: Role; zone_id: string | null; phone: string | null; is_active: boolean; must_change_password?: boolean }
export interface ResetPasswordResponse { ok: boolean; user_id: string; must_change_password: boolean; temporary_password?: string }
export interface PointMeta { ranking?: number; alcaldia?: string; node_type?: string; score?: number; horario_sugerido?: string; afluencia?: string; riesgo?: string; resguardo?: string; justificacion?: string; estrategia?: string; validacion?: string; fuente?: string; geo_source?: string; source?: string }
export interface Point { id: string; name: string; address: string | null; lat: number; lng: number; geofence_radius_m: number; zone_id: string | null; open_time: string | null; close_time: string | null; daily_target_cents: number; daily_target_tx: number; is_active: boolean; geo_verified?: boolean; meta?: PointMeta }
export interface Cart { id: string; code: string; description: string | null; is_active: boolean }
export interface Assignment { id: string; operator_id: string; point_id: string; cart_id: string; shift_date: string; planned_start: string | null; planned_end: string | null; status: string; shift_id?: string | null; shift_status?: string | null }
export interface Presentation { id: string; name: string; grams: number; sort: number; is_active: boolean; product_id: string | null }
export interface PriceVersion { id: string; name: string; valid_from: string | null; valid_to: string | null; is_active: boolean; deactivated_at: string | null; sales_count?: number; prices: Record<string, number> }
/** Parámetro operativo (B6): `GET /v1/admin/settings`. */
export interface Setting { key: string; value: unknown; type: 'int' | 'float' | 'bool' | 'str'; default: unknown; description: string; updated_at: string | null; updated_by: string | null }
export interface Device { id: string; device_id: string; user_id: string | null; name: string | null; platform: string | null; revoked: boolean; revoked_at: string | null; revoked_reason: string | null; last_login_at: string | null; last_seen_at: string | null }
