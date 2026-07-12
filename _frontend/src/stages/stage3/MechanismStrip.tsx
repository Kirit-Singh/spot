// Compact relationship strip making the linkage legible:
// gene → target entity → mechanism → active moiety → form.

import type { DrugCandidate } from '../../domain/stage3';

// Each node keeps a readable minimum width and never shrinks; the strip scrolls
// horizontally instead of crushing the evidence chain into `G… / IN…` fragments.
function Node({ kind, value }: { kind: string; value: string }) {
  return (
    <span className="flex w-[96px] flex-none flex-col">
      <span className="font-mono text-[9px] uppercase tracking-wide text-muted">{kind}</span>
      <span className="truncate text-[11.5px] font-semibold text-ink" title={value}>
        {value}
      </span>
    </span>
  );
}

function Arrow() {
  return <span className="flex-none px-1 font-mono text-[11px] text-line-strong">→</span>;
}

export function MechanismStrip({ candidate }: { candidate: DrugCandidate }) {
  const form = candidate.forms[0];
  return (
    <div
      data-testid="mechanism-strip"
      className="flex items-center gap-1 overflow-x-auto rounded-lg border border-line bg-sunken/50 px-3 py-2"
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
