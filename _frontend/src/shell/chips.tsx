// Small, low-chrome status primitives. Scientific status appears compactly where
// it matters — a namespace/status chip, an evidence-state cell — never as banners.

import type { MeasurementState, Namespace } from '../domain/common';
import { measurementLabel, namespaceLabel } from '../domain/common';

const NS_STYLE: Record<Namespace, string> = {
  production: 'border-accent/40 text-accent',
  research_only: 'border-amber/40 text-amber',
  fixture: 'border-line-strong text-muted',
};

/** Quiet namespace chip (fixture/research-only/production). */
export function NamespaceChip({ ns }: { ns: Namespace }) {
  return (
    <span
      className={`inline-flex items-center rounded-md border px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wide ${NS_STYLE[ns]}`}
      title={`namespace: ${namespaceLabel(ns)}`}
    >
      {namespaceLabel(ns)}
    </span>
  );
}

/** Chip stating production eligibility (always visible for fixtures). */
export function EligibilityChip({ eligible }: { eligible: boolean }) {
  return (
    <span className="inline-flex items-center rounded-md border border-line px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wide text-muted">
      production_eligible={eligible ? 'true' : 'false'}
    </span>
  );
}

const MEAS_STYLE: Record<MeasurementState, string> = {
  measured: 'text-ink border-ink/25',
  calculated: 'text-accent border-accent/30',
  label_derived: 'text-ink-2 border-line-strong',
  not_evaluated: 'text-muted border-line',
  missing: 'text-danger border-danger/30',
};

/** Evidence/measurement-state cell — distinguishes measured/calculated/…/missing. */
export function MeasurementBadge({ state }: { state: MeasurementState }) {
  return (
    <span
      className={`inline-flex items-center rounded border px-1.5 py-0.5 font-mono text-[10px] ${MEAS_STYLE[state]}`}
    >
      {measurementLabel(state)}
    </span>
  );
}

/** A generic small pill for enum-ish states (cross-class, compatibility, tier). */
export function StatePill({
  label,
  tone = 'neutral',
  title,
}: {
  label: string;
  tone?: 'neutral' | 'accent' | 'ok' | 'amber' | 'danger' | 'muted';
  title?: string;
}) {
  const tones: Record<string, string> = {
    neutral: 'text-ink-2 border-line',
    accent: 'text-accent border-accent/35',
    ok: 'text-ok border-ok/35',
    amber: 'text-amber border-amber/35',
    danger: 'text-danger border-danger/35',
    muted: 'text-muted border-line',
  };
  return (
    <span
      title={title ?? label}
      className={`inline-flex items-center rounded-md border px-1.5 py-0.5 font-mono text-[10px] ${tones[tone]}`}
    >
      {label}
    </span>
  );
}
