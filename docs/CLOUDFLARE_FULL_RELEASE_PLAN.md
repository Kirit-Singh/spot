# Canonical full-app Cloudflare Pages release plan

**Status: PLAN ONLY. Nothing here has been deployed and no Cloudflare state has been changed.**
`spotpathways.com` still serves the 6-file placeholder at deployment `dd9bd15b`.

The release is **atomic**: a Pages deployment is immutable and all-or-nothing, so the canonical
host flips from placeholder to full app in a single direct upload, with the placeholder retained
as the rollback floor.

## What must NOT change

The reviewer gate and host policy are already live and verified; the release reuses them untouched:

- `functions/` — access-code / HMAC-cookie flow, constant-time compare, host-only
  `__Host-spot-review` cookie, `Sec-Fetch-Site` same-origin handling.
- Security headers + CSP from `withSecurityHeaders` (`script-src 'self' 'unsafe-inline'`,
  `connect-src 'self'`, `form-action 'self'`, `frame-ancestors 'none'`, HSTS, noindex, no-store).
- `SITE_MODE=production`; canonical `spotpathways.com`; `spotpathways.pages.dev` → 308 canonical;
  `spotpathway.com` (+ `www` forms) → 308 canonical **preserving full path + query**, credential-like
  keys stripped, never `Set-Cookie`; deployment subdomains and all other hosts → 503.
- `_routes.json` = `{"version":1,"include":["/*"],"exclude":[]}` so every app byte is gated.
- Secrets are untouched: `ACCESS_CODE` / `SESSION_SIGNING_KEY` are never read, printed, or rotated.

## The artifact: mirror the admitted tree, never rebuild it

The approved artifact is the `:8347` distribution described by
`01_programs/app/release_manifest.json` (`release: spot-8347-same-origin`, 38 hash-pinned files),
produced and accepted by `_frontend/deploy/deploy_8347.sh` (which itself proves remote == local
byte-for-byte and never prints GO — only the live U01–U18 harness may).

**`deploy/cloudflare/build_pages.sh` cannot produce that artifact.** It runs `npm run build`, so Vite
re-mints chunk names and hashes and the HTML that references them. Measured against the approved
manifest today:

```
byte-identical to admitted : 25 / 38
DRIFTED                    :  7   01_page.html, index.html, targets/pathways/drugs/pksafety.html,
                                   data/stage01_selection_bundle.json
in dist, NOT in manifest   :  6   assets/resolveRouteArtifact-*, drugs-DQaB_GDM, …
in manifest, NOT packaged  :  6   assets/StageIsland-CwnTt7gM, drugs-B84b5mvt, …
```

So production packaging **mirrors** the admitted `01_programs/app` tree byte-for-byte and adds only
the Pages control files. It never invokes Vite. `build_pages.sh` stays as-is for the legacy path and
is **not** the release build.

## Blockers — every one must clear before any deploy

| # | Blocker | Evidence |
|---|---------|----------|
| B1 | **Stage-1 gate refuses deployment.** | `stage01_release_manifest.json`: `app_deployment_ready: false`, `overlay_release_ok: false`, `not_lockable_reason_codes: ["overlay_release_blocked"]`. `verify_served_manifests.py` exists to refuse a served tree that claims deployed while the gate says not-ready. |
| B2 | **Admitted manifest is stale vs HEAD.** | `:8347` manifest is commit `22f27ff6`; this branch is `5e47579`. The landing and the frontend chunking have both changed since. `:8347` must be re-cut and re-admitted **at the release commit**. |
| B3 | **Reactome ships in the app bundle (GO-BP-only violation).** | `assets/resolveRouteArtifact-*.js` carries a live provenance `source_chain` entry — `Reactome V97`, `ReactomePathways.gmt.zip`, `license: CC0-1.0` — plus coverage text ("Reactome loses 39.6069% of member slots"). That is release metadata, **not** parked licence/history. |
| B4 | **Interim copy would ship.** | The landing About modal says "currently being assembled" and "Access is limited to reviewers while the work is in progress" — false once the full app is released. |
| B5 | **Downstream results tree undecided.** | `public_release/results/` is absent, and the admitted 38-file manifest contains no `results/` entries — yet `build_pages.sh` hard-requires the tree when `CF_PAGES_BRANCH=main`. Decide explicitly: either the 38-file tree IS the complete release, or an admitted `results/` tree must be produced and pinned. |

