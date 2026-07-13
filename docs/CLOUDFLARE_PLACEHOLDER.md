# Cloudflare Pages placeholder

An interim, deliberately-labelled placeholder for the eventual canonical site. It
reuses the frozen reviewer landing and the existing fail-closed Functions gate, and
ships one post-auth page that states the workbench is being assembled. It carries no
scientific claim, result, or Stage-1..4 data, and it never contains the reviewer code.

This lane is separate from the full-site assembler (`deploy/cloudflare/build_pages.sh`
and `docs/CLOUDFLARE_PAGES_CLOSEOUT.md`), which publishes the admitted Stage-1..4
release. Do not deploy the full site from this lane, and do not weaken that gate.

## Build

```bash
bash deploy/cloudflare/build_placeholder.sh        # -> dist/cloudflare-placeholder
```

Deterministic. It copies only the frozen landing (`01_programs/app/index.html`), the
placeholder page (`deploy/cloudflare/static/placeholder.html` -> `01_page.html`), and
the static control files, then runs the shared, hardened `finalize_pages_dist.mjs`
(unchanged) and asserts the exact six-file inventory. It never runs the Vite build,
never copies `data/` / `results/` / hashed assets, and hard-refuses any drift.

Output directory: `dist/cloudflare-placeholder` (git-ignored). Inventory — 5 served
files + a self-excluded manifest; content hashes are commit-independent:

| path | bytes | sha256 |
|------|------:|--------|
| index.html | 6289 | 29adcdac190630b311e37c0ad9a3d7f8342026ebd2de9ca81de8cd447c9d03ab | (frozen landing, byte-identical)
| 01_page.html | 2661 | ce4dff4508a88e35a5174c806ce9018453f17065128ffa381d537f313603d5c0 | (placeholder)
| 404.html | 312 | cfaad9a8a6e9b142e5ee531b301133493a38f1e7e2757f570dba31d3349105ac |
| _routes.json | 57 | cd85544e6e0aaaee95f1e480ba45c72388ae8db8a09ac23cbe103e9eb0bc16b7 |
| _headers | 152 | e6c5d0a13755e2463c43d884f592b3e267912d75434d34c09b0b8cb7d28657e3 |
| site_release_manifest.json | — | — | (sha256 inventory; `source_commit` set at build time; self-excluded)

Total 6 files / 10,434 bytes; largest single file 6,289 bytes — far under Pages' 25 MiB
limit. `_routes.json` is `{"version":1,"include":["/*"],"exclude":[]}`, so every asset
routes through the fail-closed Function.

## Protection: `SITE_MODE='placeholder'`

The interim deployment is the production deployment served **only** at
`spotpathways.pages.dev`, before the canonical domain is attached. `SITE_MODE='placeholder'`
runs the same application access-code / HMAC-cookie flow as `production`:

- Any host other than exactly `spotpathways.pages.dev` is **refused** with `503` (never
  redirected — the canonical domain is not attached yet).
- `GET /` and `POST /auth` are the only public surface; every other asset requires a
  valid `__Host-spot-review` session. `POST /auth` requires a same-origin
  `https://spotpathways.pages.dev` submission, compares the code in constant time, and
  issues a 4-hour host-only `Secure; HttpOnly; SameSite=Lax; Path=/` cookie (no `Domain`).
- Missing/short secrets or a missing/unknown `SITE_MODE` fail closed with `503`.

This mode does **not** change `SITE_MODE='production'` canonical-host behavior (production
still 308-redirects any non-canonical host, including `*.pages.dev`, to
`spotpathways.com`). `SITE_MODE='preview'` remains separate (Cloudflare Access upstream,
no application cookie).

The reviewer code and `SESSION_SIGNING_KEY` are deployment secrets: never committed,
printed, embedded in HTML/JS/URLs, or logged. Set Pages **Runtime → Fail closed**.

## Exact host policy (`SITE_MODE='production'`)

`productionHostDecision(hostname, env)` in `functions/lib/reviewerGate.ts` is the single
source of truth. It **defaults to refuse**, so an unknown host never serves and is never
redirected:

