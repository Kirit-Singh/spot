# spot Foundation — Build Chunks (shared roadmap for both lanes)

> Lightweight ordered roadmap, not full TDD code. Build **one chunk at a time**:
> create -> run the metric -> commit -> review -> next. Each chunk is independently
> testable with a clear pass/fail metric. Design + lanes:
> `docs/superpowers/specs/2026-07-07-spot-design.md` (see 12 and 13).

**Conventions (every chunk):** <=500 lines/file, small single-purpose modules,
tests for deterministic logic, Python 3.12 / Node 22, pip-tools hash-locked deps,
generator != evaluator (an independent verify gate on every change).

This foundation is the **shared base for both lanes**. After it, the repo forks:
**Lane A - Evidence Graph** and **Lane B - Predictive Modeling**, each in its own
git worktree with its own roadmap + CI job group, meeting only at `contracts/`.

- [x] **Chunk 0 - bootstrap** (DONE): repo on tcedirector `~/projects/spot`, MIT LICENSE, spec + roadmap committed.
- [ ] **Chunk 1 - repo meta & docs**: `CLAUDE.md` (lean), `README.md`, `infra.env` (tracked, non-secret), `.gitignore`, `docs/brief.md`, `justfile` skeleton. **Metric:** files present; `just --list` runs.
- [ ] **Chunk 2 - Python workspace + core skeleton**: `requirements.in`/`.lock` (pip-tools), `pyproject.toml` + ruff/mypy config, `core/src/spot_core/__init__.py`, `core/tests/test_smoke.py`. **Metric:** `pytest core` green; `ruff check` clean; `mypy core` runs.
- [ ] **Chunk 3 - contracts/ seam**: standalone `contracts/` package (`spot_contracts`) with the `Hit` + `Evidence/Edge` pydantic schemas both lanes agree on, + tests (deterministic logic -> must test). **Metric:** `pytest contracts` green; schema round-trips (serialize/validate).
- [ ] **Chunk 4 - file-size guard**: `scripts/check_file_size.py` (<=500 lines + per-file opt-out comment) + tests. **Metric:** passes on repo; fails on a synthetic 501-line file.
- [ ] **Chunk 5 - api /health**: `api/src/spot_api/main.py` (FastAPI + `/health`) + `api/tests/test_health.py`. **Metric:** `pytest api` green; `uvicorn` serves `GET /health` -> 200.
- [ ] **Chunk 6 - frontend skeleton**: `frontend/` React+Vite+TS+Tailwind, `App.tsx` + a vitest component test. **Metric:** `npm test`, `tsc --noEmit`, `npm run build`, eslint all green.
- [ ] **Chunk 7 - containerize + compose**: `deploy/` backend Dockerfile, frontend Dockerfile, `docker-compose.yml` (postgres, redis, api, frontend). **Metric:** `docker compose up` boots; api `/health` reachable; frontend served on localhost.
- [ ] **Chunk 8 - CI workflow**: `.github/workflows/ci.yml` - `Backend: Lint` / `Type Check` (non-blocking) / `Test`, `Frontend: Lint` / `Type Check` / `Build` / `Test`, `File Size`, `ShellCheck`. **Metric:** push -> all jobs green.
- [ ] **Chunk 9 - justfile wiring**: real `up`/`down`/`lint`/`fmt`/`typecheck`/`test` targets across services. **Metric:** `just lint` + `just test` run all services green.

**FORK POINT ->** create two worktrees, each with its own roadmap:
- **Lane A roadmap**: core discovery -> Tier-1 confirmation edges (Census + Open Targets) -> graph assembly -> frontend graph UI -> agent adapter (live GEO) -> GBM stretch.
- **Lane B roadmap**: data prep -> baseline model -> training loop (Sparks: train -> eval on held-out metric -> improve) -> eval/robustness harness -> emit candidate Hits into `contracts/`.
