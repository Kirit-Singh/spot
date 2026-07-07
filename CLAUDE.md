# CLAUDE.md

**spot** — a cross-dataset evidence graph: take a hit found in one dataset, confirm or refute it in independent public datasets, rendered as an interactive **typed + weighted** graph where every edge is click-through to the real statistic and the code that made it. Full brief: `docs/brief.md`. Design: `docs/superpowers/specs/2026-07-07-spot-design.md`.

## Infra
Host names, paths, and ports live in **`infra.env`** (tracked, non-secret). Dev happens on the dev host in tmux; the Mac is a thin SSH client. GPU work targets the GPU host; the DGX Sparks are an optional training modality (Lane B). The NAS dataset mount is never a live-run dependency.

## Data rules
- Copy the small precomputed files (`infra.env` → `SPOT_DATASET_DIR`) to local scratch; never depend on the NFS mount in a live/recorded run.
- **Never invent a statistic** — every number comes from a deterministic tool (scanpy / pyDESeq2 / decoupler / Census).
- **Type + weight every edge** (replication / consistency / genetic / predictive); never present consistency as replication.
- **Adversarially falsify** a hit (donor consistency · context specificity · guide-efficiency · effect-vs-noise) before its edge lights up.

## Engineering conventions
- Small modules, one purpose each. **≤500 lines/file — CI-enforced** (per-file opt-out comment w/ reason; lockfiles/generated/migrations excluded).
- **`core/` is deterministic + importable** — no LLM, no network at import; never imports from `api`/`worker`/`agent`. Claude lives only in `agent/`, feature-flagged.
- **Tests:** deterministic logic (scoring, verdicts, edge weighting, graph assembly, parsers, gene-ID/ontology harmonization) must have tests; thin IO/glue smoke-or-skip; every bugfix ships a regression test.
- **Efficiency:** vectorize (no Python loops over cells/genes); never hold a full cohort in memory — lazy-load/stream; avoid array copies; cache deterministic results; measure before optimizing.
- **Uniform env:** Python 3.12, Node 22, pinned everywhere. **The Docker image is the environment** (dev/CI/prod identical). Deps hash-locked via pip-tools (`requirements/*.in` → `requirements/*.lock`); frontend via `package-lock.json`.
- **Build small chunk by small chunk:** bite-sized TDD tasks, each green (`ruff`/`mypy`/`pytest`) before commit. **generator ≠ evaluator:** an independent verify gate on every change and every confirmation.

## Lanes
**Lane A — Evidence Graph** (`core api frontend worker agent`) and **Lane B — Predictive Modeling** (`modeling`, training loops on the Sparks; Claude Science for reasoning) share a foundation and meet only at the **`contracts/`** package (`Hit` + `Evidence/Edge`). See spec §12–13.

## File & folder hygiene
- **Minimal files:** add a file only when working code absolutely requires it — never speculatively or "for later."
- **Simple, clean folders:** keep the tree flat and obvious; avoid deep nesting and one-file folders without cause.
- **Explain before reorganizing:** when adding, moving, splitting, or renaming files/folders, say what and why first and get a nod — don't restructure silently.

## Dev commands (`just`)
`just up` / `just down` · `just lint` · `just fmt` · `just typecheck` · `just test` (add a service name to scope, e.g. `just test core`).

## Layout
`core/` engine (`spot_core`: data·evidence·confirm·graph) · `api/` FastAPI · `worker/` GPU jobs · `agent/` Claude adapter (flagged) · `frontend/` React+Vite+TS+Tailwind+Cytoscape · `contracts/` shared Hit/Evidence schema · `modeling/` Lane B · `deploy/` compose+Dockerfiles · `loops/` + `skills/` loop recipes · `docs/` brief+specs.
