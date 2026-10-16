# Marson paper concordance — cytokine sign-control lane (diagnostic, NON-RANKING, NON-GATING)

A separate diagnostic lane that re-derives the **Results-section cytokine sign controls** of
Zhu R., Dann E. et al. (2025), bioRxiv `10.64898/2025.12.23.696273` (v1, CC-BY 4.0), directly
from the **primary preprint** (`2025.12.23.696273v1.full.pdf`, Results **p8–9**, Figures
2A–D + Suppl. Fig 10) and the **pinned public DE object** (`GWCD4i.DE_stats.h5ad`, sha256
`c355f535…cfbb62`) at authors' code commit `848d62f`. **No secondary summary; no invented
citation** — every control carries its exact page/figure and verbatim quote.

**This lane never ranks, gates, or alters any production output, and never claims exact
replication.** spot's production estimand (a per-program base-delta over the reusable-arm
system) differs from the paper's per-cytokine DESeq2 knockdown effects; this lane only checks
the paper's reported **sign** at a significant condition.

## Sign convention (p9, verbatim)
Readout = the cytokine's log2FC on regulator **knockdown** (CRISPRi), from the `log_fc` layer
at (perturbation row `{ENSG}_{condition}`, cytokine column).
- **negative regulator** ⇒ knockdown log2FC **> 0** (KD raises the cytokine)
- **positive regulator** ⇒ knockdown log2FC **< 0** (KD lowers the cytokine)

## Controls (all p9)
- **Broad**: TCR / Mediator (MED12, MED24) / SAGA (TAF6L, TADA1, TADA2B, SUPT20H, USP22) →
  control a *large set* of cytokines, stimulation-specific (incl. TNF, IL-16) [Fig 2A-B].
- **IL2 / IL13** (after re-stimulation): CD3(D/E/G), LCP2 → IL2 (positive); GATA3 → IL13
  (positive) [Fig 2A].
- **IL10**: MEN1 (negative) [Fig 2C]; SAGA (SGF29, ATXN7L3, USP22) + ELOB (negative) [Fig 2D].
- **IL21**: CYB5R4 (positive); calcium (ATP2A2, ORAI1) + Elongator (ELP2, ELP3) (negative)
  [Fig 2C-D].
- **Divergent**: NFKB2, KDM1A — positive for IL10 **but** negative for IL21 [Fig 2C-D].

## Real-run result (pinned DE object, `de_sha_matches_pin: true`)
- **10 / 10 directional sign controls concordant** at a significant condition (Stim8hr /
  Stim48hr — matching the paper's "after re-stimulation"); 0 discordant.
- **Broad-effect confirmed**: 6/7 Mediator/SAGA regulators significantly affect ≥5 of the 15
  paper-named cytokines (MED24 / TADA1 / TADA2B each 9).

## Files
- `sign_controls_spec.json` — frozen spec: every control + exact page/figure/quote, the sign
  convention, input pins, and the `provenance_diagnostics_policy` + `tissue_organ_axis` notes.
- `sign_derivation.py` — deterministic core (pure over an abstract DE `observe`; no HDF5).
- `de_accessor.py` — thin h5py accessor over the pinned object (IO glue; backed reads).
- `run_sign_controls.py` — CLI; fail-closed on DE hash; emits `sign_control_report.json`.
- `compare_stage2.py` — **descriptive, non-gating** overlay of the eventual Stage-2
  targets/pathways vs the control regulators (records overlap only; asserts no directional
  equivalence; no rank change).
- `tests/` — 12 tests over synthetic fixtures (no HDF5) incl. sign semantics, divergence,
  broad-effect count, provenance confinement, no-ranking, and the panel-wiring regression.

## Firewalls
- **Upstream FDR** (`adj_p_value`, `p_value`) is `authors_reported_upstream` and lives ONLY in
  each observation's `provenance_diagnostics` block (`used_for_gating_or_ranking: false`) —
  never a top-level field, never a rank/gate input, never a production output.
- **No tissue/organ axis**: this is a CD4+ T-cell blood/immune-cell in-vitro assay with donor
  × condition × perturbation axes only. The HPA tissue annotation (Suppl. Fig 13) is external
  gene-cluster annotation, not a Marson tissue measurement, and is out of scope here.

## Run
```
python run_sign_controls.py \
  --de <GWCD4i.DE_stats.h5ad> --spec sign_controls_spec.json --out sign_control_report.json
```
Post-run: compare to a Stage-2 output with `compare_stage2.compare_to_stage2(spec, rows)` —
descriptive only, never gating.
