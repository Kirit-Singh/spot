// FIX #2 — the admitted-artifact canvas. Given a resolved JoinedView (two independent gene
// arms + the two pathway-panel arms) this renders COMPACT, DATA-FIRST real rows/tables:
//
//   · identity joins by immutable base_key (never by symbol) — nativeTemporalIdentity for the
//     native temporal lane, joinRowIdentity for the Direct lane;
//   · desired-direction disposition via desiredDirectionDisposition(effect, desired_change);
//   · values come ONLY from the artifact — a null renders as a compact neutral em-dash, never
//     invented, never a demo/fixture value; there is no editorial / caveat copy on the canvas.
//
// It is rendered ONLY behind StageIsland's temporal ADMISSION gate (resolveTemporalAdmission
// === 'admitted'); production, which binds no admitted artifact yet, never reaches here.

import type { JoinedView, ResolvedBundles } from '../repository/joinResolver';
import type { StageMethodsManifest } from '../domain/methodsManifest';
import type { DirectArm, DesiredDirectionDisposition, PathwayArm, PathwayArmRecord } from '../domain/reusableArm';
import type { NativeTemporalArm, NativeTemporalArmBundle } from '../domain/nativeTemporalArm';
import { joinRowIdentity, desiredDirectionDisposition } from '../repository/armIdentity';
import { nativeTemporalIdentity } from '../adapters/nativeTemporalArmAdapter';
import { StatePill } from '../shell/chips';

/** A resolved, admission-gated real artifact the island renders. Never demo/fixture data. */
export interface RealArtifactResolution {
  view: JoinedView;
  bundles: ResolvedBundles;
  /** Temporal admission verdict — StageIsland renders real rows ONLY when 'admitted'. */
  admission: 'admitted' | 'pending';
  /** Parsed content-addressed methods manifest for the drawer, when one is bound. */
  manifest?: StageMethodsManifest | null;
}

/**
 * Production real-artifact resolution seam. Production binds NO admitted W5 release + W11
 * verification yet, so this resolves to null and the island shows the compact pending state.
 * When a content-addressed release + independent verification are bound, they are parsed and
 * admission-gated here (via resolveTemporalAdmission) — this NEVER returns demo/fixture data.
 */
export async function resolveProductionRealArtifact(): Promise<RealArtifactResolution | null> {
  return null;
}

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

function num(n: number | null): string {
  return n === null ? '—' : String(n);
}
function txt(s: string | null): string {
  return s === null || s === '' ? '—' : s;
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

const TH = 'px-2 py-1 text-left font-mono text-[9.5px] uppercase tracking-wide text-muted';
const TD = 'px-2 py-1 font-mono text-[10.5px] text-ink-2';

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

/**
 * Render the admitted JoinedView as compact real rows/tables. Temporal selections rank genes
 * from native Temporal DiD arms (identity via nativeTemporalIdentity); within-condition
 * selections from Direct arms (identity via joinRowIdentity). No editorial copy.
 */
export function renderReal(view: JoinedView, bundles: ResolvedBundles): React.ReactNode {
  const temporal = view.mode === 'temporal_cross_condition';
  const geneRows = (arm: DirectArm | NativeTemporalArm | null): GeneRow[] => {
    if (!arm) return [];
    return temporal
      ? nativeGeneRows(bundles.temporal ?? null, arm as NativeTemporalArm)
      : directGeneRows(bundles.direct ?? null, arm as DirectArm);
  };

  return (
    <div data-real-canvas className="flex min-h-0 flex-1 flex-col gap-3 overflow-auto p-4">
      <GeneArmTable arm={view.geneArmA} rows={geneRows(view.geneArmA)} />
      <GeneArmTable arm={view.geneArmB} rows={geneRows(view.geneArmB)} />
      <PathwayArmTable arm={view.pathwayArmA} context={view.pathway_context} />
      <PathwayArmTable arm={view.pathwayArmB} context={view.pathway_context} />
    </div>
  );
}
