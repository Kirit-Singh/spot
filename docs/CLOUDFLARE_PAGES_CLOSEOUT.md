# Cloudflare Pages closeout

This is a closeout lane. Do not attach domains or enable production deployment until the Stage 1–4 release and `public_release/results/` tree are admitted. The scaffold does not contain credentials and does not deploy anything.

The interim `spotpathways.pages.dev` placeholder (served before this full release is admitted) is a separate build and mode, documented in `docs/CLOUDFLARE_PLACEHOLDER.md`.

## Deployment boundary

Neither existing build directory is a valid Pages source:

- `deploy/build_dist.sh` is the legacy six-file Stage-1 distribution and omits the downstream pages, most Stage-1 artifacts, hashed assets, and downstream results.
- `_frontend/dist` is a Vite intermediate. In a clean Git checkout, `_frontend/public/data/` is intentionally ignored, so publishing this directory directly omits required Stage-1 data.

The only publishable directory is `dist/cloudflare-pages`, assembled by:

```bash
bash deploy/cloudflare/build_pages.sh
```

The assembler runs `npm ci`, typecheck, lint, tests, and the Vite MPA build; copies the frozen landing, admitted pages, exact 22-file Stage-1 allowlist, and optional content-addressed downstream results; then writes `site_release_manifest.json`. It never mutates `01_programs/app` and never recursively publishes the repository. On `main`, absence of `public_release/results/current.json` fails the build.

At scaffold verification, the unbound output is 42 files / 59,940,014 bytes. The largest asset is `data/stage01_umap_seed.json` at 21,422,364 bytes, leaving 4,792,036 bytes below Pages' 25 MiB single-file limit. Every build hard-refuses a file over 25 MiB, more than 20,000 files, symlinks, unapproved extensions, dotpaths, or machine-local/private tokens. Re-check after final downstream results are added. Cloudflare's current limits are documented at <https://developers.cloudflare.com/pages/platform/limits/>.

## Pages project configuration

Create one Git-integrated Pages project only at closeout:

- Project: `spotpathways` (or the nearest available Pages project slug).
- Repository: `Kirit-Singh/spot`.
- Production branch: `main`.
- Root directory: repository root (`/`, blank in the dashboard).
- Build system: v3.
- Build command: `bash deploy/cloudflare/build_pages.sh`.
- Build output directory: `dist/cloudflare-pages`.
- Node: `.nvmrc` pins `22.16.0`, which satisfies Vite 8.
- Preview branch controls: Custom; include only the closeout/release branches (for example `deploy/*` and `release/*`), not active scientific agent branches.
- Keep automatic production deployments disabled until final approval; then enable it for `main`.

Pages keeps atomic commit preview URLs and branch aliases. Record the immutable commit URL for review, not the moving branch alias. Protect all preview deployments with Cloudflare Access under Pages **Settings → General → Enable access policy**. Preview mode issues no application reviewer cookie; Access is the preview boundary. Pages documents this separation at <https://developers.cloudflare.com/pages/configuration/preview-deployments/>.

`wrangler.jsonc` pins the Pages output directory, compatibility date, and environment modes. It contains no secret values. The root `functions/` directory is required because Pages Functions must live at the project root.

## Production reviewer gate

Set these as encrypted **production** secrets under **Settings → Variables and Secrets** before the production deployment that uses them:

- `ACCESS_CODE`: the reviewer-approved shared value.
- `SESSION_SIGNING_KEY`: at least 32 random characters; generate a fresh high-entropy value outside the repository.

Never place either value in Git, build variables, a URL, a command checked into documentation, analytics, or logs. Missing secrets yield `503` and cannot open protected content.

The exact public surface is `GET/HEAD /` and `POST /auth`. `functions/_middleware.ts` runs on `/*`, with `_routes.json` containing no exclusions. Every HTML page, JS/CSS asset, Stage-1 data file, result, manifest, and unknown path is checked before static bytes are served. Set Pages **Settings → Runtime → Fail open / closed → Fail closed**; otherwise quota exhaustion could bypass an authentication Function and expose static assets. See <https://developers.cloudflare.com/pages/functions/routing/#fail-open--closed>.

`POST /auth` accepts one small `application/x-www-form-urlencoded` `code` field from the same origin. The server compares it in constant time and never logs or echoes it. Success returns `303 /01_page.html` with a four-hour HMAC-signed opaque cookie:

