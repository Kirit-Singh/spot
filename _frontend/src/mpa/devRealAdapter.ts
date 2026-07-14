import type { PageKey } from './pages';
import { readStage1SelectionV3 } from './contrastTitle';
import { resolveProductionRealArtifact } from './resolveRouteArtifact';
import type { RealRouteResolution } from './renderReal';

export type JsonRecord = Record<string, unknown>;

export interface DevPathwayTerm extends JsonRecord {
  set_id: string;
  set_name: string;
  enrichment_value: number | null;
  arm_headline_rankable: boolean;
  leading_edge: string[];
  n_hits_in_ranking: number;
  target_source_coverage: number;
}

export interface DevPathwayArm extends JsonRecord {
  arm_key: string;
  program_id: string;
  desired_change: string;
  selection_role: string;
  n_headline_rankable: number;
  terms: DevPathwayTerm[];
}

export interface DevPathwaysArtifact extends JsonRecord {
  schema_version: 'spot.stage03_pathway_context_ui.v0';
  condition: string;
  arms: DevPathwayArm[];
}

export interface DevDrugEdge extends JsonRecord {
  molecule_chembl_id: string;
  pref_name: string;
  directional_evidence_status: string;
  observed_perturbation_support: boolean;
  mechanism_of_action: string;
  max_phase_source: string | null;
}

export interface DevDrugTarget extends JsonRecord {
  target_id: string;
  target_symbol: string;
  arm_rank: number;
  arm_value: number;
  drugs: DevDrugEdge[];
}

export interface DevDrugArm extends JsonRecord {
  arm_key: string;
  program_id: string;
  desired_change: string;
  role: string;
  targets: DevDrugTarget[];
}

export interface DevDrugsArtifact extends JsonRecord {
  schema_version: 'spot.stage03_ui_drugs.v1';
  condition: string;
  arms: DevDrugArm[];
  sources: JsonRecord;
}

export interface DevPkCandidate extends JsonRecord {
  candidate_id: string;
  moiety_name: string;
  acquisition_status: string;
  brain_penetrance: JsonRecord;
  cns_mpo: JsonRecord;
  pk_properties: JsonRecord;
  safety: JsonRecord;
  stage3_arms: JsonRecord[];
}

export interface DevPkArtifact extends JsonRecord {
  schema_id: string;
  selection: string;
  not_a_ranking: true;
  candidates: DevPkCandidate[];
  counts: JsonRecord;
}

export type DevelopmentRealResolution =
  | { admission: 'development'; route: 'pathways'; artifact: DevPathwaysArtifact }
  | { admission: 'development'; route: 'drugs'; artifact: DevDrugsArtifact }
  | { admission: 'development'; route: 'pksafety'; artifact: DevPkArtifact };

const conditions = new Set(['Rest', 'Stim8hr']);

interface SelectionContext {
  condition: string;
  programA: string;
  programB: string;
  desiredA: 'increase' | 'decrease';
  desiredB: 'increase' | 'decrease';
  directArmKeys: [string, string];
  pathwayArmKeys: [string, string];
}

function record(value: unknown): JsonRecord | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as JsonRecord
    : null;
}

function selectionContext(value: Awaited<ReturnType<typeof readStage1SelectionV3>>): SelectionContext | null {
  if (!value || value.analysis_mode !== 'within_condition' || value.conditions.length !== 1) return null;
  const condition = value.conditions[0];
  if (!conditions.has(condition)) return null;
  const desiredA = value.A.direction === 'high' ? 'decrease' : 'increase';
  const desiredB = value.B.direction === 'high' ? 'increase' : 'decrease';
  const directArmKeys: [string, string] = [
    `direct|${value.A.program_id}|${desiredA}|${condition}`,
    `direct|${value.B.program_id}|${desiredB}|${condition}`,
  ];
  return {
    condition,
    programA: value.A.program_id,
    programB: value.B.program_id,
    desiredA,
    desiredB,
    directArmKeys,
    pathwayArmKeys: directArmKeys.map((key) => `pathway|${key.slice('direct|'.length)}|go_bp`) as [string, string],
  };
}

