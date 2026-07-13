# 04_PKPD — delivery, CNS-MPO, transporters, exposure, NEBPI, safety

Stage 4 is an **evidence engine**, not a recommendation engine. It consumes a hash-bound
Stage-3 DrugCandidateSet and emits **six separate evidence lanes**, each traceable from
every displayed number back to a public source response and a declared transform.

**It does not emit a composite clinical score, a traffic light, a ranking, or a
prescribing recommendation.** A test scans every artifact and fails the build if a field
like `traffic_light`, `safety_score` or `recommendation` ever appears. This supersedes the
"🟢/🟡/🔴 safety traffic light" sketched in the earlier version of this README: a single
combined verdict would hide exactly the provenance this stage exists to preserve, and Spot
is decision-support — not a prescriber, a PK/tox oracle, or a substitute for clinical,
regulatory or safety expertise.

> **Status: fixture-only.** No real drug is characterised, ranked, or claimed to be safe,
> brain-permeable, NEBPI-classified or clinically suitable. Every candidate in this pass is
> a labelled `FIXTURE-*`. Stage 3 has not landed, no real-source evidence loader is wired,
> and the production-pointer and selection gates are fail-closed.

## The six lanes

| Lane | What it is | What it can never do |
|---|---|---|
| **Delivery requirement** | `local_CNS_target_engagement_required` \| `systemic_immune_priming` \| `delivery_requirement_uncertain` | Be *inferred*. An immune-related target is never evidence of systemic priming. |
| **CNS-MPO** | Wager 2010 v1: six properties, equal weights, sum 0–6 | Be read as measured permeability, a probability, or an NEBPI class |
| **Transporters** | One row per observation (ABCB1/P-gp, ABCG2/BCRP, …) | Collapse into an unqualified boolean |
| **Exposure** | One row per measurement; a margin only when it is genuinely computable | Compare total tissue vs free potency; infer Kp,uu,brain from CSF |
| **NEBPI** | Criterion-level Part I / Part II evidence model (Grossman 2026) | Turn absent evidence into "impermeable" |
| **Safety** | One row per labelled finding, per named GBM scenario, per interaction type | Render `no_evidence_found` as safe |

The lanes never merge. The scorecard puts candidates side by side in a declared
**non-evaluative** order (`is_ranking: false`).

## Primary sources

- **NEBPI** — Grossman et al., *Evaluating "brain permeability": A critical issue for the
  development of therapeutic agents for primary and metastatic brain tumors*,
  Neuro-Oncology 2026, **DOI 10.1093/neuonc/noag051**, **PMCID PMC13338342**, CC BY 4.0.
  The Part I / Part II criteria and the exact branch logic are transcribed verbatim in
  `method/nebpi_grossman2026_v1.json`.
- **CNS-MPO** — Wager et al., *Moving beyond Rules: The Development of a Central Nervous
  System Multiparameter Optimization (CNS MPO) Approach…*, ACS Chem Neurosci
  2010;1(6):435–449, **DOI 10.1021/cn100008c**, **PMCID PMC3368654**. Table 1
  (transformation functions) and Table 2 (published golden scores) are transcribed in
  `method/cns_mpo_wager2010_v1.json`. CNS-MPO is a **physicochemical heuristic** — a
  design-space desirability score. It is **not** measured CNS exposure.
- **Label structure** — LOINC section codes read from live DailyMed SPL responses, not recalled.

**Claude/LLM output is never a scientific source.** There is no `model_output` source type,
and an LLM-shaped `assigned_by` is refused by the delivery rules.

## Layout

```
analysis/   the engine — one purpose per module, every file < 500 lines
method/     source-bound method parameters: the published numbers live here, not in code,
            so editing one moves the method hash and invalidates every cached scorecard set
schemas/    generated JSON Schema + parquet table contracts (a test guards against drift)
tests/      195 tests, no network. tests/fixtures/ holds labelled synthetic public-shaped records
outputs/    <scorecard_set_id>/ — eight artifacts, written atomically (gitignored)
```

## Public acquisition

Where the evidence comes from. Every record carries the canonical URL + query, the UTC access
time, the HTTP status and media type, the source release, the **licence/terms URL**, the raw byte
count + SHA-256, the adapter code hash and the exact extraction transform
(`spot.stage04_acquisition_manifest.v1`).

```bash
python -m analysis.run_acquire --stage3-bundle <dir> --run-root <dir>   # offline: no network
python -m analysis.run_acquire --stage3-bundle <dir> --run-root <dir> \
    --acquire-identity temozolomide --allow-network --dailymed-setid <setid>
```

- **Raw bytes live outside Git**, under a caller-supplied run root, addressed by their own
  SHA-256. `RunRoot` *refuses* a cache inside the working tree. Git holds synthetic fixtures only.
- **ChEMBL and UniProt are never re-queried.** Stage 3 already acquired and hashed them; those
  records are carried across verbatim, and asking to fetch one raises.
- **Identity converges or the candidate is refused** — PubChem, RxNorm, DailyMed and Drugs@FDA
  must agree. A salt/prodrug needs a sourced mapping to its active moiety.
- **DailyMed selection is deterministic**: one product, or an explicit `--dailymed-setid` pin, or
  a refusal that names every candidate. (Live, "temozolomide" returns 20 products.)
- **Missing stays missing.** Absent lanes are `not_evaluated`, in writing.

| Source | Terms | Stage-4 use |
|---|---|---|
| PubChem PUG REST | no NCBI restriction on molecular data; third-party rights may exist | structure + the descriptors PubChem computes. **Never logD7.4 or pKa** — it has neither, so CNS-MPO stays incomplete rather than fabricated |
| RxNorm (RxNav) | NLM terms, source-vocabulary restrictions | identity crosswalk only |
| DailyMed SPL v2 | **no blanket licence verified** | label identity + labelled safety sections. Live labels are **never committed** |
| openFDA / Drugs@FDA | generally CC0, **with marked source exceptions** | approval / application cross-check |
| ChEMBL, UniProt | CC BY-SA 3.0 / CC BY 4.0 | **reuse-only** from the admitted Stage-3 bundle |
| ClinicalTrials.gov | *not* public domain — no adapter | — |
| DrugBank | no valid public licence | **forbidden** |

## Run

```bash
cd 04_PKPD
python -m analysis.run_stage4 --fixtures --outputs-root outputs   # fixture smoke run
python -m pytest tests/ -q                                        # no network
python -m analysis.schemas_export                                 # regenerate schemas

# one bounded live probe (TEMODAR/temozolomide — a reference probe, never a candidate)
SPOT_STAGE4_LIVE=1 SPOT_STAGE4_RUN_ROOT=/tmp/spot-live pytest tests/test_live_reference_smoke.py
```

Environment: `requirements-stage4.lock` — a real solver lock (`pip-compile
--generate-hashes`), installable with `pip install --require-hashes -r
requirements-stage4.lock`.

See **[METHODS.md](METHODS.md)** for the formulas, the NEBPI branch logic, the provenance
chain, the firewalls, and the limitations.
