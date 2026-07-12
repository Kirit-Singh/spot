// Data-adapter (repository) layer. Components depend ONLY on this interface and
// never learn where artifacts come from, nor which namespace they belong to.
//
// Three strictly separated worlds, decided in code — never by editing a data field:
//   - fixture           : direct entry with no live selection → synthetic preview
//   - research_only      : a Stage-1 research-bridge selection in localStorage
//   - production (future): a separate source; production_gate_passed=false can never
//                          reach it, so it is not constructible here today.
//
// A research selection with no matching artifact is `not_generated` — the shell must
// NEVER fall back to fixture results beneath a real research selection.

import type { Namespace } from '../domain/common';
import type { StageSelection } from '../domain/selection';
import type { Stage2Artifact } from '../domain/stage2';
import type { Stage3Artifact } from '../domain/stage3';
import type { Stage4Artifact } from '../domain/stage4';
import { AdapterError } from '../adapters/errors';
import { parseSelection } from '../adapters/selectionAdapter';
import { parseStage2 } from '../adapters/stage2Adapter';
import { parseStage3 } from '../adapters/stage3Adapter';
import { parseStage4 } from '../adapters/stage4Adapter';
import { selectionFixtureRaw } from '../fixtures/selection.fixture';
import { stage2FixtureRaw } from '../fixtures/stage2.fixture';
import { stage3FixtureRaw } from '../fixtures/stage3.fixture';
import { stage4FixtureRaw } from '../fixtures/stage4.fixture';
import type { ArtifactSource } from './source';
import { SELECTION_KEY, STAGE2_KEY, STAGE3_KEY, STAGE4_KEY } from './source';

/** A stage artifact is either loaded, not-yet-generated, or rejected (with a reason). */
export type ArtifactSlot<T> =
  | { status: 'loaded'; artifact: T }
  | { status: 'not_generated' }
  | { status: 'rejected'; reason: string };

// empty  — no selection, no demo: honest workflow scaffold, no data.
// demo   — explicit demo gate: synthetic example artifacts (unmistakably synthetic).
// research — a real Stage-1 research selection in localStorage.
export type RepositoryMode = 'empty' | 'demo' | 'research' | 'rejected_selection';

export interface BuildOptions {
  /** Explicit demo gate (e.g. ?demo=1). Only then do synthetic artifacts render. */
  demo?: boolean;
}

export interface SpotRepository {
  readonly namespace: Namespace;
  readonly mode: RepositoryMode;
  /** The ingested selection context, or null when the selection was rejected. */
  readonly selection: StageSelection | null;
  /** Why a present selection was rejected (mode === 'rejected_selection'). */
  readonly selectionRejection: string | null;
  getStage2(): ArtifactSlot<Stage2Artifact>;
  getStage3(): ArtifactSlot<Stage3Artifact>;
  getStage4(): ArtifactSlot<Stage4Artifact>;
}

const loaded = <T,>(artifact: T): ArtifactSlot<T> => ({ status: 'loaded', artifact });
const rejected = <T,>(reason: string): ArtifactSlot<T> => ({ status: 'rejected', reason });
const notGenerated = <T,>(): ArtifactSlot<T> => ({ status: 'not_generated' });

function parseJson(raw: string): { ok: true; value: unknown } | { ok: false; reason: string } {
  try {
    return { ok: true, value: JSON.parse(raw) };
  } catch {
    return { ok: false, reason: 'malformed JSON' };
  }
}

/**
 * Build the repository from a source. The mode is decided by whether a Stage-1
 * selection is present and valid — this is the single place that binds a namespace.
 */
export function buildRepository(source: ArtifactSource, opts: BuildOptions = {}): SpotRepository {
  const selRaw = source.read(SELECTION_KEY);
  // No selection: honest empty scaffold by default; synthetic demo only behind the gate.
  if (selRaw === null) return opts.demo ? demoRepository() : emptyRepository();

  const parsed = parseJson(selRaw);
  if (!parsed.ok) return rejectedSelectionRepository(parsed.reason);

  // The research bridge is bound to research_only in code. A selection declaring any
  // other namespace (fixture / production) is rejected — production can never enter here.
  try {
    const selection = parseSelection(parsed.value, 'research_only');
    return researchRepository(selection, source);
  } catch (err) {
    return rejectedSelectionRepository(describe(err));
  }
}

