// Resolución de URLs de evidencia (B4): una URL absoluta (presignada) se usa directa; una relativa a la API
// (`/v1/evidence/{id}/file`) requiere Bearer, así que se descarga con fetch y se expone como blob URL.
import { getSession } from '../state/session';
import { ApiError } from '../api/client';

export function isAbsoluteUrl(url: string): boolean {
  return /^https?:\/\//i.test(url);
}

export interface ResolvedUrl {
  url: string;
  /** true si es un blob URL creado aquí (hay que revocarlo al desmontar). */
  revocable: boolean;
}

export async function resolveEvidenceUrl(url: string): Promise<ResolvedUrl> {
  if (isAbsoluteUrl(url)) return { url, revocable: false };
  const session = getSession();
  const headers: Record<string, string> = {};
  if (session?.token) headers.Authorization = `Bearer ${session.token}`;
  let res: Response;
  try {
    res = await fetch(url, { headers });
  } catch {
    throw new ApiError(0, 'NETWORK', 'Sin conexión con el servidor');
  }
  if (!res.ok) {
    let code = `HTTP_${res.status}`;
    let message = `No se pudo cargar la evidencia (${res.status})`;
    try {
      const body = (await res.json()) as { error?: { code?: string; message?: string } };
      code = body.error?.code ?? code;
      message = body.error?.message ?? message;
    } catch {
      /* sin cuerpo JSON */
    }
    throw new ApiError(res.status, code, message);
  }
  const blob = await res.blob();
  return { url: URL.createObjectURL(blob), revocable: true };
}

export function revokeResolved(r: ResolvedUrl | null | undefined) {
  if (r?.revocable) {
    try {
      URL.revokeObjectURL(r.url);
    } catch {
      /* ya revocada */
    }
  }
}
