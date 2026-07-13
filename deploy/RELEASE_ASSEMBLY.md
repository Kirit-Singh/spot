# Public-release assembly (fail-closed)

`assemble_release.py` builds the final public release from the **exact admitted** Stage-1..4
artifacts and their verifier receipts. It copies only allowlisted public files into an
**external** staging directory and emits a content-addressed manifest. It **never uploads** and
never reads credentials.

## Commands
```bash
# 0. fail-closed dry test — validates + prints the inventory, copies NOTHING
python3 deploy/assemble_release.py --spec deploy/release_spec.closeout.json \
    --staging-dir <abs dir outside repo> --dry-run

# 1. assemble (refuses unless every lane is ADMIT)
python3 deploy/assemble_release.py \
    --spec       deploy/release_spec.closeout.json \
    --staging-dir <ABSOLUTE dir OUTSIDE the repo> \
    [--run-utc 2026-07-13T00:00:00Z] [--lenient-receipt]

# 2. one-command handoff to the UI / Cloudflare deploy lane (re-verifies; does not deploy)
deploy/handoff_release.sh <staging-dir>
```
`deploy/release_spec.closeout.json` holds the **exact** slots; `release_spec.template.json` is the
bare shape. Both ship `PENDING` on every lane, so they **refuse** — no path or hash in them is
real, and none may be invented.

## Receipt binds the artifact bytes (the bc3b10b lesson)
The Stage-2 display-projection receipt (`spot.stage02.display_projection.independent_verifier.v1`)
names the bytes it judged in `subject.projection_raw_sha256`, recomputed from the file on disk.
The assembler enforces that binding:

- an artifact marked `"bound_by_receipt": true` must hash to bytes the receipt actually names —
  **an altered artifact paired with its original receipt is refused**;
- every hash the receipt says it judged must be staged for that lane (its subject cannot be absent);
- a receipt may not contradict its own body: `verdict: "admit"` alongside a non-empty `failures`,
  `n_failed > 0`, `self_hash_agrees: false`, `rebuilt_from_admitted_native_bytes: false`, or
  `generator_is_not_verifier: false` is a refusal.

## Routes, dist (Cloudflare) and HF
- `lanes.<stage>.route` is recorded in the manifest (`routes`) and the handoff, so the deploy lane
  knows which artifact serves which page. It is part of the content address.
- `dist.src` — a prebuilt UI dist (e.g. from `deploy/build_dist.sh <dir>`). Every file is scanned,
  hashed and staged under `dist/`; the handoff exposes it as `cloudflare.dist_dir`.
- `hf.card` / `hf.manifest` — the immutable source revision must be a real 40-hex revision, and
  `stage1_release_hf_revision` must stay **null** until a real upload returns one. A placeholder
  such as `"PENDING"` is refused: a revision is never invented.

## Refusal behaviour (exit 2, nothing staged)
Validation and scanning run **before any copy**, so a refusal writes nothing at all.

| Refuses when | |
|---|---|
| a lane of stage1..stage4 is missing from the spec | all four are required |
| a lane's `status` is not exactly `ADMIT` | e.g. `PENDING`, `HOLD` |
| a declared artifact or receipt file does not exist | |
| a declared `expected_sha256` ≠ the bytes on disk | the mismatch is the refusal; the hash is never "fixed" |
| a receipt is missing / empty / not valid JSON | |
| a receipt carries a negative verdict (`REFUSE`, `FAIL`, …) | only verdict-like keys are read |
| a receipt carries no positive verdict | unless `--lenient-receipt` (a negative still refuses) |
| any file contains a secret or a machine-local path | official URLs containing `/home/` are not false positives |
| a file has a denied extension/name (`.h5ad`, `.env`, `.pem`, …) | raw source and credentials can never be staged |
| `--staging-dir` is relative, inside the repo, or non-empty | it is never deleted — pick a fresh dir |

The staged copy is re-hashed after the copy; any drift refuses.

## Outputs
- `MANIFEST.json` — `spot.public_release_manifest.v1`. Records only **measured** hashes and
  staging-relative paths (never a source machine path), plus `manifest_content_sha256` (the
  content address over lanes + sorted files) and `uploaded: false`.
- `DEPLOY_HANDOFF.json` — staging dir, manifest content hash, lane statuses, next command.
- `public/` — the allowlisted repo docs; `lanes/stage{1..4}/` — the admitted artifacts + receipts.

`handoff_release.sh` re-hashes every staged file against the manifest and re-derives the content
address independently (generator ≠ verifier). Any drift refuses with exit 2.