/** Demo/example repository — synthetic artifacts, only reachable behind the demo gate. */
export function createDemoRepository(): SpotRepository {
  return demoRepository();
}

/** @deprecated alias retained for existing stage-view tests that exercise loaded rendering. */
export function createFixtureRepository(): SpotRepository {
  return demoRepository();
}

function describe(err: unknown): string {
  if (err instanceof AdapterError) return `${err.code}: ${err.message}`;
  return err instanceof Error ? err.message : String(err);
}

/** Honest empty scaffold: no selection, no data. Stages render their output shape only. */
function emptyRepository(): SpotRepository {
  return {
    namespace: 'research_only',
    mode: 'empty',
    selection: null,
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
    selectionRejection: null,
    getStage2: () => loaded(parseStage2(stage2FixtureRaw, 'fixture')),
    getStage3: () => loaded(parseStage3(stage3FixtureRaw, 'fixture')),
    getStage4: () => loaded(parseStage4(stage4FixtureRaw, 'fixture')),
  };
}

function rejectedSelectionRepository(reason: string): SpotRepository {
  const reject = <T,>(): ArtifactSlot<T> => rejected('selection rejected');
  return {
    namespace: 'research_only',
    mode: 'rejected_selection',
    selection: null,
    selectionRejection: reason,
    getStage2: reject,
    getStage3: reject,
    getStage4: reject,
  };
}

function researchRepository(selection: StageSelection, source: ArtifactSource): SpotRepository {
  // Parse each stage once; downstream stages bind to the loaded upstream artifact-id.
  const s2 = loadStage2(source.read(STAGE2_KEY), selection);
  const upstream2 = s2.status === 'loaded' ? s2.artifact.provenance.artifact_id : null;
  const s3 = loadDownstream(source.read(STAGE3_KEY), (v) => parseStage3(v, 'research_only'), upstream2);
  const upstream3 = s3.status === 'loaded' ? s3.artifact.provenance.artifact_id : null;
  const s4 = loadDownstream(source.read(STAGE4_KEY), (v) => parseStage4(v, 'research_only'), upstream3);

  return {
    namespace: 'research_only',
    mode: 'research',
    selection,
    selectionRejection: null,
    getStage2: () => s2,
    getStage3: () => s3,
    getStage4: () => s4,
  };
}

/** Load + bind a research Stage-2 artifact to its selection (id, namespace, contrast). */
function loadStage2(raw: string | null, selection: StageSelection): ArtifactSlot<Stage2Artifact> {
  if (raw === null) return notGenerated();
  const parsed = parseJson(raw);
  if (!parsed.ok) return rejected(parsed.reason);
  let artifact: Stage2Artifact;
  try {
    artifact = parseStage2(parsed.value, 'research_only');
  } catch (err) {
    return rejected(describe(err));
  }
  const s = artifact.selection;
  if (s.selection_id !== selection.selection_id) return rejected('selection_id mismatch');
  if (s.namespace !== selection.namespace) return rejected('namespace mismatch');
  if (s.contrast_id !== selection.contrast_id) return rejected('contrast_id mismatch');
  return loaded(artifact);
}

/** Load + bind a downstream (Stage-3/4) artifact to its upstream artifact-id. */
function loadDownstream<T extends { provenance: { upstream_ref: { artifact_id: string } | null } }>(
  raw: string | null,
  parse: (v: unknown) => T,
  upstreamArtifactId: string | null,
): ArtifactSlot<T> {
  if (raw === null) return notGenerated();
  const parsed = parseJson(raw);
  if (!parsed.ok) return rejected(parsed.reason);
  let artifact: T;
  try {
    artifact = parse(parsed.value);
  } catch (err) {
    return rejected(describe(err));
  }
  if (upstreamArtifactId === null) return rejected('no matching upstream artifact to bind to');
  if (artifact.provenance.upstream_ref?.artifact_id !== upstreamArtifactId) {
    return rejected('upstream artifact-id mismatch');
  }
  return loaded(artifact);
}
