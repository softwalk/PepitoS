// Botón "Tomar foto" reutilizable (conteo, recepción, incidente): comprime, estampa fecha/hora/punto/GPS dentro de
// la imagen y devuelve base64 JPEG. Nunca bloquea: si la cámara falla, el operador sigue sin foto.
import { useState, type ChangeEvent } from 'react';
import { compressImage, ImageTooLargeError, isSupportedImage, stampImage, stampLines, type StampInfo } from '../offline/image';
import { useApp } from '../state/store';

export default function PhotoCapture({
  label,
  value,
  onChange,
  stamp,
  disabled,
  testId = 'photo-capture',
}: {
  /** Etiqueta del sello (Conteo, Recepción, Incidente). */
  label: string;
  value: string | null;
  onChange: (b64: string | null) => void;
  /** Datos del sello además de la fecha/hora; `gps` se resuelve al momento de la toma. */
  stamp?: () => Promise<Partial<StampInfo>> | Partial<StampInfo>;
  disabled?: boolean;
  testId?: string;
}) {
  const { config, assignment } = useApp();
  const [status, setStatus] = useState<'idle' | 'processing' | 'error'>('idle');
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<StampInfo | null>(null);

  const onFile = async (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    e.target.value = '';
    if (!f) return;
    if (!isSupportedImage(f)) {
      setStatus('error');
      setError('Formato no permitido: usa JPEG, PNG o WebP');
      return;
    }
    setStatus('processing');
    setError(null);
    try {
      const raw = await compressImage(f, { maxBytes: config?.evidence_max_bytes });
      const extra = (await stamp?.()) ?? {};
      const si: StampInfo = { at: new Date(), label, place: assignment?.assignment?.point?.name ?? null, ...extra };
      const stamped = await stampImage(raw, si, { maxBytes: config?.evidence_max_bytes });
      setInfo(si);
      onChange(stamped);
      setStatus('idle');
    } catch (err) {
      onChange(null);
      setInfo(null);
      setStatus('error');
      setError(err instanceof ImageTooLargeError ? err.message : 'No se pudo procesar la foto. Puedes continuar sin ella.');
    }
  };

  return (
    <div className="photo-capture" data-testid={testId}>
      {value ? (
        <div className="photo-capture-preview">
          <img src={`data:image/jpeg;base64,${value}`} alt={`Foto: ${label}`} className="photo-preview" data-testid={`${testId}-preview`} />
          {info && (
            <div className="photo-stamp-info" data-testid={`${testId}-stamp`}>
              {stampLines(info).map((l) => (
                <div key={l}>{l}</div>
              ))}
            </div>
          )}
        </div>
      ) : null}
      {error && (
        <div className="exception" role="alert">
          <span className="ico" aria-hidden>
            ⚠️
          </span>
          <div>{error}</div>
        </div>
      )}
      <label className={`btn ${value ? 'btn-outline' : 'btn-blue'}`} style={{ cursor: 'pointer' }}>
        <span className="ico" aria-hidden>
          📷
        </span>
        {status === 'processing' ? 'Procesando…' : value ? 'Repetir foto' : `Tomar foto (${label.toLowerCase()})`}
        <input className="sr" type="file" accept="image/*" capture="environment" onChange={onFile} disabled={disabled || status === 'processing'} data-testid={`${testId}-input`} />
      </label>
      {value && (
        <button type="button" className="btn btn-ghost" onClick={() => { onChange(null); setInfo(null); }} disabled={disabled}>
          Quitar foto
        </button>
      )}
    </div>
  );
}
