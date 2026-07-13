// Rendering for a Field<T>. Measured / calculated / label-derived / not-evaluated /
// missing are always distinguished; a null value is shown as its state, never 0.

import type { Field } from '../../domain/common';
import { MeasurementBadge } from '../../shell/chips';

function displayValue<T>(f: Field<T>): string {
  if (f.value === null) {
    return f.state === 'missing' ? 'missing' : f.state === 'not_evaluated' ? 'not evaluated' : '—';
  }
  const v = typeof f.value === 'number' ? String(f.value) : String(f.value);
  return f.unit ? `${v} ${f.unit}` : v;
}

export function FieldRow<T>({ label, field }: { label: string; field: Field<T> }) {
  const absent = field.value === null;
  return (
    <div className="grid grid-cols-[1fr_auto] items-center gap-2 border-t border-line/70 py-1.5 first:border-t-0">
      <span className="text-[11.5px] text-ink-2">{label}</span>
      <span className="flex items-center gap-2">
        <span className={`font-mono text-[11.5px] ${absent ? 'text-muted' : 'text-ink'}`}>
          {displayValue(field)}
        </span>
        <MeasurementBadge state={field.state} />
      </span>
    </div>
  );
}
