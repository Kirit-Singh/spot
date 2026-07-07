# spot — Design Spec

**Date:** 2026-07-07 · **Status:** approved design, pre-implementation

## 1. What we're building
`spot` is a hosted web product that carries a scientific finding across datasets. It takes a **hit** discovered in one dataset and **confirms or refutes it in independent public datasets**, rendering the result as an interactive **evidence graph**: every edge is **typed** (replication / consistency / genetic), **weighted** by strength, and **click-through** to the real statistic and the exact code that produced it. Biology's missing layer is cross-dataset replication; `spot` makes it visible.

Seeded from the "Built with Claude: Life Sciences" hackathon (Marson CD4+ T cell Perturb-seq), but designed for long-term use. Full origin brief: `docs/brief.md`.

## 2. Goals & non-goals
**Goals**
- Trustworthy, reproducible confirmation of a finding across ≥2 independent public datasets.
- A beautiful, live-resolving evidence graph as the primary UI.
- A deterministic core that never invents a statistic.
- Long-lived, transferable, uniform-environment codebase.

**Non-goals (for now)**
- Generic support for every finding / every dataset. Build one gorgeous vertical thread; the architecture is the argument for generality.
- Cloud hosting on day one (homelab + localhost first).
- Proprietary or access-restricted data.

## 3. Architecture
Service-split, deterministic-core design:
- **core/** — the deterministic engine (`spot_core`). Sub-packages: `data` (loaders, lazy/stream), `evidence` (verification brain, per-edge scoring, verdict objects), `confirm` (Census / Open Targets / GEO adapters), `graph` (node/edge/provenance assembly). No LLM, no network at import. `core` never imports from `api`/`worker`/`agent`.
- **api/** — FastAPI service. REST for queries; websocket to stream edges as they resolve. Calls `core`.
- **worker/** — GPU-capable job runner; deployable to tcefold. Calls `core`. Stub now; real when async lands.
- **agent/** — optional, feature-flagged Claude adapter for long-tail dataset ingestion (e.g. bespoke GEO parsers). The only place an LLM runs at runtime.
- **frontend/** — React + Vite + TypeScript + Tailwind + Cytoscape.js.
- **deploy/** — docker-compose, Dockerfiles, host configs.

**Data flow:** hit → confirm adapters pull real stats from independent datasets → evidence/verification brain grades each candidate edge (adversarial falsification) → survivors become typed+weighted edges → graph assembly → api streams to frontend → user clicks an edge to see the statistic + code + methods sentence.

## 4. Infrastructure & environments
Host specifics live in tracked `infra.env`; CLAUDE.md stays lean and points to it.
- **tcedirector** — dev + web/API + orchestration. Ubuntu 24.04, py3.12, docker+compose, node22, NFS dataset mount live, 1.4 TB NVMe scratch, 31 GB RAM, weak GPU. Develop here in tmux; Mac is a thin SSH client.
- **tcefold** — GPU workhorse (24c / 91 GB / 3× RTX 3090). "Scale to CUDA/GPU" target. Dataset NOT yet mounted there — a tracked task.
- **tcenas** — `192.168.68.69:/volume1/datasets` (NFS); source of the data. Never a live-run dependency.
- **tcespark** — LLM inference (DeepSeek); frequently asleep.

**Uniform environment:** Python 3.12, Node 22, pinned everywhere. **The Docker image IS the environment** — dev, CI, and prod run the same image. Python deps hash-locked via pip-tools (`requirements.in` → `requirements.lock`); frontend via `package-lock.json`. Homelab-first; `localhost` via `docker compose` to start; hybrid cloud possible later.

## 5. Repo layout
```
spot/
├─ core/        # deterministic engine (spot_core: data·evidence·confirm·graph) + tests
├─ api/         # FastAPI (REST + websocket) + tests
├─ worker/      # GPU job runner → tcefold (stub)
├─ agent/       # optional feature-flagged Claude adapter (stub)
├─ frontend/    # React + Vite + TS + Tailwind + Cytoscape.js
├─ deploy/      # docker-compose.yml, Dockerfiles, host configs
├─ loops/       # transferable build→verify + runtime loop recipes (Workflow/sub-agent based)
├─ skills/      # composable verified routines loops call (pseudobulk-DE, donor-consistency, …)
├─ docs/        # brief.md + superpowers/specs/
├─ .github/workflows/ci.yml
├─ CLAUDE.md · README.md · infra.env · LICENSE(MIT) · .gitignore · justfile
```

## 6. Engineering conventions
- **Small, single-purpose modules. ≤500 lines/file — hard CI fail**, with a per-file opt-out comment (+reason) for rare exceptions. Excluded: lockfiles, generated code, migrations, vendored assets.
- **Testing policy.** Must-test: deterministic logic (scoring, verdicts, edge weighting, graph assembly, parsers, gene-ID/ontology harmonization). Smoke-test-or-skip: thin IO/glue/adapters. Every bugfix ships a regression test that failed before the fix.
- **Efficiency.** Vectorize (no Python loops over cells/genes). Never hold a full cohort in memory — lazy-load/stream (TileDB-SOMA, lazy zarr). Avoid array copies. Cache expensive deterministic results. Measure before optimizing.
- **Boundaries.** Each service independently testable via a clear interface; `core` is pure/deterministic and never imports upward.

## 7. Loops (generator ≠ evaluator)
Loop engineering (Boris Cherny): small loops, each with a **cheap objective success metric**, that ratchet quality upward. The agent that produces work and the agent that checks it are **different**, with different instructions.
- **Dev-time build→verify loop.** Builder agent writes a small module + tests → separate verifier agent runs `ruff`/`mypy`/`pytest` + the ≤500-line and convention checks and returns `{pass, reasons}` → re-prompt until green or budget exhausted → report; recurring lessons promoted to CLAUDE.md.
- **Runtime confirmation loop (same shape).** Generator = "propose a hit"; evaluator = the verification brain that adversarially tries to falsify it (donor consistency · context specificity · guide-efficiency · effect-vs-noise). Only survivors earn edges. Fan-out over the 33,983 perturbation pairs = parallel sub-loops → hit cards → synthesized graph.
- **Implementation.** Built with the **native Workflow / sub-agent primitives** (portable across machines), not homelab shell scripts. Recipes live in `loops/`; verified routines in `skills/`.

## 8. CI/CD
GitHub-hosted runners now; self-hosted runner (tcedirector/tcefold) later for data/GPU integration tests. Granular, per-concern named jobs:
- `Backend: Lint` (ruff check + ruff format --check) · `Backend: Type Check` (mypy, **non-blocking** to start) · `Backend: Test` (pytest)
- `Frontend: Lint` · `Frontend: Type Check` · `Frontend: Build` · `Frontend: Test`
- `File Size` (≤500-line enforcement) · `ShellCheck`
Triggers: push + pull_request to `main`.

## 9. Data handling & scientific invariants
- Work off the **small precomputed files copied to local NVMe scratch**; never depend on the NFS mount in a live/recorded run.
- **Never invent a statistic** — deterministic tools only (scanpy / pyDESeq2 / decoupler / Census).
- **Type + weight every edge**; never present consistency-level evidence as replication.
- **Adversarially falsify** before an edge lights up.
- **Public data + MIT only.** Everything reproducible from public sources + this repo.

## 10. Build sequence (each a stop-and-show)
1. Scaffold repo on tcedirector: CLAUDE.md, README.md, infra.env, docs/brief.md, .gitignore, justfile, MIT LICENSE.
2. CI green on an empty `core` + `frontend` (lint/type/test/build/file-size/shellcheck all pass).
3. `docker compose up` with postgres + redis + api(hello) + frontend(hello) on localhost.
4. First `core` primitive built via the dev build→verify loop (e.g. donor-consistency), with tests.
5. Tier-1 confirmation edges (CELLxGENE Census + Open Targets) → one confirmed vertical rendered on the graph.
6. Live GEO edge via the agent adapter. Then GBM cross-disease stretch edge.

## 11. Open items / decisions pending
- ~~LICENSE: Apache-2.0 -> MIT~~ RESOLVED 2026-07-07: swapped to MIT (Copyright 2026 Kirit Singh).
- Choose the exact localhost port for the frontend/api.
- Decide when to mount the dataset on tcefold for GPU work.
- Remove the stale inactive `SWOOPPMAIN` gh account from tcedirector? (optional cleanup)

## 12. Optional ML / training modality (Sparks) — future, NOT core
Infra: **2× DGX Spark** (GB10 Grace-Blackwell, ~128 GB unified each; `tcespark` + `tcespark2`), currently tensor-parallel **serving DeepSeek-V4-Flash** (shared inference backend for other loops). Capable of LoRA/fine-tune/small-model training, not large-scale pretraining. No dataset NFS mount (stage data); SSH owned by SWOOPPMAIN.

Training is **optional and never part of the deterministic core.** If used it powers a distinct `evidence_type = predictive/model`, clearly typed and **weighted below experimental replication, never presented as replication**; every model carries held-out validation provenance (seed, pinned splits, metrics -> outputs/, versioned artifact in /mnt/tcenas/models). Candidate uses: (a) sequence->regulatory-activity predictor (adds a modality edge); (b) learned context-matching recommender (suggests datasets to confirm in); (c) LoRA-fine-tuned small model to self-host the agent adapter vs Claude API.

Loop fit: train -> eval on held-out metric -> adjust -> repeat until plateau. generator!=evaluator = trainer produces checkpoint; a SEPARATE eval/robustness harness gates it before it can back an edge.

Constraints: Sparks are inference-busy (contention with DeepSeek serving — decide dedicate vs time-share); stage data; sort access. Placement: a `training/` concern (or worker mode), NOT in core; artifacts are external inputs to the engine like Census/Open Targets. Delivered as a later **Plan 6**; foundation plan unaffected.

Open items (added): confirm ML/training modality scope (Plan 6 vs park); decide Spark contention (dedicate vs time-share with DeepSeek serving).
