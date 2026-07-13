// One Stage-4 scorecard: candidate identity + form on top, then separate panels
// for human safety, systemic/unbound exposure, measured CNS/tumour evidence,
// CNS-MPO descriptor support (a heuristic, not clinical exposure), and the exact
// 2026 NEBPI decision path.

import type { NebpiTier, Scorecard as ScorecardModel } from '../../domain/stage4';
import { NamespaceChip, StatePill } from '../../shell/chips';
import { useProvenance } from '../../shell/provenanceContext';
import { FieldRow } from './fieldDisplay';

const TIER_LABEL: Record<NebpiTier, string> = {
  sufficiently_permeable: 'sufficiently permeable',
  insufficiently_permeable: 'insufficiently permeable',
  impermeable: 'impermeable',
  not_evaluated: 'not evaluated',
};
// NEBPI tiers are NOT a traffic light: the tier name carries the meaning, so styling
// stays neutral with a single accent for the permeable tier — no safe/caution/danger hues.
const TIER_TONE: Record<NebpiTier, Parameters<typeof StatePill>[0]['tone']> = {
  sufficiently_permeable: 'accent',
  insufficiently_permeable: 'neutral',
  impermeable: 'neutral',
  not_evaluated: 'muted',
};

function Panel({ title, note, children }: { title: string; note?: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-line p-3">
      <h4 className="font-mono text-[9.5px] uppercase tracking-wide text-muted">{title}</h4>
      {note && <p className="mt-0.5 text-[10px] leading-tight text-muted">{note}</p>}
      <div className="mt-2">{children}</div>
    </section>
  );
}

export function Scorecard({ scorecard }: { scorecard: ScorecardModel }) {
  const { open } = useProvenance();
  const s = scorecard;
  return (
    <article className="rounded-xl border border-line bg-surface p-4">
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-[14px] font-semibold text-ink">{s.active_moiety}</h3>
            <span className="font-mono text-[10px] text-muted">{s.candidate_id}</span>
          </div>
          <div className="mt-0.5 font-mono text-[10.5px] text-muted">form: {s.form}</div>
        </div>
        <div className="flex items-center gap-2">
          <StatePill label={`NEBPI: ${TIER_LABEL[s.nebpi.tier]}`} tone={TIER_TONE[s.nebpi.tier]} />
          <NamespaceChip ns={s.provenance.namespace} />
        </div>
      </header>

      <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
        <Panel title="Delivery requirement">
          <FieldRow label="Requirement" field={s.delivery.requirement} />
          <FieldRow label="Supporting evidence" field={s.delivery.supporting_evidence} />
        </Panel>

        <Panel title="Human safety / regulatory">
          <FieldRow label="Regulatory status" field={s.safety.regulatory_status} />
          <FieldRow label="Boxed warning" field={s.safety.boxed_warning} />
          <FieldRow label="Key risks" field={s.safety.key_risks} />
        </Panel>

        <Panel title="Systemic / unbound exposure">
          <FieldRow label="Systemic Cmax" field={s.exposure.systemic_cmax} />
          <FieldRow label="Unbound fraction" field={s.exposure.unbound_fraction} />
          <FieldRow label="Half-life" field={s.exposure.half_life} />
        </Panel>

        <Panel title="Measured CNS / tumour">
          <FieldRow label="Kp,uu" field={s.cns.kp_uu} />
          <FieldRow label="CSF concentration" field={s.cns.csf_concentration} />
          <FieldRow label="Tumour concentration" field={s.cns.tumour_concentration} />
        </Panel>

        <Panel title="CNS-MPO descriptor support">
          <FieldRow label="ClogP" field={s.cns_mpo.clogp} />
          <FieldRow label="ClogD" field={s.cns_mpo.clogd} />
          <FieldRow label="TPSA" field={s.cns_mpo.tpsa} />
          <FieldRow label="MW" field={s.cns_mpo.mw} />
          <FieldRow label="HBD" field={s.cns_mpo.hbd} />
          <FieldRow label="pKa" field={s.cns_mpo.pka} />
          <FieldRow label="Descriptor score" field={s.cns_mpo.descriptor_score} />
        </Panel>

        <Panel title="Treatment-context safety">
          <FieldRow label="Setting" field={s.treatment_context.setting} />
          <FieldRow label="Concerns" field={s.treatment_context.concerns} />
        </Panel>
      </div>

      <section className="mt-3 rounded-lg border border-line p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h4 className="font-mono text-[9.5px] uppercase tracking-wide text-muted">
            NEBPI decision path
          </h4>
          <span className="font-mono text-[10px] text-muted">{s.nebpi.version}</span>
        </div>
        <ol className="mt-2 space-y-1">
          {s.nebpi.decision_path.map((step, i) => (
            <li key={i} className="grid grid-cols-[18px_1fr_auto] items-center gap-2 text-[11.5px]">
              <span className="flex h-[18px] w-[18px] items-center justify-center rounded-full bg-sunken font-mono text-[10px] text-ink-2">
                {i + 1}
              </span>
              <span className="text-ink-2">{step.label}</span>
              <span className="font-mono text-[10.5px] text-ink">{step.outcome}</span>
            </li>
          ))}
        </ol>
        <p className="mt-2 text-[11px] leading-relaxed text-ink-2">{s.nebpi.rationale}</p>
      </section>

      <div className="mt-3">
        <button
          type="button"
          onClick={() => open(`Stage 4 — ${s.scorecard_id}`, s.provenance)}
          className="text-[11px] font-semibold text-ink-2 hover:text-accent"
        >
          Provenance
        </button>
      </div>
    </article>
  );
}
