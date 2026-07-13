// Adapter for spot.stage04_scorecard_set.v1 — safety & brain-exposure scorecards.
//
// Distinguishes measured / calculated / label-derived / not-evaluated / missing.
// A `missing` or `not_evaluated` field keeps a null value — never coerced to 0.

import type { Field, Namespace } from '../domain/common';
import type {
  CnsEvidence,
  CnsMpoSupport,
  DeliveryEvidence,
  ExposureEvidence,
  NebpiDecision,
  NebpiStep,
  NebpiTier,
  SafetyEvidence,
  Scorecard,
  SortKey,
  Stage4Artifact,
  TreatmentContextSafety,
} from '../domain/stage4';
import { NEBPI_TIERS } from '../domain/stage4';
import { fail } from './errors';
import {
  arr,
  enumOf,
  isObject,
  measurementState,
  num,
  optStr,
  provenance,
  str,
} from './guards';

export const KNOWN_STAGE4_VERSIONS = ['spot.stage04_scorecard_set.v1'] as const;

const SORT_KEYS: readonly SortKey[] = ['evidence_completeness', 'nebpi_tier'];

/** Parse a Field<T>. A value is required unless the state is not_evaluated/missing. */
function field<T>(v: unknown, path: string, kind: 'number' | 'string'): Field<T> {
  if (!isObject(v)) fail('malformed', `${path} field object is required`);
  const state = measurementState(v.state, `${path}.state`);
  const absent = state === 'missing' || state === 'not_evaluated';

  let value: T | null = null;
  if (v.value === null || v.value === undefined) {
    if (!absent) {
      fail('malformed', `${path}.value may only be null when state is missing/not_evaluated`);
    }
  } else if (absent) {
    // A present value contradicts a missing/not_evaluated state — reject rather than mislead.
    fail('malformed', `${path}.value must be null when state is ${state}`);
  } else {
    value = (kind === 'number' ? num(v.value, `${path}.value`) : str(v.value, `${path}.value`)) as T;
  }

  let source: Field<T>['source'] = null;
  if (v.source !== null && v.source !== undefined) {
    if (!isObject(v.source)) fail('malformed', `${path}.source must be an object or null`);
    source = {
      label: str(v.source.label, `${path}.source.label`),
      record_id: str(v.source.record_id, `${path}.source.record_id`),
      url: optStr(v.source.url, `${path}.source.url`),
      detail: str(v.source.detail, `${path}.source.detail`),
    };
  }

  return { value, state, unit: optStr(v.unit, `${path}.unit`), source };
}

const numField = (v: unknown, p: string) => field<number>(v, p, 'number');
const strField = (v: unknown, p: string) => field<string>(v, p, 'string');

function safety(v: unknown, path: string): SafetyEvidence {
  if (!isObject(v)) fail('malformed', `${path} safety is required`);
  return {
    regulatory_status: strField(v.regulatory_status, `${path}.regulatory_status`),
    boxed_warning: strField(v.boxed_warning, `${path}.boxed_warning`),
    key_risks: strField(v.key_risks, `${path}.key_risks`),
  };
}

function delivery(v: unknown, path: string): DeliveryEvidence {
  if (!isObject(v)) fail('malformed', `${path} delivery is required`);
  return {
    requirement: strField(v.requirement, `${path}.requirement`),
    supporting_evidence: strField(v.supporting_evidence, `${path}.supporting_evidence`),
  };
}

function treatmentContext(v: unknown, path: string): TreatmentContextSafety {
  if (!isObject(v)) fail('malformed', `${path} treatment_context is required`);
  return {
    setting: strField(v.setting, `${path}.setting`),
    concerns: strField(v.concerns, `${path}.concerns`),
  };
}

