// Fail-closed adapter for the UI RELEASE MANIFEST (src/domain/uiReleaseManifest.ts): the compact,
// browser-safe artifact W1 packages after a REAL Stage-2/3/4 run to bind an admitted result into the
// drawer. Nothing is trusted until:
//   1. content-address — recompute sha256 over the canonical bytes; REJECT on any mismatch;
//   2. schema — the exact schema_version;
//   3. firewall — stage_label + method_id must equal the code-bound route/method;
//   4. admission — an EXPLICIT admitted verifier token (isAdmittedVerifier), never a partial/failed one;
//   5. completeness — every run field present + nonempty; artifact_paths nonempty.
// A rejection (thrown AdapterError) or an absent manifest leaves the route UNBOUND (the static
// method-definition + the one-line status). mergeAdmittedManifest overlays the admitted run onto the
// STATIC route method-definition — the definition prose is never taken from the release manifest.

import type { StageMethodsManifest, SourceChainLink } from '../domain/methodsManifest';
import type { UiReleaseManifest } from '../domain/uiReleaseManifest';
import { UI_RELEASE_SCHEMA_VERSION, isAdmittedVerifier } from '../domain/uiReleaseManifest';
import { canonicalJson, sha256Hex } from '../stage1/canonical';
import { fail } from './errors';
import { arr, isObject, optStr, str } from './guards';

/** A required, NON-empty string field (empty is treated as absent → incomplete_admitted_run). */
function reqStr(v: unknown, path: string): string {
  const s = str(v, path);
  if (s.trim() === '') fail('incomplete_admitted_run', `${path} is empty`);
  return s;
}
function reqStrList(v: unknown, path: string, min: number): string[] {
  const list = arr(v, path).map((x, i) => str(x, `${path}[${i}]`));
  if (list.length < min) fail('incomplete_admitted_run', `${path} must have at least ${min} entr${min === 1 ? 'y' : 'ies'}`);
  return list;
}

/**
 * Parse + fully validate a UI release manifest, FAIL-CLOSED. `expectedContentHash` is the sha256 the
 * shell pins for this admitted bundle; `stageLabel` / `methodId` are the code-bound route + method.
 * Returns the validated manifest, or throws AdapterError (content_hash_mismatch / unknown_schema_version
 * / stage_label_mismatch / method_id_mismatch / verifier_not_admitted / incomplete_admitted_run).
 */
export async function parseUiReleaseManifest(
  raw: unknown,
  expectedContentHash: string,
  stageLabel: string,
  methodId: string,
): Promise<UiReleaseManifest> {
  if (!isObject(raw)) fail('malformed', 'ui release manifest must be an object');

  // 1. content-address FIRST — trust nothing until the pinned hash verifies.
  const actual = await sha256Hex(canonicalJson(raw));
  if (actual !== expectedContentHash) {
    fail('content_hash_mismatch', `ui release manifest content hash ${actual} does not match bound ${expectedContentHash}`);
  }

  // 2. schema
  if (str(raw.schema_version, 'schema_version') !== UI_RELEASE_SCHEMA_VERSION) {
    fail('unknown_schema_version', `expected ${UI_RELEASE_SCHEMA_VERSION}`);
  }

  // 3. firewall — a manifest cannot rebind another route/method.
  const declaredStage = str(raw.stage_label, 'stage_label');
  if (declaredStage !== stageLabel) fail('stage_label_mismatch', `manifest stage_label "${declaredStage}" != code-bound "${stageLabel}"`);
  const declaredMethod = str(raw.method_id, 'method_id');
  if (declaredMethod !== methodId) fail('method_id_mismatch', `manifest method_id "${declaredMethod}" != code-bound "${methodId}"`);

  // 4. admission — an explicit admitted verifier token, never partial/failed/pending.
  const verifier = str(raw.verifier_status, 'verifier_status');
  if (!isAdmittedVerifier(verifier)) fail('verifier_not_admitted', `verifier_status "${verifier}" is not an admitted token`);

  // 5. completeness — every run field present + nonempty; artifacts nonempty.
  return {
    schema_version: UI_RELEASE_SCHEMA_VERSION,
    stage_label: declaredStage,
    method_id: declaredMethod,
    release_revision: reqStr(raw.release_revision, 'release_revision'),
    raw_sha256: reqStr(raw.raw_sha256, 'raw_sha256'),
    canonical_sha256: reqStr(raw.canonical_sha256, 'canonical_sha256'),
    method_code_sha256: reqStr(raw.method_code_sha256, 'method_code_sha256'),
    environment: reqStr(raw.environment, 'environment'),
    last_run_utc: reqStr(raw.last_run_utc, 'last_run_utc'),
    generator_status: reqStr(raw.generator_status, 'generator_status'),
    verifier_status: verifier,
    reproduce_command: reqStr(raw.reproduce_command, 'reproduce_command'),
    cs_notebook_url: optStr(raw.cs_notebook_url, 'cs_notebook_url'),
    artifact_paths: reqStrList(raw.artifact_paths, 'artifact_paths', 1),
    source_artifact_ids: reqStrList(raw.source_artifact_ids, 'source_artifact_ids', 0),
  };
}

/**
 * Overlay a VALIDATED admitted run onto the STATIC route method-definition. The definition prose
 * (data_input, estimand, masks/QC, upstream, method_id, source_chain) is preserved verbatim; only the
 * run-status fields are bound from the release manifest, plus the preserved source artifact IDs are
 * appended to the source chain. The result binds a complete admitted-run identity (isRunBound → true),
 * so the drawer renders the real run rows + reproduce command in place of the one-line status.
 */
export function mergeAdmittedManifest(staticDef: StageMethodsManifest, admitted: UiReleaseManifest): StageMethodsManifest {
  const sourceArtifacts: SourceChainLink[] = admitted.source_artifact_ids.map((id) => ({
    label: 'admitted source artifact',
    record_id: id,
    url: null,
    license: null,
    retrieval_utc: null,
    raw_sha256: null,
    canonical_sha256: null,
  }));
  return {
    stage_label: staticDef.stage_label,
    methods: {
      ...staticDef.methods,
      method_code_sha256: admitted.method_code_sha256,
      environment: admitted.environment,
      last_run_utc: admitted.last_run_utc,
      reproduce_command: admitted.reproduce_command,
    },
    provenance: {
      ...staticDef.provenance,
      release_revision: admitted.release_revision,
      raw_sha256: admitted.raw_sha256,
      canonical_sha256: admitted.canonical_sha256,
      generator_status: admitted.generator_status,
      verifier_status: admitted.verifier_status,
      cs_notebook_url: admitted.cs_notebook_url,
      artifact_paths: admitted.artifact_paths,
      source_chain: [...staticDef.provenance.source_chain, ...sourceArtifacts],
    },
  };
}

/**
 * W1 PACKAGING INTERFACE — call after a real run to package its admitted bundle for the shell.
 * Validates the manifest through the SAME fail-closed adapter (so W1 cannot hand over an incomplete or
 * non-admitted manifest) and returns it with its pinned content hash. W1 serves `manifest` and the
 * shell binds it against `content_hash`; the pair round-trips through parseUiReleaseManifest.
 */
export async function packageUiReleaseManifest(input: UiReleaseManifest): Promise<{ manifest: UiReleaseManifest; content_hash: string }> {
  const content_hash = await sha256Hex(canonicalJson(input));
  // Round-trip through the real gate: rejects an incomplete / non-admitted / mislabelled manifest.
  const manifest = await parseUiReleaseManifest(input, content_hash, input.stage_label, input.method_id);
  return { manifest, content_hash };
}
