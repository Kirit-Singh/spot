// Adapter for spot.stage02_gene_lever_set.v1 — the target set.
//
// Enforces (beyond the shared firewall): no numeric combined/balanced score, and a
// null rank on any arm that is not evaluated. The two objectives stay independent;
// the only cross-arm summary is the TYPED joint ordering (joint_status / pareto_tier
// / joint_ordering_method_id) — never an averaged score.

import type { Namespace } from '../domain/common';
import type {
  ArmSupport,
  DepMapAnnotation,
  DonorSupport,
  GeneEvidence,
  GeneLever,
  GuideSupport,
  JointStatus,
  LeverArm,
  MarkerBreadth,
  Objective,
  PathwayNode,
  Perturb2StateStatus,
  Stage2Artifact,
} from '../domain/stage2';
import { ARM_SUPPORTS, JOINT_STATUSES } from '../domain/stage2';
import { fail } from './errors';
import {
  arr,
  assertNoCombinedFields,
  bool,
  enumOf,
  isObject,
  num,
  optBool,
  optNum,
  optStr,
  provenance,
  str,
} from './guards';
import { parseSelection } from './selectionAdapter';

export const KNOWN_STAGE2_VERSIONS = ['spot.stage02_gene_lever_set.v1'] as const;

const OBJECTIVES: readonly Objective[] = ['away_from_A', 'toward_B'];
const P2S: readonly Perturb2StateStatus[] = [
  'direct_only',
  'perturb2state_supported',
  'perturb2state_discordant',
  'not_evaluated',
];

function arm(v: unknown, objective: Objective, path: string): LeverArm {
  if (!isObject(v)) fail('malformed', `${path} arm is required`);
  const evaluated = bool(v.evaluated, `${path}.evaluated`);
  const rank = optNum(v.rank, `${path}.rank`);
  // Firewall: a non-null rank is illegal on an arm that was not evaluated.
  if (!evaluated && rank !== null) {
    fail('illegal_rank_on_ineligible_arm', `${path}.rank must be null when arm is not evaluated`);
  }
  return {
    objective,
    evaluated,
    reason: optStr(v.reason, `${path}.reason`),
    effect: optNum(v.effect, `${path}.effect`),
    rank,
    coverage: optNum(v.coverage, `${path}.coverage`),
  };
}

function guide(v: unknown, path: string): GuideSupport {
  if (!isObject(v)) fail('malformed', `${path} guide is required`);
  return {
    guide_id: str(v.guide_id, `${path}.guide_id`),
    effect: optNum(v.effect, `${path}.effect`),
    sign_agrees: optBool(v.sign_agrees, `${path}.sign_agrees`),
  };
}

function donorSupport(v: unknown, path: string): DonorSupport {
  if (!isObject(v)) fail('malformed', `${path} donor_support is required`);
  return {
    effective_n: num(v.effective_n, `${path}.effective_n`),
    denominator: str(v.denominator, `${path}.denominator`),
    pair_discordance: optBool(v.pair_discordance, `${path}.pair_discordance`),
  };
}

function depmap(v: unknown, path: string): DepMapAnnotation {
  if (!isObject(v)) fail('malformed', `${path} depmap is required`);
  return {
    status: str(v.status, `${path}.status`),
    detail: optStr(v.detail, `${path}.detail`),
  };
}

function markerBreadth(v: unknown, path: string): MarkerBreadth {
  if (!isObject(v)) fail('malformed', `${path} marker_breadth is required`);
  return {
    supporting_markers: num(v.supporting_markers, `${path}.supporting_markers`),
    single_marker_driven: bool(v.single_marker_driven, `${path}.single_marker_driven`),
    detail: optStr(v.detail, `${path}.detail`),
  };
}

