# Final public-package admission checklist

The assembler is **fail-closed**: it refuses today and stages nothing. This lists, per lane, the
**exact receipt/file field** that lifts each refusal, and the **test / manifest hash** that proves
inclusion afterwards. Nothing is uploaded or deployed. Coordination: the orchestrator.

## One-command assembly path
```bash
# assemble — refuses unless EVERY lane is ADMIT (dry-run first: --dry-run stages nothing)
python3 deploy/assemble_release.py --spec deploy/release_spec.closeout.json \
    --staging-dir <ABSOLUTE dir OUTSIDE the repo>

# THE one command that closes it out: re-verifies every byte independently, then SEALS
deploy/handoff_release.sh <staging-dir>
```
`handoff_release.sh` re-hashes each staged file against `MANIFEST.json`, re-derives
`manifest_content_sha256`, and writes `SEAL.json` (`uploaded: false`). It never uploads.

## What lifts each refusal

### Every lane (stage1, stage2, stage3, stage4)
| Current refusal | Field that lifts it |
|---|---|
| `status is 'PENDING', required 'ADMIT'` | spec `lanes.<lane>.status = "ADMIT"` — only once that lane's **independent** receipt admits |
| `no source path supplied` | spec `artifacts[].src` + `receipt.src` = the real admitted paths |
| receipt `carries no positive verdict` | receipt `verdict: "admit"` (verdict-like key, positive value) |
| receipt `carries a negative verdict` | **not** `reject` / `fail` / **`pending`** / **`pending_independent_verification`** — the producer's own pre-admission state is *not* an admission, and is refused even under `--lenient-receipt` |
| receipt `contradicts its own body` | `failures: []`, `n_failed: 0`, `self_hash_agrees: true`, `rebuilt_from_admitted_native_bytes: true`, `generator_is_not_verifier: true` |
| `receipt does not name these bytes` | receipt `subject.projection_raw_sha256` (or `subject.raw_sha256`) **== the staged artifact's sha256** |
| `comes from an UNADMITTED producer run` | the artifact must be re-emitted from an **admitted** run — an `…-unadmitted` output is *excluded*, not merely labelled pending |
| `fixture/demo may never be released as production` | no `is_fixture: true`, no `namespace != "production"`, no gene-set `source: "fixture"` |

### Stage-2 — Direct / Temporal (Targets)
| Refusal | Field |
|---|---|
| display projection not bound | `stage2_display_projection.json` + receipt whose `subject.projection_raw_sha256` equals its bytes (`bound_by_receipt: true`) |
| receipt not the right verifier | `verifier_id: "spot.stage02.display_projection.independent_verifier.v1"` |
| per-condition admission | `w10_admission_Rest.json` (schema `spot.stage02_direct_arm_bundle_verification.v1`) |

### Stage-2 — Pathways (**GO-BP only**)
| Refusal | Field |
|---|---|
| `pathway_collection 'reactome' is PARKED` | use `go_bp`. Reactome is parked licence/history only |
| `names no gene-set release_id` / `not dated` | a **dated** GO-BP `release_id` (`YYYY-MM` or `YYYY-MM-DD`) |
| `does not bind the authoritative GO-BP gene-set bundle` | gene-set pin **== `4f8b124432e9c1f75f4780b233bd55a29b04150e36d71e04d183d85e5914d2a6`** (`go_bp_ensembl.genesets.json`) |
| `UNADMITTED producer run` | Rest bundle `47a0d01fd23f705e` (run `pathway-117ccc4-stream1w8-unadmitted`) must pass **W18/W4** independent admission; Stim8/Stim48 (`pathway-117ccc4-prodonly-gobp-w8-unadmitted`) must finish **and** admit |
| admission report wrong lane | must declare the pathway lane's **own** schema `spot.stage02_pathway_arm_external_admission.v1` (a *temporal* report may not admit it) |
| artifact | `pathway_arm_release.json` (`spot.stage02_pathway_arm_release.v1`), from `python -m direct.release_inventory --lane pathway` |

### Release envelope / deployable metadata (`current.json`)
| Refusal | Field |
|---|---|
| `pathway_sources lists PARKED source(s) ['reactome']` | `pathway_sources: ["go_bp"]` |
| `active_pathway_source is 'reactome'` | `null` while unadmitted, or `"go_bp:awaiting_admission"` |
| `active_pathway_source is 'go_bp' but no admitted GO-BP pathway artifact is staged` | the active source must be **derived from the admitted topology** — set it to `go_bp` only once the admitted GO-BP pathway artifact is in the release |

Fixing the producer of this envelope is **W23's** job — see `docs/HANDOFF_W23_pathway_source_topology.md`.
No manual live edits.

### Stage-3 (Drugs) and Stage-4 (PK/Safety)
| Refusal | Field |
|---|---|
| `artifact needs a 'dst'` | keep `dst_from_receipt: true` — the public filename is **taken from the final receipt's subject**, never guessed |
| `dst_from_receipt requires bound_by_receipt` | `bound_by_receipt: true`, so the bytes are the ones that receipt judged |
| `receipt must name exactly ONE subject file` | receipt `subject.artifact_file` (or `projection_file`) |
| `consumes an artifact … with no artifact_sha256` | `consumes[].artifact_sha256` = the exact sha256 of the **independently admitted** upstream artifact (Stage-3 ← Stage-2; Stage-4 ← Stage-3) |
| `consumes … not among that lane's admitted staged artifacts` | the hash must match a staged, admitted upstream artifact |

## Proof of inclusion (after assembly)
- `MANIFEST.json` → `files[].sha256` — **measured** from the staged bytes (never asserted), and
  `manifest_content_sha256` — the content address over `release_id + lanes + routes + files`.
- `SEAL.json` → written by `handoff_release.sh` only after it **independently re-hashes every file**
  and re-derives the content address (generator ≠ verifier). Any drift refuses with exit 2.
- Tests that prove the gates hold: `deploy/tests/test_assemble_release.py` (68 cases) — receipt↔byte
  binding, producer-pending refusal, unadmitted-run exclusion, fixture-not-production, GO-BP pin,
  Reactome parked (collection / artifact / envelope / dist), consumes-admitted-only, shape-from-receipt.

## Reconcile with `agent/ui-final-integration`
Once W23's GO-BP-only `current.json` correction lands, re-run the dry test against the rebuilt dist;
the Reactome/topology refusals must disappear. Then, and only then, is the bundle deployable — by the
deploy lane, not from here.
