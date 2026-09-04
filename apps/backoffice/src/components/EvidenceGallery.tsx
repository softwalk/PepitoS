// Galería de evidencias (B4): miniaturas de 120 px, clic → visor modal con fecha y tamaño.
// `url` absoluta (presignada) se usa directa; relativa (`/v1/evidence/{id}/file`) se descarga con Bearer → blob URL,
// que se revoca al desmontar.
import { useEffect, useState } from 'react';
import type { Evidence } from '../types';
import { fmtBytes, fmtDateTime } from '../lib/format';
import { resolveEvidenceUrl, revokeResolved, type ResolvedUrl } from '../lib/evidence';
import { Modal } from './ui';

const KIND_LABEL: Record<string, string> = {
  help_case: 'Ayuda',
  shift_open: 'Apertura',
  shift_close: 'Cierre',
  audit: 'Auditoría',
  case_note: 'Nota',
};

type Resolved = { status: 'loading' } | { status: 'ok'; src: ResolvedUrl } | { status: 'error'; message: string };

/** Resuelve las URLs de una lista de evidencias; revoca los blob URLs al desmontar o cambiar la lista. */
export function useEvidenceUrls(items: Evidence[]): Record<string, Resolved> {
  const [state, setState] = useState<Record<string, Resolved>>({});
  const key = items.map((e) => `${e.id}:${e.url ?? ''}`).join('|');
  useEffect(() => {
    let alive = true;
    const resolved: ResolvedUrl[] = [];
    setState(Object.fromEntries(items.map((e) => [e.id, { status: 'loading' } as Resolved])));
    for (const e of items) {
      if (!e.url) {
        setState((s) => ({ ...s, [e.id]: { status: 'error', message: 'Archivo no disponible' } }));
        continue;
      }
      resolveEvidenceUrl(e.url)
        .then((r) => {
          if (!alive) {
            revokeResolved(r);
            return;
          }
          resolved.push(r);
          setState((s) => ({ ...s, [e.id]: { status: 'ok', src: r } }));
        })
        .catch((err: unknown) => {
          if (!alive) return;
          setState((s) => ({ ...s, [e.id]: { status: 'error', message: err instanceof Error ? err.message : 'No se pudo cargar' } }));
        });
    }
    return () => {
      alive = false;
      resolved.forEach(revokeResolved);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return state;
}

export function EvidenceGallery({ items, emptyText = 'Sin evidencias', title }: { items: Evidence[] | null | undefined; emptyText?: string; title?: string }) {
  const list = items ?? [];
  const urls = useEvidenceUrls(list);
  const [open, setOpen] = useState<Evidence | null>(null);

  if (list.length === 0) return <p className="empty">{emptyText}</p>;
  const current = open ? urls[open.id] : undefined;

  return (
    <div className="evidence-gallery" data-testid="evidence-gallery">
      {title && <div className="small muted" style={{ marginBottom: 6 }}>{title}</div>}
      <div className="evidence-grid">
        {list.map((e) => {
          const r = urls[e.id];
          const label = `${KIND_LABEL[e.kind] ?? e.kind} · ${fmtDateTime(e.taken_at)} · ${fmtBytes(e.size_bytes)}`;
          return (
            <button type="button" key={e.id} className="evidence-thumb" onClick={() => setOpen(e)} title={label} aria-label={`Ver evidencia: ${label}`} data-testid={`evidence-thumb-${e.id}`} disabled={!r || r.status !== 'ok'}>
              {r?.status === 'ok' ? <img src={r.src.url} alt={label} loading="lazy" /> : <span className="evidence-thumb-ph">{r?.status === 'error' ? '⚠︎' : '…'}</span>}
              <span className="evidence-meta">
                <span>{KIND_LABEL[e.kind] ?? e.kind}</span>
                <span>{fmtBytes(e.size_bytes)}</span>
              </span>
            </button>
          );
        })}
      </div>
      {open && (
        <Modal className="wide" title={`${KIND_LABEL[open.kind] ?? open.kind} · ${fmtDateTime(open.taken_at)}`} onClose={() => setOpen(null)}>
          <div className="evidence-viewer" data-testid="evidence-viewer">
            {current?.status === 'ok' ? <img src={current.src.url} alt={`Evidencia ${open.id}`} /> : <p className="muted">{current?.status === 'error' ? current.message : 'Cargando…'}</p>}
            <div className="small muted evidence-viewer-meta">
              <span>Tomada: {fmtDateTime(open.taken_at)}</span>
              <span>Tamaño: {fmtBytes(open.size_bytes)}</span>
              <span>{open.content_type}</span>
              <span className="mono" title={open.sha256}>
                sha256 {open.sha256.slice(0, 12)}…
              </span>
              {current?.status === 'ok' && (
                <a href={current.src.url} target="_blank" rel="noreferrer" download={`evidencia-${open.id}.jpg`}>
                  Abrir original
                </a>
              )}
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
