# Canonical full-app Cloudflare Pages release plan

**Status: PLAN ONLY. Nothing here has been deployed and no Cloudflare state has been changed.**
`spotpathways.com` still serves the 6-file placeholder at deployment `dd9bd15b`.

The release is **atomic**: a Pages deployment is immutable and all-or-nothing, so the canonical
host flips from placeholder to full app in a single direct upload, with the placeholder retained
as the rollback floor.

## Gate invariants

The canonical Programs route changes, but the verified reviewer-gate and host-policy invariants remain:

- `functions/` — access-code / HMAC-cookie flow, constant-time compare, host-only
  `__Host-spot-review` cookie, `Sec-Fetch-Site` same-origin handling; successful auth now lands on
  `/programs.html`, and authenticated `/01_page.html` requests permanently redirect there.
- Security headers + CSP from `withSecurityHeaders` (`script-src 'self' 'unsafe-inline'`,
  `connect-src 'self'`, `form-action 'self'`, `frame-ancestors 'none'`, HSTS, noindex, no-store).
- `SITE_MODE=production`; canonical `spotpathways.com`; `spotpathways.pages.dev` → 308 canonical;
  `spotpathway.com` (+ `www` forms) → 308 canonical **preserving full path + query**, credential-like
  keys stripped, never `Set-Cookie`; deployment subdomains and all other hosts → 503.
- `_routes.json` = `{"version":1,"include":["/*"],"exclude":[]}` so every app byte is gated.
- Secrets are untouched: `ACCESS_CODE` / `SESSION_SIGNING_KEY` are never read, printed, or rotated.

## The artifact: EXTERNAL staging, mirrored — never a repo tree, never rebuilt

**Corrected by independent audit.** An earlier draft of this plan bound to the repo app tree
`/Users/kiritsingh/spot/01_programs/app` (commit `22f27ff6`, 38 files) — that tree is **stale** and
must never be the release input.

The approved artifact is **external staging**:

| | |
|---|---|
| `SPOT_APPROVED_ROOT` | `~/.spot-runs/spot-8347-staging-9f53aeb` |
| `SPOT_APPROVED_MANIFEST` | `$SPOT_APPROVED_ROOT/release_manifest.json` |
| `SPOT_DEPLOY_RECEIPT` | `~/.spot-runs/spot-8347-deployed_manifest.txt` |
| release / commit | `spot-8347-same-origin` / `9f53aebe`, `dirty: false` |
| `files[]` | **42** — 22 `stage1-data`, 13 `built`, 4 `downstream-data` (`results/`), 3 `preserved-stage1` |

The final build takes these **explicitly**; the gate hard-refuses an `--approved` path under
`01_programs/app`, so a repo tree cannot be bound by accident. The root and manifest are supplied by
the **post-GO-BP** staging, not `9f53aeb` (see B3). That recut must name `programs.html`, omit a static
`01_page.html`, and point its admitted index stub at the canonical Programs route.

`deploy/cloudflare/build_pages.sh` **cannot** produce the admitted artifact: it re-runs Vite, which
re-mints chunk names/hashes and the HTML referencing them. Production packaging **mirrors** the
approved root byte-for-byte and adds only the Pages control surface. `build_pages.sh` is not the
release build.

## Root serving: the admitted index.html is preserved, the landing is a control surface

The admitted `index.html` is a hash-bound **meta-refresh stub** into `/programs.html`. Overwriting it
with the reviewer landing would destroy an admitted byte *and* publish an app entry point.

So the landing ships as its own control surface, `landing.html`, and the root Function forwards `/`
to it. `index.html` stays a gated app artifact. Verified on the real Pages runtime:

```
GET /                     200   the reviewer landing
GET /index.html no cookie 303 -> /       (admitted artifact, GATED)
GET /landing  no cookie   303            (reachable only via /)
POST /auth  correct       303 -> /programs.html + host-only cookie
GET /01_page.html authed  308 -> /programs.html (compatibility; no duplicate file)
```

