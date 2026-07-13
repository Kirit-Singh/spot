# Stage-4 methods, provenance and limitations

Every scientific number in Stage 4 binds to a public source response (URL/record id +
access date + **raw SHA-256** + the exact extraction transform). Nothing is imputed,
averaged, or remembered. **Claude/LLM output is never a source**: there is no
`model_output` source type, and an LLM-shaped assigner is refused.

---

## 1. Primary sources

| id | Source | Bound by |
|---|---|---|
| `grossman2026_nebpi` | Grossman et al., Neuro-Oncology 2026. **DOI 10.1093/neuonc/noag051**, **PMCID PMC13338342**, CC BY 4.0 | BioC XML, raw sha256 `8bb0324d…b23f47` (re-verified 2026-07-11) |
| `wager2010_cnsmpo_jats` | Wager et al., ACS Chem Neurosci 2010;1(6):435–449. **DOI 10.1021/cn100008c**, **PMCID PMC3368654** | JATS XML, raw sha256 `cf3816cf…3debc7623`. **Metadata + abstract only** (publisher-limited): it contains no tables and cannot encode the functions |
| `wager2010_cnsmpo_pmc_web` | The same article, PMC-rendered full text (contains Table 1, Table 2, Methods) | HTML, raw sha256 `731fe2b7…16113133`, accessed 2026-07-11 |
| `dailymed_spl_structure_probe` | Live DailyMed SPL v2 responses | Used **only** to verify XML paths + LOINC codes. No drug content from the probes is used as evidence |

Raw documents are **not bundled** in the repo (public-data-only rule + ACS copyright).
They are cached outside it, at `/home/tcelab/.spot-runs/20260712T021343Z/…`, and pinned by
hash so a reviewer can re-verify byte-for-byte. All method parameters live in
`method/*.json`, whose file hashes feed `scorecard_set_id`.

---

## 2. CNS-MPO — Wager 2010 v1, exactly as published

Six inputs only: **ClogP, ClogD(7.4), MW, TPSA, HBD, most-basic pKa**. Each is transformed
to a desirability value `T0 ∈ [0,1]`; the score is their **sum**, range **0–6**, equal
weights.

**Table 1 (transcribed verbatim):**

| property | transform | T0 = 1.0 | T0 = 0.0 |
|---|---|---|---|
| ClogP | monotonic decreasing | ≤ 3 | > 5 |
| ClogD (7.4) | monotonic decreasing | ≤ 2 | > 4 |
| MW | monotonic decreasing | ≤ 360 | > 500 |
| TPSA | **hump** | 40 < TPSA ≤ 90 | ≤ 20; > 120 |
| HBD | monotonic decreasing | ≤ 0.5 | > 3.5 |
| most-basic pKa | monotonic decreasing | ≤ 8 | > 10 |

Linear between inflection points (Figure 3): monotonic decreasing is `1.0` at `x ≤ x1`,
falling linearly to `0.0` at `x ≥ x2`; the hump rises `0→1` across `[x1, x2]`, plateaus at
`1.0` on `[x2, x3]`, falls `1→0` across `[x3, x4]`.

**CNS-MPO is a heuristic.** It is a physicochemical design-space desirability score. It is
**not** measured brain permeability, **not** a probability of CNS exposure, **not**
Kp,uu,brain, and it **can never satisfy an NEBPI Part-II branch** — physicochemistry is a
Part-I input, not a Part-II branch. `total ≥ 4` means nothing beyond "high MPO score".

**Calculator policy** (`method/calculator_policy_v1.json`). Wager's Methods state: *"Biobyte
for ClogP calculations, ACD/Laboratories for ClogD at pH 7.4, and ACD/Laboratories for
pKa."* So:

- **RDKit is forbidden for ClogD(7.4) and most-basic pKa** — RDKit implements neither. Such
  a value would not be a worse estimate; it would be fabricated. Mechanically rejected.
- RDKit *may* supply TPSA (its implementation is the Ertl method Wager cite), MW and HBD,
  recorded as `published_method_equivalent` with version.
- A different-but-real calculator (e.g. RDKit Crippen logP for ClogP) is allowed as a
  `documented_deviation` and is **always surfaced**, never silent.
- Two conflicting records for one property → `ambiguous_multiple_sources`; Stage 4 will not
  pick one.

