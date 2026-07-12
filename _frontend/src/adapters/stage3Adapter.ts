// Adapter for spot.stage03_drug_candidate_set.v1 — direction-compatible drug linkage.

import type { Namespace } from '../domain/common';
import type {
  AdministeredForm,
  CandidateOrigin,
  DirectionCompat,
  Directness,
  DrugCandidate,
  EvidenceState,
  MechanismDirection,
  PotencyRecord,
  SourceConflict,
  Stage3Artifact,
  TargetEntity,
} from '../domain/stage3';
import { CANDIDATE_ORIGINS } from '../domain/stage3';
import type { Objective } from '../domain/stage2';
import { fail } from './errors';
import {
  arr,
  assertNoCombinedFields,
  enumOf,
  isObject,
  optNum,
  optStr,
  provenance,
  str,
} from './guards';

export const KNOWN_STAGE3_VERSIONS = ['spot.stage03_drug_candidate_set.v1'] as const;

const OBJECTIVES: readonly Objective[] = ['away_from_A', 'toward_B'];
const DIR_COMPAT: readonly DirectionCompat[] = ['compatible', 'incompatible', 'not_evaluated'];
const DIRECTNESS: readonly Directness[] = ['direct', 'indirect', 'not_evaluated'];
const MECH_DIRECTIONS: readonly MechanismDirection[] = ['up', 'down', 'not_evaluated'];
const GBM_STATES: readonly EvidenceState[] = [
  'measured',
  'conflicting',
  'mixed',
  'not_evaluated',
  'missing',
];

function form(v: unknown, path: string): AdministeredForm {
  if (!isObject(v)) fail('malformed', `${path} form is required`);
  return {
    form_id: str(v.form_id, `${path}.form_id`),
    relation: str(v.relation, `${path}.relation`),
    route: optStr(v.route, `${path}.route`),
  };
}

function target(v: unknown, path: string): TargetEntity {
  if (!isObject(v)) fail('malformed', `${path} target_entity is required`);
  return {
    entity_id: str(v.entity_id, `${path}.entity_id`),
    entity_type: str(v.entity_type, `${path}.entity_type`),
    label: str(v.label, `${path}.label`),
  };
}

function potency(v: unknown, path: string): PotencyRecord {
  if (!isObject(v)) fail('malformed', `${path} potency record is required`);
  const src = v.source;
  if (!isObject(src)) fail('malformed', `${path}.source is required`);
  return {
    relation: str(v.relation, `${path}.relation`),
    value: optNum(v.value, `${path}.value`),
    unit: optStr(v.unit, `${path}.unit`),
    assay: str(v.assay, `${path}.assay`),
    source: {
      label: str(src.label, `${path}.source.label`),
      record_id: str(src.record_id, `${path}.source.record_id`),
      url: optStr(src.url, `${path}.source.url`),
    },
  };
}

function conflict(v: unknown, path: string): SourceConflict {
  if (!isObject(v)) fail('malformed', `${path} conflict is required`);
  return {
    field: str(v.field, `${path}.field`),
    values: arr(v.values, `${path}.values`).map((val, i) => {
      if (!isObject(val)) fail('malformed', `${path}.values[${i}] is required`);
      return {
        source: str(val.source, `${path}.values[${i}].source`),
        value: str(val.value, `${path}.values[${i}].value`),
      };
    }),
  };
}

function candidate(v: unknown, path: string, expected: Namespace): DrugCandidate {
  if (!isObject(v)) fail('malformed', `${path} candidate is required`);
  return {
    candidate_id: str(v.candidate_id, `${path}.candidate_id`),
    active_moiety: str(v.active_moiety, `${path}.active_moiety`),
    forms: arr(v.forms, `${path}.forms`).map((f, i) => form(f, `${path}.forms[${i}]`)),
    mechanism_action: str(v.mechanism_action, `${path}.mechanism_action`),
    origin: enumOf<CandidateOrigin>(v.origin, CANDIDATE_ORIGINS, `${path}.origin`),
    pathway_node: optStr(v.pathway_node, `${path}.pathway_node`),
    mechanism_direction: enumOf<MechanismDirection>(
      v.mechanism_direction,
      MECH_DIRECTIONS,
      `${path}.mechanism_direction`,
    ),
    target_entity: target(v.target_entity, `${path}.target_entity`),
    source_lever_gene_id: str(v.source_lever_gene_id, `${path}.source_lever_gene_id`),
    desired_arm: enumOf<Objective>(v.desired_arm, OBJECTIVES, `${path}.desired_arm`),
    direction_compatibility: enumOf<DirectionCompat>(
      v.direction_compatibility,
      DIR_COMPAT,
      `${path}.direction_compatibility`,
    ),
    directness: enumOf<Directness>(v.directness, DIRECTNESS, `${path}.directness`),
    potency_records: arr(v.potency_records, `${path}.potency_records`).map((p, i) =>
      potency(p, `${path}.potency_records[${i}]`),
    ),
    gbm_context: enumOf<EvidenceState>(v.gbm_context, GBM_STATES, `${path}.gbm_context`),
    source_conflicts: arr(v.source_conflicts, `${path}.source_conflicts`).map((c, i) =>
      conflict(c, `${path}.source_conflicts[${i}]`),
    ),
    // Each candidate carries its own provenance, validated against the same
    // code-bound namespace as the set — a candidate can never claim another one.
    provenance: provenance(
      v.provenance,
      `${path}.provenance`,
      expected,
      'stage03',
      KNOWN_STAGE3_VERSIONS,
    ),
  };
}

export function parseStage3(raw: unknown, expected: Namespace): Stage3Artifact {
  if (!isObject(raw)) fail('malformed', 'stage3 artifact must be an object');
  assertNoCombinedFields(raw.candidates, 'stage3.candidates');

  const prov = provenance(
    raw.provenance,
    'stage3.provenance',
    expected,
    'stage03',
    KNOWN_STAGE3_VERSIONS,
  );

  return {
    provenance: prov,
    desired_arms: arr(raw.desired_arms, 'stage3.desired_arms').map((a, i) =>
      enumOf<Objective>(a, OBJECTIVES, `stage3.desired_arms[${i}]`),
    ),
    candidates: arr(raw.candidates, 'stage3.candidates').map((c, i) =>
      candidate(c, `stage3.candidates[${i}]`, expected),
    ),
  };
}
