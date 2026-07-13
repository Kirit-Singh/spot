// Helpers for building obviously-synthetic fixture artifacts.
//
// Every fixture is bound to the `fixture` namespace and is production_eligible=false.
// Hashes are well-formed (64 hex) but visibly synthetic; identifiers use GENE_A /
// PATHWAY_01 / COMPOUND_A style so a fixture can never be mistaken for real data.

/** Deterministic, well-formed 64-hex string from a hex seed (visibly synthetic). */
export function h64(seed: string): string {
  const hex = seed.replace(/[^0-9a-f]/g, '') || 'f';
  return hex.repeat(Math.ceil(64 / hex.length)).slice(0, 64);
}

/** Raw provenance block for a fixture artifact (shape validated by the adapters). */
export function fixtureProvenance(opts: {
  stage: 'stage01' | 'stage02' | 'stage03' | 'stage04';
  slug: string;
  seed: string;
  methodId: string;
  sources: { label: string; record_id: string; url: string | null; detail: string }[];
  upstream?: { stage: string; slug: string; seed: string } | null;
}) {
  const canonical = h64(opts.seed);
  return {
    artifact_id: `fixture:${opts.stage}:${opts.slug}@${canonical.slice(0, 12)}`,
    schema_version: schemaVersionFor(opts.stage),
    namespace: 'fixture',
    production_eligible: false,
    hashes: { raw_sha256: h64('ab' + opts.seed), canonical_sha256: canonical },
    method: {
      method_id: opts.methodId,
      config_id: `fixture_config_${opts.slug}`,
      code_ref: 'synthetic-fixture-not-a-real-pipeline',
      env_ref: 'synthetic-fixture-env',
    },
    sources: opts.sources,
    cs_session: { session_ref: 'fixture-session', frame_ref: 'fixture-frame' },
    upstream_ref: opts.upstream
      ? {
          artifact_id: `fixture:${opts.upstream.stage}:${opts.upstream.slug}@${h64(
            opts.upstream.seed,
          ).slice(0, 12)}`,
          canonical_sha256: h64(opts.upstream.seed),
        }
      : null,
  };
}

function schemaVersionFor(stage: string): string {
  switch (stage) {
    case 'stage02':
      return 'spot.stage02_gene_lever_set.v1';
    case 'stage03':
      return 'spot.stage03_drug_candidate_set.v1';
    case 'stage04':
      return 'spot.stage04_scorecard_set.v1';
    default:
      return 'spot.stage01_selection.v1';
  }
}
