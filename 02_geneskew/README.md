# 02_geneskew — gene levers for a Stage-1-selected program contrast

Rank gene knockdowns by how much their **measured** transcriptional effect aligns with an
ordered **A→B program contrast** selected in Stage-1 (**same-timepoint at Stim48**: A =
activation-induced FOXP3⁺ **regulatory-like** program, B = inflammatory **Th1-like** program).
Because B may be sparse and is unmeasurable from the release, the **primary endpoint is the
one-sided A-program (regulatory-like) reduction (`a_down`)**; `b_up` / total A→B alignment are
secondary/descriptive until B is measured. Target-masked (self + off-target), and gated on
power, off-target, guide, donor-pair, and cell-level support.

**Produces:** a ranked **gene-lever hypothesis** — a *suggestive* candidate set that **requires
external validation**, not a confirmed target. Stage-2 stops here; drug / GBM / PK / safety
evidence is Stages 3–4.

Design decisions and schemas: `STAGE2_PLAN.md`. Runs as a Claude Science **specialist**
(perturbation genomics) over the authors' released `GWCD4i.DE_stats` (+ `by_guide` / `by_donors`),
and — for cell-level support — the Stim48 `assigned_guide` files (~1.7 TB, I/O-bound).

- `inputs/`  — the Stage-1 **selection contract** `stage01_selection.json` (an *unimplemented
  prerequisite* — the current picker serializes nothing); Marson `DE_stats` / `by_guide` /
  `by_donors`
- `analysis/` — donor-paired axis construction, target-masked measured-effect screen,
  guide/donor replication, cell-level within-dataset support
- `outputs/` (organized by immutable `contrast_id`) — `stage02_programs` (signed program vector) ·
  `stage02_screen` (ranked, gated levers; p/q **only if calibrated**) · `stage02_cell_support`
  (within-dataset support verdict). **GO enrichment and essentiality annotation are unresolved**
  (STAGE2_PLAN §17) — to be either fully specified + pinned or omitted, never merely promised.
