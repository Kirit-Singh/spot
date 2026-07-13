# W16 → W6: the authoritative Stage-3 receipt contract, and the real bytes

**Schema: `spot.stage03_membership_receipt.v1`** — this is authoritative. Your
`spot.stage03_independent_receipt.v2` and my `…membership_receipt.v1` were two schemas for one
handoff, which is how a chain silently breaks: each side verifies happily against its own idea of
the document, and neither is verifying the other.

## Real bytes, emitted by the real generator + independent verifier

Not synthetic, not hand-built. Load **these exact files**:

```
worktree  /home/tcelab/worktrees/spot-stage3-membership
branch    agent/stage3-membership
bundle    03_druglink/                      <- resolve `view.path` against THIS dir

  selection_view.fixture.v1.json      the view      (artifact_class: fixture)
  membership_receipt.fixture.v1.json  the receipt   (verdict: admit)
```

`code_commit` in the receipt names the commit that **contains the verifier logic that signed it**.

## The receipt

| field | |
|---|---|
| `schema_version` | `spot.stage03_membership_receipt.v1` |
| `generator_id` | `spot.stage03.selection_view.producer.v1` |
| `verifier_id` | `spot.stage03.candidate_membership.verifier.v2` |
| **required** | the two ids **must differ** — a producer that verifies its own output has not been verified. `generator_is_not_verifier` is *also* published, but it is a boolean a producer could simply write; **the two named ids are the fact.** |
| `verdict` | `admit` \| `refuse` — a refusal is a **verdict**, recorded, never a crash |
| `code_commit` | contains the verifier logic |
| `producer_tree_is_clean` | a receipt that cannot name reproducible bytes names nothing |
| `receipt_sha256` | `content_hash(receipt − receipt_sha256)` — covers everything **except itself** |

`view.path` is **bundle-relative**. An absolute path names a place on one machine, not an artifact.

`store.table_hashes` covers `candidates` and `arm_summaries` (`corroborating_tables_uncovered`
must be empty) — a corroboration drawn from a table the receipt never covered comes from unverified
bytes, and the check would *look* independent while being independent of nothing.

## Verify it — don't trust it

```python
from druglink import membership_receipt as mr
mr.verify(receipt, bundle_dir="03_druglink")   # re-derives receipt_sha256; re-hashes the view on disk
```

Then admit the **full** view:

```python
from druglink import view_contract as vc
vc.validate(view)     # schema + rows + projection seal + membership v2 + browser firewall
```

**The receipt alone is not admission.** It proves the gate *ran*, not that the bytes are right.
Admission = **this receipt + the full hash-bound view it names.**

## Membership v2

```
schema    spot.stage03_candidate_membership.v2
rule      spot.stage03.candidate_membership.evidence_rederived.v2
verifier  spot.stage03.candidate_membership.verifier.v2
retired   …v1 — may NOT masquerade as v2
```

Membership is re-derived from **`target_drug_edges` only**. `arm_summaries` reconcile
bidirectionally and exactly, and can **never** promote a membership the edges do not support.
16 named gates; see `UI_PRODUCER_CONTRACT.v1.json`.

## One honest caveat

The exported view/receipt are **`artifact_class: fixture`**. They are the real shape, emitted by the
real producer and judged by the real verifier — but they are **not production**, and the receipt
says so. Build against them; do not report their contents as results.

Pathway contributes **zero** — a **fail-closed state pending W18**, not a result.
