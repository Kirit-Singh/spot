import type { PageKey } from './pages';
import { readStage1SelectionV3 } from './contrastTitle';
import { resolveProductionRealArtifact } from './resolveRouteArtifact';
import type { RealRouteResolution } from './renderReal';
import { directArmKey, pathwayArmKey } from '../repository/armKey';

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

export interface DevelopmentSelectionContext {
  conditionA: 'Rest' | 'Stim8hr';
  conditionB: 'Rest' | 'Stim8hr';
  analysisMode: 'within_condition' | 'endpoint_comparison';
  programA: 'treg_like';
  programB: 'th1_like';
  desiredA: 'decrease';
  desiredB: 'increase';
  directArmKeys: [string, string];
  pathwayArmKeys: [string, string];
}

export type DevelopmentRealResolution =
  | { admission: 'development'; route: 'pathways'; artifact: DevPathwaysArtifact; context: DevelopmentSelectionContext }
  | { admission: 'development'; route: 'drugs'; artifact: DevDrugsArtifact; context: DevelopmentSelectionContext }
  | { admission: 'development'; route: 'pksafety'; artifact: DevPkArtifact; context: DevelopmentSelectionContext };

function record(value: unknown): JsonRecord | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as JsonRecord
    : null;
}

function fixedReviewContext(
  conditionA: 'Rest' | 'Stim8hr',
  conditionB: 'Rest' | 'Stim8hr' = conditionA,
): DevelopmentSelectionContext {
  const desiredA = 'decrease' as const;
  const desiredB = 'increase' as const;
  const directArmKeys: [string, string] = [
    directArmKey('treg_like', desiredA, conditionA),
    directArmKey('th1_like', desiredB, conditionB),
  ];
  return {
    conditionA,
    conditionB,
    analysisMode: conditionA === conditionB ? 'within_condition' : 'endpoint_comparison',
    programA: 'treg_like',
    programB: 'th1_like',
    desiredA,
    desiredB,
    directArmKeys,
    pathwayArmKeys: [
      pathwayArmKey('treg_like', desiredA, conditionA, 'go_bp'),
      pathwayArmKey('th1_like', desiredB, conditionB, 'go_bp'),
    ],
  };
}

/** Resolve an immediately-viewable real-data snapshot for the review build. */
function reviewContext(value: Awaited<ReturnType<typeof readStage1SelectionV3>>): DevelopmentSelectionContext | null {
  if (typeof window !== 'undefined') {
    const params = new URLSearchParams(window.location.search);
    const from = params.get('from');
    const to = params.get('to');
    if ((from === 'Rest' || from === 'Stim8hr') && (to === 'Rest' || to === 'Stim8hr')) {
      return fixedReviewContext(from, to);
    }
    const query = params.get('condition');
    if (query === 'Rest' || query === 'Stim8hr') return fixedReviewContext(query);
  }
  if (!value) return fixedReviewContext('Rest', 'Stim8hr');
  if (
    value.analysis_mode === 'within_condition'
    && value.conditions.length === 1
    && value.A.program_id === 'treg_like'
    && value.A.direction === 'high'
    && value.B.program_id === 'th1_like'
    && value.B.direction === 'high'
  ) {
    const condition = value.conditions[0];
    if (condition === 'Rest' || condition === 'Stim8hr') return fixedReviewContext(condition);
  }
  if (
    value.analysis_mode === 'temporal_cross_condition'
    && value.conditions.length === 2
    && value.A.program_id === 'treg_like'
    && value.A.direction === 'high'
    && value.B.program_id === 'th1_like'
    && value.B.direction === 'high'
  ) {
    const [conditionA, conditionB] = value.conditions;
    if (
      (conditionA === 'Rest' || conditionA === 'Stim8hr')
      && (conditionB === 'Rest' || conditionB === 'Stim8hr')
    ) return fixedReviewContext(conditionA, conditionB);
  }
  return null;
}

async function fetchJson(path: string): Promise<unknown> {
  const response = await fetch(path, { cache: 'no-store' });
  if (!response.ok) throw new Error(`fetch ${path} -> ${response.status}`);
  return response.json() as Promise<unknown>;
}

function validatePathways(raw: unknown, context: DevelopmentSelectionContext): DevPathwaysArtifact | null {
  const value = record(raw);
  if (!value || value.schema_version !== 'spot.stage03_pathway_context_ui.v0' || value.condition !== context.conditionA) return null;
  if (value.status !== 'development_unadmitted' || value.admission_pending !== true || value.is_production_result !== false) return null;
  if (value.analysis_mode !== 'within_condition') return null;
  if (!Array.isArray(value.arms) || value.arms.length !== 2) return null;
  if (value.arms.some((arm, i) => record(arm)?.arm_key !== context.pathwayArmKeys[i] || !Array.isArray(record(arm)?.terms))) return null;
  if (value.arms.some((arm, i) => record(arm)?.direct_arm_key !== context.directArmKeys[i])) return null;
  return value as unknown as DevPathwaysArtifact;
}

function validateDrugs(raw: unknown, context: DevelopmentSelectionContext): DevDrugsArtifact | null {
  const value = record(raw);
  if (!value || value.schema_version !== 'spot.stage03_ui_drugs.v1' || value.condition !== context.conditionA) return null;
  if (value.analysis_mode !== 'within_condition' || record(value.admission)?.receipt_verified !== false) return null;
  if (!Array.isArray(value.arms) || value.arms.length !== 2) return null;
  if (value.arms.some((arm, i) => record(arm)?.arm_key !== context.directArmKeys[i] || !Array.isArray(record(arm)?.targets))) return null;
  return value as unknown as DevDrugsArtifact;
}