function evidence(v: unknown, path: string): GeneEvidence {
  if (!isObject(v)) fail('malformed', `${path} evidence is required`);
  return {
    guides: arr(v.guides, `${path}.guides`).map((g, i) => guide(g, `${path}.guides[${i}]`)),
    donor_support: donorSupport(v.donor_support, `${path}.donor_support`),
    on_target_detected: optBool(v.on_target_detected, `${path}.on_target_detected`),
    perturb2state: enumOf<Perturb2StateStatus>(v.perturb2state, P2S, `${path}.perturb2state`),
    depmap: depmap(v.depmap, `${path}.depmap`),
    support_status: str(v.support_status, `${path}.support_status`),
    source_links: arr(v.source_links, `${path}.source_links`).map((l, i) => {
      if (!isObject(l)) fail('malformed', `${path}.source_links[${i}] is required`);
      return {
        label: str(l.label, `${path}.source_links[${i}].label`),
        url: optStr(l.url, `${path}.source_links[${i}].url`),
        detail: str(l.detail, `${path}.source_links[${i}].detail`),
      };
    }),
  };
}

function lever(v: unknown, path: string): GeneLever {
  if (!isObject(v)) fail('malformed', `${path} lever is required`);
  const armsRaw = v.arms;
  if (!isObject(armsRaw)) fail('malformed', `${path}.arms is required`);
  const pareto_tier = optNum(v.pareto_tier, `${path}.pareto_tier`);
  if (pareto_tier !== null && (!Number.isInteger(pareto_tier) || pareto_tier < 1)) {
    fail('malformed', `${path}.pareto_tier must be a positive integer or null`);
  }
  return {
    gene_id: str(v.gene_id, `${path}.gene_id`),
    ensembl_id: optStr(v.ensembl_id, `${path}.ensembl_id`),
    arms: {
      away_from_A: arm(armsRaw.away_from_A, 'away_from_A', `${path}.arms.away_from_A`),
      toward_B: arm(armsRaw.toward_B, 'toward_B', `${path}.arms.toward_B`),
    },
    joint_status: enumOf<JointStatus>(v.joint_status, JOINT_STATUSES, `${path}.joint_status`),
    pareto_tier,
    marker_breadth: markerBreadth(v.marker_breadth, `${path}.marker_breadth`),
    evidence: evidence(v.evidence, `${path}.evidence`),
  };
}

function pathwayNode(v: unknown, path: string): PathwayNode {
  if (!isObject(v)) fail('malformed', `${path} pathway node is required`);
  return {
    pathway_id: str(v.pathway_id, `${path}.pathway_id`),
    name: str(v.name, `${path}.name`),
    contributing_targets: arr(v.contributing_targets, `${path}.contributing_targets`).map((t, i) =>
      str(t, `${path}.contributing_targets[${i}]`),
    ),
    arm_support: enumOf<ArmSupport>(v.arm_support, ARM_SUPPORTS, `${path}.arm_support`),
    enrichment: optNum(v.enrichment, `${path}.enrichment`),
    druggable: bool(v.druggable, `${path}.druggable`),
    method: str(v.method, `${path}.method`),
    source_hash: str(v.source_hash, `${path}.source_hash`),
  };
}

export function parseStage2(raw: unknown, expected: Namespace): Stage2Artifact {
  if (!isObject(raw)) fail('malformed', 'stage2 artifact must be an object');
  // Reject any stale numeric combined/balanced field anywhere in the payload. The
  // typed ordering (joint_status / pareto_tier / joint_ordering_method_id) is permitted.
  assertNoCombinedFields(raw.levers, 'stage2.levers');

  const prov = provenance(
    raw.provenance,
    'stage2.provenance',
    expected,
    'stage02',
    KNOWN_STAGE2_VERSIONS,
  );

  return {
    provenance: prov,
    selection: parseSelection(raw.selection, expected),
    tested_family_size: num(raw.tested_family_size, 'stage2.tested_family_size'),
    significance_calibrated: bool(raw.significance_calibrated, 'stage2.significance_calibrated'),
    joint_ordering_method_id: str(raw.joint_ordering_method_id, 'stage2.joint_ordering_method_id'),
    levers: arr(raw.levers, 'stage2.levers').map((l, i) => lever(l, `stage2.levers[${i}]`)),
    pathways: arr(raw.pathways, 'stage2.pathways').map((p, i) => pathwayNode(p, `stage2.pathways[${i}]`)),
  };
}

export { OBJECTIVES };
