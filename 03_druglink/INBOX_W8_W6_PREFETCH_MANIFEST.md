# W16 → W8, W6: PREFETCH-ONLY drug-candidate manifest (ready now)

A **work list, not a result.** Emitted from W3's real Direct display projection intersected with
the admitted global universe store. Available immediately — does not wait on the pathway lane.

## The artifact

```
path             /home/tcelab/.spot-runs/stage3-universe-20260713/prefetch/
                   prefetch_manifest.353b79206c0a0a7f.json
raw_sha256       546110cc05d56263edb1d7ab6ab189ba1fdff079cce26bf15651d81a8545095e
manifest_sha256  353b79206c0a0a7f2720cc414c734fcf22490fdfa10439f2f0e3d9329722db8b
schema           spot.stage03_prefetch_manifest.v1
artifact_class   prefetch_only
```

## Counts

| | |
|---|---|
| Direct arms | 60 |
| target ids in Direct prefixes (union, deduped) | 2,841 |
| resolved in the admitted universe | **2,841** (0 unresolved, 0 ambiguous) |
| targets carrying any public-source record | **101** |
| **prefetch records (what W8 fetches)** | **455** |
| distinct molecules | 439 |

2,841 targets resolve; 101 of them carry drug evidence. The other 2,740 resolve cleanly and simply
have no drug — that is a **finding, not a gap**, which is why it is counted explicitly rather than
left to be inferred from the difference between two other numbers.

## Bindings (every one re-derived, never copied)

```
stage2_display_projection.raw_sha256          2d9dc1fe99226ba6d938a7103860feb24b902fb3de76003696f66173fae2e70e
stage2_display_projection.projection_self_sha256  recomputed and compared — not read
universe_store.store_id                       625c921fce2daf60b69fb0ae33570a9f074a0a0042b1717ee2111f81c1160bff
universe_store.typed_universe_sha256          1c19db2b5d666a8f33c715cb634cf111953c7cdd6c23d082e9b375643a3e7cc8
```

## Each record carries

- **typed target identity** — `target_id` + `target_id_namespace`
- **source record identity** — `source_record_id`, `mec_id`, `assertion_lane`
- **drug identity** — `molecule_chembl_id`, `target_chembl_id`
- **the exact public-source lookup key** — `source_locator`, `source_release`
- `action_type_source`, **verbatim and uninterpreted**

## What it is NOT, and cannot become

`artifact_class: prefetch_only` is a value Stage-3's own `artifact_class.require()` **REFUSES**.
Stage-3 has exactly two classes, `analysis` and `fixture`, and this is neither — so the artifact
**cannot be admitted as a Stage-3 analysis by construction**, not by convention. Any code path
that tries raises `ArtifactClassError` before reading a row.

**No score. No rank. No cross-arm ordering. No combined objective. No candidate selection.**
Records are sorted by identity (`namespace`, `target_id`, `source_record_id`) — an order that
carries no claim. A prefetch list that quietly acquired an ordering would be a ranking wearing a
work-list's clothes, and the first consumer to sort by it would be reading a claim nobody made.

## One thing worth knowing

The projection's rows carry `target_id` and `target_symbol` but **no namespace**. Stage-3 does not
guess one: the admitted universe holds 11,522 Ensembl ids **and** 4 gene symbols, so a shape-based
guess types most rows right, mistypes the rest, and a mistyped row fails the exact-identity join by
simply finding no drug — indistinguishable from a target that genuinely has none. Every id is
resolved **by the store**, which is the authority on typed identity. A target resolving to more than
one typed identity is refused and reported as ambiguous, never silently collapsed to one.

(Here: 0 ambiguous, 0 unresolved.)