**No imputation.** Any of the six absent, non-finite, or from a disallowed calculator →
`status = incomplete`, `total = null`, `missing_inputs` explicit. Five of six is not a
score; it is a lower score.

**Published golden checks** (Table 2, "CNS MPO Scores and Individual Transformed Scores
(T0) for Selected Drugs"): alprazolam 5.8, zolpidem 5.4, paroxetine 4.2, risperidone 5.5,
methylphenidate 4.8 — the six published components sum to the published total in every case.
These are *the authors'* values for those drugs; **Spot makes no claim about them.**

**There is no end-to-end golden.** The 2010 Table 2 publishes the six *transformed*
components but **not** the raw property values behind them, and the Supporting Information
holding the raw values is paywalled (ACS returned **HTTP 403**). So the published goldens
above validate the equal weighting, the 0–6 summation and the published rounding — they
**cannot** validate the raw-property → T0 transforms end to end. An end-to-end compound
golden requires raw published property values; Stage 4 holds no primary-source bytes for
one, and it remains **deferred to independent review**.

The row below is **not** that golden. It is carried in
`method/cns_mpo_wager2010_v1.json` as `unverified_derived_regression_example`
(`is_a_published_golden: false`, `counts_toward_source_verified_goldens: false`) — an
**internal regression fixture** that pins current engine behaviour:

| ClogP 3.7 | ClogD 2.7 | TPSA 90 | MW 375 | HBD 1 | pKa 9 | total |
|---|---|---|---|---|---|---|
| 0.65 | 0.65 | 1.00 | 0.89 | 0.83 | 0.50 | **4.5** |

**No bytes of the 2016 article (DOI 10.1021/acschemneuro.6b00029) were ever acquired or
hashed** — `pubs.acs.org` returned HTTP 403 and the DOI is not in PMC. `document_acquired:
false`; `python -m analysis.source_verify` reports it **`not_acquired`**, and it is never
counted as verified. These six values were copied from a prior audit report, not
transcribed from primary-source bytes, and they are then pushed through the very transforms
they would be checking: agreement proves only that this implementation is self-consistent.
It is circular, and it cannot corroborate itself.

**4.5 is not a cutoff.** It is the total of this one worked example on the 0–6 desirability
scale — not a threshold, not a validated value, not a universal one. Nothing in Stage 4 may
cite this row as evidence that the implementation reproduces a published result. To promote
it: acquire the lawful public 2016 bytes, record the locator and raw SHA-256 in
`method/sources.json`, transcribe the row independently *from those bytes*, and only then
does it become a published golden.

---

## 3. NEBPI — Grossman 2026, criterion-level

**Part I** (importance graded *"from A (best) to F (worst)"*):

| criterion | importance | can satisfy a Part-II branch? |
|---|---|---|
| Physical characteristics of drug | A | no |
| Permeability in normal animal brain | A | no |
| Known MEC (potency) | A | no — but it is **required context** for every PK branch |
| PK demonstrating MEC in NEB | A | **yes** |
| Relevant PD effects in NEB | A | **yes** |
| CSF drug levels | C | no |
| Responses in contrast-enhancing lesions | C | no |
| In-vitro BBB model permeability | D | no |
| Radiographic response in NEB | *(not in Table 1)* | **yes** |

**Part II (exact branch logic, transcribed):**

```
sufficiently_permeable   = PK therapeutic in NEB(a)  OR  relevant PD in NEB
                                                     OR  radiographic response in NEB
insufficiently_permeable = low PK in NEB(a)          AND no relevant PD in NEB
                                                     AND no radiographic response in NEB
impermeable              = little/no drug in NEB(a)  AND no relevant PD in NEB
                                                     AND no radiographic response in NEB
(a) = "Accounting for potency."
```

Load-bearing consequences, all tested:

- **Absent evidence is never "impermeable."** `not_evaluated` can never satisfy a
  "no PD" / "no radiographic response" conjunct. Only `observed_absent` **with an adequate
  assessment** can. An inadequate look is not evidence of absence.
- **A PK branch with no bound MEC/potency context satisfies nothing** — footnote (a) makes
  every PK branch a comparison *against the MEC*.
- **Descriptors, CSF, in-vitro BBB models, normal-animal-brain permeability and responses in
  enhancing lesions can never produce a positive class**, alone or together.
- If the complete logic is unsupported: `nebpi_status = not_classifiable`, `class = null`.
- **A class belongs to a context, not to a drug.** Every NEBPI result is keyed on
  `(active moiety × route × formulation × dose × schedule × tumour × potency)`. The source's
  own example: methotrexate is *impermeable* at standard dose for glial neoplasms and
  *sufficiently permeable* at high-dose IV for PCNSL. A drug-level class is structurally
  unrepresentable in this engine.
- Every result carries a **branch proof** (each branch: required / observed / satisfied /
  blocking reason / supporting observation ids) and a **counterfactual** (exactly what would
  have to be observed to change the outcome).

**Delivery gate.** `local_CNS_target_engagement_required` → `nebpi_primary_gate = true`.
`systemic_immune_priming` → `false`: NEB evidence is retained and displayed, but such an
agent is **never failed solely for low direct NEB exposure** (the source explicitly excludes
"immunotherapies that activate systemic lymphocytes that travel to the brain").
`delivery_requirement_uncertain` → `null`, and is never silently treated as either.

> **Interpretation flagged for review.** "Radiographic response in NEB" is a Part-II branch
> in Table 2 but is **not** one of the eight rows of Table 1, so the source assigns it no
> importance letter. Stage 4 models it as its own criterion with `importance: null` rather
> than folding it into "relevant PD in NEB" or into the *enhancing*-lesion row (importance C),
> which is a different criterion. Also: footnote (a) is attached to all three PK branches, so
> Stage 4 requires potency context even for "little to no drug in NEB" — conservative in the
> safe direction (it makes "impermeable" *harder* to assert).

---

## 4. Exposure and potency compatibility

One row per **actual measurement**. `Kp` and `Kp,uu,brain` are carried **only when the source
reports them**; a `Kp,uu,brain` on a CSF measurement is rejected at the record level — the
blood-CSF barrier is not the BBB, and Stage 4 will not infer one from the other.

A margin is computed **only** when: the active moiety matches (a salt, prodrug or metabolite
is not the same molecule); free/total states are compatible; units are in an explicit registry
and in the same family; the potency's biological context is relevant (or linked to this one by
an explicitly sourced relevance link); and route/dose/schedule are known. Otherwise
`status = not_computable` with an exact `reason_code`. There is no best-effort margin.

