// Compact relationship strip making the linkage legible:
// gene → target entity → mechanism → active moiety → form.
// Nodes wrap (rather than a single crushed/scrolling row) and keep a readable minimum
// width, and values wrap instead of ellipsizing — so nothing truncates to "Compound A (ac…".

import type { DrugCandidate } from '../../domain/stage3';

function Node({ kind, value }: { kind: string; value: string }) {
  return (
    <span className="flex min-w-[130px] max-w-[240px] flex-1 flex-col">
      <span className="font-mono text-[9px] uppercase tracking-wide text-muted">{kind}</span>
      <span className="text-[11.5px] font-semibold leading-tight text-ink [overflow-wrap:anywhere]" title={value}>
        {value}
      </span>
    </span>
  );
}

function Arrow() {
  return (
    <span aria-hidden="true" className="flex-none self-center px-1 font-mono text-[11px] text-line-strong">
      →
    </span>
  );
}

export function MechanismStrip({ candidate }: { candidate: DrugCandidate }) {
  const form = candidate.forms[0];
  return (
    <div
      data-testid="mechanism-strip"
      className="flex flex-wrap items-stretch gap-x-1 gap-y-2 rounded-lg border border-line bg-sunken/50 px-3 py-2"
    >
      <Node kind="gene" value={candidate.source_lever_gene_id} />
      <Arrow />
      <Node kind={candidate.target_entity.entity_type} value={candidate.target_entity.label} />
      <Arrow />
      <Node kind="mechanism" value={candidate.mechanism_action} />
      <Arrow />
      <Node kind="active moiety" value={candidate.active_moiety} />
      <Arrow />
      <Node kind="form" value={form ? form.form_id : 'no form'} />
    </div>
  );
}
