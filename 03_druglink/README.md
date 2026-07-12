# 03_druglink — direction-aware target/pathway → drug link

Maps a **verified Stage-2 Direct run** onto direction-compatible drugs from public
sources. Generic by contract: any Stage-1 selection produces Stage-2 direct target arms
(and, optionally, pathway-node hypotheses), and Stage 3 maps both to drugs. Treg-like →
Th1-like is one example, not the contract.

Stage 3 reports **scientific workflow states**. It has no promotion, eligibility or
recommendation vocabulary — that is retired.

## Input: a verified Direct run. There is no other.

```bash
PYTHONPATH=analysis python -m druglink.run_stage3 \
  --artifact-class analysis \
  --direct-run "$DIRECT_RUN" --direct-inputs-root "$DIRECT_INPUTS_ROOT" \
  --cache-root "$STAGE3_CACHE" --output-root "$STAGE3_OUT" \
  [--pathway-hypotheses "$PATHWAYS"]
```

There is **no `--lever-set`**: the argument does not exist, so no code path can reach a
caller-authored lever document. The Direct run is admitted only after Direct's **own
standalone verifier** reconstructs it from the raw sources and exits 0
(`direct.verify_run`); Stage 3 then re-hashes every file it consumes. A verifier that
crashes, or that cannot be located, is an **abort** — "verified" never quietly becomes
"assumed".

## Two artifact classes, one firewall

| class | what it is | Stage 4 |
|---|---|---|
| `analysis` | a real computation over real inputs — **one generic class** | may be queued |
| `fixture` | synthetic test data (`fx_`), own output subtree | **never** |

The production / research_only namespaces and the whole promotion lattice are
**RETIRED**: `production_candidate`, `production_promotion_eligible`,
`may_write_production_pointer`, `production_pointer_written`,
`research_pk_annotation_eligible`, `namespace`. They are refused **structurally**, at any
depth, by both the writer and the independent verifier. The 0-of-33 Stage-1 gate
assumption is gone: Stage 3 carries upstream gate fields as **context** and gates on
none of them.

## Two arms, authoritative

`away_from_A` and `toward_B` are Stage-2's authoritative arm evidence. One screen row
becomes exactly **two** arm-lever rows, always — each with its own nullable `Int64`
rank, evaluability, support, tier and desired modulation. An `A` row never reads a `B`
field. There is **no combined, balanced, best-of, primary, headline or overall score or
rank**, and no field for one to live in.

Stage-2 **joint context** is accepted as **typed** context and republished verbatim:
`joint_status` (closed enum), **`pareto_tier` — a positive integer from 1, or null when
not jointly evaluable**, and `joint_ordering_method_id` (string). A Pareto tier is a
rank-like **label**, not a score, so it is correctly **numeric**. What stays refused is a
numeric **combined objective** — `combined_score`, `balanced_skew`, a weighted sum of the
arms. None of it is **ever** used to infer drug direction, and Stage 3 **never rewrites**
it — structurally: `direction.translate()` has no parameter through which it could arrive.

## Two origins, never merged

| `origin_type` | what it is | strongest status reachable |
|---|---|---|
| `direct_target` | the gene was **perturbed**; its arm moved | `observed_perturbation` |
| `pathway_node` | the gene was **inferred**; never perturbed | `pathway_hypothesis` |

A pathway node must state its **own** direction — "in the same pathway" is not evidence
about a gene, and no direction propagates between sibling nodes. Its programmatic
evidence must be **arm-specific**, and it must cite a contributing perturbation that
really exists in this screen, on that arm. A gene that is both a measured target and an
inferred node holds **two separate levers**. Claude Science interpretation is provenance
and is kept strictly apart from computed enrichment: it can never support a node.

**Stage 2 owns and emits the pathway document.** Stage 3 is the consumer;
`schemas/spot.stage02_pathway_hypotheses.v1.json` is a **consumer proposal pending the
Stage-2 owner's agreement — the lane is NOT frozen.** Unfed, it records
`pathway_lane=not_evaluated`. Nothing is invented to fill it.

## Workflow states