```text
__Host-spot-review=<opaque>; Path=/; Max-Age=14400; HttpOnly; Secure; SameSite=Lax
```

There is no `Domain` attribute. `SameSite=Lax` lets an already admitted reviewer follow a top-level link from email without an unnecessary gate bounce while withholding the cookie from cross-site POSTs. This is a lightweight shared-reviewer gate, not identity, authorization by reviewer, or protection for regulated/confidential data. Rotate `SESSION_SIGNING_KEY` to revoke all live sessions; changing only `ACCESS_CODE` affects new sessions.

Configure a zone rate-limiting rule for `/auth` before go-live. On a plan that supports method matching, scope it to canonical host + `POST` + exact path. On Free, the compatible fallback is exact path `/auth` (the Function returns 405 for non-POST): five requests per 10 seconds per IP, block for 10 seconds. Keep the Function stateless; do not pretend an in-isolate counter is durable.

All Function responses set `Cache-Control: private, no-store, max-age=0`, CSP, HSTS, noindex, frame denial, MIME sniffing denial, referrer, permissions, and cross-origin headers. `_headers` repeats a minimal static fallback, but it is not the security boundary because Cloudflare does not apply `_headers` rules to Function responses.

## Canonical domains

The canonical origin is `https://spotpathways.com`. `spotpathway.com` is redirect-only. The middleware performs canonicalization before auth or cookie parsing and permanently redirects to the plural host with path and safe query parameters preserved; credential-like query keys are stripped. It never sets a cookie on the singular response. Production `*.pages.dev` requests also redirect to the canonical host.

As checked on 2026-07-13, both zones are delegated to `bart.ns.cloudflare.com` and `heather.ns.cloudflare.com`, with no public A, AAAA, or CAA record. At closeout:

1. Deploy and verify the Git build and Access-protected preview without custom domains.
2. Configure production secrets, Runtime **Fail closed**, the `/auth` rate limit, and produce two successful gated production deployments so there is a safe rollback floor.
3. In the Pages project's **Custom domains** screen, add `spotpathways.com` first. Do not manually create a CNAME before associating the domain with Pages; Cloudflare warns that doing so can produce a 522. Wait for Active DNS and certificate status, then run the production gate smoke test.
4. Add `spotpathway.com` to the same project only after the canonical host passes. Verify every singular path/query gets a 308 to plural, no loop, no protected bytes, and no `Set-Cookie`.
5. Optionally add both `www` names and make them redirect-only through the same canonical-first logic.

Cloudflare's apex/domain sequence is documented at <https://developers.cloudflare.com/pages/configuration/custom-domains/>.

## Acceptance and rollback

Run before merge:

```bash
cd _frontend
npm ci
npm run typecheck
npm run lint
npm test
cd ..
python3 deploy/test_landing_contract.py
bash deploy/cloudflare/test_build_pages.sh
npx --yes wrangler@4.110.0 pages functions build functions --compatibility-date 2026-07-13
```

Production checks must cover:

- Root is the frozen `spot` + clickable dot landing and makes no third-party request.
- Singular domain and production `pages.dev` redirect before auth; alias POST `/auth` returns a redirect and no cookie.
- Wrong, missing, duplicated, oversized, wrong-content-type, and cross-origin codes all produce the same generic invalid state and never echo input.
- Correct access produces only the host-only cookie above and a 303 to `/01_page.html`.
- Without a cookie, direct HTML, asset, `data/`, `results/`, and manifest requests return no protected bytes. With a valid cookie, every file in `site_release_manifest.json` loads and hashes correctly.
- Tampered, expired, wrong-host, and old-signing-key cookies fail closed. Every response is `no-store`.
- Stage 1–4 browser acceptance passes at desktop and 320-pixel mobile widths, including keyboard, reduced motion, and forced colors.
- Preview URL is blocked by Access when signed out and emits no application cookie when signed in.
- Dashboard/API evidence records Runtime **Fail closed**, secrets present (names only), rate-limit rule, deployment ID, commit SHA, and release-manifest SHA. Never capture secret values.

Pages can instantly roll production back only to a previous successful production deployment; preview deployments are not rollback targets. Never roll back below the first fully gated deployment after domains are attached. Perform one rollback drill between the two gated baseline deployments, rerun canonical/auth/hash smoke tests, then restore the intended release. Cloudflare documents Pages rollback behavior at <https://developers.cloudflare.com/pages/configuration/rollbacks/>.
