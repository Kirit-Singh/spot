# Stage-3 universe drug-evidence cache — handoff to W16 & W1

**Branch:** `agent/stage3-universe-cache` (base `a7cd03d`; W16's `agent/stage3-druglink` untouched).
**Status:** built + real-extracted + generator-independently verified; **HELD for independent admission
audit before publish** (per instruction: do not publish until post-extraction audit passes).

## Store identity
- **store_id:** `446c3b78937593e89d13afe941eb3a6dbe6d37e3beac17f7edd5dd0abdde914d`
- store_rows_sha256 `6c88b53a…`; eligibility_evidence_sha256 `cf5d7088…`; both bound into `store_id`.
- **verify_ok: true** (generator-independent `universe_verify`, imports only the `hashing` leaf).

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

## Data artifacts (out-of-Git; tcefold data cache `/home/tcelab/.cache/spot-stage3-universe/`)
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

**Ask of W16/W1:** independent admission audit of the store (re-run `universe_verify`, re-hash sources vs
publisher, re-parse all JSON, confirm dispositions/counts, review the two schemas). Publish only on pass.
