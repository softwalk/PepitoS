interface Props {
  icon: string;
  label: string;
  value: boolean | null;
  onChange: (v: boolean) => void;
}

/** Fila de checklist Sí/No: icono + color + texto. */
import Icon from './Icon';

export default function YesNo({ icon, label, value, onChange }: Props) {
  return (
    <div className={`check-item ${value === true ? 'is-yes' : value === false ? 'is-no' : ''}`}>
      <div className="label">
        <Icon icon={icon} />
        <span>{label}</span>
      </div>
      <div className="yn" role="group" aria-label={label}>
        <button type="button" className={value === true ? 'on-yes' : ''} aria-pressed={value === true} onClick={() => onChange(true)}>
          ✓ Sí
        </button>
        <button type="button" className={value === false ? 'on-no' : ''} aria-pressed={value === false} onClick={() => onChange(false)}>
          ✕ No
        </button>
      </div>
    </div>
  );
}
