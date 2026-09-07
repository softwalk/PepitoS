/** Tabla ejecutiva reutilizable: ordenar por columna, elegir columnas visibles y detalle al pulsar una fila.
 *  No conoce el dominio: recibe columnas {key,label,render?,sortValue?,numeric?} y filas. */
import { useMemo, useState, type ReactNode } from 'react';

export interface DTColumn<T> {
  key: string;
  label: string;
  numeric?: boolean;
  render?: (row: T) => ReactNode;
  sortValue?: (row: T) => number | string | null | undefined;
  /** Oculta por defecto (se puede mostrar desde el selector de columnas). */
  hidden?: boolean;
}

interface Props<T> {
  columns: DTColumn<T>[];
  rows: T[];
  rowKey: (row: T, i: number) => string;
  /** Detalle expandible al pulsar la fila. */
  detail?: (row: T) => ReactNode;
  pageSize?: number;
  defaultSort?: { key: string; dir: 'asc' | 'desc' };
  compact?: boolean;
  testId?: string;
  emptyText?: string;
}

export function DataTable<T extends Record<string, unknown>>({ columns, rows, rowKey, detail, pageSize = 25, defaultSort, compact = true, testId, emptyText = 'Sin registros' }: Props<T>) {
  const [sort, setSort] = useState<{ key: string; dir: 'asc' | 'desc' } | null>(defaultSort ?? null);
  const [hidden, setHidden] = useState<Set<string>>(() => new Set(columns.filter((c) => c.hidden).map((c) => c.key)));
  const [open, setOpen] = useState<string | null>(null);
  const [picker, setPicker] = useState(false);
  const [limit, setLimit] = useState(pageSize);
  const visible = columns.filter((c) => !hidden.has(c.key));
  const sorted = useMemo(() => {
    if (!sort) return rows;
    const col = columns.find((c) => c.key === sort.key);
    if (!col) return rows;
    const val = (r: T) => (col.sortValue ? col.sortValue(r) : (r[col.key] as number | string | null | undefined));
    const arr = rows.slice();
    arr.sort((a, b) => {
      const x = val(a);
      const y = val(b);
      if (x == null && y == null) return 0;
      if (x == null) return 1;
      if (y == null) return -1;
      const c = typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y), 'es');
      return sort.dir === 'asc' ? c : -c;
    });
    return arr;
  }, [rows, sort, columns]);
  const toggleSort = (key: string) => setSort((s) => (s?.key === key ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: 'desc' }));
  if (!rows.length) return <p className="empty">{emptyText}</p>;
  return (
    <div data-testid={testId}>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 6 }}>
        <div className="col-picker">
          <button type="button" className="btn btn-ghost small" onClick={() => setPicker((v) => !v)} aria-expanded={picker} data-testid="col-picker">
            Columnas ({visible.length}/{columns.length})
          </button>
          {picker && (
            <div className="col-picker-menu" role="menu">
              {columns.map((c) => (
                <label key={c.key}>
                  <input type="checkbox" checked={!hidden.has(c.key)} onChange={(e) => setHidden((h) => { const n = new Set(h); if (e.target.checked) n.delete(c.key); else n.add(c.key); return n; })} /> {c.label}
                </label>
              ))}
            </div>
          )}
        </div>
      </div>
      <div className="table-wrap">
        <table className={`table ${compact ? 'compact' : ''}`}>
          <thead>
            <tr>
              {visible.map((c) => (
                <th key={c.key} className={`sortable ${c.numeric ? 'num' : ''}`} onClick={() => toggleSort(c.key)} aria-sort={sort?.key === c.key ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none'}>
                  {c.label}
                  <span className="sort-ind" aria-hidden>{sort?.key === c.key ? (sort.dir === 'asc' ? '▲' : '▼') : '↕'}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.slice(0, limit).map((r, i) => {
              const k = rowKey(r, i);
              const isOpen = open === k;
              return [
                <tr key={k} className={detail ? 'clickable' : ''} onClick={detail ? () => setOpen(isOpen ? null : k) : undefined} aria-expanded={detail ? isOpen : undefined}>
                  {visible.map((c) => (
                    <td key={c.key} className={c.numeric ? 'num' : ''}>{c.render ? c.render(r) : String(r[c.key] ?? '—')}</td>
                  ))}
                </tr>,
                detail && isOpen ? (
                  <tr key={k + ':d'} className="row-detail">
                    <td colSpan={visible.length}>{detail(r)}</td>
                  </tr>
                ) : null,
              ];
            })}
          </tbody>
        </table>
      </div>
      {sorted.length > limit && (
        <p className="muted small">
          Mostrando {limit} de {sorted.length} filas ·{' '}
          <button type="button" className="btn btn-ghost small" onClick={() => setLimit((l) => l + pageSize)}>
            Ver más
          </button>
        </p>
      )}
    </div>
  );
}
