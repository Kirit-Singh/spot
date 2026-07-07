# spot Foundation — Build Chunks (shared roadmap for both lanes)

> Lightweight ordered roadmap, not full TDD code. Build **one chunk at a time**:
> create -> run the metric -> PR -> review/merge -> next. Each chunk is
> independently testable with a clear pass/fail metric. Design + lanes:
> `docs/superpowers/specs/2026-07-07-spot-design.md` (see 12 and 13).

**Conventions (every chunk):** <=500 lines/file, small single-purpose modules,
tests for deterministic logic, Python 3.12 / Node 22, pip-tools hash-locked deps,
generator != evaluator, **minimal files + simple/clean folders**.

Shared base for both lanes. After it the repo forks into **Lane A - Evidence
Graph** and **Lane B - Predictive Modeling**, each in its own git worktree with
its own roadmap + CI job group, meeting only at `contracts/`.

- [x] **Chunk 0 - bootstrap**: repo on tcedirector, MIT LICENSE, spec + roadmap.
- [x] **Chunk 1 - repo meta & docs** (PR #1, merged).
- [x] **Chunk 2 - Python workspace + spot_core skeleton** (PR #2, merged).
- [x] **Chunk 3 - CI workflow + file-size guard** (PR #3, merged; brought forward). CI: `Backend: Lint / Type Check` (non-blocking) `/ Test`, `File Size`, `ShellCheck`.
- [ ] **Chunk 4 - contracts/ seam**: standalone `contracts` package (`Hit` + `Evidence/Edge` schemas both lanes agree on) + round-trip tests. **Metric:** `pytest contracts` green.
- [ ] **Chunk 5 - api /health**: FastAPI + `/health` + test. **Metric:** `pytest api` green; serves 200.
- [ ] **Chunk 6 - frontend skeleton**: React+Vite+TS+Tailwind + a vitest test; adds `Frontend: *` CI jobs. **Metric:** npm test / tsc / build / lint green.
- [ ] **Chunk 7 - containerize + compose**: Dockerfiles + `docker-compose.yml` (postgres, redis, api, frontend); runtime image installs from `requirements/base.lock`. **Metric:** `docker compose up` boots; `/health` reachable.
- [ ] **Chunk 8 - justfile wiring**: real `up`/`down`/`lint`/`fmt`/`typecheck`/`test`. **Metric:** `just lint` + `just test` green.

**FORK POINT ->** Lane A roadmap + Lane B roadmap in separate worktrees.
