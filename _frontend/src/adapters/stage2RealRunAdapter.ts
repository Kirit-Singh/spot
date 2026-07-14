// Adapters for the three Stage-2 REAL-RUN artifacts (read/normalize only — nothing rendered):
//   · parseDirectScreen        ← screen.parquet   (FLAT rows: spot.stage02_screen.v1)
//   · parseTemporalDiD         ← temporal.parquet  (FLAT rows: population-level DiD)
//   · parsePathwayConvergence  ← pathway.json     (records[].enrichment.{away_from_A,toward_b})
//
// DESIGN: ALLOWLIST-AND-PROJECT. Each adapter reads ONLY the UI-facing fields it renders and
// silently drops the rest — machine/provenance columns (delta_*, *_zscore, balanced_skew,
// support_*, mask_*), the temporal methods-only `batch_partially_confounded` field + its
// reliability metric, and any stray combined column. A projected-away field is never
// rendered and its mere presence NEVER rejects an already server-verified artifact (the
// fail-closed lane verifiers already ran an exact column allowlist + p/q/combined firewall
// over the shipped bytes). The two Direct arms (`away_from_A`, `toward_b`) stay independent;
// no combined/balanced value is ever read. Stage 2 emits no new p/q — only the upstream
// `ontarget_significant` boolean is carried.

import type { Namespace } from '../domain/common';
import type {
  DirectObjective,
  DirectScreenArtifact,
  DirectScreenRow,
  PathwayArmEnrichment,
  PathwayConvergenceArtifact,
  PathwayConvergenceRecord,
  TemporalDiDArtifact,
  TemporalDiDRow,
} from '../domain/stage2RealRun';
import { fail } from './errors';
import { arr, bool, enumOf, isObject, optBool, optNum, optStr, provenance, str } from './guards';
import { parseSelection } from './selectionAdapter';

export const KNOWN_SCREEN_VERSIONS = ['spot.stage02_screen.v1'] as const;
export const KNOWN_TEMPORAL_VERSIONS = ['spot.stage02_temporal.v1'] as const;
export const KNOWN_PATHWAY_VERSIONS = ['spot.stage02_pathway.v1'] as const;

// ───────────────────────── Direct screen (flat rows) ─────────────────────────

/** Read one flat screen row, keeping only the UI-facing allowlist (everything else dropped). */
function screenRow(v: unknown, path: string): DirectScreenRow {
  if (!isObject(v)) fail('malformed', `${path} row is required`);
  return {
    target_ensembl: str(v.target_ensembl, `${path}.target_ensembl`),
    target_symbol: optStr(v.target_symbol, `${path}.target_symbol`),
    condition: str(v.condition, `${path}.condition`),
    ontarget_significant: optBool(v.qc_ontarget_significant, `${path}.qc_ontarget_significant`),
    eligibility_state: optStr(v.eligibility_state, `${path}.eligibility_state`),
    direction_class: optStr(v.direction_class, `${path}.direction_class`),
    rank: optNum(v.rank, `${path}.rank`),
    // the two independent arm effects — read straight from the flat columns
    away_from_A: optNum(v.away_from_A, `${path}.away_from_A`),
    toward_b: optNum(v.toward_b, `${path}.toward_b`),
    // NB: balanced_skew / delta_* / *_zscore / support_* / mask_* are deliberately NOT read.
  };
}

export function parseDirectScreen(raw: unknown, expected: Namespace): DirectScreenArtifact {
  if (!isObject(raw)) fail('malformed', 'direct screen artifact must be an object');
  return {
    provenance: provenance(raw.provenance, 'screen.provenance', expected, 'stage02', KNOWN_SCREEN_VERSIONS),
    selection: parseSelection(raw.selection, expected),
    condition: str(raw.condition, 'screen.condition'),
    rows: arr(raw.rows, 'screen.rows').map((r, i) => screenRow(r, `screen.rows[${i}]`)),
  };
}

// ───────────────────────── Temporal DiD (flat rows) ─────────────────────────

