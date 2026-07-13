// The admitted-artifact canvas, ROUTE-AWARE. Each downstream route renders its OWN native artifact
// through a DISTINCT path:
//   · Targets      → Stage-2 gene arms (two independent arms; identity by immutable base_key)
//   · Pathways     → Stage-2 pathway arms (two independent (condition, source) panels)
//   · Drugs        → Stage-3 candidate workflow states (native cards; no gbm_context/directness)
//   · PK & Safety  → Stage-4 scorecard evidence lanes (six independent lanes; missing stays missing)
// Stage 3/4 NEVER reuse the Stage-2 table renderer. Values come ONLY from the artifact — a null
// renders as a compact neutral em-dash / not_evaluated pill, never invented, never demo/fixture. No
// editorial / caveat copy on the canvas.
//
// Rendered ONLY behind StageIsland's admission gate (a resolution is returned ONLY when admitted).
// Production binds no admitted artifact yet (resolveProductionRealArtifact → null), so it never
// reaches here — it shows the compact neutral pending panel instead.

import type { JoinedView, ResolvedBundles } from '../repository/joinResolver';
import type { StageMethodsManifest } from '../domain/methodsManifest';
import type { DirectArm, DesiredDirectionDisposition, PathwayArm, PathwayArmRecord } from '../domain/reusableArm';
import type { NativeTemporalArm, NativeTemporalArmBundle } from '../domain/nativeTemporalArm';
import type { CompactStage2SelectionView } from '../domain/compactStage2Projection';
import type { Stage3UiArtifact, Stage3Candidate } from '../domain/stage3UiArtifact';
import type { Stage4UiArtifact, Stage4Candidate } from '../domain/stage4UiArtifact';
import { STAGE4_LANE_KEYS } from '../domain/stage4UiArtifact';
import { joinRowIdentity, desiredDirectionDisposition } from '../repository/armIdentity';
import { nativeTemporalIdentity } from '../adapters/nativeTemporalArmAdapter';
import { StatePill } from '../shell/chips';
import { renderCompactPathways, renderCompactTargets } from './renderCompactStage2';

/** A resolved, admission-gated real artifact the island renders, DISCRIMINATED by route. Never demo. */
interface ResolutionCommon {
  /** Admission verdict — the loader returns a resolution ONLY when 'admitted'. */
  admission: 'admitted' | 'pending';
  /** Parsed content-addressed methods manifest for the drawer, when a merged admitted run is bound. */
  manifest?: StageMethodsManifest | null;
}
export type RealRouteResolution =
  | (ResolutionCommon & { route: 'targets'; view: CompactStage2SelectionView | JoinedView; bundles?: ResolvedBundles })
  | (ResolutionCommon & { route: 'pathways'; view: CompactStage2SelectionView | JoinedView; bundles?: ResolvedBundles })
  | (ResolutionCommon & { route: 'drugs'; artifact: Stage3UiArtifact })
  | (ResolutionCommon & { route: 'pksafety'; artifact: Stage4UiArtifact });

/** @deprecated legacy name retained for existing import sites; use RealRouteResolution. */
export type RealArtifactResolution = RealRouteResolution;

function isCompactStage2(view: CompactStage2SelectionView | JoinedView): view is CompactStage2SelectionView {
  return 'schema_version' in view && view.schema_version === 'spot.ui_compact_stage2_selection_view.v1';
}

// ── shared cell formatting (a null value is a compact neutral em-dash, never invented) ──
function num(n: number | null): string {
  return n === null ? '—' : String(n);
}
function txt(s: string | null): string {
  return s === null || s === '' ? '—' : s;
}
function count(list: string[]): string {
  return list.length === 0 ? '—' : String(list.length);
}
const TH = 'px-2 py-1 text-left font-mono text-[9.5px] uppercase tracking-wide text-muted';
const TD = 'px-2 py-1 font-mono text-[10.5px] text-ink-2';
const CANVAS = 'flex min-h-0 flex-1 flex-col gap-3 overflow-auto p-4';

// ─────────────────────────────────────────────────────────────────────────────
// Stage-2 — Targets (gene arms) + Pathways (pathway arms)
// ─────────────────────────────────────────────────────────────────────────────

