import { useState, type ChangeEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { getPosition } from '../offline/gps';
import { speak } from '../offline/speech';
import { requestHelp } from '../state/actions';
import { useApp } from '../state/store';
import type { HelpCategory } from '../types';

const CARDS: { code: HelpCategory; icon: string; label: string }[] = [
  { code: 'cart', icon: '🛒', label: 'Carrito' },
  { code: 'battery', icon: '🔋', label: 'Batería' },
  { code: 'product', icon: '🥜', label: 'Producto' },
  { code: 'payment', icon: '💳', label: 'Cobro' },
  { code: 'security', icon: '🚨', label: 'Seguridad' },
  { code: 'other', icon: '❓', label: 'Otro' },
];

async function fileToBase64(file: File): Promise<string> {
  // Reduce la foto a ≤1024 px para no saturar la cola.
  const bitmap = await createImageBitmap(file).catch(() => null);
  if (!bitmap) {
    return new Promise((resolve) => {
      const r = new FileReader();
      r.onload = () => resolve(String(r.result).split(',')[1] ?? '');
      r.readAsDataURL(file);
    });
  }
  const scale = Math.min(1, 1024 / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  canvas.getContext('2d')!.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL('image/jpeg', 0.7).split(',')[1] ?? '';
}

export default function Help() {
  const nav = useNavigate();
  const { catalog, reload } = useApp();
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

  const onPhoto = async (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) setPhoto(await fileToBase64(f));
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
            <span className="ico" aria-hidden>
              {c.icon}
            </span>
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