```
directional_evidence_status : observed_perturbation | inverse_direction_hypothesis
                            | pathway_hypothesis | opposed | unresolved
drug_mapping_status         : mapped | unmapped | refused
stage4_assessment_status    : queued | not_queued        (+ compact reason codes)
stage3_evidence_class       : measured_perturbation | inverse_direction_hypothesis
                            | pathway_hypothesis | no_supporting_evidence   (UNORDERED)
```

`refused` is not `unmapped`: entities matched but every one was a complex/family, and a
complex is never translated into a component gene.

### The inverse-direction hypothesis

When knockdown moved an arm the **undesired** way **and a real sourced activation/agonism
mechanism exists** on the exact single-protein target, that is its own state —
`inverse_direction_hypothesis`. It is **not** folded into `unresolved` and **not** folded
into observed support:

* `observed_perturbation_support = false` — it is **not observed gain of function**;
* `stage3_evidence_class = inverse_direction_hypothesis` — **never** a measurement's
  class, and the class is **unordered**;
* `drug_mapping_status = mapped`; `stage4_assessment_status = queued` with reason
  `mapped_inverse_direction_hypothesis`;
* the **exact supporting arm and source mechanism are preserved**;
* it **never alters** a Direct rank, a Direct arm evidence tier, or a Stage-2 Pareto tier;
* **Claude Science reviews its biological plausibility later** — Stage 3 flags it
  (`claude_science_review_status`) and does not judge it;
* if **no real activation mechanism exists, nothing is invented**: no hypothesis edge, and
  the candidate is not queued on that basis.

**A Stage-4 assessment is not biological promotion and not a recommendation.** It asks
Stage 4 to compute PK/safety properties.

`intervention_effect` is closed: `abundance_reduction` · `functional_inhibition` ·
`functional_activation` · `unknown`. An **inhibitor is never serialized as a change in
target abundance**; degraders stay distinguishable; **activation is never inferred from
inhibition**.

## Public acquisition — bounded, frozen, offline-replayable

```bash
PYTHONPATH=analysis python -m druglink.acquire_public \
  --artifact-class analysis \
  --direct-run "$DIRECT_RUN" --direct-inputs-root "$DIRECT_INPUTS_ROOT" \
  --top-per-arm 25 --sources uniprot,chembl --chembl-release CHEMBL_37 \
  --cache-root "$STAGE3_CACHE"

PYTHONPATH=analysis:. python -m druglink.verify_acquisition \
  --cache-root "$STAGE3_CACHE" \
  --direct-run "$DIRECT_RUN" --direct-inputs-root "$DIRECT_INPUTS_ROOT"
```

The target queue is frozen and written to disk **before the first HTTP request** — top
25 per arm, **independently** by that arm's own rank. No adaptive expansion; **zero
candidates is a valid result**. Every page keeps its exact bytes, count, SHA-256,
canonical URL, headers, release, licence, attribution, pagination position and the moment
it was **actually** retrieved. UniProt release comes from the `X-UniProt-Release`
**header** (CC BY 4.0); ChEMBL from `status.json` → `chembl_db_version` (CC BY-SA 3.0).

Generation **requires a passing acquisition gate**: `load_manifest` runs the offline
verifier first and refuses to build on unverified evidence, then binds the verdict.

## Independent verification

```bash
PYTHONPATH=. python -m verifier.verify_stage3 \
  --bundle "$STAGE3_BUNDLE" --cache-root "$STAGE3_CACHE" \
  --direct-run "$DIRECT_RUN" --direct-inputs-root "$DIRECT_INPUTS_ROOT" \
  --artifact-class analysis --write-report
```

`verifier/` imports **nothing** from `druglink`. It restates the contract, reimplements
content addressing, re-runs Direct's own verifier, re-expands both arms from
`screen.parquet`, **opens the acquisition cache and hashes the raw bytes itself**,
**re-parses** the UniProt/ChEMBL responses with its own parsers, and **rebuilds**
identity, mechanisms, edges and candidates. A nonexistent cache is a **failure**, not an
empty one; evidence from an adapter it cannot re-parse is **refused**, not blessed.

## Layout

`analysis/druglink/` engine · `verifier/` independent verifier · `schemas/` contracts ·
`tests/` (109 tests; the pinned real UniProt/ChEMBL bytes are **parser/acquisition
regression data only — never research results**) · `env/` (see the **UNRESOLVED
portability gap** recorded in the lock header) · `outputs/` gitignored.