function validatePk(raw: unknown, context: DevelopmentSelectionContext): DevPkArtifact | null {
  const value = record(raw);
  if (!value || value.schema_id !== 'spot.stage04_pk_safety_compact.v1' || value.not_a_ranking !== true || !Array.isArray(value.candidates)) return null;
  if (value.selection !== context.conditionA.toLowerCase().replace('hr', '')) return null;
  const source = record(value.stage3_source);
  if (source?.analysis_mode !== 'within_condition' || source.condition !== context.conditionA) return null;
  if (!Array.isArray(source.arm_keys) || source.arm_keys.length !== 2 || source.arm_keys.some((key, i) => key !== context.directArmKeys[i])) return null;
  return value as unknown as DevPkArtifact;
}

export async function resolveDevelopmentRealArtifact(page: PageKey): Promise<DevelopmentRealResolution | null> {
  if (page !== 'pathways' && page !== 'drugs' && page !== 'pksafety') return null;
  const context = reviewContext(await readStage1SelectionV3().catch(() => null));
  if (!context) return null;
  const sourceA = fixedReviewContext(context.conditionA);
  const sourceB = fixedReviewContext(context.conditionB);
  const [rawA, rawB] = await Promise.all([
    fetchJson(`results/dev-real/${page}.${context.conditionA}.json`).catch(() => null),
    context.conditionA === context.conditionB
      ? Promise.resolve(null)
      : fetchJson(`results/dev-real/${page}.${context.conditionB}.json`).catch(() => null),
  ]);

  if (page === 'pathways') {
    const artifactA = validatePathways(rawA, sourceA);
    if (!artifactA) return null;
    if (context.analysisMode === 'within_condition') {
      return { admission: 'development', route: page, artifact: artifactA, context };
    }
    const artifactB = validatePathways(rawB, sourceB);
    if (!artifactB) return null;
    const artifact: DevPathwaysArtifact = {
      schema_version: 'spot.stage03_pathway_context_ui.v0',
      condition: `${context.conditionA}->${context.conditionB}`,
      analysis_mode: 'endpoint_comparison',
      gene_set_source: 'go_bp',
      input_binding: {
        endpoint_A: artifactA.input_binding,
        endpoint_B: artifactB.input_binding,
      },
      arms: [artifactA.arms[0], artifactB.arms[1]],
    };
    return { admission: 'development', route: page, artifact, context };
  }

  if (page === 'drugs') {
    const artifactA = validateDrugs(rawA, sourceA);
    if (!artifactA) return null;
    if (context.analysisMode === 'within_condition') {
      return { admission: 'development', route: page, artifact: artifactA, context };
    }
    const artifactB = validateDrugs(rawB, sourceB);
    if (!artifactB) return null;
    const artifact: DevDrugsArtifact = {
      schema_version: 'spot.stage03_ui_drugs.v1',
      condition: `${context.conditionA}->${context.conditionB}`,
      analysis_mode: 'endpoint_comparison',
      sources: {
        universe_store: artifactA.sources.universe_store,
        endpoint_A: {
          condition: context.conditionA,
          stage2_direct_arms: artifactA.sources.stage2_direct_arms,
          stage2_target_identity: artifactA.sources.stage2_target_identity,
        },
        endpoint_B: {
          condition: context.conditionB,
          stage2_direct_arms: artifactB.sources.stage2_direct_arms,
          stage2_target_identity: artifactB.sources.stage2_target_identity,
        },
      },
      arms: [artifactA.arms[0], artifactB.arms[1]],
    };
    return { admission: 'development', route: page, artifact, context };
  }

  const artifactA = validatePk(rawA, sourceA);
  if (!artifactA) return null;
  if (context.analysisMode === 'within_condition') {
    return { admission: 'development', route: page, artifact: artifactA, context };
  }
  const artifactB = validatePk(rawB, sourceB);
  if (!artifactB) return null;
  const hasArm = (candidate: DevPkCandidate, armKey: string) => candidate.stage3_arms.some(
    (arm) => record(arm)?.arm_key === armKey,
  );
  const candidates = [
    ...artifactA.candidates.filter((candidate) => hasArm(candidate, context.directArmKeys[0])),
    ...artifactB.candidates.filter((candidate) => hasArm(candidate, context.directArmKeys[1])),
  ];
  const artifact: DevPkArtifact = {
    schema_id: 'spot.stage04_pk_safety_compact.v1',
    selection: 'rest_to_stim8',
    not_a_ranking: true,
    stage3_source: {
      analysis_mode: 'endpoint_comparison',
      conditions: [context.conditionA, context.conditionB],
      arm_keys: context.directArmKeys,
      endpoint_A: artifactA.stage3_source,
      endpoint_B: artifactB.stage3_source,
    },
    counts: {
      n_rows: candidates.length,
      n_unacquired_reported: null,
      n_named_but_not_prefetched: null,
    },
    candidates,
  };
  return { admission: 'development', route: page, artifact, context };
}

/** Production has precedence; the direct real-data development seam is only the fallback. */
export async function resolveProductionThenDevelopment(
  page: PageKey,
): Promise<RealRouteResolution | DevelopmentRealResolution | null> {
  return await resolveProductionRealArtifact(page) ?? resolveDevelopmentRealArtifact(page);
}
