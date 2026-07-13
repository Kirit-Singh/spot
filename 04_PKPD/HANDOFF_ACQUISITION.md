# Stage-4 public acquisition — handoff to W6 (cross-check) and W9 (v2 records)

**Commit:** `b87c629` (branch `agent/stage4-acquisition-core`, on top of `e410d72`; not pushed)
**Suite:** 755 passed, 5 skipped. Ruff clean. mypy clean on all 11 acquisition modules.
**Skips:** 2 = the opt-in live probe; 3 = pre-existing.
**Live acquisition performed:** one bounded TEMODAR/temozolomide reference probe. Nothing else.
No candidate was acquired, and no drug is ranked, scored, selected or recommended anywhere here.

---

## 1. The deterministic-selection repair (W6's flag)

The flagged seams were not merely fragile — they returned a **wrong answer** on the only drug this
lane has ever probed. TEMODAR's openFDA label declares **two** application numbers, `NDA021029`
(capsule) and `NDA022277` (injection), and its Drugs@FDA record carries **six** products.

| Was | Consequence | Now |
|---|---|---|
| `_first(application_number)` | the approval cross-check ran against an arbitrarily chosen **route** | every declared application survives, canonically ordered, and each is fetched in its **own pinned query** |
| `products[0].marketing_status` | reported one status; the two applications actually differ (`Discontinued` vs `Prescription`) | every product's status survives, sorted and de-duplicated. None is chosen |
| `limit=1` | truncated the result set, so multiplicity was undetectable **in principle** — while `meta.results.total` sat unread | the source's own match total must equal what arrived, or the result set is refused as truncated |

`analysis/selection.py` is the single primitive. Every selection in the layer is now exactly one of:

- **`exactly_one`** — matched on an identity **pin**. Zero and many are both typed refusals, and
  duplicates are never silently collapsed into a choice.
- **`sorted_unique`** — collect-all in canonical order. Nothing dropped, nothing chosen.
- **`assert_result_set_complete`** — a total the source did not report is not a proof of uniqueness
  either.

Reordering a response cannot change an outcome.

Also closed: DailyMed **listing completeness** (a page-1 response claiming 40 elements is not the
candidate set), **set-ID mismatch** on the served document, and the **unversioned-label hole** — a
missing version now refuses (`dailymed_version_unavailable`). There is no `.vunversioned` label; a
placeholder version is a fabricated identity.

Mutations under test: reordered responses, duplicate records, set-ID mismatch, missing version,
truncated result set, missing match total, two active-moiety UNIIs, two applications.

`cross_check_approval` remains as a set-level **invariant**. Pinning each application in its own
query means it is no longer load-bearing on this path; it is kept as the only thing standing
between a future bulk/unpinned query and the subset-of-my-own-approvals bug.

---

## 2. Source boundaries

| Source | Terms | Use |
|---|---|---|
| PubChem PUG REST | no NCBI restriction on molecular data; third-party rights may exist | structure + the descriptors PubChem computes. **Never logD7.4 or pKa** |
| RxNorm (RxNav) | NLM terms; source-vocabulary restrictions | identity crosswalk only |
| DailyMed SPL v2 | **no blanket licence verified** | label identity + labelled safety sections. Live labels **never committed** |
| openFDA / Drugs@FDA | generally CC0, **with marked source exceptions** | approval / application cross-check |
| ChEMBL, UniProt | CC BY-SA 3.0 / CC BY 4.0 | **reuse-only** from the admitted Stage-3 bundle — fetching either raises |
| ClinicalTrials.gov | *not* public domain | no adapter |
| DrugBank | no valid public licence | **forbidden**; `drugbank_id` never populated |

- Raw bytes are cached **outside Git** under a caller-supplied run root, addressed by their own
  SHA-256. The cache refuses to open inside a Git working tree. Git holds synthetic fixtures only.
