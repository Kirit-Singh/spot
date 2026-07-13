# 02_geneskew — gene levers for a Stage-1 program contrast

Rank gene knockdowns by how much their **measured** transcriptional effect moves the
ordered **A → B program contrast** selected in Stage-1 — for **any** pair of continuous
programs and directions, not a fixed biological axis. Target-masked (self + off-target) and
gated on power, off-target, guide, donor-pair, and cell-level support.

**Produces:** a ranked **gene-lever hypothesis** — a *suggestive* candidate set that
**requires external validation**, not a confirmed target. Drug / brain-PK / safety evidence
is Stages 3–4.

## Origins kept separate
Levers carry a typed **origin** and are never merged across origins:
- **Direct** — a measured perturbation effect on the selected program at one condition.
- **Temporal** — a cross-condition (timepoint-to-timepoint) effect.
- **Pathway** — an inferred pathway-node lever, flagged as inferred (not a measured target).

## Inputs
- The Stage-1 **selection contract** `spot.stage01_selection.v3` (the ordered A/B poles and
  their independent per-program arms).
- The authors' released Marson `GWCD4i.DE_stats` (+ `by_guide` / `by_donors`); the Stim48
  `assigned_guide` files for cell-level support (~1.7 TB, I/O-bound; not bundled).

## Outputs
Organized by immutable contrast identity: a signed program vector, the ranked gated levers
(p/q **only if calibrated**), and the within-dataset cell-level support verdict. Each records
its provenance. **GO enrichment and essentiality annotation are unresolved** (`STAGE2_PLAN.md`
§17) — to be either fully specified and pinned, or omitted; never merely promised.

## Reproduce
Runs from `analysis/` as a Claude Science specialist (perturbation genomics):
```bash
cd 02_geneskew/analysis
python -m direct.run_screen        # target-masked measured-effect screen
python -m perturb2state.run_p2s    # perturbation → state signature
```
Deterministic logic is covered by `02_geneskew/tests/`.

## Provenance & history
Design decisions and schemas: `STAGE2_PLAN.md`. Review rounds, the temporal exploration, and
the independent Claude Science reviews are catalogued in `docs/history/`.