/** One normalized gene-arm display row (arm-scoped; no pair columns). */
interface GeneRow {
  key: string;
  rank: number | null;
  symbol: string | null;
  target_ensembl: string | null;
  target_id: string | null;
  effect: number | null;
  disposition: DesiredDirectionDisposition;
  status: string | null;
}

function nativeGeneRows(bundle: NativeTemporalArmBundle | null, arm: NativeTemporalArm): GeneRow[] {
  return arm.records.map((r, i) => {
    const id = bundle
      ? nativeTemporalIdentity(bundle, r)
      : { target_id: r.target_id, target_ensembl: null, target_symbol: null };
    return {
      key: `${r.base_key}:${i}`,
      rank: r.rank,
      symbol: id.target_symbol,
      target_ensembl: id.target_ensembl,
      target_id: id.target_id,
      effect: r.arm_value,
      disposition: desiredDirectionDisposition(r.arm_value, arm.desired_change),
      status: r.temporal_status,
    };
  });
}

function directGeneRows(bundle: ResolvedBundles['direct'] | null, arm: DirectArm): GeneRow[] {
  return arm.rows.map((r, i) => {
    const id = bundle
      ? joinRowIdentity(bundle, r)
      : { target_id: null, target_ensembl: r.target_ensembl, target_symbol: r.target_symbol };
    return {
      key: `${r.base_key ?? r.target_ensembl}:${i}`,
      rank: r.rank,
      symbol: id.target_symbol,
      target_ensembl: id.target_ensembl,
      target_id: id.target_id,
      effect: r.effect,
      disposition: desiredDirectionDisposition(r.effect, arm.desired_change),
      status: null,
    };
  });
}

