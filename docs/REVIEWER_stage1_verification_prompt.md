# External-reviewer prompt — spot Stage-1 CD4 transcriptional-program workbench

_Hand this to an independent senior computational immunologist / single-cell methods reviewer
who did **not** build the artifact. Grounded in branch `stage1-remediation`, PR #16. Current as of
the 2026-07-11 provenance + display remediation pass._

---

You are an independent senior computational immunologist and a scientific-integrity code reviewer.
Your job is to **adversarially verify** spot's Stage-1 workbench — not to improve it. Assume every
displayed number is guilty until traced to a named source + method + hash. Report anything false,
overclaimed, unprovenanced, or internally inconsistent. Where it's correct, say so plainly.

## What Stage-1 is
A continuous **RNA program-compatibility** viewer over ~396,000 non-targeting-control CD4 T cells
from the Marson genome-scale CRISPRi Perturb-seq (4 donors × Rest / Stim8hr / Stim48hr; public via
the CZI Virtual Cells Platform, mirrored to Hugging Face at a pinned, SHA-verified revision). Each
cell carries continuous `score_genes` panel-minus-expression-bin-matched-control scores for 12
programs. **No categorical cell-type/fate calls, no p/q/FDR, no prevalence.** A 40,000-cell display
overlay drives the UMAP.

## Access
- **Repo / branch / PR:** github.com/Kirit-Singh/spot — `stage1-remediation`, PR #16.
- **Live workbench:** http://100.117.50.59:8347/ (served by the hardened `deploy/serve_static.py`,
  GET/HEAD-only allowlist; the old `serve.py` with `POST /rerun` is retired).
- **Key files:** `01_programs/app/01_page.html` (app), `01_programs/app/01_notebook.html` (methods
  report), `01_programs/analysis/stage1_pipeline.py` (pipeline), `.../verify_reproduce.py` (the gate),
  `01_programs/app/data/stage01_program_registry.json` (frozen registry), `docs/HANDOVER.md`.

## Frozen identifiers to re-derive independently
- `canonical_table_sha256` = `6e1665d13eab1781407b43d232d089fb5fb6a6b9df5acd83cbbfb8fe3aed2755`
- `barcode_set_sha256` = `1224312e52231f4b2e07c192b39c6f9c69dd6e2d5b8bd64d936c17a9b2435a93` (n = 40,000)
- `registry_sha256` = `1ac9f6b2c3a738e0f44119add5c4f72f61225372fedb3fa6dd8d5f6ae19e95fa`
- HF source `KiritSingh/spot-CD4-Marson` @ `e5fcf98b…`; `ntc_clustered.h5ad` SHA-256 `2edc6d31…`.

## What to verify (be adversarial)
1. **Continuous-score design is intact.** No forced categorical labels, no argmax/winner-take-all,
   no p/q/FDR anywhere in the scoring path. Confirm the prior permutation "null" is removed and
   documented as mislabeled, not silently dropped.
2. **Provenance of the gene panels.** Masopust et al. (*Guidelines for T cell nomenclature*, Nat Rev
   Immunol 2026;26:298-313) is a **naming consensus**, NOT a gene-panel source. Confirm that nowhere
   in the app, notebook, script, registry, README, or HANDOVER are the panels attributed to a
   Masopust table/figure or called a "panel source." The panels must be presented as **curated
   canonical markers** restricted to genes measurable in this probe-based (10x Flex) dataset. Flag
   any residual attribution drift. (This was remediated on 2026-07-11 — pressure-test it.)
3. **The exact frozen control genes.** For each program, confirm the registry's `control_genes`
   match a fresh `score_genes` control draw at `SEED=12345` (25 bins, ctrl_size 50), and that the
   panels shown in the UI equal `panel_genes` in the registry (no UI gene outside the frozen panel).
4. **"Programs over time" grid.** It must show the **median continuous score per timepoint**
   (Rest/8h/48h), shaded within each program's own range, with the definition on screen. Confirm it
   does **not** threshold cells, count a "% high," or otherwise smuggle in a prevalence/categorical
   claim. Recompute a couple of medians from the overlay and check them against the displayed values.
5. **Labels don't overclaim.** `Checkpoint-high` (not `Checkpoint+`); the modular-definition column
   reads `checkpoint-associated` / `cytotoxic-like` (RNA compatibility does not demonstrate
   exhaustion or cytotoxicity); Th9 is correctly degenerate ("Too sparse to shade", `stage2_selectable=false`
   — IL9/SPI1 absent). The Treg-like program is a candidate transcriptional program, not a confirmed
   Treg identity.
6. **The reproducibility gate is real.** Run `cd 01_programs/app && python3 ../analysis/verify_reproduce.py`;
   it must re-derive `6e1665d1` / `1224312e`, enforce the cell-key whitelist, forbid `p_value/q_value/
   fdr/perm/null` key substrings, and scan served artifacts for retired categorical strings. Run
   `pytest` in `01_programs/analysis/` (expect green). Optionally run the full `reproduce.sh` from the
   pinned HF revision on a scanpy host and confirm the emitted overlay reproduces the frozen hashes.
7. **Server posture.** Try to break the allowlist: source, scripts, logs, and `/rerun` must return
   404/405; app + data return 200. The in-app "Regenerate overlay" affordance must only reveal/copy
   the offline `reproduce.sh` command — it must not trigger any server-side execution.
8. **Every displayed number traces.** Walk the Methods & provenance panel and the map/pills/grid;
   report any figure, label, or citation that does not trace to a named source + method + hash.

## Deliverable
A prioritized findings list (blocker / important / minor / nit): file:line or on-screen anchor, the
exact quoted text, why it violates the rules above, and a concrete fix. End with a short "verified
correct" list — especially the hash re-derivations, the Masopust naming-consensus provenance, and the
continuous / no-prevalence / no-p-q design. Re-derive or challenge any number you rely on.
