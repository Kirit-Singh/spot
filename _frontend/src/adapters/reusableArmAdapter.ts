// Fail-closed adapters for the Round-4 REUSABLE-ARM bundles (ROUND4_ADDENDUM.md, Rule 2,
// sha c4773562). These REPLACE the legacy pair-shaped Stage-2 contracts.
//
// A bundle is one physical, content-addressed all-arm artifact per (lane, context) carrying
// EVERY program × desired_change arm, each independently addressable by its `arm_key`. The
// UI JOINS two independent arms (away_from_A of program A + toward_b of program B) on demand;
// it NEVER loads a pre-joined pair. So every parser here:
//   · validates provenance + the namespace firewall FIRST (guards.provenance),
//   · derives each arm's expected key from armKey.ts for the BUNDLE's context and REJECTS any
//     `arm_key` (or map key) that disagrees — `arm_key_mismatch`,
//   · REJECTS a legacy pair-shaped arm (top-level away_from_A / toward_b / joint_status /
//     pareto_tier) — `legacy_pair_shape`,
//   · for pathway, checks `convergence_ref === convergenceKey(condition, source)` —
//     `convergence_ref_mismatch`,
//   · ALLOWLISTS-AND-PROJECTS everything else (machine/batch cols dropped, never a reason to
//     reject an already server-verified artifact).
// No combined/balanced/weighted score is ever read; Stage 2 emits no new p/q.

import type { Namespace } from '../domain/common';
import type {
  DirectArm,
  DirectArmBundle,
  DirectArmRow,
  PathwayArm,
  PathwayArmBundle,
  PathwayArmEnrichment,
  PathwayArmRecord,
  TemporalArm,
  TemporalArmBundle,
  TemporalArmRow,
} from '../domain/reusableArm';
import {
  convergenceKey,
  directArmKey,
  pathwayArmKey,
  temporalArmKey,
  type DesiredChange,
} from '../repository/armKey';
import { fail } from './errors';
import { arr, bool, enumOf, HEX_SHORT, isObject, optBool, optNum, optStr, provenance, str } from './guards';

export const KNOWN_DIRECT_ARM_BUNDLE_VERSIONS = ['spot.stage02_direct_arm_bundle.v1'] as const;
export const KNOWN_TEMPORAL_ARM_BUNDLE_VERSIONS = ['spot.stage02_temporal_arm_bundle.v1'] as const;
export const KNOWN_PATHWAY_ARM_BUNDLE_VERSIONS = ['spot.stage02_pathway_arm_bundle.v1'] as const;

const DESIRED_CHANGES: readonly DesiredChange[] = ['increase', 'decrease'];

/** Legacy pair-shaped fields that must never appear on a single reusable arm. */
const LEGACY_PAIR_KEYS = ['away_from_A', 'toward_b', 'joint_status', 'pareto_tier'];

/** Required lowercase-hex content address (the bundle's own digest). */
function bundleSha(v: unknown, path: string): string {
  const s = str(v, path);
  if (!HEX_SHORT.test(s)) fail('malformed', `${path} must be a lowercase hex content address`);
  return s;
}

/** Reject an arm carrying any legacy pair-shaped field (a pre-joined pair, not a reusable arm). */
function rejectLegacyPairShape(v: Record<string, unknown>, path: string): void {
  for (const k of LEGACY_PAIR_KEYS) {
    if (k in v) {
      fail(
        'legacy_pair_shape',
        `${path}.${k} is a legacy pair-shaped field; reusable arms are single-arm artifacts (join happens at display time)`,
      );
    }
  }
}

/** Common arm header: reject pair shape, read program_id + desired_change + arm_key. */
function armHeader(
  v: unknown,
  path: string,
): { obj: Record<string, unknown>; program_id: string; desired_change: DesiredChange; arm_key: string } {
  if (!isObject(v)) fail('malformed', `${path} arm is required`);
  rejectLegacyPairShape(v, path);
  return {
    obj: v,
    program_id: str(v.program_id, `${path}.program_id`),
    desired_change: enumOf<DesiredChange>(v.desired_change, DESIRED_CHANGES, `${path}.desired_change`),
    arm_key: str(v.arm_key, `${path}.arm_key`),
  };
}

