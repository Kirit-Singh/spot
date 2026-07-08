# spot

Carry a scientific finding across datasets. **spot** takes a hit discovered in one dataset and confirms or refutes it in independent public datasets, then renders the result as an interactive evidence graph — every edge **typed** (replication / consistency / genetic / predictive), **weighted** by strength, and **click-through** to the real statistic and the code that produced it.

Two ideas drive it:

- **Make the plumbing easier, to expedite discovery.** Carrying a finding across datasets is mostly plumbing — harmonizing gene IDs and ontologies, pulling the right statistics, matching context, tracking provenance. spot automates that plumbing so researchers spend their time on the science, not the glue. Biology's missing layer is cross-dataset replication; spot makes it visible.
- **Loops that refine, not one-shot answers.** Every claim runs through a small generator ≠ evaluator loop: it is proposed, then adversarially tested before it earns an edge. The same pattern refines the tool itself — concepts are continually sharpened rather than asserted once.

**Status:** early WIP · **MIT** licensed

## Quickstart
Requires Docker (+ Compose).
```
git clone https://github.com/Kirit-Singh/spot && cd spot
just up      # postgres, redis, api, frontend on localhost
just test    # run the suite
```

## Architecture
Service-split monorepo, two lanes sharing a `contracts/` seam:
- **Lane A — Evidence Graph:** `core/` deterministic engine · `api/` FastAPI · `frontend/` React + Cytoscape · `worker/` GPU jobs · `agent/` optional Claude adapter.
- **Lane B — Predictive Modeling:** `modeling/` training loops (identify perturbation hot spots / favorable pathways).

Conventions in `CLAUDE.md`; full design in `docs/superpowers/specs/`; frontend design in `docs/frontend-design.md`; origin brief in `docs/brief.md`.

## Data
Built on public datasets (Marson CD4+ T cell Perturb-seq, CZ CELLxGENE Census, Open Targets). No data is bundled in this repo.

## License
MIT
