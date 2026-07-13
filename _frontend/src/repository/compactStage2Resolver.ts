// Exact selection-to-prefix binding for the compact all-arm Stage-2 view. Conditions and pathway
// source come from the explicit release metadata; ordering is NEVER inferred from arm keys.

import type { SelectionV3 } from '../adapters/selectionV3Adapter';
import type {
  CompactPathwayArm,
  CompactStage2Projection,
  CompactStage2ReleaseMetadata,
  CompactStage2SelectionView,
  CompactTargetArm,
} from '../domain/compactStage2Projection';
import { desiredChange, directArmKey, pathwayArmKey, temporalArmKey } from './armKey';
import { fail } from '../adapters/errors';

function targetArm(projection: CompactStage2Projection, key: string, lane: 'direct' | 'temporal'): CompactTargetArm {
  const arm = projection.arms[key];
  if (!arm) fail('incomplete_release', `compact Stage-2 projection has no requested arm ${key}`);
  if (arm.lane !== lane) fail('arm_key_mismatch', `requested ${key} resolved to ${arm.lane}, not ${lane}`);
  return arm;
}

function pathwayArm(projection: CompactStage2Projection, key: string): CompactPathwayArm {
  const arm = projection.arms[key];
  if (!arm) fail('incomplete_release', `compact Stage-2 projection has no requested pathway arm ${key}`);
  if (arm.lane !== 'pathway') fail('arm_key_mismatch', `requested ${key} is not a pathway arm`);
  return arm;
}

function validateReleaseAxes(
  projection: CompactStage2Projection,
  metadata: CompactStage2ReleaseMetadata,
): void {
  const conditions = new Set<string>(metadata.release_conditions);
  const sources = new Set<string>(metadata.pathway_sources);
  for (const arm of Object.values(projection.arms)) {
    if (arm.lane === 'temporal') {
      if (!('from_condition' in arm.context) || !conditions.has(arm.context.from_condition) ||
          !conditions.has(arm.context.to_condition)) {
        fail('incomplete_release', `${arm.arm_key} lies outside the explicit release condition axis`);
      }
    } else if (!('condition' in arm.context) || !conditions.has(arm.context.condition)) {
      fail('incomplete_release', `${arm.arm_key} lies outside the explicit release condition axis`);
    } else if (arm.lane === 'pathway' && !sources.has(arm.context.gene_set_source)) {
      fail('incomplete_release', `${arm.arm_key} lies outside the explicit pathway-source axis`);
    }
  }
}

/** Resolve exactly two independent gene arms and their matching pathway contexts. */
export function resolveCompactStage2Selection(
  projection: CompactStage2Projection,
  metadata: CompactStage2ReleaseMetadata,
  selection: SelectionV3,
  route: 'targets' | 'pathways' | 'all' = 'all',
): CompactStage2SelectionView {
  validateReleaseAxes(projection, metadata);
  const released = metadata.release_conditions;
  if (selection.conditions.some((c) => !released.includes(c as typeof released[number]))) {
    fail('incomplete_release', 'selection names a condition outside the explicit release metadata');
  }
  const changeA = desiredChange('away_from_A', selection.A.direction);
  const changeB = desiredChange('toward_b', selection.B.direction);
  const source = metadata.active_pathway_source;

  if (selection.analysis_mode === 'within_condition') {
    if (selection.conditions.length !== 1) fail('malformed', 'within-condition selection must name exactly one condition');
    const condition = selection.conditions[0];
    return {
      schema_version: 'spot.ui_compact_stage2_selection_view.v1',
      display_release_id: metadata.display_release_id,
      pathway_source: source,
      mode: selection.analysis_mode,
      pathway_context: 'condition_matched',
      geneArmA: targetArm(projection, directArmKey(selection.A.program_id, changeA, condition), 'direct'),
      geneArmB: targetArm(projection, directArmKey(selection.B.program_id, changeB, condition), 'direct'),
      effectRankFacets: [
        { role: 'A', program_id: selection.A.program_id,
          increase: targetArm(projection, directArmKey(selection.A.program_id, 'increase', condition), 'direct'),
          decrease: targetArm(projection, directArmKey(selection.A.program_id, 'decrease', condition), 'direct') },
        { role: 'B', program_id: selection.B.program_id,
          increase: targetArm(projection, directArmKey(selection.B.program_id, 'increase', condition), 'direct'),
          decrease: targetArm(projection, directArmKey(selection.B.program_id, 'decrease', condition), 'direct') },
      ],
      pathwayArmA: route === 'targets' ? null : pathwayArm(projection, pathwayArmKey(selection.A.program_id, changeA, condition, source)),
      pathwayArmB: route === 'targets' ? null : pathwayArm(projection, pathwayArmKey(selection.B.program_id, changeB, condition, source)),
    };
  }

  if (selection.conditions.length !== 2) fail('malformed', 'cross-condition selection must name two ordered conditions');
  const [from, to] = selection.conditions;
  if (from === to) fail('malformed', 'cross-condition endpoints must differ');
  // The admitted compact release currently carries only same-time pathway arms. Those endpoint
  // arms are not a temporal enrichment estimand and must never be substituted for one.
  if (route === 'pathways') fail('incomplete_release', 'awaiting_temporal_pathway_bundle');
  return {
    schema_version: 'spot.ui_compact_stage2_selection_view.v1',
    display_release_id: metadata.display_release_id,
    pathway_source: source,
    mode: selection.analysis_mode,
    pathway_context: 'awaiting_temporal_pathway_bundle',
    geneArmA: targetArm(projection, temporalArmKey(selection.A.program_id, changeA, from, to), 'temporal'),
    geneArmB: targetArm(projection, temporalArmKey(selection.B.program_id, changeB, from, to), 'temporal'),
    effectRankFacets: [
      { role: 'A', program_id: selection.A.program_id,
        increase: targetArm(projection, temporalArmKey(selection.A.program_id, 'increase', from, to), 'temporal'),
        decrease: targetArm(projection, temporalArmKey(selection.A.program_id, 'decrease', from, to), 'temporal') },
      { role: 'B', program_id: selection.B.program_id,
        increase: targetArm(projection, temporalArmKey(selection.B.program_id, 'increase', from, to), 'temporal'),
        decrease: targetArm(projection, temporalArmKey(selection.B.program_id, 'decrease', from, to), 'temporal') },
    ],
    pathwayArmA: null,
    pathwayArmB: null,
  };
}