| Host | Decision |
|------|----------|
| `spotpathways.com` | **serve** — the canonical allowed application host; full reviewer gate |
| `spotpathway.com`, `www.spotpathway.com`, `www.spotpathways.com` | **redirect** — 308 to canonical *before auth*, path + query preserved, credential-like query keys stripped, never `Set-Cookie` |
| `spotpathways.pages.dev` (the project's stable alias) | **serve** while `ALLOW_PAGES_DEV_ALIAS=1` (certificate provisioning); otherwise **redirect** 308 to canonical |
| unique per-deployment / per-branch subdomains (`<id>.spotpathways.pages.dev`, `release.spotpathways.pages.dev`) | **refuse** — 503, never serve, never redirect, never issue a cookie |
| every other host | **refuse** — 503 |

`POST /auth` requires the submission to be same-origin with the host that rendered the
form (canonical, or the stable alias while provisioning). The access-code comparison,
constant-time check, and host-only `__Host-spot-review` cookie are unchanged.

## Placeholder -> production switch (DONE)

Pages environment variables come from the committed `wrangler.jsonc` `env.production.vars`.
`wrangler pages deploy` **reapplies them on every deploy**, so an out-of-band dashboard or
API change to `SITE_MODE` is silently clobbered. Change it here, not there.

1. `SITE_MODE=production` in `env.production.vars` **before** attaching the custom domain —
   attaching it while `SITE_MODE=placeholder` 503s the canonical host (placeholder mode
   refuses every host but the alias).
2. Attach `spotpathways.com`, then `spotpathway.com`. Wait for Active DNS + certificate.
   `ALLOW_PAGES_DEV_ALIAS=1` keeps the stable alias serving during provisioning.
3. Once the canonical certificate is active, **remove `ALLOW_PAGES_DEV_ALIAS`** so the alias
   308s to the canonical host. *(Completed — both domains `status=active cert=active`.)*
4. Point the build at the full-site assembler once the Stage-1..4 release is admitted:
   `pages_build_output_dir` currently pins `./dist/cloudflare-placeholder` so that a bare
   `wrangler pages deploy` cannot publish the app bundle. Flip it to `./dist/cloudflare-pages`
   only at admitted release.

The cookie mechanism is identical across modes (same signing key, same signed message),
so the switch is a mode/host change, not a crypto change. Host-only cookies from
`spotpathways.pages.dev` do not carry to `spotpathways.com`; reviewers re-authenticate on
the canonical host. Rotate `SESSION_SIGNING_KEY` to revoke all live sessions.

## Verify (all green in this branch)

```bash
cd _frontend && npm run typecheck && npm run lint && npm test && cd ..
python3 deploy/test_landing_contract.py
bash deploy/cloudflare/test_build_placeholder.sh
npx --yes wrangler@4.110.0 pages functions build functions --compatibility-date 2026-07-13
```

## Deploy — do NOT run here

Deployment is performed by the independent audit and orchestrator, not this lane.

Prerequisite: an authenticated Wrangler session with `pages (write)` scope
(`wrangler whoami`). Production secrets `ACCESS_CODE` and `SESSION_SIGNING_KEY` (>=32
chars) must be set as encrypted **production** secrets on the `spotpathways` project.

Project settings for the interim placeholder deployment:

- Build command: `bash deploy/cloudflare/build_placeholder.sh`;
  output directory: `dist/cloudflare-placeholder`; Node `.nvmrc` 22.16.0.
- Production environment variable `SITE_MODE=placeholder` (switch to `production` at
  cutover). Root `functions/` is the gate (Pages requires it at the project root).
- Runtime → **Fail closed**. Rate-limit `/auth`.
- Do not attach `spotpathways.com` / `spotpathway.com` DNS until instructed; the
  interim URL is `https://spotpathways.pages.dev` only.

Equivalent direct-upload command (from the repo root, `functions/` picked up
automatically) — for reference only:

```bash
npx wrangler@4.110.0 pages deploy dist/cloudflare-placeholder \
  --project-name spotpathways --branch main \
  --commit-hash "$(git rev-parse HEAD)" --commit-dirty=false
```
