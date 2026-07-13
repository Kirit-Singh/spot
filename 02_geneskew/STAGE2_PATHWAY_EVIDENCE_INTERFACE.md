# Stage-2 pathway: the PRODUCER ↔ INDEPENDENT-VERIFIER interface

W18 owns the producer (`pathway_evidence.py`, `run_pathway.py`).
W4 owns the independent verifier (`verify_reconstruct.py`, `verify_pathway.py`) and the
forgery attacks (`tests/direct/test_pathway_forgery.py`). They share no code, by design:
a producer that also wrote the check that its counts were honest would be marking its own
homework.

This file is the contract between them. It is what the verifier LOADS.

## Why

`verify_pathway` used to re-derive the coverage arithmetic **from the record's own declared
counts**. Every number in `target_source_coverage = n_genes_in_target_universe /
n_source_symbols` came out of the document under attack. Forge them together, honestly
reseal `records_sha256`, and a pathway with **zero** perturbed members admits as
headline-rankable in both arms with `n_failed = 0`.

Internal consistency is not provenance. A count nobody can recount is a claim.

## What the producer must ship, per pathway output bundle

| File (bundle-relative) | Content | Status |
|---|---|---|
| `pathway_evidence.json` | full pre-intersection membership, both universes, each arm's ranking | ✅ landed (`20a4726`) |
| `pathway_signatures.parquet` | masked signatures, LONG `(target_id, gene_id, value)` | ✅ landed (`e393285`) |
| `gene_sets.source.json` | the exact pinned gene-set JSON bytes, copied VERBATIM | ✅ landed (`9d55c66`) |

### The pinned bundle ships inside the artifact

The source gene-set JSON is copied **byte for byte** into every pathway output bundle at the
fixed bundle-relative path `gene_sets.source.json`, and bound at
`run_binding.evidence_artifacts.gene_set_source`:

```python
{
    "path_in_bundle": "gene_sets.source.json",   # RELATIVE. Never an absolute path.
    "raw_sha256":     "<sha256 of the source>",  # == gene_sets.gene_set_release.sha256
    "canonical_sha256": ...,
    "gene_set_release": {"source", "release_id", "n_sets", "license", "sha256"},
    "gene_id_namespace": ..., "copied_byte_for_byte": True,
}
```

Rules the verifier enforces:
- **Verbatim bytes.** `sha256(shipped copy) == gene_set_release.sha256` (the pinned source
  identity the run was given). The verifier refuses on any drift.
- **`gene_set_source` enters `run_binding` BEFORE `pathway_run_id` is computed.** The run id
  is `sha256(canonical_json(run_binding))[:16]`, and the verifier **recomputes** it
  (`pathway_run_id_rederives_from_run_binding`) rather than reading it.
- **The bound path must be bundle-relative.** An absolute path, or one containing `..`,
  refuses at `the_pinned_gene_set_bundle_is_shipped_inside_the_artifact`.
- **No absolute path** enters provenance, the method hash or the run hash. An artifact that
  can only be verified on the machine that wrote it is not a portable artifact.
- Six small pathway bundles each carrying their own source copy is the intended trade:
  portability and self-containment beat deduplication.
- Release identity travels with it: `release_id`, `source`, `license`, `license_reference`,
  `gene_id_namespace`, and the declared `target_universe_sha256` / `effect_universe_sha256`.

## Why this file and not a path

Everything else in the bundle — the record, the evidence, the run id — can be recomputed by
whoever owns the output directory. Content-addressing proves an artifact is *internally
coherent*, never that it is *true*: a forger who reseals the evidence and the run id along
with it produces a perfectly self-consistent lie.

The pinned release is the one link in the chain the forger does not own. Its raw sha256 is
published with the release, and it **declares the content hash of both universes it was
built against**. So the anchor runs OUTWARD:

> to promote a pathway with no perturbed members, its genes must enter the
> perturbation-target universe → that universe's content hash changes → it no longer equals
> the hash the pinned bundle declares → refused. Fixing *that* means editing the pinned
> bundle → its raw sha256 changes → and that is the number published with the release.

## What the verifier does with it

Loads **only** the shipped bundle-relative copy. Confirms its raw hash equals the pinned
source identity, then its release id / licence / namespace against the run provenance. Then
it takes the **full mapped membership** from those bytes and computes, itself:

```
n_source_genes        the source-symbol denominator            <- pinned bundle
n_in_target_universe  |members ∩ bound target universe|        <- verifier's own intersection
n_hits_in_ranking     |members ∩ that arm's ranked targets|    <- verifier's own intersection
the leading edge      the ranking, walked again
convergence support   the cosine, recomputed on the signatures
```

The **rankability decision is taken on these numbers**, never on the declared ones. A
declared value that disagrees is refused at a named gate.

`--gene-sets` remains available as an **optional second opinion** — an auditor comparing the
shipped copy against their own copy of the release
(`the_shipped_gene_set_copy_matches_the_original_source_cache`). It is never how the shipped
evidence is located.

## Named gates

Drift gates (a `*_mismatch` check that PASSES means no such drift was found):

- `gene_set_raw_hash_mismatch`
- `gene_set_release_identity_mismatch`
- `full_membership_mismatch`
- `target_intersection_count_mismatch`
- `ranking_hit_count_mismatch`

Fail-closed structural gates:

- `pathway_run_id_rederives_from_run_binding` — the id is recomputed from the binding, never
  read. A forger who swaps a bound evidence hash and reseals the documents inside the bundle
  still has to produce an id the binding hashes to.
- `the_pinned_gene_set_bundle_is_shipped_inside_the_artifact`
- `the_shipped_gene_set_bundle_loads_from_its_bundle_relative_path`
- `the_reconstruction_evidence_artifact_is_present`
- `the_reconstruction_evidence_hashes_to_the_run_binding`
- `the_masked_signature_artifact_hashes_to_the_run_binding`
- `the_bound_target_universe_is_the_one_the_pinned_bundle_declares`
- `the_bound_readout_universe_is_the_one_the_pinned_bundle_declares`
- `enrichment_tests_membership_in_the_perturbation_target_universe`
- `every_ranked_target_lies_in_the_bound_target_universe`
- `every_signature_target_lies_in_the_bound_target_universe`

Count-drift refusals carry the reason code `gene_set_pathway_member_count_mismatch`.

## Preserved invariants

- **Two universes, bound separately.** Enrichment tests membership in the
  perturbation-target universe; convergence's vectors live in the DE-readout universe.
- **Independent arms.** No combined eligibility, no combined score, no Pareto tier, no
  concordance class.
- **No p, no q, no FDR** — the recursive key firewall runs over every shipped document.
