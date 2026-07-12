# spot — external reviewer handover (Stages 1–2 complete)

_Prepared 2026-07-11 by the lead implementation agent. This pack lets an independent
reviewer check accuracy end-to-end. Scope of this handover: **Stage 1 fully built +
live, Stage 2 (direct primary screen + Perturb2State secondary) complete + verified.**
Stages 3 (drug link) and 4 (PK/PD) are **not yet built** — see "Not evaluated / not built"._

## Links
- **Repo / PR:** github.com/Kirit-Singh/spot — branch `stage1-remediation`, **PR #16**
  (https://github.com/Kirit-Singh/spot/pull/16). Head commit `9e5ced2`.
- **Live workbench:** http://100.117.50.59:8347/ (Stage-1 CD4 UMAP). Served by the
  hardened `deploy/serve_static.py`; the previous unsafe `serve.py` is retired.
- **Assignment (verbatim):** `docs/spot_buildout_plan.md`. **Shared schemas:** `schemas/README.md`.

## What is done (by wave)
| Wave | Commit | Summary |
|---|---|---|
| Wave 0 — live-server security | `0e8b561` | Replaced `serve.py` (exposed source + unauthenticated `POST /rerun` running the withdrawn permutation-FDR pipeline) with a GET/HEAD-only allowlist server. `deploy/smoke_test.sh` asserts source/scripts/logs/`/rerun` → 404/405, app+data → 200. |
| Stage-1 viewer + registry | `50a107f`,`2e787bc` | UMAP pan/zoom/top-anchor; sensitivity option removed (UI). Program registry §4.4 with **exact frozen `score_genes` control genes** + Ensembl (honest `null` for genes absent from the effect universe), coverage, Th9 `stage2_selectable=false` (IL9+SPI1 absent). |
| Stage-1 display §4.1/4.2/4.7 | `7af314b` | Sparse-aware transform (Th9 no longer maps 24,523 zeros to max intensity → renders degenerate/neutral); **continuous bivariate A/B render** (removed winner-take-all); doctype/lang/viewport/favicon/a11y; inert rerun client removed. |
| Shared schemas §11 | `a8a5066` | `spot.stage01_selection.v1` `contrast_id` recipe (canonical scientific content only). |
| Stage-1 selection §4.3/4.5/4.6 | `60659bf` | Display vs analysis scope separated; in-browser `contrast_id` (SubtleCrypto) reproduces `26b866f2ad813d71`; preflight rejects (A==B same dir / sensitivity axis / All-times / differing conditions / Th9 / unknown hashes); Identify-genes never implies a gene was found. |
| Stage-2 primary §5 | `2344f24` | Direct target-masked **DE-space projection** on `DE_stats.layers['log_fc']` onto the exact frozen scorers. Every target emitted with full disposition; **no p/q** (`inference_status=not_calibrated`); deterministic ranking; guide + donor-pair support; cell-level honestly stubbed (§5.7). |
| Stage-2 Perturb2State §6 | `5339b57`,`4a99fc0` | Pinned upstream `emdann/pert2state_model @2c2e3095` (MIT). Broad 396k-NTC signature (A/B panel+control excluded), masked z-score+logFC matrix, `positive=False`, LODO/config stability. **Strictly secondary** support lane; never validation/p-q; `coef_sem`=fit-variation; **direct ranks byte-identical with/without P2S**. |
| Stage-1 display + provenance remediation | `0e6981a`…`9e5ced2` | Finished the Masopust **naming-consensus** provenance (panels are curated canonical markers, not a "panel source") across app/notebook/script/README/HANDOVER. "Programs over time" grid → **median continuous score per timepoint** on a **shared absolute scale** (no threshold, no prevalence, no categorical call); activation-adjusted CD4 CTL-like **sensitivity lane surfaced** in the color-by (see Methods); Regenerate-overlay affordance reveals the offline `reproduce.sh` (no live server trigger); `Checkpoint-high`, later renamed `Checkpoint+` (user-authorized 2026-07-12; Tier-2 display-only). Independent **Claude Science** read (project "spot pipeline robustness") confirmed the engine is clean; its presentation-layer catches are actioned or logged. `verify_reproduce.py` still gates `6e1665d1`/`1224312e`; **frozen hashes untouched** (all edits display/comment/doc). New reviewer prompt: `docs/REVIEWER_stage1_verification_prompt.md`. |

## Content-addressed identifiers (all independently re-derived by the lead)
- Stage-1 `canonical_table_sha256` = `6e1665d13eab1781407b43d232d089fb5fb6a6b9df5acd83cbbfb8fe3aed2755`;
  `barcode_set_sha256` = `1224312e52231f4b2e07c192b39c6f9c69dd6e2d5b8bd64d936c17a9b2435a93`; n = 40,000.
- Stage-1 HF source: `KiritSingh/spot-CD4-Marson` @ `e5fcf98b56a9302921d402e97fc5a190bd88f9a6`;
  `ntc_clustered.h5ad` SHA-256 `2edc6d318415c8b0ee779d707ab86e26ddb6f0274db51ab4a12f21ebfda50e43`.
- `registry_sha256` = `1ac9f6b2c3a738e0f44119add5c4f72f61225372fedb3fa6dd8d5f6ae19e95fa`.
- Stage-2 `contrast_id` = `26b866f2ad813d71` (canonical `26b866f2ad813d717022d22d9ac1966f6bb35cbfda0c585d9023a0b6a8e0b42d`).
- Stage-2 mask sha = `dc3c6512b848835309bb1539c5b0670938fdb8342e572d66d55e28c0185e1b1d`;
  `screen.parquet` sha = `27341af34c5203a4ffab8cc7e309e58d63048fe7b6a1f910c5bf9ac8dc4fb03a`.
- Perturb2State `model_manifest_sha256` = `67682f8e72cd065463b37511519b5e6dae2823037101bf333d7664608ae57694`;
  upstream model commit `2c2e30959ffafadecc6af5d4d7b5bde868ab5313`.

## Tests executed (results)
- `01_programs/analysis/test_program_registry.py` — 6/6.
- `01_programs/analysis/verify_reproduce.py` — OK (schema whitelist + `6e1665d1`/`1224312e`; run by the lead against the committed + the live-served overlay).
- `01_programs/analysis/test_sparse_domain.py` — 8/8.
- `01_programs/analysis/test_selection_contract.py` — 3/3 (reproduces `26b866f2`).
- `02_geneskew/tests/` (direct) — 20 passed.
- `02_geneskew/tests/perturb2state/` — 24 passed on-host (determinism, gene/target-order invariance, intended+off-target masking, **panel/control exclusion = 0 leakage**, synthetic-contributor recovery, reversed→negative coef, shuffled→loses reconstruction, coef-SEM-not-p-value, gene-CV-not-donor-validation, ineligible-cannot-enter, **direct-rank invariance**, UI/artifact consistency).
- Live deployment smoke test — PASSED (forbidden paths 404/405, app+data 200).

## Independent verification pass (lead, did NOT generate the artifacts)
Re-derived and confirmed: Stage-1 `6e1665d1`/`1224312e` via `verify_reproduce.py`; `registry_sha256`
`1ac9f6b2` recomputes (excluding self-hash + `created_at`); `contrast_id` `26b866f2` recomputes from
canonical content; Stage-2 `screen.parquet` has **no p/q columns** and `complete_disposition=True`;
P2S support lane has **no p/q**, `role=secondary_reconstruction_support`, negative coefficients flagged
`p2s_opposed`, and `screen.parquet` is byte-unchanged with/without P2S. Per-stage `verification.json`
files are in each `outputs/<contrast_id>/` dir (gitignored, regenerable — see "Reproduce").

## Public data / sources used
- Marson (Zhu et al. 2026) genome-scale CRISPRi CD4 Perturb-seq, via **CZI Virtual Cells Platform**,
  redistributed at the pinned HF revision above. `GWCD4i.DE_stats.h5ad` (10,282-gene effect universe),
  `.by_guide.h5mu`, `.by_donors.h5mu`, sgRNA library metadata. Program **naming**: Masopust et al.,
  *Guidelines for T cell nomenclature*, Nat Rev Immunol 2026;26:298-313 (nomenclature consensus; the
  gene panels are curated canonical markers, not taken from that paper). Perturb2State:
  `emdann/pert2state_model` (MIT).
- No proprietary/account-gated data. No DrugBank/SIDER/DrugComb.

## Not evaluated / not built (honest)
- **Stage 3 (§8 drug link)** and **Stage 4 (§9 PK/PD)** — NOT built in this pass. The plan is fully
  specified; they are a large, external-public-DB-dependent effort (Open Targets/ChEMBL/PubChem/LINCS/
  GBmap/DailyMed/Drugs@FDA) and are offered as a follow-up.
- Stage-2 **cell-level support** — stubbed `screen_only` (`cell_level_extraction_deferred`, §5.7); the
  44 GB `pseudobulk_merged.h5ad` extraction was deferred. Guide + donor-pair support ARE computed.
- Stage-2 `input_manifest.upstream_code_commit` — genuinely unavailable (not distributed with the data);
  omitted rather than invented.
- P2S one-sided lanes (`away_from_A`, `toward_b`) reconstruct poorly (r2 0.076 / 0.035) — reported
  honestly; the combined lane is the informative one (r2 mean 0.686, 0.398–0.778 across LODO).
- Stage-1 landing state currently initializes to the default contrast (treg→th1); trivially revertible
  to the single-program Naïve gradient if preferred.
- `registry_sha256` uses the builder's own `_canon_bytes`; an external reviewer should re-run
  `build_program_registry.py`'s canon or `test_program_registry.py` to reconfirm.

## Reproduce
- Stage-1 scoring: `cd 01_programs/analysis && ./reproduce.sh` (pins HF rev + SHA; runs the chain;
  `verify_reproduce.py` must print `6e1665d1`).
- Stage-2 primary: `python 02_geneskew/analysis/direct/run_screen.py …` (see its `--help`); regenerates
  `02_geneskew/outputs/26b866f2ad813d71/` (parquets are gitignored).
- Perturb2State: `python 02_geneskew/analysis/perturb2state/run_p2s.py …` on a ≥16 GB host (chunked
  loader; ~20 min). Do NOT use `anndata.to_memory()` (it swap-wedges a 31 GB host).
- Deployment: `deploy/build_dist.sh` → serve via `deploy/serve_static.py` → `deploy/smoke_test.sh`.

## Reviewer prompt (suggested)
> Adversarially verify spot Stages 1–2 on branch `stage1-remediation` (PR #16). Re-derive every hash
> above from the committed code + pinned public inputs. Confirm: Stage-1 continuous-score design intact
> (no forced categorical labels, no p/q); the exact frozen control genes in the registry match a fresh
> `score_genes` control draw at SEED=12345; Th9 is correctly `stage2_selectable=false`; the Stage-2
> direct projection formula (panel-minus-control means recomputed separately after masking) matches the
> emitted `delta_A`/`delta_B`; `screen.parquet` emits every target with full disposition and NO p/q;
> the guide-specific mask (30-kb neighborhood + resolved off-targets) is correct and `neighboring_gene_KD`/
> `distal_offtarget_flag` are never used as gene identities; Perturb2State is strictly secondary
> (direct ranks byte-identical with/without it), never labelled validation, `coef_sem` never presented as
> a p-value, gene-fold CV never called donor validation, panel/control genes excluded from the readout,
> negative coefficients flagged opposed. Try to break the live server's allowlist (source/scripts/`/rerun`
> must 404/405). Report any displayed number that does not trace to a named source + method + hash.
