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

function armLabel(program: string, desired: string, labels: Map<string, string>): string {
  return `${labels.get(program) ?? program.replaceAll('_', ' ')} ${desired}`;
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

function DrugArm({ arm, labels, release, condition }: { arm: DevDrugArm; labels: Map<string, string>; release: string; condition: string }) {
  const rows = drugRows(arm);
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
              return (
                <tr key={`${target.target_id}:${drug.molecule_chembl_id}:${index}`} className={`border-t border-line align-top ${opposed ? 'bg-amber-50/60' : ''}`}>
                  <td className={CELL}><span className="block font-sans text-[11px] font-semibold text-ink">{text(drug.pref_name)}</span><span className="text-[9.5px] text-muted">{drug.molecule_chembl_id}</span></td>
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

function renderDrugs(resolution: Extract<DevelopmentRealResolution, { route: 'drugs' }>, labels: Map<string, string>) {
  const store = object(resolution.artifact.sources.universe_store);
  const release = text(store.chembl_release);
  return (
    <div data-real-canvas data-development-real data-route="drugs" className={CANVAS}>
      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        {resolution.artifact.arms.map((arm, index) => (
          <DrugArm
            key={arm.arm_key}
            arm={arm}
            labels={labels}
            release={release}
            condition={index === 0 ? resolution.context.conditionA : resolution.context.conditionB}
          />
        ))}
      </div>
    </div>
  );
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
  return (
    <section className="rounded-lg border border-line bg-surface" aria-label={candidate.moiety_name}>
      <header className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2">
        <span className="text-[12px] font-semibold text-ink">{candidate.moiety_name}</span>
        <span className="font-mono text-[9.5px] text-muted">{candidate.candidate_id}</span>
        <StatePill label={text(brain.assessment)} tone="muted" />
      </header>
      <div className="grid grid-cols-2 gap-x-4 gap-y-2 px-3 py-2 sm:grid-cols-4">
        <Value label="brain assessment" value={text(brain.assessment)} />
        <Value label="measured brain exposure" value={brain.assessment_state === 'not_evaluated' ? 'unknown' : text(brain.assessment_state)} />
        <Value label="molecular weight" value={property(candidate, 'molecular_weight')} />
        <Value label="tPSA" value={property(candidate, 'tpsa')} />
        <Value label="xLogP" value={property(candidate, 'xlogp')} />
        <Value label="CNS-MPO" value={object(candidate.cns_mpo).state === 'not_evaluated' ? 'unknown' : text(object(candidate.cns_mpo).state)} />
        <Value label="label state" value={text(safety.label_state)} />
        <Value label="boxed warning" value={typeof safety.boxed_warning_present === 'boolean' ? (safety.boxed_warning_present ? 'present' : 'not present') : '—'} />
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