Only an **MEC** or a declared **target concentration** may be a margin denominator. An IC50 is
not an MEC: converting one needs an unbound fraction and a declared transform, and Stage 4
supplies neither silently.

---

## 5. Safety and named GBM scenarios

Adapters are **pure parsers over cached bytes** (`parse_dailymed_spl`, `parse_openfda_label`,
`parse_ema_product_information`) — no network, ever. Each row binds setid / application
number, active moiety, label version, effective date, the exact LOINC-coded section, and the
raw response hash. **A label is never summarized from memory.**

LOINC section codes, read from live SPLs (not recalled): boxed warning `34066-1`,
contraindications `34070-3`, warnings & precautions `43685-7`, drug interactions `34073-7`.
One evidence row per finding — a boxed warning with three bullets is three rows.

Evidence states, and only these five: `label_supported`, `literature_supported`,
`signal_only`, `no_evidence_found`, `not_evaluated`.

- **`no_evidence_found` never renders as safe.** It is a claim about the *search*, not about
  the drug, and it cannot even be recorded without naming the sources searched. Every row
  carries `renders_as_safe: false`.
- `not_evaluated` (nobody looked) is distinct from `no_evidence_found` (we looked, found
  nothing). An empty scenario cell is `not_evaluated`.
- **FAERS is not accepted** in this pass. If ever accepted it is `signal_only` and can never
  establish incidence, causality, safety or a contraindication.

Five named GBM scenarios (temozolomide, radiation, corticosteroid exposure, antiseizure
therapy, perioperative setting) × eight interaction types (PK interaction, overlapping
toxicity, marrow effects, infection liability, immune activation/autoimmunity, bleeding,
QT/cardiac, mechanistic antagonism) are **kept separate** — 40 independent cells, never merged.

---

## 6. Firewall, identity and verification

**`scorecard_set_id`** = first 16 hex of `sha256(canonical_json({...}))` over: the Stage-3
binding (including the **candidate row content hash**), the Stage-4 method version, **every
method file hash**, the config hash, the **evidence-input hash** (every property, potency,
transporter, exposure, delivery, NEBPI and safety record — including each one's calculator and
raw response hash), the source-registry hash, and the **environment lock hash**.

