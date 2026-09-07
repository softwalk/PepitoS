import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Icon from '../components/Icon';
import { BatteryIcon, OtherIcon, PaymentIcon, SecurityIcon } from '../components/HelpIcons';
import PhotoCapture from '../components/PhotoCapture';
import { getPosition, recentPosition } from '../offline/gps';
import { speak } from '../offline/speech';
import { requestHelp } from '../state/actions';
import { useApp } from '../state/store';
import type { HelpTag, HelpCategory } from '../types';

// Iconos: imágenes (/public) o SVG propios; nunca emojis, que en algunos Android no tienen fuente y salen como cuadros.
const CARDS: { code: HelpCategory; icon: string | JSX.Element; label: string }[] = [
  { code: 'cart', icon: 'img:/icon-cart.png', label: 'Carrito' },
  { code: 'battery', icon: <BatteryIcon />, label: 'Batería' },
  { code: 'product', icon: 'img:/icon-product.png', label: 'Producto' },
  { code: 'payment', icon: <PaymentIcon />, label: 'Cobro' },
  { code: 'security', icon: <SecurityIcon />, label: 'Seguridad' },
  { code: 'other', icon: <OtherIcon />, label: 'Otro' },
];

const TAGS: { code: HelpTag; label: string }[] = [
  { code: 'rain', label: '🌧️ Lluvia' },
  { code: 'planned_closure', label: '🚧 Cierre planeado' },
  { code: 'traffic', label: '🚦 Tráfico / acceso' },
  { code: 'low_footfall', label: '🚶 Poca gente' },
  { code: 'stockout', label: '📦 Sin producto' },
];

/** Resuelve con `null` si la promesa tarda más de `ms` (el GPS no puede retrasar un aviso de ayuda). */
function withTimeout<T>(p: Promise<T>, ms: number): Promise<T | null> {
  return new Promise((resolve) => {
    const t = setTimeout(() => resolve(null), ms);
    p.then((v) => {
      clearTimeout(t);
      resolve(v);
    }).catch(() => {
      clearTimeout(t);
      resolve(null);
    });
  });
}

export default function Help() {
  const nav = useNavigate();
  const { catalog, reload } = useApp();
  const [sent, setSent] = useState<HelpCategory | null>(null);
  const [other, setOther] = useState(false);
  const [note, setNote] = useState('');
  const [tags, setTags] = useState<HelpTag[]>([]);
  const [photo, setPhoto] = useState<string | null>(null);
  const [busy, setBusy] = useState<HelpCategory | null>(null);
  const [sendError, setSendError] = useState<string | null>(null);
  const labels = new Map((catalog?.help_categories ?? []).map((c) => [c.code, c.label]));

  /**
   * Envía el aviso. Responde de inmediato: la tarjeta pasa a «Enviando…», el GPS se toma del último fix reciente o se
   * espera como máximo 2.5 s (1.5 s en Seguridad) — nunca más — y cualquier error se muestra en pantalla en vez de
   * quedarse en silencio. El aviso se encola offline, así que sin señal también sale.
   */
  const send = async (category: HelpCategory, extra: { note?: string; photo_base64?: string; tags?: HelpTag[] } = {}) => {
    if (busy) return;
    setBusy(category);
    setSendError(null);
    try {
      const gps = recentPosition() ?? (await withTimeout(getPosition(category === 'security' ? 1500 : 2500), category === 'security' ? 1800 : 3000));
      await requestHelp(category, { ...extra, gps });
      setSent(category);
      speak('Enviado. Te contactan.');
      void reload().catch(() => undefined);
    } catch (err) {
      setSendError(err instanceof Error && err.message ? err.message : 'No se pudo registrar el aviso. Inténtalo de nuevo.');
    } finally {
      setBusy(null);
    }
  };

  // Foto del incidente: se estampa con ubicación (GPS al momento de la toma), punto, fecha y hora dentro de la imagen.
  const stampWithGps = async () => ({ gps: (await getPosition(4000)) ?? recentPosition() ?? null });

  if (sent) {
    return (
      <div className={`result ${sent === 'security' ? 'result-amber' : 'result-green'}`} role="status">
        <div className="ico" aria-hidden>
          📨
        </div>
        <p className="h1">Enviado, te contactan</p>
        {sent === 'security' && <p className="h2">Mantente a salvo. Ayuda prioritaria en camino.</p>}
        <button className="btn" onClick={() => nav('/', { replace: true })}>
          Volver al inicio
        </button>
      </div>
    );
  }

  if (other) {
    return (
      <div className="stack">
        <h1 className="h1">¿Qué pasa?</h1>
        {/* Contexto que no es una falla del vendedor: sirve para que los reportes separen «no vendió» de «no pudo vender». */}
        <div className="flavor-chips" role="group" aria-label="Contexto">
          {TAGS.map((t) => (
            <button key={t.code} type="button" className={`chip ${tags.includes(t.code) ? 'active' : ''}`} aria-pressed={tags.includes(t.code)} onClick={() => setTags((v) => (v.includes(t.code) ? v.filter((x) => x !== t.code) : [...v, t.code]))}>
              {t.label}
            </button>
          ))}
        </div>
        <textarea placeholder="Escribe una nota corta (opcional)" value={note} maxLength={280} onChange={(e) => setNote(e.target.value)} />
        <PhotoCapture label="Incidente" value={photo} onChange={setPhoto} stamp={stampWithGps} disabled={!!busy} testId="help-photo" />
        {sendError && (
          <div className="exception" role="alert" data-testid="help-error">
            <span className="ico" aria-hidden>
              ⚠️
            </span>
            <div>{sendError}</div>
          </div>
        )}
        <button className="btn btn-blue" disabled={!!busy} onClick={() => void send('other', { note: note.trim() || undefined, photo_base64: photo ?? undefined, tags })}>
          <span className="ico" aria-hidden>
            📨
          </span>
          {busy ? 'Enviando…' : 'ENVIAR'}
        </button>
        <button className="btn btn-ghost" onClick={() => setOther(false)}>
          Volver
        </button>
      </div>
    );
  }

  return (
    <div className="stack">
      <h1 className="h1">¿Con qué necesitas ayuda?</h1>
      {sendError && (
        <div className="exception" role="alert" data-testid="help-error">
          <span className="ico" aria-hidden>
            ⚠️
          </span>
          <div>{sendError}</div>
        </div>
      )}
      <div className="help-grid">
        {CARDS.map((c) => (
          <button
            key={c.code}
            type="button"
            className={`help-card ${c.code} ${busy === c.code ? 'sending' : ''}`}
            disabled={!!busy}
            aria-busy={busy === c.code}
            data-testid={`help-${c.code}`}
            onClick={() => (c.code === 'other' ? setOther(true) : void send(c.code))}
            aria-label={c.code === 'security' ? 'Seguridad: envía ayuda prioritaria de inmediato' : labels.get(c.code) ?? c.label}
          >
            {typeof c.icon === 'string' ? <Icon icon={c.icon} /> : c.icon}
            {busy === c.code ? 'Enviando…' : labels.get(c.code) ?? c.label}
            {c.code === 'security' && busy !== c.code && <small style={{ fontSize: '0.6em' }}>Envío inmediato</small>}
          </button>
        ))}
      </div>
      <button className="btn btn-ghost" onClick={() => nav('/')}>
        Volver
      </button>
    </div>
  );
}
