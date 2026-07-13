# Stage-3 → UI / packer / Stage-4: the producer contract you pin

Machine-readable: **`UI_PRODUCER_CONTRACT.v1.json`** · `contract_sha256 78b6f31a9a56abfc…`
This is the **producer** contract. It is not a UI wrapper; it is what the UI pins.

## Entry point — the only one

```python
from druglink import view_contract
view_contract.validate(view)      # raises on any refusal; returns the view
```

`validate` runs: **schema → row columns → projection seal → candidate membership (v2) → browser
firewall.** All five. Nothing less is admission.

> **The membership gate alone is NEVER admission.** It proves *belonging*, not *bytes*. A consumer
> admits the **full hash-bound view** plus a verifier receipt naming this gate.

## Identity

| | |
|---|---|
| `view_content_sha256` | `content_hash(view − {view_id, view_content_sha256})`, with each projected table's rows canonicalised to the store's total order (a row set is a set; `arm_evidence` order is meaning and is **not** sorted) |
| `view_id` | `view_content_sha256[:16]` |
| projection seal | per table: `raw_sha256` (the store file's bytes) + `content_sha256` (the projected rows) + `row_count` + `schema_id` |
| membership rule | hashed into `selection_view.vocabularies()` → **into every view id**. Weakening the rule **moves the identity** (verified: `069d53db… → 07f460f6…`). |

## Membership — v2

```
schema    spot.stage03_candidate_membership.v2
rule      spot.stage03.candidate_membership.evidence_rederived.v2
verifier  spot.stage03.candidate_membership.verifier.v2
retired   …v1 (may NOT masquerade as v2 — a receipt for the weaker rule must not pass for this one)
```

**Membership is re-derived from `target_drug_edges`. Only the edges.**
`arm_summaries` are redundant consistency evidence: they must reconcile **bidirectionally and
exactly** (presence both ways, `edge_ids`, `n_edges`, evidence state) — and a summary can **never**
promote a membership the edges do not support. *A summary summarises an edge; it can never be the
evidence that an edge does not exist.*

## The filter rule

```
selected_gene = set(view.selected_arms.gene_arm_keys)          # EXACT strings, whole key
shown         = { c for c in candidates
                  if derive_from_edges(c) ∩ selected_gene }    # never prefix, never a name
```

- **Never a prefix.** `direct|X|decrease|Rest` and `…|Stim48hr` differ *only* in the context tail.
- **Never a display name.** Two arms can share a label. **The full key is the identity.**
- **Never the candidate's own claim.** `arm_keys` is the **global** membership (180 arms in the
  published view against 2 shown). Read it as the view's arms and you reject every reusable
  candidate.

## Typed evidence state

Every active arm must sit in the typed column its **edges** carry
(`directional_evidence_status`) — not the one the summary claims:

`observed_perturbation_arm_keys` · `inverse_direction_hypothesis_arm_keys` ·
`opposed_arm_keys` · `pathway_hypothesis_arm_keys` · `unresolved_arm_keys`

Moving an arm from *observed* to *opposed* leaves the arm set and every hash intact **and reverses
the science.** It is refused.

## Roles and endpoints — ordered, and the selection's

`selection_roles` on **every** edge and summary is re-derived against `selected_arms.arms`:
**A = `away_from_A` at `conditions[0]`, B = `toward_B` at `conditions[-1]`.**
One arm may carry **both** roles — that is the reusable design working, not a degenerate question.
Reversing `conditions` reverses the question while every row and every hash stays as it was. Refused.

## Pathway context — a separate domain

Joined on the **exact typed target** `(target_id, target_id_namespace)` taken from the candidate's
own edges, then intersected with `selected_arms.pathway_context_arm_keys`.
**Pathway context NEVER promotes a candidate into a question.**

> Pathway currently contributes **zero**. That is a **fail-closed state pending W18** — whose
> verifier crashes, so its refusals were vacuous — **not a result, and it must not be pinned as one.**

## The 13 named gates

See `UI_PRODUCER_CONTRACT.v1.json → gates`. Each has a test that makes it **fire**, against the real
published view, with the honest view admitted first so no refusal is vacuous.