`LANDING_ASSET` is **extensionless** (`/landing`) on purpose: Pages canonicalises `.html` URLs, so
forwarding to `/landing.html` makes the asset layer answer `308 -> /landing` and the root route stops
serving anything. The placeholder build uses the same serving model, so the two builds never diverge.

## Blockers — every one must clear before any deploy

| # | Blocker | Status | Evidence |
|---|---------|--------|----------|
| B1 | Stage-1 gate refuses deployment | **CLEARED** — was stale | The accepted staging's `data/stage01_release_manifest.json` reads `app_deployment_ready: true`, `overlay_release_ok: true`, `served_artifact_integrity_ok: true`, `overlay_release_fidelity_ok: true`, `not_lockable_reason_codes: []`, `missing_required_artifacts: []`. The earlier "false" flags came from the **stale repo tree**. |
| B2 | Admitted manifest stale | **CORRECTED** | The accepted artifact is external staging `9f53aeb` (42 entries), not the repo tree `22f27ff6` (38). The build must take `SPOT_APPROVED_ROOT`/`SPOT_APPROVED_MANIFEST` explicitly; the gate refuses a repo app tree. Still requires the **post-GO-BP** re-cut (see B3). |
| **B3** | **Reactome ships — GO-BP-only violation** | **OPEN — the only substantive blocker** | `results/current.json` declares **`"active_pathway_source": "reactome"`**, and `assets/resolveRouteArtifact-D-T-7ROR.js` carries Reactome release metadata. This is a parsed *production claim*, not merely text. The post-GO-BP staging must flip it to `go_bp`. |
| B4 | Interim landing copy | **OPEN** | The About modal says "currently being assembled" / reviewer-limited — false once the full app ships. Caught as `INTERIM_COPY`. |
| B5 | Downstream results undecided | **CLEARED** — was stale | `results/` **is** in the accepted manifest: 4 `downstream-data` entries (`results/current.json`, `results/manifests/targets.ui_release.json`, `results/stage02/*`). The absent `public_release/` is irrelevant — the release mirrors external staging, not a repo tree. |

Run against the **accepted `9f53aeb` staging**, the gate reports exactly:
`2 REACTOME · 1 CLAIMS · 5 CONTROL` — zero DRIFT, UNLISTED, MISSING, GATE, INDEX, or RECEIPT
findings. The 5 CONTROL are the Pages control files the packaging adds. So the staging is internally
consistent, receipt-bound and gate-admitted, and **GO-BP is the only thing standing between it and
release.**

## Build gate (added, tested)

`deploy/cloudflare/verify_release_binding.py` — refuses the release unless every condition holds.
`generator != verifier`: it re-derives every hash from the packaged bytes and re-reads the deployment
signal from the manifests; it never trusts a self-declared flag and never repairs the tree.

- **GATE** — `release_gates.app_deployment_ready` must be `true`, `overlay_release_ok` must not be
  `false`, `not_lockable_reason_codes` and `missing_required_artifacts` must be empty.
- **Byte binding** — every packaged path (excluding exactly the control surface: `_headers`,
  `_routes.json`, `404.html`, `landing.html`, `site_release_manifest.json`) must appear in the approved
  manifest at its admitted sha256. `UNLISTED` / `DRIFT` / `MISSING` are each fatal, so nothing can be
  added, changed, or silently dropped.
- **RECEIPT / SELF_EXCLUDE** — the approved manifest **non-recursively self-excludes**: it does not list
  `release_manifest.json` in its own `files[]`. Copying it must therefore not read as `UNLISTED`, and it
  must not go unbound either. Its raw bytes are pinned by the **external deploy receipt**
  (`spot-8347-deployed_manifest.txt`, verified: `0cbcca76…` matches the staging byte-for-byte). A missing
  receipt, a receipt that does not bind it, a drifted manifest, or a manifest that lists itself are each fatal.
