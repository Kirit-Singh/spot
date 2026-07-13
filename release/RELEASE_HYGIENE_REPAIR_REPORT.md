# Release-hygiene repair and verification report

**Date:** 2026-07-13

**Starting head:** `98abbd576ee7a0e9d92e075023c43a86fd667fcf`

**Re-audit worklist:** `RELEASE_HYGIENE_REAUDIT_98ABBD5.md`, SHA-256
`70cc4d10848a5fc421934270d64e14b2e96c9427737063f1bc04321f2c06b50c`

No push, upload, Hugging Face mutation, or public deployment was performed. Scientific
artifacts were not edited.

## Repairs

| Finding | Repair | Verification |
|---|---|---|
| Active code could self-authorize a machine path | The scanner now inspects every tracked worktree file and any different staged/index bytes. Allowlist classifications are restricted to exact immutable historical, solver, attestation, or negative-test locations. A separately pinned release policy binds the reviewed allowlist. | An exact `deploy/serve_static.py` machine-path mutation plus a matching historical classification is rejected. |
| Scanner files could hide a credential | No tracked file is excluded from secret scanning, including the scanner, allowlist and release policy. Invalid allowlist rows now raise fixed-shape exceptions that contain only an entry number and named gate, never any row field or payload. | A credential-shaped value in the staged allowlist snapshot is detected by name. A subprocess regression exercises normal pytest failure rendering for an invalid row and proves the inserted value is absent from captured stdout/stderr. No credential value is stored in this report or repository. |
| Bare private networks and local paths were missed | The scanner now covers bare RFC1918 and CGNAT IPv4 addresses, Unix user/runtime/volume roots, tilde paths, Windows user homes, and local spot run-directory forms. | Ten mutation forms are detected. The active UI contract now uses `${SPOT_RUN_ROOT}/ui-baseline-8347/`. |
| HF state test was one-file prose | `release/public_external_artifacts.json` records the immutable public revision and each public/staged artifact. Current user-facing docs and served artifacts are scanned for affirmative v3-public claims. | The false sentence “v3 396k score Parquet is public on Hugging Face” is rejected. The public manifest records the full-score Parquet as staged and not public. |
| Current/prospective release state conflicted | Root/CFF/stage READMEs now consistently say Stage 1 is implemented, Stage-2 code is preliminary with no released production result, and Stages 3–5 are prospective. | A regression test binds those states. The stale hand-maintained tracked-size claim was removed in favor of the exact inventory. |
| Regulatory-source terms were conflated | `DATA_LICENSES.md` now distinguishes openFDA, FAERS and ClinicalTrials.gov, with official terms/limitations and no public-domain overclaim. | A regression test rejects the collapsed source name and requires the official locators and FAERS signal-evidence boundary. |
| Reactome release/news dates were conflated | The actual external cache now records V97 release `2026-06-30` and news-record creation `2026-06-23` separately. Original metadata was retained as superseded provenance, and downstream Ensembl-cache provenance was re-bound. | Cache provenance and all source/bundle byte hashes were independently re-derived after the amendment. |
| Rebound Ensembl provenance retained machine-absolute artifact paths | Both lane `path` fields are now deterministic artifact names relative to their provenance file. The prior provenance was retained as a superseded record, and the new record explicitly binds the portability-only amendment. | The rebound provenance contains zero machine-absolute/local run paths; both relative artifacts re-hash to their unchanged bundle pins; old/current scientific projections are identical. |
| The pathway/gene-set result omitted its executable identity | This report now records the exact remote Stage-2 commit and complete eight-file pytest invocation. | The bound command was rerun at the named clean commit and reports exactly 218 passed. |

## External cache amendment

The cache under `${SPOT_RUN_ROOT}` was amended without changing a gene set, crosswalk, or
effect universe:

- symbol-cache provenance: `cf3255d0…` →
  `00ec824a1e498db98383fa8f7613fe140cd3bfb945b8d1ff3c04f27df2a6ee46`
- Ensembl-cache provenance: `7cba971c…` → date rebind
  `78e7ab9faeaf84f9b0a5d73a44058762a2722ac7dd9d67d47971a0b8a422df7b`
  → path-portable rebind
  `d78cbf2df4110fcc9cb5765e7b59b71d040e16f5bd2b6d7dc20316691d361a1a`
