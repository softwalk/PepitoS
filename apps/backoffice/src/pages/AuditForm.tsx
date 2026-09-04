import { useEffect, useRef, useState, type ChangeEvent, type FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api } from '../api/client';
import { useFetch } from '../lib/useFetch';
import { useAuth } from '../state/auth';
import { useToast } from '../components/Toast';
import { Badge, Card, Field, Loading, PageTitle } from '../components/ui';
import type { Point, User } from '../types';
import { fmtBytes, money, todayLocalISO } from '../lib/format';
import { base64Bytes, compressImage } from '../lib/image';

export const MAX_PHOTOS = 3;
interface PhotoDraft { key: string; base64: string; name: string }

const CHECKLIST: { key: string; label: string }[] = [
  { key: 'clean_ok', label: 'Limpieza del punto y carrito' },
  { key: 'uniform_ok', label: 'Uniforme completo' },
  { key: 'product_ok', label: 'Producto en buen estado' },
  { key: 'display_ok', label: 'Exhibición correcta' },
  { key: 'prices_visible', label: 'Precios visibles' },
  { key: 'cart_secure', label: 'Carrito seguro' },
  { key: 'pos_ok', label: 'POS / terminal funcionando' },
];

interface Corrective { description: string; owner_id: string; due_date: string }

type SpeechRecognitionCtor = new () => {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((ev: { resultIndex: number; results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }> }) => void) | null;
  onend: (() => void) | null;
  onerror: (() => void) | null;
  start: () => void;
  stop: () => void;
};

