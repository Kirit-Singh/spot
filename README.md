# spot

Carry a scientific finding across datasets. **spot** takes a hit discovered in one dataset and confirms or refutes it in independent public datasets, then renders the result as an interactive evidence graph — every edge **typed** (replication / consistency / genetic), **weighted** by strength, and **click-through** to the real statistic and the code that produced it. Biology's missing layer is cross-dataset replication; spot makes it visible.

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
- **Lane A — Evidence Graph:** `core/` deterministic engine · `api/` FastAPI · `frontend/` React+Cytoscape · `worker/` GPU jobs · `agent/` optional Claude adapter.
- **Lane B — Predictive Modeling:** `modeling/` training loops (identify perturbation hot spots / favorable pathways).

Conventions in `CLAUDE.md`; full design in `docs/superpowers/specs/`; origin brief in `docs/brief.md`.

## Data
Built on public datasets (Marson CD4+ T cell Perturb-seq, CZ CELLxGENE Census, Open Targets). No data is bundled in this repo.

## License
MIT