- **INDEX** — the admitted `index.html` (a hash-bound meta-refresh stub) must be packaged unchanged. It is
  never overwritten or omitted to make room for the reviewer landing, which ships as `landing.html`.
- **REACTOME** — any Reactome mention in a served text byte is fatal unless the path is listed in
  `deploy/cloudflare/reactome_parked.allowlist` (licence/history only). That file is **empty by design**:
  no app artifact is parked, so every current mention is a blocker. Adding a line is a reviewable act.
- **CLAIMS** — the authoritative fixture/production gate **parses** what each `results/**.json` artifact
  DECLARES about itself, rather than pattern-matching text: `verifier_status` must be `admitted`,
  `generator_status` `generated`, `target_namespace` `ensembl_gene_id`, `symbol_namespace` `hgnc_symbol`,
  and **`active_pathway_source` must be GO-BP** — never `reactome`. Any field whose value is
  `fixture`/`demo`/`synthetic`/`placeholder`/`research_only`/`mock` is fatal.
- **FIXTURE** — a `fixture:`/`demo:`-classed artifact id in raw text (defence in depth only).
- **PLACEHOLDER** — the `data-placeholder` route marker is fatal.
- **INTERIM_COPY** — "being assembled" / reviewer-limited prose is reported on its own (it is stale
  copy, not a placeholder route).
- **CONTROL** — the five Pages control files must all be present.
- **Repo-tree guard** — `--approved` under `01_programs/app` is refused outright: the admitted release is
  external staging, and a repo tree is a build input, never the release.

Run:

```bash
python3 deploy/cloudflare/verify_release_binding.py dist/cloudflare-release \
  --approved "$SPOT_APPROVED_MANIFEST" \
  --receipt  "$SPOT_DEPLOY_RECEIPT" \
  --parked   deploy/cloudflare/reactome_parked.allowlist
```

Against the accepted `9f53aeb` staging it REFUSES with exactly `2 REACTOME · 1 CLAIMS · 5 CONTROL`
and zero binding findings — GO-BP is the only substantive blocker.
Contract: `python3 deploy/cloudflare/test_verify_release_binding.py` (24 tests, including exact-admission and fail-closed refusal cases).

## Files and scripts

| Path | Role |
|------|------|
| `deploy/cloudflare/verify_release_binding.py` | **NEW** the release-binding gate |
| `deploy/cloudflare/reactome_parked.allowlist` | **NEW** parked licence/history exemptions (empty) |
| `deploy/cloudflare/test_verify_release_binding.py` | **NEW** 24 exact-admission / fail-closed contract tests |
| `deploy/cloudflare/build_release.sh` | **TO WRITE at execution** — mirrors the admitted tree; see contract below |
| `deploy/cloudflare/finalize_pages_dist.mjs` | reuse unchanged — size/symlink/dotpath/private-token validator + `site_release_manifest.json` |
| `deploy/cloudflare/static/{_routes.json,_headers,404.html}` | reuse unchanged |
| `01_programs/analysis/verify_served_manifests.py` | reuse — refuses a contradictory served/gate manifest pair |
| `functions/**` | access flow, CSP, host policy, canonical Programs route + authenticated legacy redirect |
| `wrangler.jsonc` | at execution only: `pages_build_output_dir` → `./dist/cloudflare-release` |

`build_release.sh` contract (deliberately not written until B3/B4 clear, so it cannot be run early):
require `SPOT_APPROVED_ROOT` / `SPOT_APPROVED_MANIFEST` / `SPOT_DEPLOY_RECEIPT` to be set and to point
**outside** the repo; mirror exactly the 42 admitted paths from `$SPOT_APPROVED_ROOT` →
`dist/cloudflare-release`; copy `release_manifest.json` and verify it against the receipt; copy the
static control files and the reviewer landing as `landing.html`; run `finalize_pages_dist.mjs`,
`verify_served_manifests.py`, then `verify_release_binding.py`. Refuse on any non-zero. No Vite, no
`data/` regeneration, no fixtures, and **never** write over `index.html`.