A biology-only identifier (a drug name, a target, a Stage-3 `candidate_set_id`) is **never** a
cache key: swap the ClogD package and the score changes while the biology does not.

The firewall rejects, with a stable code: `schema_unknown`, `schema_invalid`, `hash_missing`,
`hash_mismatch`, `duplicate_candidate_identity`, `ambiguous_moiety_mapping`,
`namespace_escalation`, `path_traversal`, `unbound_source_record`, `source_hash_mismatch`.
**Research-only stays research-only**: accumulating PK/safety annotations in Stage 4 never
promotes a candidate to production. Stage 4 adds evidence; it does not launder provenance.

**Verification is independent of the generator.** `verify.py` re-derives the id from the
inputs, re-reads every artifact, recomputes content and file hashes, re-checks column order,
dtypes and row order, and **re-derives the scientific claims from the emitted document** — a
class with no satisfied branch fails, an incomplete CNS-MPO with a total fails, a safety cell
that renders as safe fails. It also **recomputes the Stage-3 candidate row hash rather than
trusting the declared one** (a row edited in place with its hash left untouched would
otherwise ride through — that gap was found by a test).

Canonical hashing: sorted keys, no whitespace, floats rounded to 10 dp, NaN/Inf rejected,
timestamps / display labels / machine-local paths excluded. Publication rounding is
ROUND_HALF_UP (Python's half-to-even does not reproduce printed tables).

---

## 7. Artifacts

Written **atomically** to `outputs/<scorecard_set_id>/` (temp dir + swap: a reader sees the
whole set or nothing):

`delivery_evidence.parquet` · `transporter_evidence.parquet` · `exposure_evidence.parquet` ·
`safety_evidence.parquet` · `scorecards.json` · `manifest.json` · `verification.json` ·
`selection.json`

Each parquet table has a fixed column order, fixed dtypes and a fixed sort key
(`schemas/spot.stage04_evidence_tables.v1.schema.json`), and two hashes: `content_sha256`
(canonical rows — writer-independent, the scientific identity) and `file_sha256` (the bytes).
`scorecards.json` carries a per-candidate **provenance chain**: every displayed field → its
source response hash and the deterministic transform that produced it.

---

## 7b. Public acquisition — `spot.stage04_acquisition_manifest.v1`

The source audit's §4.7 finding was that a Stage-4 source record carried an access *date* and
nothing else a reviewer could reconstruct the request from. The acquisition manifest is the
repair: per response — canonical URL + query, `accessed_at_utc`, HTTP status, media type, an
**allowlisted** subset of response headers (per-request noise would make the same document hash
differently), source release/`last_updated`, licence **and terms URL**, raw byte count +
SHA-256, a stable `content_sha256` + declared rule where the transport envelope is volatile, the
**adapter code hash**, the exact extraction transform, and a review status.

**Three origins, no path between them.** `fetched_public` must show its locator, its terms and
its bytes (HTTP 200, cached under the run root) or it is refused. `reused_from_stage3` is carried
verbatim. `synthetic_fixture` is hashed and can never become public.

**Bytes live outside Git.** `RunRoot` refuses a cache inside the working tree: a live label
committed by accident is a licensing problem that no later `git rm` undoes. DailyMed in
particular has **no verified blanket licence** — `method/sources.json` previously called it
"Public domain (NLM DailyMed)", which was an overclaim and is corrected. openFDA is generally
CC0 **with marked source exceptions**. ClinicalTrials.gov is **not** relabelled public domain and
has no adapter. DrugBank is forbidden and `drugbank_id` is never populated on this path.

**ChEMBL/UniProt are reuse-only.** Stage 3 acquired, hashed and released those responses, and
Stage-4 gate 1 re-derives their table hash at admission. Re-querying them would mint a second,
unreconciled provenance for the same number, so `assert_fetch_permitted` raises. Stage 3 stores
its canonical query as a SHA-256; it is carried as a SHA-256, never reconstructed as text.

**Deterministic label selection.** Discovery → **exactly one product, or an explicit set-ID pin,
or a refusal that names every candidate**. Live, `drug_name=temozolomide` returns 20 products, so
"the first hit" would have read a repackager's label instead of TEMODAR. The served document must
also *be* the version the listing offered (`dailymed_version_conflict`), and the label must tie to
a Drugs@FDA application (`approval_conflict` → the safety lane stays `not_evaluated`).

**Identity converges or the candidate is refused** (`identity_converged` → refuse_candidate).
PubChem, RxNorm, DailyMed and Drugs@FDA claims are collected separately — no source's identifier
is silently preferred over another's — and any disagreement refuses. An administered form that is
not the active moiety needs an explicit, **sourced** mapping; a shared InChIKey first block is a
salt/free-base relationship, not a match.

**CNS-MPO stays incomplete under a public-only rule.** PubChem supplies neither logD7.4 nor a
most-basic pKa (XLogP3 is a logP at no stated pH), and `assert_descriptor_is_public` refuses to
let either be substituted. Per the audit, that incompleteness must **not** block the measured
exposure, transporter, label-safety or NEBPI lanes.

**One live probe.** `tests/test_live_reference_smoke.py` (opt-in, `SPOT_STAGE4_LIVE=1`) acquires
TEMODAR/temozolomide — the GBM standard of care, and emphatically **not** a Stage-3 candidate, so
it can never be mistaken for one. It re-proves the e410d72 nested-warning repair against the real
innovator SPL, whose bytes hash to `9437c054…f652a29ce7` (275 112 bytes, v40) — the same digest
the independent source audit recorded.

---

## 8. Limitations, and what is *not* done

1. **Fixture-only. No real result.** Every candidate is a labelled `FIXTURE-*`; every
   evidence record is synthetic and labelled. **No real drug is asserted to be safe,
   brain-permeable, NEBPI-classified or clinically suitable.** Nothing here is production-ready.
2. **Stage 3 has not landed.** `03_druglink/` is scaffolding and emits nothing. The Stage-3
   contract here is **provisional and adapter-bound**, authored unilaterally by Stage 4 and
   **not agreed with Stage 3** (`stage3_contract_status` is stamped into every artifact).
   Expected reconciliation: a Stage-3 → Stage-4 **adapter** plus a schema version bump — *not*
   a silent widening of these models.
3. **No real-source evidence loader is wired.** Passing a real `--candidate-set` validates
   against the provisional contract and then **refuses** (`no_real_evidence_adapters_wired`):
   an empty evidence lane is not a result. Fetching real DailyMed / openFDA / literature
   records requires independent review first.
4. **Fail-closed gates.** The production pointer is never written (fixture inputs, fixture
   sources, research-only namespace, or simply "no real Stage-3 artifact yet"). `selection.json`
   is always `no_selection_emitted`. **There is no `--force`.**
5. **There is no end-to-end golden, and the Wager-2016 row is not one.** No bytes of the 2016
   article were ever acquired or hashed (ACS 403; not in PMC), so it is `not_acquired` and
   nothing is validated against it. The 3.7/2.7/90/375/1/9 → 4.5 row is an internal
   regression fixture (`unverified_derived_regression_example`) — not a published golden, not
   primary-source validation, and **4.5 is not a cutoff of any kind**. Because it is checked
   through the very transforms it would be checking, its agreement is circular. Acquiring the
   document is an outstanding public-source prerequisite (§2).
6. **The EMA adapter's cached shape is unverified** against a live EMA response
   (`EMA_ADAPTER_STATUS = shape_declared_unverified_against_live_source`). It must be reviewed
   before any EMA record is admitted.
7. **The Wager PMC HTML is a volatile representation.** The byte hash pins exactly what this
   build read; NLM may re-render the page. The article (DOI/PMCID) is immutable and the
   extracted parameters are pinned separately and are the reviewable unit.
8. **`_requirements/base.lock` still lacks pandas/pyarrow.** Stage 4 pins its own hashed lock
   rather than editing shared files. Folding pyarrow into `_requirements/base.in` via
   `pip-compile --generate-hashes` is a **maintainer follow-up**.
9. **Not reviewed by a clinician or pharmacologist.** The NEBPI transcription and the two
   interpretation calls flagged in §3 need domain review before any real use.
10. **Acquisition covers IDENTITY only.** §7b acquires identity, label selection and the approval
    cross-check. It does **not** acquire potency, exposure, transporter or primary-literature
    evidence — those lanes remain `not_evaluated`, in writing, and their schemas need the
    structured fields the audit lists (§4.2, §4.4) before an adapter is written for them. No
    candidate has been acquired: identity acquisition is per-moiety and explicit, and the only
    moiety run live is a reference probe.
11. **Root `DATA_LICENSES.md` still collapses openFDA/FAERS and calls ClinicalTrials.gov public
    domain** (source audit §4.6). Stage 4's own ledger (`method/acquisition_sources_v1.json`) is
    correct on both points; fixing the shared root file is a **maintainer follow-up** outside
    this lane.

---

## Reason codes — the sentence behind each code

Stage 4 emits **typed codes**, not sentences, wherever an explanation would otherwise be free
prose. A sentence that lives only in the emitter is bound by nothing: a resealed release could
rewrite the reason a branch failed, or the reason a property was refused, while the machine
state beside it stayed honest. Every code below is reconstructed by the independent verifier;
the sentence is here, and in `method/stage4_prose_v1.json` (hashed into `scorecard_set_id`).

### NEBPI — why a Part-II branch did not fire (`branch_proof[].blocking_code`)

| code | meaning |
|---|---|
| `pk_level_is_not_the_required_level` | the derived PK level is not the level this branch requires |
| `pk_not_derivable` | no PK level could be derived (see pk_blocked_code) |
| `pk_has_no_potency_context` | PK was measured but no MEC/potency context binds it (Table 2 footnote a) |
| `context_incomplete` | the evidence context is incomplete (route/formulation/dose/schedule/tumour) |
| `state_is_not_observed_present` | the criterion was not observed present |
| `state_is_not_observed_absent` | the criterion was not observed absent by an adequate assessment |
| `absence_claim_inadequate` | an absence was claimed but no adequate assessment looked for it |
| `conflicting_observations` | two distinct observations of this criterion disagree |

### NEBPI — context caveats (`nebpi[].context_caveats[].code`)

| code | meaning |
|---|---|
| `context_incomplete` | NEBPI is context-dependent; part of the route/formulation/dose/schedule/tumour context is missing |
| `no_potency_context` | no MEC/potency record binds the PK observations in this context |

### NEBPI — why a negative class is blocked (`counterfactual.negative_classes_blocked_because[].code`)

| code | meaning |
|---|---|
| `pk_not_measured_in_neb` | no PK was measured in non-enhancing brain |
| `pd_absence_not_established` | 'No relevant PD in NEB' is not established |
| `radiographic_absence_not_established` | 'No radiographic response in NEB' is not established |

### Exposure — margin caveats (`exposure_evidence.caveats[]`)

| code | meaning |
|---|---|
| `csf_is_not_non_enhancing_brain` | CSF is not non-enhancing brain: the blood-CSF barrier is more permeable than the BBB (Grossman 2026). A CSF margin says nothing about NEB exposure and cannot satisfy an NEBPI branch. |
| `measured_in_enhancing_tissue` | Measured in contrast-enhancing tissue, where the BBB is disrupted. Not NEB evidence. |
| `potency_applied_via_sourced_relevance_link` | The potency was measured in a different tumour context and applied here via a sourced relevance link. |

### Exposure — why a margin was not computed (`margin_reason_code`)

`context_disagreement`, `no_potency_record`, `active_moiety_mismatch`, `candidate_mismatch`, `potency_metric_not_a_target_concentration`, `binding_state_unspecified`, `free_total_mismatch`, `dosing_context_unknown`, `potency_context_not_relevant`, `no_quantified_concentration`, `unit_family_mismatch`, `margin_undefined`, `ambiguous_potency_records`

### Delivery — why a requirement was not assigned (`delivery_evidence.reason_code`)

`assigned`, `no_assignment`, `conflicting_assignments`, `explicitly_uncertain`, `assigner_not_accepted`, `immune_target_is_not_evidence_of_systemic_priming`, `no_evidence_binding`, `unknown_delivery_requirement`

A delivery `rationale` is present ONLY when it came from the input assignment (and is
therefore bound by the evidence-input digest). A decision Stage 4 generated carries a code
and no sentence.

### CNS-MPO — why a property was not used (`property_evidence.rejection_reason_code`)

`absent`, `disallowed_calculator`, `ambiguous_multiple_sources`, `requirements_unmet`, `unlisted`, `forbidden`

### Production eligibility (`production_eligible.reason_code`)

`eligible`, `fixture_namespace`, `research_only_namespace`, `direction_incompatible`, `direction_unknown`, `non_public_source_in_evidence`, `not_evaluated`

**None of these codes is a clinical conclusion.** `no_evidence_found` is a statement about a
SEARCH, not a finding of safety; `not_evaluated` is not `observed_absent`; and an incomplete
CNS-MPO is not brain exposure.