/** The arm's own key AND its position in the bundle map must equal the canonical armKey.ts key. */
function assertArmKey(arm_key: string, mapKey: string, expected: string, path: string): void {
  if (arm_key !== expected) {
    fail('arm_key_mismatch', `${path}.arm_key "${arm_key}" != canonical key "${expected}"`);
  }
  if (mapKey !== arm_key) {
    fail('arm_key_mismatch', `${path} bundle map key "${mapKey}" != arm_key "${arm_key}"`);
  }
}

// ───────────────────────────── Direct ─────────────────────────────

function directArmRow(v: unknown, path: string): DirectArmRow {
  if (!isObject(v)) fail('malformed', `${path} row is required`);
  return {
    target_ensembl: str(v.target_ensembl, `${path}.target_ensembl`),
    target_symbol: optStr(v.target_symbol, `${path}.target_symbol`),
    effect: optNum(v.effect, `${path}.effect`),
    rank: optNum(v.rank, `${path}.rank`),
    ontarget_significant: optBool(v.ontarget_significant, `${path}.ontarget_significant`),
  };
}

function directArm(mapKey: string, v: unknown, condition: string, path: string): DirectArm {
  const h = armHeader(v, path);
  assertArmKey(h.arm_key, mapKey, directArmKey(h.program_id, h.desired_change, condition), path);
  return {
    arm_key: h.arm_key,
    program_id: h.program_id,
    desired_change: h.desired_change,
    condition,
    rows: arr(h.obj.rows, `${path}.rows`).map((r, i) => directArmRow(r, `${path}.rows[${i}]`)),
  };
}

export function parseDirectArmBundle(raw: unknown, expected: Namespace): DirectArmBundle {
  if (!isObject(raw)) fail('malformed', 'direct arm bundle must be an object');
  const prov = provenance(
    raw.provenance,
    'directArmBundle.provenance',
    expected,
    'stage02',
    KNOWN_DIRECT_ARM_BUNDLE_VERSIONS,
  );
  const condition = str(raw.condition, 'directArmBundle.condition');
  const bundle_sha256 = bundleSha(raw.bundle_sha256, 'directArmBundle.bundle_sha256');
  if (!isObject(raw.arms)) fail('malformed', 'directArmBundle.arms must be an object keyed by arm_key');
  const arms: Record<string, DirectArm> = {};
  for (const [k, v] of Object.entries(raw.arms)) {
    arms[k] = directArm(k, v, condition, `directArmBundle.arms[${k}]`);
  }
  return { provenance: prov, lane: 'direct', condition, bundle_sha256, arms };
}

export function getDirectArm(b: DirectArmBundle, program_id: string, change: DesiredChange): DirectArm | null {
  return b.arms[directArmKey(program_id, change, b.condition)] ?? null;
}

// ───────────────────────────── Temporal ─────────────────────────────

function temporalArmRow(v: unknown, path: string): TemporalArmRow {
  if (!isObject(v)) fail('malformed', `${path} row is required`);
  return {
    target_ensembl: str(v.target_ensembl, `${path}.target_ensembl`),
    target_symbol: optStr(v.target_symbol, `${path}.target_symbol`),
    did: optNum(v.did, `${path}.did`),
    effect_from: optNum(v.effect_from, `${path}.effect_from`),
    effect_to: optNum(v.effect_to, `${path}.effect_to`),
    present_from: optBool(v.present_from, `${path}.present_from`),
    present_to: optBool(v.present_to, `${path}.present_to`),
  };
}

function temporalArm(mapKey: string, v: unknown, from: string, to: string, path: string): TemporalArm {
  const h = armHeader(v, path);
  assertArmKey(h.arm_key, mapKey, temporalArmKey(h.program_id, h.desired_change, from, to), path);
  return {
    arm_key: h.arm_key,
    program_id: h.program_id,
    desired_change: h.desired_change,
    from,
    to,
    rows: arr(h.obj.rows, `${path}.rows`).map((r, i) => temporalArmRow(r, `${path}.rows[${i}]`)),
  };
}

export function parseTemporalArmBundle(raw: unknown, expected: Namespace): TemporalArmBundle {
  if (!isObject(raw)) fail('malformed', 'temporal arm bundle must be an object');
  const prov = provenance(
    raw.provenance,
    'temporalArmBundle.provenance',
    expected,
    'stage02',
    KNOWN_TEMPORAL_ARM_BUNDLE_VERSIONS,
  );
  const from = str(raw.from, 'temporalArmBundle.from');
  const to = str(raw.to, 'temporalArmBundle.to');
  const bundle_sha256 = bundleSha(raw.bundle_sha256, 'temporalArmBundle.bundle_sha256');
  if (!isObject(raw.arms)) fail('malformed', 'temporalArmBundle.arms must be an object keyed by arm_key');
  const arms: Record<string, TemporalArm> = {};
  for (const [k, v] of Object.entries(raw.arms)) {
    arms[k] = temporalArm(k, v, from, to, `temporalArmBundle.arms[${k}]`);
  }
  return { provenance: prov, lane: 'temporal', from, to, bundle_sha256, arms };
}