## Deploy command (atomic — do not run yet)

```bash
# after B1–B5 clear and the gate is green
npx wrangler@4.110.0 pages deploy dist/cloudflare-release \
  --project-name spotpathways --branch main \
  --commit-hash "$(git rev-parse HEAD)" --commit-dirty=false
```

Direct upload to the production branch is a single immutable deployment; the canonical host flips
atomically. Record the new deployment id immediately.

## Rollback

- **Floor:** `dd9bd15b` — the current placeholder, already verified live (canonical 200, Programs
  route 303 fail-closed, manifest 401, alias 308, singular 308, deployment subdomain 503).
- Pages rolls production back only to a previous **successful production** deployment; preview
  deployments are not rollback targets. Never roll back below `dd9bd15b`.
- **Trigger:** any failure in the post-deploy smoke → immediate rollback to `dd9bd15b`.
- Rehearse the rollback once between two gated deployments, re-run the smoke, then restore.
- Env vars are unchanged by the release, so rollback needs no var edit.

## Preview verification strategy

**A Pages preview deployment cannot be reviewed through the app gate** — the host policy refuses
deployment subdomains and preview aliases with `503`, by design. So preview verification is local
and exhaustive, and the production step is a canary with instant rollback:

1. **Local edge run** (proven technique): `wrangler pages dev dist/cloudflare-release`, driving the
   real Functions runtime with `Host`/`Origin` spoofed to `spotpathways.com`. Verify:
   - full access flow: browser-shaped native form POST (`Origin: null` + `Sec-Fetch-Site: same-origin`)
     → 303 `/programs.html` + host-only cookie; authenticated `/01_page.html` → 308 `/programs.html`;
     wrong / cross-site / foreign-origin → invalid, no cookie.
   - every one of the 38 admitted artifacts is gated without a cookie and served with one, and each
     served byte re-hashes to the approved manifest.
   - `spotpathway.com` → 308 canonical preserving path + query; alias → 308; deployment subdomain → 503.
2. **Browser pass** (real Chrome, desktop + 320px): Stage-1 + Targets/Pathways/Drugs/PK render from
   admitted artifacts; **console clean of CSP violations** (the app must run under
   `script-src 'self' 'unsafe-inline'`, `connect-src 'self'`); no third-party request; keyboard,
   reduced-motion, forced-colors.
3. **Limits:** 42 files, ~60 MB, largest `data/stage01_umap_seed.json` at 21,422,364 B — under the
   25 MiB single-file cap with ~4.8 MB of headroom. Re-check if `results/` is added (B5).
4. **Production canary:** deploy, then immediately re-run the full external smoke against
   `spotpathways.com`. Any failure → roll back to `dd9bd15b`.
5. Cloudflare **Web Analytics must stay disabled** — it rewrites served HTML at the edge and would
   break the served==staged binding this gate exists to guarantee (see `CLOUDFLARE_PLACEHOLDER.md`).

## Sequence

1. **B3** — cut the **post-GO-BP** `:8347` staging: `active_pathway_source` → `go_bp`, Reactome release
   metadata out of the bundle (or an explicit licence/history path parked in
   `reactome_parked.allowlist`). Run U01–U18 → **GO**. This produces the new `SPOT_APPROVED_ROOT` /
   `SPOT_APPROVED_MANIFEST` / receipt and simultaneously clears B2.
2. **B4** — revise the landing About copy (it must no longer say the workbench is being assembled).
3. Write `build_release.sh`; build; **gate green**; local edge + browser verification.
4. Deploy atomically; smoke; keep `dd9bd15b` as the floor.

B1 and B5 need no action — they were stale readings of a superseded repo tree.
