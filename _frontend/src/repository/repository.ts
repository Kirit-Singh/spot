// Data-adapter (repository) layer. Components depend ONLY on this interface and
// never learn where artifacts come from, nor which namespace they belong to.
//
// Two strictly separated worlds, decided in code — never by editing a data field:
//   - demo (?demo=1) : synthetic preview artifacts (unmistakably synthetic) — the ONLY
//                      place fixtures are allowed.
//   - production      : the AUTHORITATIVE Stage-1 v3 selection contract in storage
//                      (spot.stage01_selection.v3), read FAIL-CLOSED. A v1 object, a
//                      raw non-v3 object, or a structurally-broken v3 is REJECTED — it
//                      never falls back to a v1 read, a stale value, or fixture results.
//
// A verified v3 selection is real, but binding downstream Stage-2/3/4 analyses to it is
// held (no v3 artifact producer yet), so every stage is `not_generated` — the shell must
// NEVER fall back to fixture results beneath a real selection.

import type { Namespace } from '../domain/common';
import type { StageSelection } from '../domain/selection';
import type { Stage2Artifact } from '../domain/stage2';
import type { Stage3Artifact } from '../domain/stage3';
import type { Stage4Artifact } from '../domain/stage4';
import { parseSelection } from '../adapters/selectionAdapter';
import { parseStage2 } from '../adapters/stage2Adapter';
import { parseStage3 } from '../adapters/stage3Adapter';
import { parseStage4 } from '../adapters/stage4Adapter';
import type { SelectionV3 } from '../adapters/selectionV3Adapter';
import { selectionFixtureRaw } from '../fixtures/selection.fixture';
import { stage2FixtureRaw } from '../fixtures/stage2.fixture';
import { stage3FixtureRaw } from '../fixtures/stage3.fixture';
import { stage4FixtureRaw } from '../fixtures/stage4.fixture';
import type { ArtifactSource } from './source';
import { SELECTION_V3_KEY } from './source';

/** A stage artifact is either loaded, not-yet-generated, or rejected (with a reason). */
export type ArtifactSlot<T> =
  | { status: 'loaded'; artifact: T }
  | { status: 'not_generated' }
  | { status: 'rejected'; reason: string };

// empty  — no selection, no demo: honest workflow scaffold, no data.
// demo   — explicit demo gate: synthetic example artifacts (unmistakably synthetic).
// research — a real Stage-1 v3 selection in storage.
// rejected_selection — a present selection that failed the fail-closed v3 gate.
export type RepositoryMode = 'empty' | 'demo' | 'research' | 'rejected_selection';

export interface BuildOptions {
  /** Explicit demo gate (e.g. ?demo=1). Only then do synthetic artifacts render. */
  demo?: boolean;
}

export interface SpotRepository {
  readonly namespace: Namespace;
  readonly mode: RepositoryMode;
  /** The legacy StageSelection context (demo/fixture only); null under a v3 selection. */
  readonly selection: StageSelection | null;
  /** The AUTHORITATIVE parsed v3 selection, or null when none is bound / it was rejected. */
  readonly selectionV3: SelectionV3 | null;
  /** Why a present selection was rejected (mode === 'rejected_selection'). */
  readonly selectionRejection: string | null;
  getStage2(): ArtifactSlot<Stage2Artifact>;
  getStage3(): ArtifactSlot<Stage3Artifact>;
  getStage4(): ArtifactSlot<Stage4Artifact>;
}

const loaded = <T,>(artifact: T): ArtifactSlot<T> => ({ status: 'loaded', artifact });
const notGenerated = <T,>(): ArtifactSlot<T> => ({ status: 'not_generated' });

function parseJson(raw: string): { ok: true; value: unknown } | { ok: false; reason: string } {
  try {
    return { ok: true, value: JSON.parse(raw) };
  } catch {
    return { ok: false, reason: 'malformed JSON' };
  }
}

/**
 * Build the repository from a source. The mode is decided by whether a Stage-1 v3
 * selection is present and passes the fail-closed schema gate — this is the single
 * place that binds a namespace.
 */
export function buildRepository(source: ArtifactSource, opts: BuildOptions = {}): SpotRepository {
  const selRaw = source.read(SELECTION_V3_KEY);
  // No selection: honest empty scaffold by default; synthetic demo only behind the gate.
  if (selRaw === null) return opts.demo ? demoRepository() : emptyRepository();

  const parsed = parseJson(selRaw);
  if (!parsed.ok) return rejectedSelectionRepository(parsed.reason);

  // FAIL-CLOSED v3 gate: only the authoritative v3 contract is accepted. A v1 object, a raw
  // non-v3 object, or a structurally-broken v3 is rejected outright — never a v1/raw fallback.
  const selectionV3 = shallowSelectionV3(parsed.value);
  if (selectionV3 === null) {
    return rejectedSelectionRepository('not a valid spot.stage01_selection.v3 contract');
  }
  return researchV3Repository(selectionV3);
}