function getSpeech(): SpeechRecognitionCtor | null {
  const w = window as unknown as { SpeechRecognition?: SpeechRecognitionCtor; webkitSpeechRecognition?: SpeechRecognitionCtor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export function AuditFormPage() {
  const { pointId = '' } = useParams();
  const nav = useNavigate();
  const toast = useToast();
  const { user, hasRole } = useAuth();
  const point = useFetch<Point>(() => api.get(`/v1/admin/points/${pointId}`), [pointId]);
  const users = useFetch<User[]>(() => api.get('/v1/admin/users'), [], { silent: true, enabled: hasRole('ops', 'admin') });

  const [checks, setChecks] = useState<Record<string, boolean | null>>(() => Object.fromEntries(CHECKLIST.map((c) => [c.key, null])));
  const [cash, setCash] = useState('');
  const [notes, setNotes] = useState('');
  const [actions, setActions] = useState<Corrective[]>([]);
  const [draft, setDraft] = useState<Corrective>({ description: '', owner_id: '', due_date: todayLocalISO() });
  const [photos, setPhotos] = useState<PhotoDraft[]>([]);
  const [photoBusy, setPhotoBusy] = useState(false);
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const recRef = useRef<InstanceType<SpeechRecognitionCtor> | null>(null);
  const speechAvailable = !!getSpeech();

  useEffect(() => () => recRef.current?.stop(), []);

  const toggleDictation = () => {
    const Ctor = getSpeech();
    if (!Ctor) return;
    if (listening) {
      recRef.current?.stop();
      setListening(false);
      return;
    }
    const rec = new Ctor();
    rec.lang = 'es-MX';
    rec.continuous = true;
    rec.interimResults = false;
    rec.onresult = (ev) => {
      let text = '';
      for (let i = ev.resultIndex; i < ev.results.length; i++) if (ev.results[i].isFinal) text += ev.results[i][0].transcript + ' ';
      if (text) setNotes((n) => (n ? n + ' ' : '') + text.trim());
    };
    rec.onend = () => setListening(false);
    rec.onerror = () => setListening(false);
    recRef.current = rec;
    rec.start();
    setListening(true);
  };

  const addPhotos = async (e: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    e.target.value = '';
    if (!files.length) return;
    const room = MAX_PHOTOS - photos.length;
    if (room <= 0) {
      toast.toast(`Máximo ${MAX_PHOTOS} fotos por auditoría`, 'error');
      return;
    }
    setPhotoBusy(true);
    try {
      const next: PhotoDraft[] = [];
      for (const f of files.slice(0, room)) {
        try {
          // Reducida en el cliente (≤1280 px, JPEG 0.8) para no exceder el máximo del servidor (3 MB).
          const base64 = await compressImage(f);
          next.push({ key: `foto_${photos.length + next.length + 1}`, base64, name: f.name });
        } catch (err) {
          toast.error(err, `No se pudo procesar ${f.name}`);
        }
      }
      if (files.length > room) toast.toast(`Sólo se agregaron ${room} foto(s): máximo ${MAX_PHOTOS}`, 'info');
      setPhotos((xs) => [...xs, ...next]);
    } finally {
      setPhotoBusy(false);
    }
  };

  const addAction = () => {
    if (!draft.description.trim()) return;
    setActions((xs) => [...xs, { ...draft, description: draft.description.trim() }]);
    setDraft({ description: '', owner_id: '', due_date: todayLocalISO() });
  };

  const pending = CHECKLIST.filter((c) => checks[c.key] === null);
  const failed = CHECKLIST.filter((c) => checks[c.key] === false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (pending.length) {
      toast.toast(`Faltan ${pending.length} respuesta(s) del checklist`, 'error');
      return;
    }
    setBusy(true);
    try {
      const body = {
        point_id: pointId,
        checklist: Object.fromEntries(CHECKLIST.map((c) => [c.key, !!checks[c.key]])),
        cash_counted_cents: cash === '' ? null : Math.round(parseFloat(cash) * 100),
        notes: notes || null,
        photos: photos.map((p) => ({ key: p.key, base64: p.base64 })),
        corrective_actions: actions.map((a) => ({ description: a.description, owner_id: a.owner_id || user?.id || null, due_date: a.due_date || null })),
      };
      const r = await api.post<{ audit_id: string; case_ids: string[]; cash_expected_cents: number | null }>('/v1/audits', body);
      if (r.case_ids.length) {
        toast.toast(`Auditoría enviada. Se abrió ${r.case_ids.length} caso(s).`, 'success');
        nav(`/casos/${r.case_ids[0]}`);
      } else {
        toast.toast(r.cash_expected_cents !== null && cash !== '' ? `Auditoría enviada. Arqueo OK (esperado ${money(r.cash_expected_cents)}).` : 'Auditoría enviada sin no conformidades.', 'success');
        nav('/supervisor');
      }
    } catch (err) {
      toast.error(err);
    } finally {
      setBusy(false);
    }
  };

  if (point.loading && !point.data) return <Loading />;

  return (
    <form onSubmit={submit}>
      <PageTitle title={`Auditoría · ${point.data?.name ?? ''}`} subtitle={point.data?.address ?? undefined} actions={<Link to="/supervisor" className="btn">← Mi día</Link>} />
      <Card title="Checklist Sí / No" actions={failed.length ? <Badge tone="red">{failed.length} no conformidad(es)</Badge> : pending.length ? <Badge tone="amber">{pending.length} pendientes</Badge> : <Badge tone="green">Completo</Badge>}>
        <div className="check-list">
          {CHECKLIST.map((c) => (
            <div className="check-item" key={c.key} data-testid={`check-${c.key}`}>
              <span className="q">{c.label}</span>
              <div className="yn">
                <button type="button" className={`btn ${checks[c.key] === true ? 'on-yes' : ''}`} onClick={() => setChecks((s) => ({ ...s, [c.key]: true }))} aria-pressed={checks[c.key] === true}>
                  Sí
                </button>
                <button type="button" className={`btn ${checks[c.key] === false ? 'on-no' : ''}`} onClick={() => setChecks((s) => ({ ...s, [c.key]: false }))} aria-pressed={checks[c.key] === false}>
                  No
                </button>
              </div>
            </div>
          ))}
        </div>
      </Card>

      <Card title="Arqueo sorpresa">
        <Field label="Efectivo contado (MXN)" hint="Se compara contra el esperado del turno abierto; una diferencia > $20 abre un caso.">
          <input className="big-input" type="number" inputMode="decimal" min="0" step="0.01" placeholder="0.00" value={cash} onChange={(e) => setCash(e.target.value)} />
        </Field>
      </Card>

      <Card
        title="Notas"
        actions={
          speechAvailable ? (
            <button type="button" className={`btn ${listening ? 'btn-danger' : ''}`} onClick={toggleDictation}>
              {listening ? '■ Detener dictado' : '🎤 Dictar'}
            </button>
          ) : (
            <span className="muted small">Dictado no disponible en este navegador</span>
          )
        }
      >
        <textarea value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Observaciones, coaching en sitio, hallazgos…" rows={4} style={{ width: '100%' }} />
      </Card>

      <Card title={`Fotos (${photos.length}/${MAX_PHOTOS})`} actions={<span className="muted small">Se reducen en el navegador antes de enviar</span>}>
        <div className="photo-picker" data-testid="audit-photos">
          {photos.map((p, i) => (
            <div className="evidence-thumb" key={p.key} data-testid="audit-photo">
              <img src={`data:image/jpeg;base64,${p.base64}`} alt={p.name} />
              <span className="evidence-meta">
                <span>{p.key}</span>
                <span>{fmtBytes(base64Bytes(p.base64))}</span>
              </span>
              <button type="button" className="remove" aria-label={`Quitar ${p.name}`} onClick={() => setPhotos((xs) => xs.filter((_, j) => j !== i))}>
                ×
              </button>
            </div>
          ))}
          {photos.length < MAX_PHOTOS && (
            <label className="btn" style={{ cursor: photoBusy ? 'wait' : 'pointer' }}>
              {photoBusy ? 'Procesando…' : '📷 Agregar foto'}
              <input type="file" accept="image/*" capture="environment" multiple onChange={addPhotos} disabled={photoBusy} style={{ display: 'none' }} data-testid="audit-photo-input" />
            </label>
          )}
        </div>
      </Card>

      <Card title={`Acciones correctivas (${actions.length})`}>
        {actions.length > 0 && (
          <table className="table compact" style={{ marginBottom: 10 }}>
            <thead>
              <tr>
                <th>Descripción</th>
                <th>Responsable</th>
                <th>Fecha</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {actions.map((a, i) => (
                <tr key={i}>
                  <td>{a.description}</td>
                  <td>{users.data?.find((u) => u.id === a.owner_id)?.name ?? user?.name}</td>
                  <td>{a.due_date}</td>
                  <td>
                    <button type="button" className="btn small btn-ghost" onClick={() => setActions((xs) => xs.filter((_, j) => j !== i))}>
                      Quitar
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <div className="form-grid">
          <Field label="Descripción">
            <input value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} placeholder="Qué debe corregirse" />
          </Field>
          <Field label="Responsable">
            {users.data ? (
              <select value={draft.owner_id} onChange={(e) => setDraft({ ...draft, owner_id: e.target.value })}>
                <option value="">{user?.name} (yo)</option>
                {users.data.filter((u) => u.is_active).map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.name}
                  </option>
                ))}
              </select>
            ) : (
              <input value={user?.name ?? ''} disabled />
            )}
          </Field>
          <Field label="Fecha objetivo">
            <input type="date" value={draft.due_date} onChange={(e) => setDraft({ ...draft, due_date: e.target.value })} />
          </Field>
          <button type="button" className="btn" onClick={addAction} disabled={!draft.description.trim()}>
            + Agregar
          </button>
        </div>
      </Card>

      <button type="submit" className="btn btn-accent btn-big btn-block" disabled={busy}>
        {busy ? 'Enviando…' : 'Enviar auditoría'}
      </button>
    </form>
  );
}