The build gate below encodes B1–B4 and fails closed on all of them **today**.

## Build gate (added, tested)

`deploy/cloudflare/verify_release_binding.py` — refuses the release unless every condition holds.
`generator != verifier`: it re-derives every hash from the packaged bytes and re-reads the deployment
signal from the manifests; it never trusts a self-declared flag and never repairs the tree.

- **GATE** — `release_gates.app_deployment_ready` must be `true`, `overlay_release_ok` must not be
  `false`, `not_lockable_reason_codes` and `missing_required_artifacts` must be empty.
- **Byte binding** — every packaged path (excluding exactly `_headers`, `_routes.json`, `404.html`,
  `site_release_manifest.json`) must appear in the approved manifest at its admitted sha256.
  `UNLISTED` / `DRIFT` / `MISSING` are each fatal, so nothing can be added, changed, or silently dropped.
- **REACTOME** — any Reactome mention in a served text byte is fatal unless the path is listed in
  `deploy/cloudflare/reactome_parked.allowlist` (licence/history only). That file is **empty by design**:
  no app artifact is parked, so every current mention is a blocker. Adding a line is a reviewable act.
- **FIXTURE** — a `fixture:`/`demo:`-classed artifact id is fatal.
- **PLACEHOLDER** — the `data-placeholder` route marker is fatal.
- **INTERIM_COPY** — "being assembled" / reviewer-limited prose is reported on its own (it is stale
  copy, not a placeholder route).
- **CONTROL** — the four Pages control files must all be present.

Run:

```bash
python3 deploy/cloudflare/verify_release_binding.py dist/cloudflare-release \
  --approved 01_programs/app/release_manifest.json \
  --parked   deploy/cloudflare/reactome_parked.allowlist
```

Against the current rebuilt dist it correctly REFUSES with 22 findings:
`1 GATE · 7 DRIFT · 6 UNLISTED · 6 MISSING · 1 REACTOME · 1 INTERIM_COPY`.
Contract: `python3 deploy/cloudflare/test_verify_release_binding.py` (12 tests, each drives a refusal).

## Files and scripts

| Path | Role |
|------|------|
| `deploy/cloudflare/verify_release_binding.py` | **NEW** the release-binding gate |
| `deploy/cloudflare/reactome_parked.allowlist` | **NEW** parked licence/history exemptions (empty) |
| `deploy/cloudflare/test_verify_release_binding.py` | **NEW** 12 refusal tests |
| `deploy/cloudflare/build_release.sh` | **TO WRITE at execution** — mirrors the admitted tree; see contract below |
| `deploy/cloudflare/finalize_pages_dist.mjs` | reuse unchanged — size/symlink/dotpath/private-token validator + `site_release_manifest.json` |
| `deploy/cloudflare/static/{_routes.json,_headers,404.html}` | reuse unchanged |
| `01_programs/analysis/verify_served_manifests.py` | reuse — refuses a contradictory served/gate manifest pair |
| `functions/**` | **unchanged** — access flow, CSP, host policy |
| `wrangler.jsonc` | at execution only: `pages_build_output_dir` → `./dist/cloudflare-release` |

`build_release.sh` contract (deliberately not written until B1–B5 clear, so it cannot be run early):
mirror `01_programs/app/**` for exactly the 38 admitted paths → `dist/cloudflare-release`; copy the
three static control files; run `finalize_pages_dist.mjs`; run `verify_served_manifests.py`; run
`verify_release_binding.py`. Refuse on any non-zero. No Vite, no `data/` regeneration, no fixtures.

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

- **Floor:** `dd9bd15b` — the current placeholder, already verified live (canonical 200, `/01_page`
  303 fail-closed, manifest 401, alias 308, singular 308, deployment subdomain 503).
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
     → 303 `/01_page.html` + host-only cookie; wrong / cross-site / foreign-origin → invalid, no cookie.
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

1. Clear B3 (strip Reactome from the shipped bundle, or park licence/history explicitly) and B4.
2. Clear B5 (decide the `results/` question).
3. Re-cut `:8347` at the release commit; run U01–U18; obtain **GO** and a fresh approved
   `release_manifest.json` with GO-BP-only release metadata. This clears B2.
4. Clear B1: the Stage-1 gate manifest must independently flip to `app_deployment_ready: true`.
5. Write `build_release.sh`; build; gate green; local edge + browser verification.
6. Deploy atomically; smoke; keep `dd9bd15b` as the floor.
