import { useState } from 'react';
import { StatePill } from '../shell/chips';
import { conditionLabel } from './contrastTitle';
import type {
  DevelopmentRealResolution,
  DevDrugArm,
  DevDrugEdge,
  DevDrugTarget,
  DevPathwayArm,
  DevPkCandidate,
  JsonRecord,
} from './devRealAdapter';

const CANVAS = 'flex min-h-0 flex-1 flex-col gap-3 overflow-auto p-4';
const CELL = 'px-2 py-1.5 font-mono text-[10.5px] text-ink-2';
const HEAD = 'px-2 py-1.5 text-left font-mono text-[9.5px] uppercase tracking-wide text-muted';

function text(value: unknown): string {
  return typeof value === 'string' && value.length > 0 ? value : '—';
}

function number(value: unknown, digits = 3): string {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : '—';
}

function scalar(value: unknown): string {
  return typeof value === 'number' && Number.isFinite(value) ? String(value) : text(value);
}

function object(value: unknown): JsonRecord {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? value as JsonRecord : {};
}

function values(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

interface HumanCnsEvidenceView {
  observed: boolean;
  summary: string;
  sourceLabel: string | null;
  sourceUrl: string | null;
}

function humanCnsEvidence(brain: JsonRecord): HumanCnsEvidenceView {
  const direct = object(brain.direct_human_cns_evidence);
  const measurements = values(direct.measurements);
  const observed = direct.status === 'observed' && measurements.length > 0;
  if (!observed) {
    return {
      observed: false,
      summary: 'Not evaluated in this evidence set',
      sourceLabel: null,
      sourceUrl: null,
    };
  }
  const measurement = object(measurements[0]);
  const source = object(measurement.source);
  const evidenceType = text(measurement.evidence_type);
  const summary = evidenceType === 'human_brain_pet_target_engagement'
    ? 'Human PET brain target engagement observed'
    : evidenceType.replaceAll('_', ' ');
  const sourceUrl = typeof source.source_url === 'string' ? source.source_url : null;
  const sourceLabel = typeof source.pmid === 'string'
    ? `PMID ${source.pmid}`
    : typeof source.doi === 'string' ? `DOI ${source.doi}` : sourceUrl ? 'primary source' : null;
  return { observed: true, summary, sourceLabel, sourceUrl };
}

function measuredConcentration(brain: JsonRecord): string {
  const exposure = object(brain.measured_exposure);
  for (const key of ['human_csf_concentration', 'unbound_brain_concentration']) {
    const field = object(exposure[key]);
    if (field.state !== 'observed' || field.value === null || field.value === undefined) continue;
    const unit = typeof field.units === 'string' ? ` ${field.units}` : '';
    return `${scalar(field.value)}${unit}`;
  }
  return 'not evaluated in this evidence set';
}

function nonhumanEvidenceLinks(brain: JsonRecord): { label: string; url: string }[] {
  return values(brain.nonhuman_cns_evidence).flatMap((raw) => {
    const evidence = object(raw);
    const source = object(evidence.source);
    if (typeof source.source_url !== 'string') return [];
    const label = typeof evidence.evidence_type === 'string'
      ? evidence.evidence_type.replaceAll('_', ' ')
      : 'nonhuman CNS evidence';
    return [{ label, url: source.source_url }];
  });
}

function armLabel(program: string, desired: string, labels: Map<string, string>): string {
  return `${labels.get(program) ?? program.replaceAll('_', ' ')} ${desired}`;
}

function ContextStrip({ resolution }: { resolution: DevelopmentRealResolution }) {
  if (resolution.context.analysisMode !== 'endpoint_comparison') return null;
  return (
    <div className="flex items-center gap-2" data-analysis-mode="endpoint_comparison">
      <StatePill label="Endpoint comparison" tone="accent" />
      <span className="font-mono text-[9.5px] text-muted">
        {conditionLabel(resolution.context.conditionA)} → {conditionLabel(resolution.context.conditionB)}
      </span>
    </div>
  );
}

function PathwayArm({ arm, labels, condition }: { arm: DevPathwayArm; labels: Map<string, string>; condition: string }) {
  return (
    <section className="min-w-0 rounded-lg border border-line bg-surface" aria-label={armLabel(arm.program_id, arm.desired_change, labels)}>
      <header className="flex items-center gap-2 border-b border-line px-3 py-2">
        <StatePill label={arm.selection_role === 'away_from_A' ? 'from' : 'to'} tone="accent" />
        <StatePill label={conditionLabel(condition)} tone="muted" />
        <span className="text-[12px] font-semibold text-ink">{armLabel(arm.program_id, arm.desired_change, labels)}</span>
        <span className="ml-auto font-mono text-[9.5px] text-muted">GO-BP · {arm.terms.length} of {arm.n_headline_rankable}</span>
      </header>
      <div className="max-h-[68vh] overflow-auto">
        <table className="w-full border-collapse">
          <thead className="sticky top-0 bg-surface">
            <tr><th className={HEAD}>process</th><th className={HEAD}>enrichment</th><th className={HEAD}>coverage</th><th className={HEAD}>targets</th></tr>
          </thead>
          <tbody>
            {arm.terms.map((term) => (
              <tr key={term.set_id} className="border-t border-line align-top">
                <td className={CELL}>
                  <span className="block font-sans text-[11px] font-medium text-ink">{term.set_name}</span>
                  <span className="text-[9.5px] text-muted">{term.set_id}</span>
                </td>
                <td className={CELL}>{number(term.enrichment_value)}</td>
                <td className={CELL}>{number(term.target_source_coverage, 2)}</td>
                <td className={CELL}>
                  <span className="block">{term.n_hits_in_ranking}</span>
                  <span className="block max-w-[240px] truncate text-[9.5px] text-muted" title={term.leading_edge.join(', ')}>
                    {term.leading_edge.join(', ') || '—'}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function renderPathways(resolution: Extract<DevelopmentRealResolution, { route: 'pathways' }>, labels: Map<string, string>) {
  return (
    <div data-real-canvas data-development-real data-route="pathways" className={CANVAS}>
      <ContextStrip resolution={resolution} />
      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        {resolution.artifact.arms.map((arm, index) => (
          <PathwayArm
            key={arm.arm_key}
            arm={arm}
            labels={labels}
            condition={index === 0 ? resolution.context.conditionA : resolution.context.conditionB}
          />
        ))}
      </div>
    </div>
  );
}

interface DrugRow { arm: DevDrugArm; target: DevDrugTarget; drug: DevDrugEdge }

function drugRows(arm: DevDrugArm): DrugRow[] {
  return arm.targets
    .flatMap((target) => target.drugs.map((drug) => ({ arm, target, drug })))
    .sort((a, b) => {
      const observed = Number(b.drug.observed_perturbation_support) - Number(a.drug.observed_perturbation_support);
      return observed || a.target.arm_rank - b.target.arm_rank || a.drug.molecule_chembl_id.localeCompare(b.drug.molecule_chembl_id);
    });
}

function DrugArm({ arm, labels, release, condition, shared, sharedOnly }: {
  arm: DevDrugArm;
  labels: Map<string, string>;
  release: string;
  condition: string;
  shared: ReadonlySet<string>;
  sharedOnly: boolean;
}) {
  const rows = drugRows(arm).filter(({ drug }) => !sharedOnly || shared.has(drug.molecule_chembl_id));
  return (
    <section className="min-w-0 rounded-lg border border-line bg-surface" aria-label={armLabel(arm.program_id, arm.desired_change, labels)}>
      <header className="flex items-center gap-2 border-b border-line px-3 py-2">
        <StatePill label={arm.role === 'away_from_A' ? 'from' : 'to'} tone="accent" />
        <StatePill label={conditionLabel(condition)} tone="muted" />
        <span className="text-[12px] font-semibold text-ink">{armLabel(arm.program_id, arm.desired_change, labels)}</span>
        <span className="ml-auto font-mono text-[9.5px] text-muted">{rows.length} links · {release}</span>
      </header>
      <div className="max-h-[68vh] overflow-auto">
        <table className="w-full table-fixed border-collapse">
          <thead className="sticky top-0 bg-surface"><tr><th className={`${HEAD} w-[26%]`}>drug</th><th className={`${HEAD} w-[18%]`}>target</th><th className={`${HEAD} w-[22%]`}>support</th><th className={HEAD}>mechanism</th></tr></thead>
          <tbody>
            {rows.map(({ target, drug }, index) => {
              const observed = drug.observed_perturbation_support;
              const opposed = drug.directional_evidence_status === 'opposed';
              const inBoth = shared.has(drug.molecule_chembl_id);
              return (
                <tr key={`${target.target_id}:${drug.molecule_chembl_id}:${index}`} className={`border-t border-line align-top ${inBoth ? 'bg-accent/10 ring-1 ring-inset ring-accent/30' : opposed ? 'bg-amber-50/60' : ''}`}>
                  <td className={CELL}><span className="flex items-center gap-1 font-sans text-[11px] font-semibold text-ink">{text(drug.pref_name)}{inBoth && <StatePill label="both arms" tone="accent" />}</span><span className="text-[9.5px] text-muted">{drug.molecule_chembl_id}</span></td>
                  <td className={CELL}><span className="block font-semibold text-ink">{target.target_symbol}</span><span className="text-[9.5px] text-muted">rank {target.arm_rank} · {number(target.arm_value)}</span></td>
                  <td className={CELL}><StatePill label={observed ? 'CRISPRi-aligned' : opposed ? 'opposed' : text(drug.directional_evidence_status)} tone={observed ? 'ok' : opposed ? 'amber' : 'muted'} /></td>
                  <td className={CELL}><span className="block font-sans text-[10.5px]">{text(drug.mechanism_of_action)}</span><span className="text-[9.5px] text-muted">phase {text(drug.max_phase_source)}</span></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function DrugsCanvas({ resolution, labels }: { resolution: Extract<DevelopmentRealResolution, { route: 'drugs' }>; labels: Map<string, string> }) {
  const store = object(resolution.artifact.sources.universe_store);
  const release = text(store.chembl_release);
  const [sharedOnly, setSharedOnly] = useState(false);
  const armMolecules = resolution.artifact.arms.map((arm) => new Set(drugRows(arm).map(({ drug }) => drug.molecule_chembl_id)));
  const shared = new Set([...armMolecules[0]].filter((id) => armMolecules[1].has(id)));
  return (
    <div data-real-canvas data-development-real data-route="drugs" className={CANVAS}>
      <div className="flex flex-wrap items-center gap-2">
        <ContextStrip resolution={resolution} />
        <div className="ml-auto flex items-center gap-1 rounded-md border border-line bg-surface p-0.5" aria-label="Drug arm overlap filter">
          <button type="button" className={`rounded px-2 py-1 font-mono text-[9.5px] ${!sharedOnly ? 'bg-ink text-white' : 'text-muted'}`} onClick={() => setSharedOnly(false)}>All</button>
          <button type="button" className={`rounded px-2 py-1 font-mono text-[9.5px] ${sharedOnly ? 'bg-ink text-white' : 'text-muted'} disabled:cursor-not-allowed disabled:opacity-50`} disabled={shared.size === 0} onClick={() => setSharedOnly(true)}>In both · {shared.size}</button>
        </div>
      </div>
      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        {resolution.artifact.arms.map((arm, index) => (
          <DrugArm
            key={arm.arm_key}
            arm={arm}
            labels={labels}
            release={release}
            condition={index === 0 ? resolution.context.conditionA : resolution.context.conditionB}
            shared={shared}
            sharedOnly={sharedOnly}
          />
        ))}
      </div>
    </div>
  );
}

function renderDrugs(resolution: Extract<DevelopmentRealResolution, { route: 'drugs' }>, labels: Map<string, string>) {
  return <DrugsCanvas resolution={resolution} labels={labels} />;
}

function property(candidate: DevPkCandidate, key: string): string {
  const field = object(candidate.pk_properties[key]);
  if (field.state !== 'observed') return '—';
  const value = field.value;
  return `${typeof value === 'number' ? number(value, 1) : text(value)}${typeof field.units === 'string' ? ` ${field.units}` : ''}`;
}

function Scorecard({ candidate }: { candidate: DevPkCandidate }) {
  const brain = object(candidate.brain_penetrance);
  const safety = object(candidate.safety);
  const arms = candidate.stage3_arms.map((arm) => object(arm));
  const humanEvidence = humanCnsEvidence(brain);
  const nonhumanEvidence = nonhumanEvidenceLinks(brain);
  return (
    <section className="rounded-lg border border-line bg-surface" aria-label={candidate.moiety_name}>
      <header className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2">
        <span className="text-[12px] font-semibold text-ink">{candidate.moiety_name}</span>
        <span className="font-mono text-[9.5px] text-muted">{candidate.candidate_id}</span>
        <StatePill label={humanEvidence.observed ? 'human CNS evidence' : 'CNS evidence not evaluated'} tone={humanEvidence.observed ? 'ok' : 'muted'} />
      </header>
      <div className="grid grid-cols-2 gap-x-4 gap-y-2 px-3 py-2 sm:grid-cols-4">
        <Value label="human CNS evidence" value={humanEvidence.summary} />
        <Value label="measured concentration" value={measuredConcentration(brain)} />
        <Value label="molecular weight" value={property(candidate, 'molecular_weight')} />
        <Value label="tPSA" value={property(candidate, 'tpsa')} />
        <Value label="xLogP" value={property(candidate, 'xlogp')} />
        <Value label="CNS-MPO inputs" value="3/6 · MW, TPSA, HBD" />
        <Value label="CNS-MPO total" value="not evaluated" />
        <Value label="label state" value={text(safety.label_state)} />
        <Value label="boxed warning" value={typeof safety.boxed_warning_present === 'boolean' ? (safety.boxed_warning_present ? 'present' : 'not present') : '—'} />
      </div>
      <div className="border-t border-line px-3 py-2 font-mono text-[9.5px] text-muted">
        <span>Missing for CNS-MPO: cLogP, cLogD7.4, most-basic pKa.</span>
        {humanEvidence.sourceUrl && humanEvidence.sourceLabel && <a className="ml-2 text-accent underline-offset-2 hover:underline" href={humanEvidence.sourceUrl} target="_blank" rel="noreferrer noopener">{humanEvidence.sourceLabel}</a>}
        {nonhumanEvidence.map((evidence) => <a key={evidence.url} className="ml-2 text-accent underline-offset-2 hover:underline" href={evidence.url} target="_blank" rel="noreferrer noopener">{evidence.label}</a>)}
      </div>
      <div className="flex flex-wrap gap-1.5 border-t border-line px-3 py-2">
        {arms.map((arm, i) => {
          const condition = text(arm.arm_key).split('|').at(-1) ?? '';
          return <StatePill key={`${text(arm.arm_key)}:${i}`} label={`${text(arm.target_symbol)} · ${conditionLabel(condition)} · ${text(arm.directional_evidence_status)}`} tone={arm.observed_perturbation_support === true ? 'ok' : 'amber'} />;
        })}
      </div>
    </section>
  );
}

function Value({ label, value }: { label: string; value: string }) {
  return <div><span className="block font-mono text-[9.5px] uppercase tracking-wide text-muted">{label}</span><span className="font-mono text-[10.5px] text-ink-2">{value}</span></div>;
}

function renderPkSafety(resolution: Extract<DevelopmentRealResolution, { route: 'pksafety' }>) {
  const counts = resolution.artifact.counts;
  return (
    <div data-real-canvas data-development-real data-route="pksafety" className={CANVAS}>
      <ContextStrip resolution={resolution} />
      <div className="flex flex-wrap gap-3 font-mono text-[9.5px] text-muted">
        <span>{scalar(counts.n_rows)} acquired</span>
        {counts.n_unacquired_reported !== null && <span>{scalar(counts.n_unacquired_reported)} unacquired</span>}
        {counts.n_named_but_not_prefetched !== null && <span>{scalar(counts.n_named_but_not_prefetched)} not prefetched</span>}
      </div>
      {resolution.artifact.candidates.map((candidate) => <Scorecard key={candidate.candidate_id} candidate={candidate} />)}
    </div>
  );
}

export function renderDevelopmentReal(resolution: DevelopmentRealResolution, labels = new Map<string, string>()): React.ReactNode {
  if (resolution.route === 'pathways') return renderPathways(resolution, labels);
  if (resolution.route === 'drugs') return renderDrugs(resolution, labels);
  return renderPkSafety(resolution);
}
