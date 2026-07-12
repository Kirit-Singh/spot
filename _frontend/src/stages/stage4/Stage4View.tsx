// Stage 4 — safety & brain exposure. One scorecard per candidate. Sorting is
// offered ONLY for keys the adapter supplies (evidence completeness / NEBPI tier);
// there is no fabricated composite ranking.

import { useMemo, useState } from 'react';
import type { MeasurementState } from '../../domain/common';
import type { NebpiTier, Scorecard as ScorecardModel, SortKey, Stage4Artifact } from '../../domain/stage4';
import { useProvenance } from '../../shell/provenanceContext';
import { STAGE4_NOTES } from '../../shell/methodNotes';
import { Scorecard } from './Scorecard';
import { completenessOf } from './completeness';

const TIER_ORDER: Record<NebpiTier, number> = {
  sufficiently_permeable: 0,
  insufficiently_permeable: 1,
  impermeable: 2,
  not_evaluated: 3,
};

function fieldStates(s: ScorecardModel): MeasurementState[] {
  return [
    s.safety.regulatory_status,
    s.safety.boxed_warning,
    s.safety.key_risks,
    s.exposure.systemic_cmax,
    s.exposure.unbound_fraction,
    s.exposure.half_life,
    s.cns.kp_uu,
    s.cns.csf_concentration,
    s.cns.tumour_concentration,
    s.cns_mpo.clogp,
    s.cns_mpo.clogd,
    s.cns_mpo.tpsa,
    s.cns_mpo.mw,
    s.cns_mpo.hbd,
    s.cns_mpo.pka,
    s.cns_mpo.descriptor_score,
  ].map((f) => f.state);
}

const SORT_LABEL: Record<SortKey, string> = {
  evidence_completeness: 'evidence completeness',
  nebpi_tier: 'NEBPI tier',
};

export function Stage4View({ artifact }: { artifact: Stage4Artifact }) {
  const { open } = useProvenance();
  const [sort, setSort] = useState<SortKey | 'none'>('none');

  const cards = useMemo(() => {
    const list = [...artifact.scorecards];
    if (sort === 'evidence_completeness') {
      list.sort((a, b) => completenessOf(fieldStates(b)).present - completenessOf(fieldStates(a)).present);
    } else if (sort === 'nebpi_tier') {
      list.sort((a, b) => TIER_ORDER[a.nebpi.tier] - TIER_ORDER[b.nebpi.tier]);
    }
    return list;
  }, [artifact.scorecards, sort]);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-line bg-surface px-5 py-2.5">
        <span className="font-mono text-[10.5px] uppercase tracking-wide text-muted">sort</span>
        <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Sort scorecards">
          <button
            type="button"
            aria-pressed={sort === 'none'}
            onClick={() => setSort('none')}
            className={`rounded-md border px-2 py-1 font-mono text-[10.5px] ${
              sort === 'none' ? 'border-accent bg-accent text-white' : 'border-line text-ink-2 hover:border-accent'
            }`}
          >
            none
          </button>
          {artifact.sortable_by.map((k) => (
            <button
              key={k}
              type="button"
              aria-pressed={sort === k}
              onClick={() => setSort(k)}
              className={`rounded-md border px-2 py-1 font-mono text-[10.5px] ${
                sort === k ? 'border-accent bg-accent text-white' : 'border-line text-ink-2 hover:border-accent'
              }`}
            >
              {SORT_LABEL[k]}
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={() => open('Stage 4 — scorecard set', artifact.provenance, STAGE4_NOTES)}
          className="ml-auto inline-flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1 text-[11px] font-semibold text-ink-2 hover:border-accent hover:text-accent"
        >
          <span className="flex h-[14px] w-[14px] items-center justify-center rounded-full border border-current text-[8px] font-bold italic">
            i
          </span>
          Provenance
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
        <div className="space-y-3">
          {cards.map((s) => (
            <Scorecard key={s.scorecard_id} scorecard={s} />
          ))}
        </div>
      </div>
    </div>
  );
}