/** Demo/example repository — synthetic artifacts, only reachable behind the demo gate. */
export function createDemoRepository(): SpotRepository {
  return demoRepository();
}

/** @deprecated alias retained for existing stage-view tests that exercise loaded rendering. */
export function createFixtureRepository(): SpotRepository {
  return demoRepository();
}

/** Honest empty scaffold: no selection, no data. Stages render their output shape only. */
function emptyRepository(): SpotRepository {
  return {
    namespace: 'research_only',
    mode: 'empty',
    selection: null,
    selectionV3: null,
    selectionRejection: null,
    getStage2: notGenerated,
    getStage3: notGenerated,
    getStage4: notGenerated,
  };
}

function demoRepository(): SpotRepository {
  return {
    namespace: 'fixture',
    mode: 'demo',
    selection: parseSelection(selectionFixtureRaw, 'fixture'),
    selectionV3: null,
    selectionRejection: null,
    getStage2: () => loaded(parseStage2(stage2FixtureRaw, 'fixture')),
    getStage3: () => loaded(parseStage3(stage3FixtureRaw, 'fixture')),
    getStage4: () => loaded(parseStage4(stage4FixtureRaw, 'fixture')),
  };
}

function rejectedSelectionRepository(reason: string): SpotRepository {
  const reject = <T,>(): ArtifactSlot<T> => ({ status: 'rejected', reason: 'selection rejected' });
  return {
    namespace: 'research_only',
    mode: 'rejected_selection',
    selection: null,
    selectionV3: null,
    selectionRejection: reason,
    getStage2: reject,
    getStage3: reject,
    getStage4: reject,
  };
}

/**
 * A verified v3 selection. It is real and exposed via `selectionV3`, but downstream
 * binding is held (no v3 artifact producer), so every stage is not_generated — NEVER
 * a fixture. `selection` (the legacy StageSelection) stays null; the v3 is the carrier.
 */
function researchV3Repository(selectionV3: SelectionV3): SpotRepository {
  return {
    namespace: 'research_only',
    mode: 'research',
    selection: null,
    selectionV3,
    selectionRejection: null,
    getStage2: notGenerated,
    getStage3: notGenerated,
    getStage4: notGenerated,
  };
}

const s = (v: unknown): string | null => (typeof v === 'string' ? v : null);
const dir = (v: unknown): 'high' | 'low' | null => (v === 'high' || v === 'low' ? v : null);

/**
 * Sync shallow projection of a spot.stage01_selection.v3 object into {@link SelectionV3}.
 * No hash recompute (that is the async {@link parseSelectionV3}) — it only schema-gates and
 * shape-checks. Returns null for anything that is not the v3 schema or is structurally
 * incomplete, so {@link buildRepository} can fail closed.
 */
function shallowSelectionV3(value: unknown): SelectionV3 | null {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return null;
  const top = value as Record<string, unknown>;
  if (top.schema_version !== 'spot.stage01_selection.v3') return null;

  const cc = top.canonical_content;
  if (typeof cc !== 'object' || cc === null) return null;
  const ccr = cc as Record<string, unknown>;
  const A = ccr.A;
  const B = ccr.B;
  if (typeof A !== 'object' || A === null || typeof B !== 'object' || B === null) return null;
  const Ar = A as Record<string, unknown>;
  const Br = B as Record<string, unknown>;

  const aId = s(Ar.program_id);
  const aDir = dir(Ar.direction);
  const bId = s(Br.program_id);
  const bDir = dir(Br.direction);
  const selection_id = s(top.selection_id);
  const question_id = s(top.question_id); // biology-only id; authoritatively re-derived in parseSelectionV3
  const estimator_id = s(top.estimator_id);
  const mode = top.analysis_mode;
  const exec = top.execution_status;
  const est = top.estimator_status;
  const conditions = Array.isArray(ccr.conditions)
    ? ccr.conditions.filter((c): c is string => typeof c === 'string')
    : null;

  if (aId === null || aDir === null || bId === null || bDir === null) return null;
  if (selection_id === null || question_id === null || estimator_id === null || conditions === null) return null;
  if (mode !== 'within_condition' && mode !== 'temporal_cross_condition') return null;
  if (exec !== 'ready' && exec !== 'refused' && exec !== 'awaiting_estimator') return null;
  if (est !== 'available' && est !== 'not_implemented') return null;

  return {
    selection_id,
    question_id,
    analysis_mode: mode,
    execution_status: exec,
    estimator_id,
    estimator_status: est,
    A: { program_id: aId, direction: aDir },
    B: { program_id: bId, direction: bDir },
    conditions,
    registry_scorer_view_sha256: s(ccr.registry_scorer_view_sha256) ?? '',
    source_h5ad_sha256: s(ccr.source_h5ad_sha256) ?? '',
    selection_full_sha256: s(top.selection_full_sha256) ?? '',
    full_contract_content_sha256: s(top.full_contract_content_sha256) ?? '',
    raw: top,
  };
}