function exposure(v: unknown, path: string): ExposureEvidence {
  if (!isObject(v)) fail('malformed', `${path} exposure is required`);
  return {
    systemic_cmax: numField(v.systemic_cmax, `${path}.systemic_cmax`),
    unbound_fraction: numField(v.unbound_fraction, `${path}.unbound_fraction`),
    half_life: numField(v.half_life, `${path}.half_life`),
  };
}

function cns(v: unknown, path: string): CnsEvidence {
  if (!isObject(v)) fail('malformed', `${path} cns is required`);
  return {
    kp_uu: numField(v.kp_uu, `${path}.kp_uu`),
    csf_concentration: numField(v.csf_concentration, `${path}.csf_concentration`),
    tumour_concentration: numField(v.tumour_concentration, `${path}.tumour_concentration`),
  };
}

function cnsMpo(v: unknown, path: string): CnsMpoSupport {
  if (!isObject(v)) fail('malformed', `${path} cns_mpo is required`);
  return {
    clogp: numField(v.clogp, `${path}.clogp`),
    clogd: numField(v.clogd, `${path}.clogd`),
    tpsa: numField(v.tpsa, `${path}.tpsa`),
    mw: numField(v.mw, `${path}.mw`),
    hbd: numField(v.hbd, `${path}.hbd`),
    pka: numField(v.pka, `${path}.pka`),
    descriptor_score: numField(v.descriptor_score, `${path}.descriptor_score`),
  };
}

function nebpiStep(v: unknown, path: string): NebpiStep {
  if (!isObject(v)) fail('malformed', `${path} step is required`);
  return { label: str(v.label, `${path}.label`), outcome: str(v.outcome, `${path}.outcome`) };
}

function nebpi(v: unknown, path: string): NebpiDecision {
  if (!isObject(v)) fail('malformed', `${path} nebpi is required`);
  return {
    version: str(v.version, `${path}.version`),
    tier: enumOf<NebpiTier>(v.tier, NEBPI_TIERS, `${path}.tier`),
    rationale: str(v.rationale, `${path}.rationale`),
    decision_path: arr(v.decision_path, `${path}.decision_path`).map((s, i) =>
      nebpiStep(s, `${path}.decision_path[${i}]`),
    ),
  };
}

function scorecard(v: unknown, path: string, expected: Namespace): Scorecard {
  if (!isObject(v)) fail('malformed', `${path} scorecard is required`);
  return {
    scorecard_id: str(v.scorecard_id, `${path}.scorecard_id`),
    candidate_id: str(v.candidate_id, `${path}.candidate_id`),
    active_moiety: str(v.active_moiety, `${path}.active_moiety`),
    form: str(v.form, `${path}.form`),
    delivery: delivery(v.delivery, `${path}.delivery`),
    safety: safety(v.safety, `${path}.safety`),
    exposure: exposure(v.exposure, `${path}.exposure`),
    cns: cns(v.cns, `${path}.cns`),
    cns_mpo: cnsMpo(v.cns_mpo, `${path}.cns_mpo`),
    nebpi: nebpi(v.nebpi, `${path}.nebpi`),
    treatment_context: treatmentContext(v.treatment_context, `${path}.treatment_context`),
    provenance: provenance(v.provenance, `${path}.provenance`, expected, 'stage04', KNOWN_STAGE4_VERSIONS),
  };
}

export function parseStage4(raw: unknown, expected: Namespace): Stage4Artifact {
  if (!isObject(raw)) fail('malformed', 'stage4 artifact must be an object');
  const prov = provenance(raw.provenance, 'stage4.provenance', expected, 'stage04', KNOWN_STAGE4_VERSIONS);
  return {
    provenance: prov,
    sortable_by: arr(raw.sortable_by, 'stage4.sortable_by').map((s, i) =>
      enumOf<SortKey>(s, SORT_KEYS, `stage4.sortable_by[${i}]`),
    ),
    scorecards: arr(raw.scorecards, 'stage4.scorecards').map((s, i) =>
      scorecard(s, `stage4.scorecards[${i}]`, expected),
    ),
  };
}
