# Public-packaging checklist — real-artifact reseal

Use this before sealing real artifacts for public release. This branch did the **documentation
and hygiene** pass; the fields below are filled later, from **real runs**, by the owning lane.
Leave any value unknown as `null` / unchecked — never fabricate a hash, timestamp, revision, or
export URL. Coordination: the orchestrator.

## Per-route reseal record (fill from the real run)
For **each** produced artifact / route (Stage-1 scoring, Stage-2 Direct, Stage-2 temporal,
Stage-2 pathway, paper-concordance, and Stages 3–4 when implemented), record:

- [ ] **method** — the frozen method id / version for the route
- [ ] **env** — interpreter + lockfile (exact pins) used for the run
- [ ] **run UTC** — ISO-8601 UTC of the run
- [ ] **reproduce** — the exact command / entry point that regenerates the artifact
- [ ] **hash** — the artifact's content hash (canonical + raw), re-derived by a verifier
- [ ] **generator** — who/what produced it
- [ ] **verifier** — the independent verifier (generator ≠ verifier) + its result
- [ ] **artifact** — the artifact path / id it binds
- [ ] **real Claude Science export URL** — the actual CS export URL, or explicit `null` if none

## Deployment / release consistency
- [ ] **UI source-build proof** — the served UI matches the reviewed source (build hash /
      source-of-truth proof), not a stale bundle
- [ ] **Consistent Stage-1 deployment manifests** — `stage01_current.json`,
      `stage01_input_manifest.json`, and `stage01_release_manifest.json` agree with each other
      and with the served overlay (no "not-deployed" gate contradicting a "deployed" manifest)
- [ ] **HF returned revision** — `stage1_release_hf_revision` filled from the actual
      owner-reviewed upload (see `01_programs/hf_release/stage1_release_hf_manifest.template.json`);
      the immutable source revision `e5fcf98b…` is unchanged
- [ ] **Paper-concordance receipt** — a completed
      `schemas/paper_concordance_run_receipt.schema.json` instance with the primary PDF SHA-256
      (prefix `7539856ecfea…`) independently re-checked

## Deferred data-only fields (do NOT edit in place — reseal required)
These live inside **frozen, hash-pinned artifacts**; their full-file SHA-256 is bound in
`01_programs/analysis/stage2_bridge/PROTECTED_HASHES.json` and the Stage-1 release manifest, so
their bytes cannot change without a coordinated re-freeze (which moves those pins). They are
tracked here rather than edited now:

- [ ] `01_programs/analysis/effect_universe_gwcd4i.json` — the `provenance.host_path` field is a
      machine-local absolute build path (a `host:/absolute/path` read location from the frozen
      build). At reseal, replace it with a **logical locator** (dataset id + `GWCD4i.DE_stats.h5ad`,
      "authors' release, not bundled"), then re-freeze `PROTECTED_HASHES.json` and update the
      release manifest hash. Until then it is intentionally left byte-for-byte unchanged.

## Fill-and-publish (orchestrator supplies final values; DO NOT UPLOAD yet)
Templates in this repo carry `null` / pending fields on purpose. When the real runs finish, the
orchestrator drops the exact final artifact path + content hash into each row below, a verifier
re-derives the hash, and only then does publication proceed. **No upload happens from this branch.**

| Artifact | Final repo path | Final sha256 | Verifier + result | Filled by | Filled UTC | Status |
|---|---|---|---|---|---|---|
| Stage-1 v3 HF bundle | _pending_ | _pending_ | _pending_ | _pending_ | _pending_ | pending |
| `stage1_release_hf_revision` (returned) | n/a (HF) | _pending_ | _pending_ | _pending_ | _pending_ | pending |
| Paper-concordance receipt | _pending_ | _pending_ | primary PDF sha `7539856ecfea…` re-checked | _pending_ | _pending_ | pending |
| Stage-2 arms/pathway artifact(s) | _pending_ | _pending_ | _pending_ | _pending_ | _pending_ | pending |
| Stage-3 / Stage-4 artifact(s) | _pending_ (not yet implemented) | _pending_ | _pending_ | _pending_ | _pending_ | pending |

Publish gate — all must be true before any upload:
- [ ] every row above filled with a real path + hash (no `_pending_`)
- [ ] each hash re-derived by an independent verifier (generator ≠ verifier), exit 0
- [ ] `source_license_inventory.json` and the HF card carry only verified licenses; no token, no
      machine path, no raw proprietary/unlicensed data, no unfinished result presented as final
- [ ] orchestrator sign-off recorded

## Secret / path hygiene (each reseal)
- [ ] Re-run the machine-path regression scan (`test_public_packaging_hygiene.py`)
- [ ] Re-run the secret scan; confirm no credentials or tokens are tracked
- [ ] Confirm `schemas/source_license_inventory.json` licenses still resolve to their official URLs