/** Read one flat temporal row; the methods-only batch fields are simply never read. */
function temporalRow(v: unknown, path: string): TemporalDiDRow {
  if (!isObject(v)) fail('malformed', `${path} row is required`);
  return {
    target_ensembl: str(v.target_ensembl, `${path}.target_ensembl`),
    target_symbol: optStr(v.target_symbol, `${path}.target_symbol`),
    away_from_A_did: optNum(v.away_from_A_did, `${path}.away_from_A_did`),
    toward_b_did: optNum(v.toward_b_did, `${path}.toward_b_did`),
    away_from_A_from: optNum(v.away_from_A_from, `${path}.away_from_A_from`),
    away_from_A_to: optNum(v.away_from_A_to, `${path}.away_from_A_to`),
    toward_b_from: optNum(v.toward_b_from, `${path}.toward_b_from`),
    toward_b_to: optNum(v.toward_b_to, `${path}.toward_b_to`),
    present_from: optBool(v.present_from, `${path}.present_from`),
    present_to: optBool(v.present_to, `${path}.present_to`),
    // NB: batch_partially_confounded / batch_reliability_metric / interaction_std_program /
    // combined_temporal_score are deliberately NOT read — methods-only, never surfaced.
  };
}

export function parseTemporalDiD(raw: unknown, expected: Namespace): TemporalDiDArtifact {
  if (!isObject(raw)) fail('malformed', 'temporal DiD artifact must be an object');
  return {
    provenance: provenance(raw.provenance, 'temporal.provenance', expected, 'stage02', KNOWN_TEMPORAL_VERSIONS),
    selection: parseSelection(raw.selection, expected),
    from_condition: str(raw.from_condition, 'temporal.from_condition'),
    to_condition: str(raw.to_condition, 'temporal.to_condition'),
    // population-level cross-condition only — never lineage
    analysis_mode: enumOf(raw.analysis_mode, ['temporal_cross_condition'], 'temporal.analysis_mode'),
    rows: arr(raw.rows, 'temporal.rows').map((r, i) => temporalRow(r, `temporal.rows[${i}]`)),
  };
}

// ─────────────────── Pathway convergence (records[].enrichment.<objective>) ───────────────────

function armEnrichment(v: unknown, objective: DirectObjective, path: string): PathwayArmEnrichment {
  if (!isObject(v)) fail('malformed', `${path} arm enrichment is required`);
  return {
    objective,
    // server-decided vocabulary; read as-is (the UI shows only `rankable` as headline)
    arm_coverage_disposition: str(v.arm_coverage_disposition, `${path}.arm_coverage_disposition`),
    arm_headline_rankable: bool(v.arm_headline_rankable, `${path}.arm_headline_rankable`),
    enrichment_value: optNum(v.enrichment_value, `${path}.enrichment_value`),
    n_hits_in_ranking: optNum(v.n_hits_in_ranking, `${path}.n_hits_in_ranking`),
    source_coverage: optNum(v.source_coverage, `${path}.source_coverage`),
  };
}

function pathwayRecord(v: unknown, path: string): PathwayConvergenceRecord {
  if (!isObject(v)) fail('malformed', `${path} record is required`);
  const enr = v.enrichment;
  if (!isObject(enr)) fail('malformed', `${path}.enrichment is required`);
  return {
    pathway_id: str(v.pathway_id, `${path}.pathway_id`),
    name: str(v.name, `${path}.name`),
    contributing_targets: arr(v.contributing_targets, `${path}.contributing_targets`).map((t, i) =>
      str(t, `${path}.contributing_targets[${i}]`),
    ),
    druggable: optBool(v.druggable, `${path}.druggable`),
    enrichment: {
      away_from_A: armEnrichment(enr.away_from_A, 'away_from_A', `${path}.enrichment.away_from_A`),
      toward_b: armEnrichment(enr.toward_b, 'toward_b', `${path}.enrichment.toward_b`),
    },
    // NB: record-level machine fields (method, source_hash, …) are deliberately NOT read.
  };
}

export function parsePathwayConvergence(raw: unknown, expected: Namespace): PathwayConvergenceArtifact {
  if (!isObject(raw)) fail('malformed', 'pathway convergence artifact must be an object');
  return {
    provenance: provenance(raw.provenance, 'pathway.provenance', expected, 'stage02', KNOWN_PATHWAY_VERSIONS),
    selection: parseSelection(raw.selection, expected),
    condition: str(raw.condition, 'pathway.condition'),
    gene_set_source: str(raw.gene_set_source, 'pathway.gene_set_source'),
    records: arr(raw.records, 'pathway.records').map((r, i) => pathwayRecord(r, `pathway.records[${i}]`)),
  };
}