function GeneArmTable({ arm, rows }: { arm: DirectArm | NativeTemporalArm | null; rows: GeneRow[] }) {
  return (
    <section aria-label="Gene arm" className="rounded-lg border border-line bg-surface">
      <header className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2">
        <StatePill label="gene arm" tone="muted" />
        <span className="break-all font-mono text-[10.5px] text-ink-2">{arm?.arm_key ?? '—'}</span>
      </header>
      {rows.length === 0 ? (
        <div className="px-3 py-2">
          <StatePill label="no rows" tone="muted" />
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr>
                <th className={TH}>rank</th>
                <th className={TH}>symbol</th>
                <th className={TH}>ensembl</th>
                <th className={TH}>effect</th>
                <th className={TH}>disposition</th>
                <th className={TH}>status</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.key} className="border-t border-line">
                  <td className={TD}>{r.rank === null ? '—' : r.rank}</td>
                  <td className={TD}>{txt(r.symbol)}</td>
                  <td className={TD}>{txt(r.target_ensembl ?? r.target_id)}</td>
                  <td className={TD}>{num(r.effect)}</td>
                  <td className={TD}>
                    <StatePill label={r.disposition} tone={r.disposition === 'supports_inhibition' ? 'ok' : 'muted'} />
                  </td>
                  <td className={TD}>{txt(r.status)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function PathwayArmTable({ arm, context }: { arm: PathwayArm | null; context: string }) {
  const records: PathwayArmRecord[] = arm?.records ?? [];
  return (
    <section aria-label="Pathway arm" className="rounded-lg border border-line bg-surface">
      <header className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2">
        <StatePill label="pathway arm" tone="muted" />
        <StatePill label={context} tone="muted" />
        <span className="break-all font-mono text-[10.5px] text-ink-2">{arm?.arm_key ?? '—'}</span>
      </header>
      {records.length === 0 ? (
        <div className="px-3 py-2">
          <StatePill label="no rows" tone="muted" />
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr>
                <th className={TH}>pathway</th>
                <th className={TH}>hits</th>
                <th className={TH}>enrichment</th>
                <th className={TH}>headline</th>
              </tr>
            </thead>
            <tbody>
              {records.map((p) => (
                <tr key={p.pathway_id} className="border-t border-line">
                  <td className={TD}>{txt(p.name || p.pathway_id)}</td>
                  <td className={TD}>{p.enrichment.n_hits_in_ranking === null ? '—' : p.enrichment.n_hits_in_ranking}</td>
                  <td className={TD}>{num(p.enrichment.enrichment_value)}</td>
                  <td className={TD}>
                    <StatePill
                      label={p.enrichment.arm_headline_rankable ? 'rankable' : 'descriptive'}
                      tone="muted"
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

/** Rank rows for a gene arm — native Temporal DiD arms for temporal selections, Direct arms otherwise. */
function geneRowsFor(view: JoinedView, bundles: ResolvedBundles, arm: DirectArm | NativeTemporalArm | null): GeneRow[] {
  if (!arm) return [];
  return view.mode === 'temporal_cross_condition'
    ? nativeGeneRows(bundles.temporal ?? null, arm as NativeTemporalArm)
    : directGeneRows(bundles.direct ?? null, arm as DirectArm);
}

/** Targets route — the two independent gene arms only (no pathway panels). */
export function renderTargets(view: JoinedView, bundles: ResolvedBundles): React.ReactNode {
  return (
    <div data-real-canvas data-route="targets" className={CANVAS}>
      <GeneArmTable arm={view.geneArmA} rows={geneRowsFor(view, bundles, view.geneArmA)} />
      <GeneArmTable arm={view.geneArmB} rows={geneRowsFor(view, bundles, view.geneArmB)} />
    </div>
  );
}

/** Pathways route — the two independent pathway panels only (no gene tables). */
export function renderPathways(view: JoinedView): React.ReactNode {
  return (
    <div data-real-canvas data-route="pathways" className={CANVAS}>
      <PathwayArmTable arm={view.pathwayArmA} context={view.pathway_context} />
      <PathwayArmTable arm={view.pathwayArmB} context={view.pathway_context} />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Stage-3 — Drugs (candidate workflow states; native cards, distinct from Stage-2 tables)
// ─────────────────────────────────────────────────────────────────────────────

function DrugCandidate({ c }: { c: Stage3Candidate }) {
  return (
    <section aria-label="Drug candidate" className="rounded-lg border border-line bg-surface">
      <header className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2">
        <StatePill label="candidate" tone="muted" />
        <span className="break-all font-mono text-[10.5px] text-ink-2">{c.candidate_id}</span>
        {c.preferred_name && <span className="font-mono text-[10.5px] text-ink">{c.preferred_name}</span>}
      </header>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 px-3 py-2 sm:grid-cols-3">
        <Field label="identity" value={txt(c.identity_status)} />
        <Field label="targets" value={count(c.target_ensembls)} />
        <Field label="edges" value={num(c.n_edges)} />
        <Field label="direct gene edges" value={num(c.n_direct_gene_edges)} />
        <Field label="development" value={txt(c.development_state_aggregate)} />
        <Field label="potency" value={txt(c.potency_state)} />
        <Field label="inverse-dir support" value={txt(c.inverse_direction_support)} />
        <Field label="disease context" value={txt(c.disease_context_review_result)} />
        <Field label="stage-4 status" value={txt(c.stage4_assessment_status)} />
      </div>
    </section>
  );
}

/** Drugs route — Stage-3 candidate cards bound to the admitted Stage-2 run. */
export function renderDrugs(artifact: Stage3UiArtifact): React.ReactNode {
  return (
    <div data-real-canvas data-route="drugs" className={CANVAS}>
      <div className="flex flex-wrap items-center gap-2">
        <StatePill label="stage-3 bundle" tone="muted" />
        <span className="break-all font-mono text-[10.5px] text-ink-2">{artifact.bundle_id}</span>
        <StatePill label="from stage-2 run" tone="muted" />
        <span className="break-all font-mono text-[10.5px] text-ink-2">{artifact.upstream_stage2_run}</span>
      </div>
      {artifact.candidates.length === 0 ? (
        <StatePill label="no candidates" tone="muted" />
      ) : (
        artifact.candidates.map((c) => <DrugCandidate key={c.candidate_id} c={c} />)
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Stage-4 — PK & Safety (scorecard evidence lanes; missing stays missing, never inferred)
// ─────────────────────────────────────────────────────────────────────────────

function eligibilityTone(v: boolean): 'ok' | 'amber' {
  return v ? 'ok' : 'amber';
}

function jsonField(v: unknown, key: string): unknown {
  return v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>)[key] : null;
}

function stage4LaneLabel(v: unknown): string {
  if (v === null) return 'not_evaluated';
  if (Array.isArray(v)) return `${v.length} record${v.length === 1 ? '' : 's'}`;
  if (typeof v === 'object') {
    for (const key of ['status', 'state', 'evidence_state']) {
      const explicit = jsonField(v, key);
      if (typeof explicit === 'string') return explicit;
    }
    return 'available';
  }
  return String(v);
}

function ScorecardCandidate({ c }: { c: Stage4Candidate }) {
  return (
    <section aria-label="Scorecard" className="rounded-lg border border-line bg-surface">
      <header className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2">
        <StatePill label="candidate" tone="muted" />
        <span className="break-all font-mono text-[10.5px] text-ink-2">{c.candidate_id}</span>
        {typeof c.active_moiety?.active_moiety_name === 'string' && (
          <span className="font-mono text-[10.5px] text-ink">{c.active_moiety.active_moiety_name}</span>
        )}
        <StatePill
          label={c.production_eligible.eligible ? 'production eligible' : 'not eligible'}
          tone={eligibilityTone(c.production_eligible.eligible)}
        />
      </header>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 px-3 py-2 sm:grid-cols-3">
        <Field label="target" value={txt(c.target)} />
        <Field label="mechanism" value={txt(c.mechanism)} />
        <Field label="direction" value={txt(c.direction_compatibility)} />
        <Field label="eligibility reason" value={txt(c.production_eligible.reason_code)} />
      </div>
      {/* independent nested evidence lanes; only explicit native states/counts are rendered */}
      <div className="flex flex-wrap gap-1.5 border-t border-line px-3 py-2">
        {STAGE4_LANE_KEYS.map((lane) => {
          return (
            <span key={lane} className="inline-flex items-center gap-1">
              <span className="font-mono text-[9.5px] uppercase tracking-wide text-muted">{lane}</span>
              <StatePill label={stage4LaneLabel(c.lanes[lane])} tone="muted" />
            </span>
          );
        })}
      </div>
    </section>
  );
}

/** PK & Safety route — Stage-4 scorecards descending from the admitted Stage-3 bundle. */
export function renderPkSafety(artifact: Stage4UiArtifact): React.ReactNode {
  return (
    <div data-real-canvas data-route="pksafety" className={CANVAS}>
      <div className="flex flex-wrap items-center gap-2">
        <StatePill label="stage-4 scorecard set" tone="muted" />
        <span className="break-all font-mono text-[10.5px] text-ink-2">{artifact.scorecard_set_id}</span>
        <StatePill label="from stage-3 candidate set" tone="muted" />
        <span className="break-all font-mono text-[10.5px] text-ink-2">{artifact.upstream_stage3_bundle}</span>
      </div>
      {artifact.candidates.length === 0 ? (
        <StatePill label="no scorecards" tone="muted" />
      ) : (
        artifact.candidates.map((c) => <ScorecardCandidate key={c.candidate_id} c={c} />)
      )}
    </div>
  );
}

// ── small labelled value cell (shared by Stage-3/Stage-4 cards) ──
function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col">
      <span className="font-mono text-[9.5px] uppercase tracking-wide text-muted">{label}</span>
      <span className="break-all font-mono text-[10.5px] text-ink-2">{value}</span>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Route dispatch — the ONE place a resolution is turned into a canvas. Each route uses its OWN
// renderer; Stage 3/4 never fall through to the Stage-2 tables.
// ─────────────────────────────────────────────────────────────────────────────
export function renderRouteReal(res: RealRouteResolution): React.ReactNode {
  switch (res.route) {
    case 'targets':
      return isCompactStage2(res.view)
        ? renderCompactTargets(res.view)
        : renderTargets(res.view, res.bundles ?? {});
    case 'pathways':
      return isCompactStage2(res.view) ? renderCompactPathways(res.view) : renderPathways(res.view);
    case 'drugs':
      return renderDrugs(res.artifact);
    case 'pksafety':
      return renderPkSafety(res.artifact);
  }
}
