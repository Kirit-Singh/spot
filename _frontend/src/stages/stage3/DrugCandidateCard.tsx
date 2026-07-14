// One drug candidate. Shows active moiety, forms/relations, mechanism, target
// entity type, direction compatibility, directness, GBM-context state and source
// conflicts. Potency records keep their ORIGINAL relation + unit. Research-only and
// fixture candidates can be inspected but never promoted (a disabled action states why).

import { useState } from 'react';
import type {
  DirectionCompat,
  Directness,
  DrugCandidate,
  EvidenceState,
} from '../../domain/stage3';
import { NamespaceChip, StatePill } from '../../shell/chips';
import { useProvenance } from '../../shell/provenanceContext';
import { MechanismStrip } from './MechanismStrip';

const COMPAT_TONE: Record<DirectionCompat, Parameters<typeof StatePill>[0]['tone']> = {
  compatible: 'ok',
  incompatible: 'danger',
  not_evaluated: 'muted',
};
const DIRECT_TONE: Record<Directness, Parameters<typeof StatePill>[0]['tone']> = {
  direct: 'accent',
  indirect: 'neutral',
  not_evaluated: 'muted',
};
const GBM_TONE: Record<EvidenceState, Parameters<typeof StatePill>[0]['tone']> = {
  measured: 'ok',
  conflicting: 'amber',
  mixed: 'amber',
  not_evaluated: 'muted',
  missing: 'danger',
};

export function DrugCandidateCard({ candidate }: { candidate: DrugCandidate }) {
  const { open } = useProvenance();
  const [expanded, setExpanded] = useState(false);
  const promotable = candidate.provenance.namespace === 'production';

  return (
    <article className="rounded-xl border border-line bg-surface p-4">
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-[14px] font-semibold text-ink">{candidate.active_moiety}</h3>
            <span className="font-mono text-[10px] text-muted">{candidate.candidate_id}</span>
          </div>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 font-mono text-[10.5px] text-muted">
            <span>
              origin: {candidate.origin === 'pathway_node' ? `pathway node · ${candidate.pathway_node}` : 'direct target'}
            </span>
            <span>·</span>
            <span>supporting arm: {candidate.desired_arm === 'away_from_A' ? 'away from A' : 'toward B'}</span>
            <span>·</span>
            <span>mechanism: {candidate.mechanism_direction}</span>
          </div>
        </div>
        <NamespaceChip ns={candidate.provenance.namespace} />
      </header>

      <div className="mt-3">
        <MechanismStrip candidate={candidate} />
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        <StatePill label={`direction: ${candidate.direction_compatibility}`} tone={COMPAT_TONE[candidate.direction_compatibility]} />
        <StatePill label={`directness: ${candidate.directness}`} tone={DIRECT_TONE[candidate.directness]} />
        <StatePill label={`GBM context: ${candidate.gbm_context}`} tone={GBM_TONE[candidate.gbm_context]} />
        {candidate.source_conflicts.length > 0 && (
          <StatePill label={`${candidate.source_conflicts.length} source conflict(s)`} tone="amber" />
        )}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
          className="text-[11px] font-semibold text-accent hover:underline"
        >
          {expanded ? 'Hide evidence' : 'Inspect evidence'}
        </button>
        <button
          type="button"
          onClick={() => open(`Stage 3 — ${candidate.candidate_id}`, candidate.provenance)}
          className="text-[11px] font-semibold text-ink-2 hover:text-accent"
        >
          Provenance
        </button>
        <span
          title={
            promotable
              ? 'Promote to the locked drug'
              : `${candidate.provenance.namespace} candidates cannot be promoted`
          }
        >
          <button
            type="button"
            disabled={!promotable}
            aria-disabled={!promotable}
            className="rounded-md border border-line px-2 py-1 text-[11px] font-semibold text-muted disabled:cursor-not-allowed disabled:opacity-60"
          >
            Promote {promotable ? '' : '(disabled)'}
          </button>
        </span>
      </div>

      {expanded && (
        <div className="mt-3 border-t border-line pt-3">
          <h4 className="mb-1.5 font-mono text-[9.5px] uppercase tracking-wide text-muted">
            Administered forms
          </h4>
          <ul className="mb-3 space-y-1 text-[11.5px]">
            {candidate.forms.map((f) => (
              <li key={f.form_id} className="flex items-center gap-2">
                <span className="font-mono text-ink-2">{f.form_id}</span>
                <span className="font-mono text-[10px] text-muted">{f.relation}</span>
                {f.route && <span className="text-[10px] text-muted">· {f.route}</span>}
              </li>
            ))}
          </ul>

          <h4 className="mb-1.5 font-mono text-[9.5px] uppercase tracking-wide text-muted">
            Potency records
          </h4>
          {candidate.potency_records.length === 0 ? (
            <p className="mb-3 text-[11px] text-muted">No potency records supplied.</p>
          ) : (
            <table className="mb-3 w-full text-left text-[11.5px]">
              <tbody>
                {candidate.potency_records.map((p, i) => (
                  <tr key={i} className="border-t border-line/70">
                    <td className="py-1 font-mono text-ink">
                      {p.relation} {p.value != null ? p.value : '—'} {p.unit ?? ''}
                    </td>
                    <td className="py-1 text-ink-2">{p.assay}</td>
                    <td className="py-1 text-right font-mono text-[10px] text-muted">
                      {p.source.label} {p.source.record_id}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {candidate.source_conflicts.length > 0 && (
            <>
              <h4 className="mb-1.5 font-mono text-[9.5px] uppercase tracking-wide text-muted">
                Source conflicts
              </h4>
              <ul className="space-y-1.5 text-[11.5px]">
                {candidate.source_conflicts.map((c, i) => (
                  <li key={i}>
                    <span className="font-mono text-ink-2">{c.field}</span>
                    <div className="mt-0.5 flex flex-wrap gap-1.5">
                      {c.values.map((v, j) => (
                        <span key={j} className="rounded border border-line px-1.5 py-0.5 font-mono text-[10px] text-ink-2">
                          {v.source}: {v.value}
                        </span>
                      ))}
                    </div>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </article>
  );
}
