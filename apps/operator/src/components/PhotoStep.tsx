// Paso "foto del puesto" (apertura/cierre por muestreo). Nunca bloquea: si la cámara falla o se cancela,
// el operador puede continuar sin foto y el comando lleva `photos: []`.
import { useState, type ChangeEvent } from 'react';
import { compressImage, ImageTooLargeError, isSupportedImage } from '../offline/image';
import type { Photo } from '../types';

export const PHOTO_KEY = 'puesto';

export default function PhotoStep({
  title,
  maxBytes,
  busy,
  onContinue,
  onBack,
  continueLabel = 'CONTINUAR',
}: {
  title: string;
  maxBytes?: number;
  busy?: boolean;
  /** Se llama con la foto (o [] si no hay) al continuar. */
  onContinue: (photos: Photo[]) => void;
  onBack?: () => void;
  continueLabel?: string;
}) {
  const [base64, setBase64] = useState<string | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [status, setStatus] = useState<'idle' | 'processing' | 'error'>('idle');
  const [error, setError] = useState<string | null>(null);

  const onFile = async (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    // Permite volver a elegir el mismo archivo.
    e.target.value = '';
    if (!f) return; // cámara cancelada: no bloqueamos
    if (!isSupportedImage(f)) {
      setStatus('error');
      setError('Formato no permitido: usa JPEG, PNG o WebP');
      return;
    }
    setStatus('processing');
    setError(null);
    try {
      const b64 = await compressImage(f, { maxBytes });
      setBase64(b64);
      setPreview(`data:image/jpeg;base64,${b64}`);
      setStatus('idle');
    } catch (err) {
      setBase64(null);
      setPreview(null);
      setStatus('error');
      setError(err instanceof ImageTooLargeError ? err.message : 'No se pudo procesar la foto. Puedes continuar sin ella.');
    }
  };

  return (
    <div className="stack" data-testid="photo-step">
      <h1 className="h1">{title}</h1>
      <p className="muted">Hoy toca foto de muestreo. Si la cámara no funciona, puedes continuar sin foto.</p>
      {preview ? (
        <img src={preview} alt="Foto del puesto" className="photo-preview" data-testid="photo-preview" />
      ) : (
        <div className="photo-placeholder" aria-hidden>
          📷
        </div>
      )}
      {error && (
        <div className="exception" role="alert">
          <span className="ico" aria-hidden>
            ⚠️
          </span>
          <div>{error}</div>
        </div>
      )}
      <label className="btn btn-blue" style={{ cursor: 'pointer' }}>
        <span className="ico" aria-hidden>
          📷
        </span>
        {status === 'processing' ? 'Procesando…' : base64 ? 'Repetir foto' : 'TOMAR FOTO'}
        <input className="sr" type="file" accept="image/*" capture="environment" onChange={onFile} disabled={busy || status === 'processing'} data-testid="photo-input" />
      </label>
      <button className={`btn ${base64 ? 'btn-green' : 'btn-outline'}`} disabled={busy || status === 'processing'} onClick={() => onContinue(base64 ? [{ key: PHOTO_KEY, base64 }] : [])} data-testid="photo-continue">
        <span className="ico" aria-hidden>
          {base64 ? '✅' : '➡️'}
        </span>
        {busy ? 'Enviando…' : base64 ? continueLabel : 'Continuar sin foto'}
      </button>
      {onBack && (
        <button className="btn btn-ghost" onClick={onBack} disabled={busy}>
          Atrás
        </button>
      )}
    </div>
  );
}
