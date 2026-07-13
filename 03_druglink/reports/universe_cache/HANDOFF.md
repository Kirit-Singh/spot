# Stage-3 universe drug-evidence cache — handoff to W16 & W1

**Branch:** `agent/stage3-universe-cache` (base `a7cd03d`; W16's `agent/stage3-druglink` untouched).
**Status:** built + real-extracted + generator-independently verified (disk-level admission); **HELD for
independent admission audit before publish**. Post-extraction audit `fa64054e` + re-audit `1f6008c2`
(verdict REPAIR) worklists fully applied test-first and regenerated (details at end).

## Store identity
- **store_id:** `bdf41b69df2be61d3f625aafa0429e643581fe50823698e77e079054c6145160`
  (W16 admitted the bytes at b20ec29b; this supersedes it with the UniProt-locator +
  provenance-gate reproducibility repair below. Eligibility science unchanged:
  `eligibility_evidence_sha256 cf5d7088…` byte-identical across the repair.)
- Bound into `store_id`: store_rows_sha256, eligibility_evidence_sha256, public_source_provenance_sha256,
  typed_universe_sha256, extraction_query_sha256, both source shas.
- **verify_ok: true** via `universe_verify.verify_from_disk` (loads + hashes + predicate-**replays** the
  actual on-disk store rows and 3.5 MB eligibility artifact; generator-independent, imports only `hashing`).
- Assertion denominators (exact): **2,227 general (rankable)** · 29 variant-specific · 6 ambiguous
  occurrences (2 unique mec_ids) · **2,258 unique source mec_ids** · **2,262 total stored occurrences**.

## Pinned public sources (independently verified)
- ChEMBL 37 `chembl_37_sqlite.tar.gz`: 5,764,252,857 bytes; sha256 `33c2037…d281` — **== publisher checksum**.
  CC BY-SA 3.0 + REQUIRED.ATTRIBUTION (preserve ChEMBL IDs, display release; cite Mendez 2019). DOI 10.6019/CHEMBL.database.37.
- UniProt 2026_02 `HUMAN_9606_idmapping.dat.gz`: 37,842,957 bytes; sha256 `0741a549…`; MD5 `7ef6a677…` — **== publisher MD5**. CC BY 4.0.
- Ensembl-gene join: idmapping `Ensembl` xref, version-stripped, matched to the pinned DE object obs.

## Coverage (typed universe; never claims 11,526 ENSG)
- 11,526 targets = **11,522 ENSG + 4 symbol-only** (MTRNR2L1/4/8, OCLM → `unsupported_namespace`).
- ENSG split: **505 drug_evidence** + 10,931 no_drug_evidence + **86 ambiguous_identity** (shared UniProt
  accession → multiple genes, e.g. calmodulin CALM1/2/3; fail-closed non-rankable) = 11,522.
- **29 variant-specific assertions** preserved but non-rankable (`variant_id != null`, incl. ChEMBL `-1`
  UNDEFINED MUTATION); only `variant_id IS NULL` enters the general lane. 2,227 general drug assertions.
- Eligibility evidence: 11,055 SINGLE PROTEIN candidates → 5,869 eligible human single-protein,
  5,186 rejected (`reject_nonhuman_target_taxon`). Accepted AND rejected records shipped (revalidatable).

## Data artifacts (out-of-Git; host-local cache `$SPOT_STAGE3_CACHE/` — real path only in the non-publishable operational log)
- `store/universe_store.rows.json` (6.6 MB), `store/target_eligibility_evidence.json` (3.5 MB) — ChEMBL-derived (CC BY-SA 3.0).
- `store/universe_manifest.json`, `verify_report.json`, `extraction_metrics.json`, `source_provenance.public.json` (sanitized, no machine path).
- `raw/` — pinned bulk archives + `source_provenance.operational.json` (**contains local paths; non-publishable, never committed**).
- Extracted SQLite `chembl_37_extract/` (30.48 GB, transient).

## Committed here (branch): code + compact reports only
- Modules `analysis/druglink/universe_*.py` (+ `build_universe_cache.py`); tests `tests/test_universe_*.py`
  (10 files, **77 universe tests**; full suite **394 green**; python3.12 / pytest, `PYTHONPATH=analysis`).
- `reports/universe_cache/` = manifest, verify_report, metrics, public provenance, this handoff.

## Schema to coordinate with W16
- `spot.stage03_universe_manifest.v1` (run-independent; releases/licenses separate; store_id binds typed
  universe + both source shas + extraction method + eligibility evidence).
- `spot.stage03_target_eligibility_evidence.v1` (per-target predicate fields + verdict; accepted+rejected).
- Store row dispositions: `drug_evidence | no_drug_evidence | unsupported_namespace | ambiguous_identity`;
  drug rows carry `action_type_source` **verbatim** (no cache direction — compatibility computed only at
  view time by frozen `direction.py`), exact `max_phase_source`/`max_phase_canonical`, `general_gene_rankable`.
- Per-run view: `universe_store.view_for_queue` (pure selection, re-acquires nothing, order-independent).

## Post-extraction repairs applied (test-first) before this handoff
1. Malformed shell-generated provenance + machine-path leak → Python `universe_source_provenance` generator,
   sanitized public record, all emitted JSON parse-validated (`test_universe_source_provenance`).
2. Shared-accession ambiguity admitted as drug_evidence → `ambiguous_identity` fail-closed (`test_universe_ambiguous_identity`, real calmodulin IDs).
3. Variant assertions in the general lane → `variant_specific_nonrankable` (`test_universe_variant_nonrankable`, real V617F/V600E/-1).
4. Eligibility source fields discarded → content-addressed evidence artifact bound to manifest/store_id (`test_universe_eligibility_evidence`).

## Re-audit `1f6008c2` (REPAIR) — applied test-first, regenerated once
1. Ambiguous nested `ambiguous_source_assertions` now `general_gene_rankable=false` + named
   `ambiguity_disposition="ambiguous_identity_nonrankable"`; verifier requires **both** (mutation refused).
2. On-disk eligibility artifact is loaded, canonically hashed, and every verdict predicate-**replayed**
   during admission (`verify_from_disk`); a one-record mutation fails at `eligibility_evidence_hash_drift` /
   `eligibility_verdict_replay_mismatch`.
3. Sanitized public provenance content-bound into manifest + `store_id`; release-specific locators (ChEMBL
   `checksums.txt`, UniProt `RELEASE.metalink`/`relnotes`); mutable `current_release` caveated, bytes pinned
   by hash; immutable `previous_releases/release-2026_02/` to be added once UniProt archives 2026_02.
4. `n_total_drug_assertions` renamed → `n_general_drug_assertions`; added `n_unique_source_mechanism_rows`,
   `n_variant_specific_assertions`, `n_ambiguous_assertion_occurrences` (+ unique) in metrics.
5. Committed HANDOFF machine path removed → `$SPOT_STAGE3_CACHE/` (real path only in the non-publishable
   operational log).
6. Mixed-license release gate: `CHEMBL_LICENSE` + `CHEMBL_REQUIRED_ATTRIBUTION` packaged in the store dir;
   ChEMBL-derived layer CC BY-SA 3.0, UniProt-derived identity CC BY 4.0 — cache data is NOT the code's MIT.

## W16 re-admission repair (post-admission of b20ec29b) — UniProt locator + provenance gate
- **UniProt locator:** primary-source check confirms `current_release` is still 2026_02 and
  `previous_releases/` archives only through 2026_01 — so `release-2026_02/` does NOT exist and is not
  invented. The real `current_release` URL is kept; the **release=2026_02 association is proven by bound
  bytes**: `UNIPROT_2026_02.relnotes.txt` (says "Release 2026_02") + `UNIPROT_2026_02.by_organism.RELEASE.metalink`
  (attests this file's MD5 `7ef6a677…`), both hashed into the provenance and packaged. An immutable
  `previous_releases/release-2026_02/` URL is to be added once UniProt archives it — without changing bytes.
- **Provenance gate:** `verify_from_disk` now also reopens and hashes `source_provenance.public.json` and
  fails with `public_source_provenance_hash_drift` on any on-disk change (proven on the real store; mutation
  test added). Packaged release metadata: `CHEMBL_checksums.txt`, `UNIPROT_2026_02.*`.

**Ask of W16/W1:** independent admission audit of `store_id bdf41b69…` — re-run `universe_verify.verify_from_disk`,
re-hash both sources vs publisher, re-parse all JSON (zero path leaks), replay eligibility predicates, confirm
dispositions/counts, review the two schemas, and reconcile with W16's `03_druglink/verifier/`. Publish only on pass.