- `method/sources.json` previously called DailyMed "Public domain (NLM DailyMed)". Corrected —
  it is not, and the terms URL plus the in-use-vs-approved caveat now ride on every record.
- **CNS-MPO stays incomplete** under a public-only rule: no ledgered source supplies logD7.4 or a
  most-basic pKa (XLogP3 is a logP at no stated pH). This must not block the measured-exposure,
  transporter, label-safety or NEBPI lanes.
- Root `DATA_LICENSES.md` still collapses openFDA/FAERS and calls ClinicalTrials.gov public
  domain. Stage 4's ledger is correct on both; fixing the shared root file is a maintainer action
  outside this lane.

---

## 3. `organ_system` (W9 v2, optional) — the boundary

Source-backed or `unspecified`. **Never inferred.** Field names are W9's own
(`evidence_records.Provenance`), not new ones:

```
organ_system            a controlled value or the source term, VERBATIM
value_kind              controlled_value | source_term | none
evidence_state          observed | not_evaluated
source_key, source_record_id
setid, label_version, raw_response_sha256
section_code, subsection_code, locator
extraction_transform, reason
```

**`ORGAN_SYSTEM_SPECS` is empty, and that is the finding — not an omission.** No ledgered source
carries the field:

- SPL/DailyMed has LOINC-coded **sections**, not an organ-system attribute. Recognising an
  adverse-reaction heading as a MedDRA System Organ Class requires the MedDRA vocabulary, whose
  licence is not established for this project — that route is a licensing problem *and* a
  classifier.
- openFDA carries **pharmacologic class** (EPC/MoA/PE/CS). A pharmacologic class is not an organ
  system.
- PubChem and RxNorm carry neither.

So every extraction returns `unspecified` / `not_evaluated` — **with the record it was looked for
in attached**, so "unspecified" can never be read as "never checked". The absence is also stated in
the acquisition manifest's `missing` lane.

`refuse_inferred_organ_system` makes classification from a target, gene, mechanism, pharmacologic
class or drug name **raise**. Adding a value is a reviewed `OrganSystemSpec` entry naming the
source and the locator — not a code change inside an adapter. No new external dataset was added,
and none is required.

---

## 4. Still open — W9's lane, untouched here

v1 remains frozen. This lane did not edit the potency/exposure record schemas, the NEBPI
calculation, `evidence_bundle.py` or `run_stage4.py`'s evidence path.

1. **Carry v2 fields end-to-end.** Schema-declared is not wired: v2 fields must travel through the
   evidence bundle and the run path, and be independently checked — not merely declared.
2. **`organ_system` consumption.** Acquisition emits the block above (see
   `acquisition_receipt.json` → `identities_acquired[].identity.organ_system`, and the
   `organ_system` entry in the manifest's `missing`). Binding it onto a v2 record is W9's.
3. **`contract_profile.py`** is referenced by `schemas_export` / README in W9's tree. It does not
   exist in this lane (verified absent), so nothing here masks the broken reference.
4. **Fraction-unbound** uniqueness / ownership / provenance checks are absent and are W9's.
5. **Acquisition covers identity only.** Potency, exposure, transporter and primary-literature
   lanes remain `not_evaluated`, in writing. Their schemas need the structured fields the source
   audit lists before an adapter is worth writing.

---

## 5. Entry points

```
python -m analysis.run_acquire --stage3-bundle <dir> --run-root <dir>        # offline, no network
python -m analysis.run_acquire --stage3-bundle <dir> --run-root <dir> \
    --acquire-identity <moiety> --allow-network [--dailymed-setid <setid>]
```

Contract: `schemas/spot.stage04_acquisition_manifest.v1.schema.json` (generated from the model).
Method detail: `METHODS.md` §7b. Source terms: `method/acquisition_sources_v1.json`.

Identity acquisition is per-moiety and explicit — there is no bulk candidate sweep. A name that is
not a queued Stage-3 candidate is recorded as a `reference_probe` and can never be reported as a
candidate.
