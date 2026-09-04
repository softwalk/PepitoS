interface Props {
  value: string; // pesos como texto, p. ej. "1250" o "1250.50"
  onChange: (v: string) => void;
}

/** Teclado numérico grande para capturar pesos. */
export default function Numpad({ value, onChange }: Props) {
  const press = (k: string) => {
    if (k === '⌫') return onChange(value.slice(0, -1));
    if (k === '.') {
      if (value.includes('.')) return;
      return onChange(value === '' ? '0.' : value + '.');
    }
    if (value.includes('.') && value.split('.')[1].length >= 2) return;
    if (value.length >= 8) return;
    onChange(value === '0' ? k : value + k);
  };
  const keys = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '.', '0', '⌫'];
  return (
    <div className="numpad" role="group" aria-label="Teclado numérico">
      {keys.map((k) => (
        <button type="button" key={k} onClick={() => press(k)} aria-label={k === '⌫' ? 'Borrar' : k}>
          {k}
        </button>
      ))}
    </div>
  );
}

export function pesosToCents(v: string): number {
  if (!v) return 0;
  const n = Number(v);
  if (!Number.isFinite(n)) return 0;
  return Math.round(n * 100);
}
