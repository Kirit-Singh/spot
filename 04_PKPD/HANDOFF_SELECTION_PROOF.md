# The selection proof: what each field means, and the attacks that must stay refused

**Owner:** Stage-4 integration. **For:** W8 (acquisition), W9 (schema/closeout).
**Contract:** `spot.stage04_evidence_inputs.v2` · `SourceAcquisitionRecord` · `analysis/materialize.py`

A record that says *"I fetched the right thing"* proves nothing. These five fields exist so a reader
can **check** that claim against the source's own arithmetic. Every defect below was a case of the
record answering a question **the source was never asked**.

## The five fields

| field | means | never |
|---|---|---|
| `selection_disposition` | **how** this record was chosen | `None` on an observed fetched row |
| `selection_pin` | the identity it was pinned on | a value read out of the query string |
| `match_total_reported` | **the source's own count of matches** | a number Stage 4 supplies |
| `records_returned` | how many rows actually came back | assumed `1` |
| `result_set_complete` | did we get the whole set | `bool(None)` |

`match_total_reported` is **the source's number or nothing**. openFDA states `meta.results.total`;
DailyMed states `metadata.total_elements`. It is the only value that can *refute* a uniqueness
claim, so Stage 4 may never author it — a total we invented cannot contradict us.

## The three dispositions, by endpoint

| disposition | endpoints | total | `result_set_complete` |
|---|---|---|---|
| `exactly_one` — a **search** matched on a pin | DailyMed listing, openFDA `drug/label`, Drugs@FDA | **required** | true/false, derived |
| `sorted_unique` — a **name-to-list** query, collect-all in canonical order | RxNorm `rxcui.json?name=`, PubChem `compound/name/{name}/cids` | if stated | true/false, derived |
| `identity_get` — one **named record** fetched by id | DailyMed `/spls/{setid}.xml`, PubChem **property-by-CID** | **null** | **null** |

Two distinctions that were each gotten wrong once:

**A name-to-list query is not an identity GET.** `compound/name/{name}/cids` and
`rxcui.json?name=` take a *name* and return a *list*. Labelling either `identity_get` claims an
identity **the request never asserted** — the endpoint was never told which record we wanted. They
are `sorted_unique`, and `records_returned` is the length of the parsed list.

**An identity GET has no completeness boolean.** There is no result set, so completeness has nothing
to be true *or* false about. `result_set_complete=true` invents a claim the endpoint never made; and
`false` is *worse than* absent, because it reads as **"we looked, and the set was truncated"** — a
different assertion again. Both stay **null**. W8's gate correctly rejects a completeness boolean
invented for a no-result-set endpoint.

## The attacks — each one is a live test

`tests/test_selection_proof_not_fabricated.py` (17)

1. **The pin appears inside the query.** The old `_selection` decided a fetch was "by identity" if
   `stable_record_id` was a **substring** of `canonical_query`. A query that *contains* an id is not
   a query *for* that id. A record stating no proof now reports `None` — not a disposition, not a
   total, not a completeness flag.
2. **openFDA reported 40 and handed back 1.** The old code emitted `match_total_reported=1,
   records_returned=1, result_set_complete=true`. The source's real total now travels with the bytes
   from fetch to bundle. **A fabricated completeness claim is the exact truncation these fields
   exist to expose, wearing the proof's clothes.**
3. **An observed, Stage-4-fetched row with no disposition** → refused,
   `acquisition_row_without_selection_proof`. Silence is not a disposition.
4. **A reused Stage-3 row that cannot name its upstream** → refused,
   `reused_row_cannot_name_its_upstream_selection`. Reuse *delegates* the proof; it must say to whom
   (`stage3_source_record_id`).
5. **A source key written where a canonical query belongs.** Nobody can re-issue the string
   `"chembl"`. The exact query, its `canonical_query_sha256`, and the Stage-3 source record id are
   all preserved.
6. **`identity_get` carrying a total, or any completeness boolean** → refused by the validator.
7. **An unreported total defaulted to 1** → refused. `None` means the source reported nothing; `1`
   is a claim, and it is not ours to make.
8. **`bool(None) → False`** — the last one found, and the subtlest: `_selection` cast the field, so
   an honest null from an identity GET was silently rewritten to *incomplete*. Null now survives
   record → row → parquet → verifier. **A test that asserted `is False` here had itself encoded the
   coercion**, which is how it lived so long.

## The seam that made it real

`record_from_response(...)` originally accepted **no proof parameters**, so every `fetched_public`
record was born with `None` and the gate above would have rejected *every* real observed row. The
proof is now threaded from each adapter's parse through to the record, and five tests drive the
**actual adapters** over the offline transport and assert on what they wrote — a gate that only ever
sees hand-built records is a test-only repair, which is the same shape as the defect it was meant to
catch.
