// Cliente HTTP tipado de la API del operador (CONTRATOS §3, §5).
import type {
  AssignmentResponse,
  Catalog,
  HelpCasePayload,
  HelpCaseResponse,
  InventoryCountPayload,
  InventoryReceiptPayload,
  LoginResponse,
  GpsPing,
  PricesCurrent,
  SaleCancelPayload,
  SalePayload,
  SaleResponse,
  ShiftClosePayload,
  ShiftCloseResponse,
  ShiftExpected,
  ShiftOpenPayload,
  ShiftOpenResponse,
  SyncBatchResponse,
  SyncCommand,
  WastePayload,
} from '../types';

export class ApiError extends Error {
  code: string;
  status: number;
  details: unknown;
  constructor(code: string, message: string, status: number, details?: unknown) {
    super(message);
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

/** Error de red (sin conexión / servidor caído): la UI lo trata como "pendiente", nunca como fallo. */
export class NetworkError extends Error {
  constructor(message = 'Sin conexión') {
    super(message);
  }
}

// En dev/preview, Vite hace proxy de /v1 → VITE_API_URL (peticiones relativas). En producción, si se define
// VITE_API_BASE al compilar, se usa esa URL absoluta; si no, las peticiones son relativas (/v1) y el servidor
// web (nginx, etc.) debe hacer proxy a la API.
const BASE = (import.meta.env.VITE_API_BASE || '').replace(/\/$/, '');

let currentToken: string | null = null;
let onUnauthorized: ((code: string) => void) | null = null;

export function setAuthToken(token: string | null) {
  currentToken = token;
}

export function configureClient(opts: { onUnauthorized?: (code: string) => void }) {
  onUnauthorized = opts.onUnauthorized ?? null;
}

async function request<T>(method: string, path: string, body?: unknown, opts: { auth?: boolean; timeoutMs?: number } = {}): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (opts.auth !== false) {
    if (currentToken) headers.Authorization = `Bearer ${currentToken}`;
  }
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), opts.timeoutMs ?? 20000);
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body), signal: ctrl.signal });
  } catch (e) {
    clearTimeout(timer);
    throw new NetworkError(e instanceof Error ? e.message : 'Sin conexión');
  }
  clearTimeout(timer);
  const text = await res.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null;
    }
  }
  if (!res.ok) {
    const err = (data as { error?: { code?: string; message?: string; details?: unknown } } | null)?.error;
    const code = err?.code ?? (res.status >= 500 ? 'SERVER' : 'HTTP_' + res.status);
    if (res.status === 401 && onUnauthorized) onUnauthorized(code);
    throw new ApiError(code, err?.message ?? `Error ${res.status}`, res.status, err?.details);
  }
  return data as T;
}

export const api = {
  // §3
  login(body: { username: string; password: string; device_id: string; device_name?: string; platform?: string }) {
    return request<LoginResponse>('POST', '/v1/auth/login', body, { auth: false });
  },
  logout() {
    return request<{ ok: boolean }>('POST', '/v1/auth/logout');
  },
  // §5 Operador
  myAssignment() {
    return request<AssignmentResponse>('GET', '/v1/me/assignment');
  },
  openShift(body: ShiftOpenPayload) {
    return request<ShiftOpenResponse>('POST', '/v1/shifts/open', body);
  },
  shiftExpected(shiftId: string) {
    return request<ShiftExpected>('GET', `/v1/shifts/${shiftId}/expected`, undefined, { timeoutMs: 8000 });
  },
  closeShift(shiftId: string, body: ShiftClosePayload) {
    return request<ShiftCloseResponse>('POST', `/v1/shifts/${shiftId}/close`, body);
  },
  createSale(body: SalePayload) {
    return request<SaleResponse>('POST', '/v1/sales', body);
  },
  cancelSale(saleId: string, body: SaleCancelPayload) {
    return request<{ sale_id: string; status: 'cancelled' }>('POST', `/v1/sales/${saleId}/cancel`, body);
  },
  createWaste(body: WastePayload) {
    return request<{ waste_id: string }>('POST', '/v1/waste', body);
  },
  createHelpCase(body: HelpCasePayload) {
    return request<HelpCaseResponse>('POST', '/v1/help-cases', body);
  },
  inventoryReceipt(body: InventoryReceiptPayload) {
    return request<{ receipt_id: string }>('POST', '/v1/inventory/receipts', body);
  },
  inventoryCount(body: InventoryCountPayload) {
    return request<{ count_id: string; differences: Record<string, number> }>('POST', '/v1/inventory/counts', body);
  },
  gpsPings(pings: GpsPing[]) {
    return request<{ accepted: number }>('POST', '/v1/gps/pings', { pings });
  },
  syncBatch(device_id: string, commands: SyncCommand[]) {
    return request<SyncBatchResponse>('POST', '/v1/sync/batch', { device_id, commands }, { timeoutMs: 30000 });
  },
  catalog() {
    return request<Catalog>('GET', '/v1/catalog');
  },
  pricesCurrent() {
    return request<PricesCurrent>('GET', '/v1/prices/current');
  },
};