async function fetchJson(path: string): Promise<unknown> {
  const response = await fetch(path, { cache: 'no-store' });
  if (!response.ok) throw new Error(`fetch ${path} -> ${response.status}`);
  return response.json() as Promise<unknown>;
}

function validatePathways(raw: unknown, context: SelectionContext): DevPathwaysArtifact | null {
  const value = record(raw);
  if (!value || value.schema_version !== 'spot.stage03_pathway_context_ui.v0' || value.condition !== context.condition) return null;
  if (value.status !== 'development_unadmitted' || value.admission_pending !== true || value.is_production_result !== false) return null;
  if (value.analysis_mode !== 'within_condition') return null;
  if (!Array.isArray(value.arms) || value.arms.length !== 2) return null;
  if (value.arms.some((arm, i) => record(arm)?.arm_key !== context.pathwayArmKeys[i] || !Array.isArray(record(arm)?.terms))) return null;
  if (value.arms.some((arm, i) => record(arm)?.direct_arm_key !== context.directArmKeys[i])) return null;
  return value as unknown as DevPathwaysArtifact;
}

function validateDrugs(raw: unknown, context: SelectionContext): DevDrugsArtifact | null {
  const value = record(raw);
  if (!value || value.schema_version !== 'spot.stage03_ui_drugs.v1' || value.condition !== context.condition) return null;
  if (value.analysis_mode !== 'within_condition' || record(value.admission)?.receipt_verified !== false) return null;
  if (!Array.isArray(value.arms) || value.arms.length !== 2) return null;
  if (value.arms.some((arm, i) => record(arm)?.arm_key !== context.directArmKeys[i] || !Array.isArray(record(arm)?.targets))) return null;
  return value as unknown as DevDrugsArtifact;
}

function validatePk(raw: unknown, context: SelectionContext): DevPkArtifact | null {
  const value = record(raw);
  if (!value || value.schema_id !== 'spot.stage04_pk_safety_compact.v1' || value.not_a_ranking !== true || !Array.isArray(value.candidates)) return null;
  if (value.selection !== context.condition.toLowerCase().replace('hr', '')) return null;
  const source = record(value.stage3_source);
  if (source?.analysis_mode !== 'within_condition' || source.condition !== context.condition) return null;
  if (!Array.isArray(source.arm_keys) || source.arm_keys.length !== 2 || source.arm_keys.some((key, i) => key !== context.directArmKeys[i])) return null;
  return value as unknown as DevPkArtifact;
}

export async function resolveDevelopmentRealArtifact(page: PageKey): Promise<DevelopmentRealResolution | null> {
  if (page !== 'pathways' && page !== 'drugs' && page !== 'pksafety') return null;
  const context = selectionContext(await readStage1SelectionV3().catch(() => null));
  if (!context) return null;
  const path = `results/dev-real/${page}.${context.condition}.json`;
  const raw = await fetchJson(path).catch(() => null);
  if (page === 'pathways') {
    const artifact = validatePathways(raw, context);
    return artifact ? { admission: 'development', route: page, artifact } : null;
  }
  if (page === 'drugs') {
    const artifact = validateDrugs(raw, context);
    return artifact ? { admission: 'development', route: page, artifact } : null;
  }
  const artifact = validatePk(raw, context);
  return artifact ? { admission: 'development', route: page, artifact } : null;
}

/** Production has precedence; the direct real-data development seam is only the fallback. */
export async function resolveProductionThenDevelopment(
  page: PageKey,
): Promise<RealRouteResolution | DevelopmentRealResolution | null> {
  return await resolveProductionRealArtifact(page) ?? resolveDevelopmentRealArtifact(page);
}
