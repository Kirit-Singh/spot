// UI RELEASE MANIFEST — the compact, browser-safe artifact W1 packages after a REAL Stage-2/3/4 run
// and hands to the shell to bind an admitted result into the Methods & Provenance drawer.
//
// It is content-addressed (a pinned sha256 over its canonical form) and FAIL-CLOSED: the adapter
// rejects it unless (a) the recomputed hash matches the pinned hash, (b) its stage_label + method_id
// match the code-bound route/method, and (c) its independent-verifier status is an explicit admission
// token. A rejected or absent manifest leaves the route in the existing one-line UNBOUND status —
// never a partial or fabricated run claim.
//
// It carries ONLY what the drawer's run-status rows need (the exact admitted code / environment /
// run UTC / generator / verifier / artifacts / reproduce command / Claude-Science notebook URL) plus
// the result content addresses and the preserved source artifact IDs. It never carries method
// DEFINITION prose — that stays the static, route-specific manifest, merged in by the shell.

export const UI_RELEASE_SCHEMA_VERSION = 'spot.ui_release_manifest.v1' as const;

export interface UiReleaseManifest {
  schema_version: typeof UI_RELEASE_SCHEMA_VERSION;
  /** Must equal the route's canonical stage label (Targets / Pathways / Drugs / PK & Safety). */
  stage_label: string;
  /** Must equal the static route method_id (a manifest cannot rebind another method's run). */
  method_id: string;

  // ── result content addresses ──
  release_revision: string;
  raw_sha256: string;
  canonical_sha256: string;

  // ── admitted-run identity (all required; a partial subset is rejected fail-closed) ──
  method_code_sha256: string;
  environment: string;
  last_run_utc: string; // ISO-8601 UTC
  generator_status: string;
  verifier_status: string; // must be an admitted token (see isAdmittedVerifier)
  reproduce_command: string; // reproduces THIS admitted artifact
  cs_notebook_url: string | null; // a real Claude-Science notebook URL, or null

  artifact_paths: string[]; // nonempty — the emitted result artifacts
  source_artifact_ids: string[]; // preserved source artifact IDs (provenance thread)
}

// Strict, ANCHORED admission vocabulary — the WHOLE normalized verifier status must equal one of
// these exact tokens. Substring matching is unsafe ("not passed" contains "pass"; "unverified"
// contains "verified"), so "not passed" / "pending independent verification" / "failed" are NOT
// admitted. Shared by the adapter (fail-closed admission gate) and the drawer (isRunBound).
export const ADMITTED_VERIFIER_TOKENS = new Set(['admit', 'admitted', 'pass', 'passed', 'verified', 'ok']);

/** True only when the verifier status is EXACTLY an admitted token (normalized, whole-string). */
export function isAdmittedVerifier(status: string | null): boolean {
  if (!status) return false;
  return ADMITTED_VERIFIER_TOKENS.has(status.trim().toLowerCase());
}
