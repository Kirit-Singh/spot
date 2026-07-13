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

> **Status — stated per gate, because "done" means four different things.**
>
> | | |
> |---|---|
> | Engine + verifier implemented | **yes** — evidence contract v1 (frozen) and v2 (acquisition) |
> | Stage-3 → Stage-4 admission wired | **yes** — two gates: Stage-4 restates the bundle byte-for-byte, *and* Stage-3's own `verifier.verify_stage3` must pass out-of-process. Schema-valid is not admitted |
> | Public acquisition adapters | **yes** — PubChem, RxNorm, DailyMed, openFDA; offline unless `--allow-network` |
> | Selection-specific real run | **NO** |
> | Public release | **NO** |
>
> **No real drug is characterised, ranked, or claimed to be safe, brain-permeable,
> NEBPI-classified or clinically suitable.** Every candidate in the test corpus is a labelled
> `FIXTURE-*`. A real Stage-4 result is gated on an externally admitted real Stage-3 v2 bundle;
> the production-pointer and selection gates are fail-closed until then.

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
  2010;1(6):435–449, **DOI 10.1021/cn100008c**, **PMCID PMC3368654**. **ACS-copyrighted, and
  not in the PMC open-access subset**: `method/cns_mpo_wager2010_v1.json` encodes the *numeric
  parameters* (the transform shape and inflection points per property) and the published golden
  scores used as arithmetic test vectors, with the locator for each. It does not reproduce the
  paper's tables or quote its prose, and the article bytes are never committed. CNS-MPO is a
  **physicochemical heuristic** — a design-space desirability score. It is **not** measured CNS
  exposure.
- **Label structure** — LOINC section codes read from live DailyMed SPL responses, not recalled.

**Claude/LLM output is never a scientific source.** There is no `model_output` source type,
and an LLM-shaped `assigned_by` is refused by the delivery rules.

## Layout

```
analysis/   the engine — one purpose per module, every file < 500 lines
method/     source-bound method parameters: the published numbers live here, not in code,
            so editing one moves the method hash and invalidates every cached scorecard set
schemas/    generated JSON Schema + parquet table contracts (a test guards against drift)
tests/      the suite; no network. tests/fixtures/ holds labelled synthetic public-shaped records
outputs/    <scorecard_set_id>/ — 19 artifacts (v1) / 21 (v2), written atomically (gitignored)
```

## Public acquisition

Where the evidence comes from. Every record carries the canonical URL + query, the UTC access
time, the HTTP status and media type, the source release, the **licence/terms URL**, the raw byte
count + SHA-256, the adapter code hash and the exact extraction transform
(`spot.stage04_acquisition_manifest.v1`).

**The full chain.** Until the materializer landed, step 2 did not exist: `run_acquire` wrote an
acquisition manifest, `run_stage4` consumed an evidence bundle, and nothing turned one into the
other — so every green run was scoring a fixture.

```bash
# 1. acquire public bytes (offline by default; cached outside Git, addressed by SHA-256)
python -m analysis.run_acquire     --stage3-bundle <dir> --run-root <R>
python -m analysis.run_acquire     --stage3-bundle <dir> --run-root <R> \
    --acquire-identity temozolomide --allow-network --dailymed-setid <setid>

# 2. materialize the typed evidence bundle from what was actually acquired
python -m analysis.run_materialize --stage3-bundle <dir> --run-root <R> --out <B>
python -m verifier.verify_bundle   <B> --run-root <R>      # independent; 0 = verified

# 3. score, emit, verify
python -m analysis.run_stage4      --stage3-bundle <dir> --evidence-bundle <B>
```

The materializer states `not_evaluated`, with a reason, for **every lane a public acquisition
cannot reach** — exposure, transporters, NEBPI observations, fu — and those reasons are hashed
into `scorecard_set_id`, so an absence is part of the release's identity rather than a gap in it.
It maps only the CNS-MPO inputs PubChem honestly supplies (MW, TPSA, HBD); **XLogP3 is not
BioByte ClogP**, so `clogp`, `clogd_74` and `pka_most_basic` stay unsourced and CNS-MPO comes out
**incomplete**. It refuses fixture evidence, refuses a label whose molecule is not the candidate's,
and never infers an organ system.

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
python -m pytest tests/ -q                                        # the suite; no network
python -m analysis.schemas_export                                 # regenerate schemas

# one bounded live probe (TEMODAR/temozolomide — a reference probe, never a candidate)
SPOT_STAGE4_LIVE=1 SPOT_STAGE4_RUN_ROOT=/tmp/spot-live pytest tests/test_live_reference_smoke.py
```

**Green means exit status 0, not a number.** The suite is the gate; a test count in a README is
stale the commit after it is written, and a stranger cannot tell a dropped test from a deleted
one. Run it and read the exit code:

```bash
python -m pytest tests/ -q       ; echo "exit=$?"   # 0 = green
python -m ruff check analysis/ verifier/ tests/     # 0 = clean
python -m mypy --ignore-missing-imports analysis/ verifier/
python -m compileall -q analysis/ verifier/ tests/
python -m verifier.verify_stage4 <release-dir>      # 0 = the release verifies
```

Skips are expected on a bare checkout and each one names the cache it wants (below); a skip is
never a pass.

**Tests that read real public bytes are SUPPLIED, never committed.** The bytes are public but
are not redistributed here (ChEMBL CC BY-SA 3.0, UniProt CC BY 4.0 — see
[DATA_LICENSES.md](../DATA_LICENSES.md)). Without these the tests **skip**, and say so:

| variable | supplies |
|---|---|
| `SPOT_STAGE3_ANNOTATION_CACHE` | the raw ChEMBL/UniProt responses the Stage-3 candidate reconstruction rebuilds its claims from (`acquisition_manifest.json` + `raw/`) |
| `SPOT_SOURCE_CACHE` | the cited primary-source documents (e.g. `PMC13338342.bioc.xml`), re-hashed against `method/sources.json` |
| `SPOT_STAGE3_ROOT` | a Stage-3 checkout, so gate 2 (`verifier.verify_stage3`) runs out-of-process |

Environment: `requirements-stage4.lock` — a real solver lock (`pip-compile
--generate-hashes`), installable with `pip install --require-hashes -r
requirements-stage4.lock`.

See **[METHODS.md](METHODS.md)** for the formulas, the NEBPI branch logic, the provenance
chain, the firewalls, and the limitations.
