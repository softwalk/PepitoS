import { useState, type ChangeEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import Icon from '../components/Icon';
import { getPosition } from '../offline/gps';
import { compressImage } from '../offline/image';
import { speak } from '../offline/speech';
import { requestHelp } from '../state/actions';
import { useApp } from '../state/store';
import type { HelpCategory } from '../types';

const CARDS: { code: HelpCategory; icon: string; label: string }[] = [
  { code: 'cart', icon: 'img:/icon-cart.png', label: 'Carrito' },
  { code: 'battery', icon: '🔋', label: 'Batería' },
  { code: 'product', icon: 'img:/icon-product.png', label: 'Producto' },
  { code: 'payment', icon: '💳', label: 'Cobro' },
  { code: 'security', icon: '🚨', label: 'Seguridad' },
  { code: 'other', icon: '❓', label: 'Otro' },
];

export default function Help() {
  const nav = useNavigate();
  const { catalog, config, reload } = useApp();
  const [sent, setSent] = useState<HelpCategory | null>(null);
  const [other, setOther] = useState(false);
  const [note, setNote] = useState('');
  const [photo, setPhoto] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const labels = new Map((catalog?.help_categories ?? []).map((c) => [c.code, c.label]));

  const send = async (category: HelpCategory, extra: { note?: string; photo_base64?: string } = {}) => {
    if (busy) return;
    setBusy(true);
    try {
      // Seguridad es prioritaria: no esperar al GPS más de 3 s.
      const gps = await getPosition(category === 'security' ? 3000 : 6000);
      await requestHelp(category, { ...extra, gps });
      await reload();
      setSent(category);
      speak('Enviado. Te contactan.');
    } finally {
      setBusy(false);
    }
  };

  const [photoError, setPhotoError] = useState<string | null>(null);
  const onPhoto = async (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    e.target.value = '';
    if (!f) return;
    setPhotoError(null);
    try {
      // ≤1280 px / JPEG 0.8 y validación contra config.evidence_max_bytes (3 MB por defecto).
      setPhoto(await compressImage(f, { maxBytes: config?.evidence_max_bytes }));
    } catch (err) {
      setPhoto(null);
      setPhotoError(err instanceof Error ? err.message : 'No se pudo procesar la foto');
    }
  };

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
        <textarea placeholder="Escribe una nota corta (opcional)" value={note} maxLength={280} onChange={(e) => setNote(e.target.value)} />
        <label className="btn btn-outline" style={{ cursor: 'pointer' }}>
          <span className="ico" aria-hidden>
            📷
          </span>
          {photo ? 'Foto lista ✓' : 'Tomar foto (opcional)'}
          <input className="sr" type="file" accept="image/*" capture="environment" onChange={onPhoto} />
        </label>
        {photoError && (
          <div className="exception" role="alert">
            <span className="ico" aria-hidden>
              ⚠️
            </span>
            <div>{photoError}</div>
          </div>
        )}
        <button className="btn btn-blue" disabled={busy} onClick={() => send('other', { note: note.trim() || undefined, photo_base64: photo ?? undefined })}>
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
      <div className="help-grid">
        {CARDS.map((c) => (
          <button
            key={c.code}
            className={`help-card ${c.code}`}
            disabled={busy}
            onClick={() => (c.code === 'other' ? setOther(true) : send(c.code))}
            aria-label={c.code === 'security' ? 'Seguridad: envía ayuda prioritaria de inmediato' : labels.get(c.code) ?? c.label}
          >
            <Icon icon={c.icon} />
            {labels.get(c.code) ?? c.label}
            {c.code === 'security' && <small style={{ fontSize: '0.6em' }}>Envío inmediato</small>}
          </button>
        ))}
      </div>
      <button className="btn btn-ghost" onClick={() => nav('/')}>
        Volver
      </button>
    </div>
  );
}