- Reactome raw ZIP:
  `8c1dbc8578431da5d2d5118262718c60b553a9be3398e93658daa069e4a9afd4`
- Reactome extracted GMT:
  `89983d5c1f0af11c52edfeee7323eb425580ac6281d387a528562ab1787ce56b`
- Reactome pathway mapping:
  `f6d7a2bf89b5bcfe0250a0bc7f51bff94641447911712b8ff129f5b55e52df3a`
- Reactome canonical GMT:
  `1bb4433fd069cbbbf8ea8308f4bcfc05c1258378866a90d1ff30ad15e2d17100`
- Reactome Ensembl bundle:
  `81cf184f9c2697236c8bbc1b445ce8b28ecf17ca90a2f0aafe709d3028a36469`
- GO-BP Ensembl bundle:
  `4f8b124432e9c1f75f4780b233bd55a29b04150e36d71e04d183d85e5914d2a6`

The final Ensembl provenance records only `reactome_ensembl.genesets.json` and
`go_bp_ensembl.genesets.json` as relative lane paths. Its portability amendment changes
provenance bytes only: both bundle hashes, both crosswalk projections, the effect
universe, target universe, mapping-loss records and canonical hashes are unchanged.

The official Reactome home page stated that V97 was released on 30 June 2026 when
checked on 2026-07-13; the V97 news page labels its record “Created: 23 June 2026.” The
official license page assigns Reactome database data and data-derived files to CC0 1.0.

## Verification results

```text
release/test_release_hygiene.py
12 passed

Stage-1 protected baseline
PROTECTED BASELINE: OK (all protected artifacts byte-identical)

Stage-1 analysis
131 passed
PROVENANCE VERIFIER: PASS (53/53)
T8 VERIFIER: PASS

Stage-1 served-data and browser contracts
40,000-cell reproduce verifier: OK
12 browser/loader cases passed

Repository Stage-2 regression
34 passed, 4 skipped

Current Stage-2 pathway/gene-set regression against the amended external cache
218 passed

External cache byte/provenance checks
CACHE PROVENANCE: PASS
ENSEMBL CACHE PORTABILITY: PASS
old/current scientific pin projection: IDENTICAL
```

The pathway/gene-set result above is bound to the clean remote Stage-2 worktree at
`4ffe853120664296c1e6387f12f31a9516f1436e` and this exact invocation:

```text
test "$(git rev-parse HEAD)" = 4ffe853120664296c1e6387f12f31a9516f1436e
cd "$(git rev-parse --show-toplevel)/02_geneskew"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=analysis python3 -m pytest -q \
  -p no:cacheprovider \
  tests/direct/test_geneset_rekey.py \
  tests/direct/test_geneset_license.py \
  tests/direct/test_universe_binding.py \
  tests/direct/test_pathway.py \
  tests/direct/test_pathway_coverage_verifier.py \
  tests/direct/test_pathway_evidence.py \
  tests/direct/test_run_pathway.py \
  tests/direct/test_run_pathway_arms.py

........................................................................ [ 33%]
........................................................................ [ 66%]
........................................................................ [ 99%]
..                                                                       [100%]
218 passed in 22.44s
```

Four end-to-end mutations were then applied to disposable worktrees at the repaired
scanner commit. Every attack failed closed:

```text
active executable path + matching allowlist row
  FAIL: release-policy raw hash mismatch
  FAIL: exception outside permitted immutable class

credential-shaped value in the allowlist
  FAIL: hugging_face_token in release/machine_path_allowlist.json

bare RFC1918 address in deploy/serve_static.py
  FAIL: unallowlisted machine-specific line

false v3-public-on-Hugging-Face claim in root README
  FAIL: affirmative public-state claim contradicts the external-artifact manifest
```

The legacy large-file inventory remains exact. `CITATION.cff` parses as YAML. The final
Git diff passes `git diff --check`.

## Primary provider records checked

- Reactome release state: <https://reactome.org/>
- Reactome V97 news record: <https://reactome.org/about/news/295-v97-released>
- Reactome license: <https://reactome.org/license>
- openFDA terms: <https://open.fda.gov/terms/>
- FDA FAERS overview: <https://www.fda.gov/drugs/surveillance/fda-adverse-event-reporting-system-faers>
- ClinicalTrials.gov terms: <https://clinicaltrials.gov/about-site/terms-conditions>