export function getTemporalArm(b: TemporalArmBundle, program_id: string, change: DesiredChange): TemporalArm | null {
  return b.arms[temporalArmKey(program_id, change, b.from, b.to)] ?? null;
}

// ───────────────────────────── Pathway ─────────────────────────────

function pathwayEnrichment(v: unknown, path: string): PathwayArmEnrichment {
  if (!isObject(v)) fail('malformed', `${path} enrichment is required`);
  return {
    arm_headline_rankable: bool(v.arm_headline_rankable, `${path}.arm_headline_rankable`),
    arm_coverage_disposition: str(v.arm_coverage_disposition, `${path}.arm_coverage_disposition`),
    enrichment_value: optNum(v.enrichment_value, `${path}.enrichment_value`),
    n_hits_in_ranking: optNum(v.n_hits_in_ranking, `${path}.n_hits_in_ranking`),
    source_coverage: optNum(v.source_coverage, `${path}.source_coverage`),
  };
}

function pathwayArmRecord(v: unknown, path: string): PathwayArmRecord {
  if (!isObject(v)) fail('malformed', `${path} record is required`);
  return {
    pathway_id: str(v.pathway_id, `${path}.pathway_id`),
    name: str(v.name, `${path}.name`),
    contributing_targets: arr(v.contributing_targets, `${path}.contributing_targets`).map((t, i) =>
      str(t, `${path}.contributing_targets[${i}]`),
    ),
    druggable: optBool(v.druggable, `${path}.druggable`),
    enrichment: pathwayEnrichment(v.enrichment, `${path}.enrichment`),
  };
}

function pathwayArm(
  mapKey: string,
  v: unknown,
  condition: string,
  source: string,
  convergence_ref: string,
  path: string,
): PathwayArm {
  const h = armHeader(v, path);
  assertArmKey(h.arm_key, mapKey, pathwayArmKey(h.program_id, h.desired_change, condition, source), path);
  return {
    arm_key: h.arm_key,
    program_id: h.program_id,
    desired_change: h.desired_change,
    condition,
    source,
    convergence_ref,
    records: arr(h.obj.records, `${path}.records`).map((r, i) => pathwayArmRecord(r, `${path}.records[${i}]`)),
  };
}

export function parsePathwayArmBundle(raw: unknown, expected: Namespace): PathwayArmBundle {
  if (!isObject(raw)) fail('malformed', 'pathway arm bundle must be an object');
  const prov = provenance(
    raw.provenance,
    'pathwayArmBundle.provenance',
    expected,
    'stage02',
    KNOWN_PATHWAY_ARM_BUNDLE_VERSIONS,
  );
  const condition = str(raw.condition, 'pathwayArmBundle.condition');
  const source = str(raw.source, 'pathwayArmBundle.source');
  const convergence_ref = str(raw.convergence_ref, 'pathwayArmBundle.convergence_ref');
  const expectedConv = convergenceKey(condition, source);
  if (convergence_ref !== expectedConv) {
    fail(
      'convergence_ref_mismatch',
      `pathwayArmBundle.convergence_ref "${convergence_ref}" != canonical "${expectedConv}" for (${condition}, ${source})`,
    );
  }
  const bundle_sha256 = bundleSha(raw.bundle_sha256, 'pathwayArmBundle.bundle_sha256');
  if (!isObject(raw.arms)) fail('malformed', 'pathwayArmBundle.arms must be an object keyed by arm_key');
  const arms: Record<string, PathwayArm> = {};
  for (const [k, v] of Object.entries(raw.arms)) {
    arms[k] = pathwayArm(k, v, condition, source, convergence_ref, `pathwayArmBundle.arms[${k}]`);
  }
  return { provenance: prov, lane: 'pathway', condition, source, convergence_ref, bundle_sha256, arms };
}

export function getPathwayArm(b: PathwayArmBundle, program_id: string, change: DesiredChange): PathwayArm | null {
  return b.arms[pathwayArmKey(program_id, change, b.condition, b.source)] ?? null;
}
