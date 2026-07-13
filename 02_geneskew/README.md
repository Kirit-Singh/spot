# 02_geneskew — gene levers for a Stage-1-selected program contrast

**Status:** preliminary analysis code; no production Stage-2 output is admitted or
released from this branch.

The intended interface accepts an ordered pair of Stage-1 continuous programs and an
analysis condition from the versioned Stage-1 selection contract. It projects measured
gene-knockdown effects onto the two axes while retaining the two effect arms separately;
the method is not restricted to one hard-coded Treg-like/Th1-like example. Direct,
temporal, pathway and optional secondary-support lanes require their own input manifests,
verification and release identity.

**Produces:** a ranked **gene-lever hypothesis** — a *suggestive* candidate set that **requires
external validation**, not a confirmed target. Stage-2 stops here; drug / GBM / PK / safety
evidence is Stages 3–4.

Design decisions and schemas: `STAGE2_PLAN.md`. Development code targets the authors'
released `GWCD4i.DE_stats` and related public artifacts. Those inputs and any large
cell-level matrices are not bundled by this README and are not evidence of a released
Stage-2 biological result.

- `inputs/`  — a versioned Stage-1 v3 selection contract plus pinned Marson effect inputs;
  a production run must bind their exact hashes
- `analysis/` — donor-paired axis construction, target-masked measured-effect screen,
  guide/donor replication, cell-level within-dataset support
- `outputs/` — prospective, content-addressed Direct/temporal/pathway records. No p/q/FDR
  is emitted without a separately calibrated inferential method; none is claimed here.
