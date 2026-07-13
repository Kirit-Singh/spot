// Production join RESOLVER (audit BLOCKER 2): binds a verified v3 selection to the loaded
// reusable-arm bundles. It executes conditionUniverse() against the bound Stage-1 release and
// joinPlan() (the frozen cross-time semantics), then resolves EXACTLY the two independent gene
// arms + the pathway-panel arms those keys name. A pair is a UI join of two independent arms —
// there is no combined/balanced score and no longitudinal pathway statistic.
//
//   within_condition        → two DIRECT gene arms + condition-matched Pathway arms
//   temporal_cross_condition → two TEMPORAL DiD gene arms + ENDPOINT Direct-Pathway arms
//                              (A at from_condition, B at to_condition), never temporal enrichment

import { conditionUniverse, joinPlan } from './joinSemantics';
import type { JoinPlan, JoinSelectionInput } from './joinSemantics';
import { desiredChange } from './armKey';
import type { SelectionV3 } from '../adapters/selectionV3Adapter';
import type { DirectArm, DirectArmBundle, PathwayArm, PathwayArmBundle } from '../domain/reusableArm';
import type { NativeTemporalArm, NativeTemporalArmBundle } from '../domain/nativeTemporalArm';
import { getDirectArm, getPathwayArm } from '../adapters/reusableArmAdapter';
import { getNativeTemporalArm } from '../adapters/nativeTemporalArmAdapter';

/** The bundles a selection needs. pathwayByContext is keyed `condition|source`. The temporal
 *  bundle is W5's NATIVE spot.stage02_temporal_arm_bundle.v1 shape. */
export interface ResolvedBundles {
  direct?: DirectArmBundle | null;
  temporal?: NativeTemporalArmBundle | null;
  pathwayByContext?: Record<string, PathwayArmBundle | null>;
}

export interface JoinedView {
  mode: SelectionV3['analysis_mode'];
  plan: JoinPlan;
  /** Perturbation-gene ranking arms (Direct for within, native Temporal DiD for cross-time). */
  geneArmA: DirectArm | NativeTemporalArm | null;
  geneArmB: DirectArm | NativeTemporalArm | null;
  /** Pathway panel arms. */
  pathwayArmA: PathwayArm | null;
  pathwayArmB: PathwayArm | null;
  pathway_context: JoinPlan['pathway_context'];
}

export function selectionToJoinInput(sel: SelectionV3, source: string): JoinSelectionInput {
  return {
    mode: sel.analysis_mode,
    A: { program_id: sel.A.program_id, direction: sel.A.direction },
    B: { program_id: sel.B.program_id, direction: sel.B.direction },
    conditions: sel.conditions,
    source,
  };
}

/**
 * Resolve the joined view. `releaseConditions` is the authoritative Stage-1 v3
 * `release.selector.conditions` — conditionUniverse() rejects a forged/missing/reordered set
 * before any arm is resolved. Throws (ConditionUniverseError) on an invalid release/selection.
 */
export function resolveJoinedView(
  sel: SelectionV3,
  bundles: ResolvedBundles,
  source: string,
  releaseConditions: unknown,
): JoinedView {
  conditionUniverse(releaseConditions); // authority = release, not --batch-policy; fail-closed
  const plan = joinPlan(selectionToJoinInput(sel, source));
  const dcA = desiredChange('away_from_A', sel.A.direction);
  const dcB = desiredChange('toward_b', sel.B.direction);
  const pw = bundles.pathwayByContext ?? {};

  if (sel.analysis_mode === 'within_condition') {
    const cond = sel.conditions[0];
    const pwBundle = pw[`${cond}|${source}`] ?? null;
    return {
      mode: sel.analysis_mode,
      plan,
      geneArmA: bundles.direct ? getDirectArm(bundles.direct, sel.A.program_id, dcA) : null,
      geneArmB: bundles.direct ? getDirectArm(bundles.direct, sel.B.program_id, dcB) : null,
      pathwayArmA: pwBundle ? getPathwayArm(pwBundle, sel.A.program_id, dcA) : null,
      pathwayArmB: pwBundle ? getPathwayArm(pwBundle, sel.B.program_id, dcB) : null,
      pathway_context: plan.pathway_context,
    };
  }

  // temporal_cross_condition: endpoint pathway contexts — A@from, B@to
  const [from, to] = sel.conditions;
  const pwFrom = pw[`${from}|${source}`] ?? null;
  const pwTo = pw[`${to}|${source}`] ?? null;
  return {
    mode: sel.analysis_mode,
    plan,
    geneArmA: bundles.temporal ? getNativeTemporalArm(bundles.temporal, sel.A.program_id, dcA) : null,
    geneArmB: bundles.temporal ? getNativeTemporalArm(bundles.temporal, sel.B.program_id, dcB) : null,
    pathwayArmA: pwFrom ? getPathwayArm(pwFrom, sel.A.program_id, dcA) : null,
    pathwayArmB: pwTo ? getPathwayArm(pwTo, sel.B.program_id, dcB) : null,
    pathway_context: plan.pathway_context,
  };
}
