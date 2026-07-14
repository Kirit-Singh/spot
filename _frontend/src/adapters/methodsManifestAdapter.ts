// Content-addressed adapter for the per-stage Methods & Provenance manifest emitted by each
// REAL run — the artifact that backs the shared header drawer (src/shell/ProvenanceDrawer.tsx).
//
// Unlike `manifestFromProvenance()` (which projects a slim `Provenance` object and hard-nulls
// most drawer rows), this parser reads a purpose-built manifest that carries EVERY field the
// drawer shows: exact data/input, estimand, masks/QC, upstream model, method-intrinsic
// limitations, method+code+env, last-run UTC, reproduce command, release/revision,
// generator/verifier status, the Claude-Science notebook URL, artifact paths, and a
// content-addressed source chain with per-source URL + license + retrieval time + raw and
// canonical hashes.
//
// FAIL-CLOSED BINDING. The artifact is bound in code by `expectedContentHash`: we recompute
// sha256 over the canonical manifest bytes (the SAME canonicalJson+sha256Hex the Stage-1
// emitter uses) and REJECT at a named gate on any mismatch — so mutating a single byte of any
// bound value (a per-source hash, a license, a retrieval date, the release) invalidates the
// whole manifest. Nothing is trusted until that gate passes.
//
// NOTHING INVENTED. A genuinely-absent optional field stays null ("unavailable"); it is never
// backfilled from a demo fixture or a conflicting hard-coded value. `source_tissue` is the one
// deterministic fallback — a source-backed fact keyed on the stage (see `stageSourceTissue`),
// not a per-run value — used only when the manifest omits it.
//
// cs_notebook_url IS A DISTINCT FIELD. A Claude-Science session/frame id (e.g. a `cs_session`
// object) is NEVER promoted into `cs_notebook_url`; only an explicit `cs_notebook_url` string
// populates that row, so a frame ref is never rendered as an `<a href>`.

import type {
  MethodsBlock,
  ProvenanceBlock,
  SourceChainLink,
  StageMethodsManifest,
} from '../domain/methodsManifest';
import { stageSourceTissue } from '../domain/methodsManifest';
import { canonicalJson, sha256Hex } from '../stage1/canonical';
import { fail } from './errors';
import { arr, isObject, optHex, optStr, str } from './guards';

/** Optional list of plain strings; a genuinely-absent list is [] (drawer shows "unavailable"). */
function stringList(v: unknown, path: string): string[] {
  if (v === null || v === undefined) return [];
  return arr(v, path).map((x, i) => str(x, `${path}[${i}]`));
}

/** One content-addressed source-chain link — every field read straight from the manifest. */
function sourceChainLink(v: unknown, path: string): SourceChainLink {
  if (!isObject(v)) fail('malformed', `${path} source-chain link is required`);
  return {
    label: str(v.label, `${path}.label`),
    record_id: str(v.record_id, `${path}.record_id`),
    url: optStr(v.url, `${path}.url`),
    license: optStr(v.license, `${path}.license`),
    retrieval_utc: optStr(v.retrieval_utc, `${path}.retrieval_utc`),
    raw_sha256: optHex(v.raw_sha256, `${path}.raw_sha256`),
    canonical_sha256: optHex(v.canonical_sha256, `${path}.canonical_sha256`),
  };
}

function methodsBlock(v: unknown, path: string, stage_label: string): MethodsBlock {
  if (!isObject(v)) fail('malformed', `${path} methods block is required`);
  return {
    data_input: optStr(v.data_input, `${path}.data_input`),
    // Manifest value wins; otherwise the deterministic stage source-tissue fact (not per-run).
    source_tissue: optStr(v.source_tissue, `${path}.source_tissue`) ?? stageSourceTissue(stage_label),
    estimand: optStr(v.estimand, `${path}.estimand`),
    masks_qc: optStr(v.masks_qc, `${path}.masks_qc`),
    upstream_model: optStr(v.upstream_model, `${path}.upstream_model`),
    limitations: stringList(v.limitations, `${path}.limitations`),
    method_id: optStr(v.method_id, `${path}.method_id`),
    method_code_sha256: optHex(v.method_code_sha256, `${path}.method_code_sha256`),
    environment: optStr(v.environment, `${path}.environment`),
    last_run_utc: optStr(v.last_run_utc, `${path}.last_run_utc`),
    reproduce_command: optStr(v.reproduce_command, `${path}.reproduce_command`),
  };
}

function provenanceBlock(v: unknown, path: string): ProvenanceBlock {
  if (!isObject(v)) fail('malformed', `${path} provenance block is required`);
  return {
    release_revision: optStr(v.release_revision, `${path}.release_revision`),
    raw_sha256: optHex(v.raw_sha256, `${path}.raw_sha256`),
    canonical_sha256: optHex(v.canonical_sha256, `${path}.canonical_sha256`),
    generator_status: optStr(v.generator_status, `${path}.generator_status`),
    verifier_status: optStr(v.verifier_status, `${path}.verifier_status`),
    // Distinct from any session/frame id — only an explicit notebook URL populates this row.
    cs_notebook_url: optStr(v.cs_notebook_url, `${path}.cs_notebook_url`),
    artifact_paths: stringList(v.artifact_paths, `${path}.artifact_paths`),
    source_chain: (v.source_chain === null || v.source_chain === undefined)
      ? []
      : arr(v.source_chain, `${path}.source_chain`).map((s, i) =>
          sourceChainLink(s, `${path}.source_chain[${i}]`),
        ),
  };
}

/**
 * Parse a REAL per-stage methods/provenance manifest into a `StageMethodsManifest`.
 *
 * @param raw                  the manifest artifact (parsed JSON) as received
 * @param expectedContentHash  sha256 the repository binds to this artifact in code; the manifest
 *                             is REJECTED (fail-closed) unless the recomputed canonical hash equals it
 * @param stage_label          the stage this artifact is bound to in code (the source of truth)
 *
 * Every drawer field is populated from the manifest — nothing invented, genuinely-absent
 * optional fields stay null. If the manifest declares its own `stage_label` it must agree with
 * the code-bound one (a firewall against showing one stage's manifest under another's label).
 */
export async function parseStageMethodsManifest(
  raw: unknown,
  expectedContentHash: string,
  stage_label: string,
): Promise<StageMethodsManifest> {
  if (!isObject(raw)) fail('malformed', 'methods manifest must be an object');

  // Content-address the artifact FIRST: trust nothing until the bound hash verifies.
  const actual = await sha256Hex(canonicalJson(raw));
  if (actual !== expectedContentHash) {
    fail(
      'content_hash_mismatch',
      `methods manifest content hash ${actual} does not match bound ${expectedContentHash}`,
    );
  }

  // Firewall: a manifest that declares a stage may not be relabelled into another.
  const declared = optStr(raw.stage_label, 'manifest.stage_label');
  if (declared !== null && declared !== stage_label) {
    fail(
      'stage_label_mismatch',
      `manifest stage_label "${declared}" does not match code-bound "${stage_label}"`,
    );
  }

  return {
    stage_label,
    methods: methodsBlock(raw.methods, 'manifest.methods', stage_label),
    provenance: provenanceBlock(raw.provenance, 'manifest.provenance'),
  };
}
