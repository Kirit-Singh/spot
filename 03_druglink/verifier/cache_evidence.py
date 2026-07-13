"""Evidence-level cache checks: mechanism identity, variant containment, shared accessions.

Split out of ``cache_identity`` (which owns TARGET identity) once it crossed the 500-line
gate. This module owns what happens to an ASSERTION once its target is admitted.

TWO REAL-STORE ATTACKS LIVE HERE, AND BOTH ARE THE SAME MISTAKE
---------------------------------------------------------------
In each case the store **noticed** the problem, **wrote it down**, and then **did not act on
it**. A flag that does not gate is decoration.

1. ``mec_id`` 6210 and 6862 each appear against THREE distinct ENSG targets, reached through
   a shared UniProt accession. The rows carry ``shared_accession`` — and carry
   ``drug_evidence`` anyway. One mechanism assertion becomes evidence for three genes, and
   each reads to a consumer as independent support.

2. The variant gate was **FAIL-OPEN**. It only complained when
   ``variant_id AND NOT variant_specific AND general_gene_rankable``. The store sets
   ``variant_specific=true`` and simply omits ``general_gene_rankable`` — so the condition
   never fired, and **29 assertions** (specific mutations, plus the ``-1`` UNDEFINED
   MUTATION sentinel) could enter general-gene ranking. The flag was true, and it gated
   nothing.

The fix is the same shape both times: **absence is not permission.** A variant assertion is
non-rankable unless something explicitly, positively says otherwise — and the only thing
allowed to say otherwise is a named non-rankable lane.

WHY A VARIANT MAY NOT RANK A GENE
---------------------------------
A JAK2 **V617F** inhibitor is evidence about V617F. It is not evidence that inhibiting
wild-type JAK2 does anything — the whole clinical point is that it does not. Same for BRAF
**V600E**. Letting a variant-specific mechanism rank the wild-type gene attaches a drug to a
target it was never shown to act on, and the screen perturbed the wild-type gene.

And ``variant_id = -1`` is ChEMBL's **UNDEFINED MUTATION** sentinel. It is emphatically not
"no variant" — it means *there is a mutation and we do not know which one*. Reading -1 as
null is the most dangerous possible interpretation: it converts "unknown mutant" into
"wild-type".
"""
from __future__ import annotations

from typing import Any

from .report import Report

# BLOCKER 2 — assertion-level fields that must survive, keyed on mec_id.
REQUIRED_ASSERTION_FIELDS = (
    "source_row_id",            # = mec_id, the ChEMBL assertion primary key
    "mechanism_of_action", "molecular_mechanism", "direct_interaction",
    "disease_efficacy", "variant_id", "selectivity_comment",
)

# ChEMBL's UNDEFINED MUTATION sentinel. NOT null. NOT wild-type.
VARIANT_UNDEFINED_MUTATION = -1

# Real mutations found in the store's variant assertions.
REAL_VARIANT_ATTACKS = ("V617F", "V600E")

# The only lane a variant assertion may occupy.
LANE_VARIANT_NON_RANKABLE = "variant_specific_non_rankable"

IDENTITY_RESOLVED = "resolved"
IDENTITY_SHARED_ACCESSION = "shared_accession"
DISP_AMBIGUOUS_IDENTITY = "ambiguous_identity"

# The real counterexamples, pinned so they can never quietly pass again.
REAL_ATTACK_MEC_IDS = (6210, 6862)
REAL_ATTACK_N_GENES = 3
REAL_VARIANT_ASSERTION_COUNT = 29


def is_variant_assertion(a: dict[str, Any]) -> bool:
    """A variant_id of ANY value — including the -1 sentinel — is a variant assertion.

    ``-1`` means "there is a mutation and we do not know which one". Treating it as null
    converts an unknown mutant into a wild-type claim, which is the worst reading available.
    """
    return a.get("variant_id") not in (None, "")


def variant_is_contained(a: dict[str, Any]) -> tuple[bool, str]:
    """FAIL-CLOSED. A variant assertion must be positively, explicitly contained.

    The old gate asked "is this variant marked rankable?" and let an ABSENT field mean no.
    Absence is not permission. This asks the opposite question: "has this variant been
    explicitly excluded from general-gene ranking?" — and an absent field is a failure.
    """
    if not is_variant_assertion(a):
        return True, "not_a_variant_assertion"

    if a.get("variant_specific") is not True:
        return False, (
            f"variant_id={a.get('variant_id')!r} but variant_specific is "
            f"{a.get('variant_specific')!r} — a variant assertion must be TYPED as one")

    # The bug: this was defaulting to True and being skipped entirely.
    rankable = a.get("general_gene_rankable")
    if rankable is not False:
        return False, (
            f"variant_id={a.get('variant_id')!r} but general_gene_rankable is "
            f"{rankable!r} — it must be EXPLICITLY false. An absent field is not a "
            "denial, and the store omits it, which is how 29 variant assertions reached "
            "general-gene ranking")

    lane = a.get("lane")
    if lane != LANE_VARIANT_NON_RANKABLE:
        return False, (
            f"variant_id={a.get('variant_id')!r} must sit in the named lane "
            f"{LANE_VARIANT_NON_RANKABLE!r}; got {lane!r}")

    return True, "variant_contained"


def check_one_assertion_per_mec_id(rep: Report,
                                   assertions: list[dict[str, Any]]) -> None:
    """BLOCKER 2. ``mec_id`` is the assertion's primary key; it is never collapsed."""
    seen: dict[str, int] = {}
    for a in assertions:
        mec = a.get("source_row_id")
        if mec is not None:
            seen[str(mec)] = seen.get(str(mec), 0) + 1

    dupes = sorted(m for m, n in seen.items() if n > 1)
    rep.check("exactly ONE cache assertion per ChEMBL mec_id (source_row_id)",
              not dupes, f"{len(dupes)} duplicated: {dupes[:3]}")

    lossy = []
    for a in assertions:
        missing = [f for f in REQUIRED_ASSERTION_FIELDS if f not in a]
        if missing:
            lossy.append(f"{a.get('source_row_id')}: {missing}")
    rep.check(
        "every assertion retains its identity/context fields (source_row_id=mec_id, "
        "mechanism_of_action, molecular_mechanism, direct_interaction, disease_efficacy, "
        "variant_id, selectivity_comment)",
        not lossy, "; ".join(lossy[:3]))


def check_variant_assertions_are_contained(rep: Report,
                                           assertions: list[dict[str, Any]]) -> None:
    """FAIL-CLOSED variant containment. Absence is not permission."""
    leaking = []
    for a in assertions:
        ok, reason = variant_is_contained(a)
        if not ok:
            leaking.append(f"mec {a.get('source_row_id')}: {reason}")

    rep.check(
        "every VARIANT assertion is explicitly contained: variant_id non-null REQUIRES "
        "variant_specific=true AND general_gene_rankable=false AND the named "
        f"{LANE_VARIANT_NON_RANKABLE!r} lane. A V617F inhibitor is evidence about V617F, "
        "not about wild-type JAK2 — and the screen perturbed the wild-type gene",
        not leaking, "; ".join(leaking[:3]))

    # The -1 sentinel, called out by name because reading it as null is the worst error.
    sentinels = [a.get("source_row_id") for a in assertions
                 if a.get("variant_id") == VARIANT_UNDEFINED_MUTATION
                 and a.get("general_gene_rankable") is not False]
    rep.check(
        "variant_id = -1 (UNDEFINED MUTATION) is treated as a VARIANT, never as null — it "
        "means 'there is a mutation and we do not know which one', and reading it as "
        "wild-type is the most dangerous available interpretation",
        not sentinels, f"{len(sentinels)} sentinel assertion(s) still rankable")


def check_no_drug_evidence_on_ambiguous_identity(
        rep: Report, *, edges: list[dict[str, Any]],
        accession_to_genes: dict[str, list[str]],
        dispositions: list[dict[str, Any]]) -> None:
    """No rankable/direct drug edge survives an unresolved or shared identity."""
    ambiguous = {a for a, genes in accession_to_genes.items() if len(set(genes)) > 1}

    bad = []
    for e in edges:
        rankable = e.get("rankable", True) or e.get("lane") == "direct_gene_mechanism"
        if not rankable:
            continue
        status, acc = e.get("identity_status"), e.get("uniprot_id")
        if status != IDENTITY_RESOLVED:
            bad.append(f"{e.get('edge_id')}: identity_status={status!r} but still rankable")
        elif acc in ambiguous:
            bad.append(
                f"{e.get('edge_id')}: accession {acc} maps to "
                f"{sorted(set(accession_to_genes[acc]))} — one mechanism cannot "
                "distinguish between them")

    rep.check(
        "no rankable/direct drug edge survives an unresolved or SHARED identity (a row that "
        "says shared_accession and then carries drug_evidence has NOTICED the ambiguity and "
        "not acted on it; the drug lands on every candidate gene and each reads as "
        "independent evidence)",
        not bad, "; ".join(bad[:3]))

    disposed = {(d.get("subject_id"), d.get("state")) for d in dispositions}
    undisposed = [a for a in sorted(ambiguous)
                  if (a, DISP_AMBIGUOUS_IDENTITY) not in disposed]
    rep.check(
        f"every shared accession emits a named {DISP_AMBIGUOUS_IDENTITY!r} disposition "
        "(an absent edge with no record is indistinguishable from a drug nobody found)",
        not undisposed, f"{len(undisposed)} without a disposition: {undisposed[:3]}")


def check_one_mec_id_is_not_spread_across_genes(
        rep: Report, edges: list[dict[str, Any]]) -> None:
    """One mechanism assertion may not be evidence for several genes at once."""
    by_mec: dict[Any, set[str]] = {}
    for e in edges:
        mec, gene = e.get("source_row_id"), e.get("target_ensembl")
        if mec is not None and gene:
            by_mec.setdefault(mec, set()).add(gene)

    spread = {m: sorted(g) for m, g in by_mec.items() if len(g) > 1}
    rep.check(
        "no single ChEMBL mec_id is admitted as drug evidence for MORE THAN ONE gene",
        not spread,
        "; ".join(f"mec {m} -> {g}" for m, g in list(spread.items())[:3]))


# --------------------------------------------------------------------------- #
# THE GAP MY OWN AUDIT MISSED — containment is not row-deep, it is ASSERTION-deep.
#
# The regenerated store gets the ROW right: an ambiguous_identity target carries
# `drugs: []`. I checked exactly that, and reported green.
#
# But the copied source assertions are preserved one level down, under
# `ambiguous_source_assertions[]`, and SIX of them still carry
# `general_gene_rankable: true` — mec_ids 6210 and 6862, on CALM1/CALM2/CALM3, the three
# genes that encode an identical calmodulin protein and therefore share every accession.
# The exact rows from the original attack.
#
# A consumer that flattens assertions — and flattening is the obvious thing to do — reads
# `general_gene_rankable: true` and ranks them. The row said no; the assertion says yes;
# the assertion is what gets read.
#
# So the rule is not "an ambiguous row has no drugs". It is: NO ASSERTION ANYWHERE INSIDE
# an ambiguous row may claim to be generally rankable, at any nesting depth, in any
# container, however honestly that container is named. A gate that holds only at the depth
# you happened to look at is not a gate.
# --------------------------------------------------------------------------- #
DISP_AMBIGUOUS_SOURCE_ASSERTION = "ambiguous_identity_source_assertion"

# The real occurrences, pinned so they cannot silently return.
CALMODULIN_GENES = ("ENSG00000143933", "ENSG00000160014", "ENSG00000198668")
AMBIGUOUS_ASSERTION_MEC_IDS = (6210, 6862)


def _assertion_nodes(obj: Any, path: str = "$"):
    """Every dict at ANY depth that makes a rankability claim. Container-agnostic."""
    if isinstance(obj, dict):
        if "general_gene_rankable" in obj:
            yield path, obj
        for key, value in obj.items():
            yield from _assertion_nodes(value, f"{path}.{key}")
    elif isinstance(obj, (list, tuple)):
        for i, item in enumerate(obj):
            yield from _assertion_nodes(item, f"{path}[{i}]")


def check_no_rankable_assertion_inside_an_ambiguous_row(
        rep: Report, rows: list[dict[str, Any]]) -> None:
    """RECURSIVE. Every copied/nested assertion under an ambiguous identity is non-rankable."""
    leaks = []
    for row in rows:
        if row.get("disposition") != DISP_AMBIGUOUS_IDENTITY:
            continue
        for path, node in _assertion_nodes(row):
            if node.get("general_gene_rankable") is not False:
                leaks.append(
                    f"{row.get('target_id')}{path[1:]} "
                    f"(mec {node.get('source_row_id')}): "
                    f"general_gene_rankable={node.get('general_gene_rankable')!r}")

    rep.check(
        "NO assertion at ANY nesting depth inside an ambiguous_identity row claims to be "
        "generally rankable (the row carrying drugs=[] is not enough — a consumer that "
        "flattens assertions reads the assertion, not the row, and flattening is the "
        "obvious thing to do)",
        not leaks, "; ".join(leaks[:4]))

    unnamed = []
    for row in rows:
        if row.get("disposition") != DISP_AMBIGUOUS_IDENTITY:
            continue
        for path, node in _assertion_nodes(row):
            if node.get("disposition") not in (DISP_AMBIGUOUS_SOURCE_ASSERTION,
                                               DISP_AMBIGUOUS_IDENTITY):
                unnamed.append(f"{row.get('target_id')}{path[1:]}")
    rep.check(
        f"every preserved ambiguous assertion carries the named "
        f"{DISP_AMBIGUOUS_SOURCE_ASSERTION!r} disposition (preserved-but-unlabelled is how "
        "it gets read as ordinary evidence)",
        not unnamed, f"{len(unnamed)} unnamed: {unnamed[:3]}")


# --------------------------------------------------------------------------- #
# DENOMINATORS. `n_total_drug_assertions` is not a total.
#
# The store reports n_total_drug_assertions = 2,227. That number is the count of GENERAL,
# rankable assertions. The cache actually holds:
#
#     2,262  occurrences  (every copy, at every depth)
#     2,258  unique source mec_ids
#     2,227  general / rankable
#        29  variant-specific
#         6  ambiguous copies  (2 unique mec_ids x 3 calmodulin genes)
#
# and 2,227 + 29 + 6 = 2,262. A field called "total" that silently excludes the variant and
# ambiguous assertions makes the excluded evidence invisible in exactly the accounting a
# reader would use to notice it was excluded. The denominators must be named for what they
# COUNT, not for what the producer happened to want in the numerator.
# --------------------------------------------------------------------------- #
REQUIRED_DENOMINATORS = (
    "n_assertion_occurrences",      # every copy, every depth
    "n_unique_source_mec_ids",
    "n_general_rankable_assertions",
    "n_variant_specific_assertions",
    "n_ambiguous_copy_assertions",
)


def check_denominators_are_exact(rep: Report, metrics: dict[str, Any]) -> None:
    """A 'total' that is really a subtotal hides the thing it excluded."""
    missing = [d for d in REQUIRED_DENOMINATORS if d not in metrics]
    rep.check(
        "the cache reports EXACT denominators (occurrences, unique mec_ids, general, "
        "variant, ambiguous) — a field named `n_total_*` that actually counts only the "
        "rankable subset makes the excluded evidence invisible in the very accounting a "
        "reader would use to notice it was excluded",
        not missing, f"missing: {missing}")

    if missing:
        return

    occ = metrics["n_assertion_occurrences"]
    parts = (metrics["n_general_rankable_assertions"]
             + metrics["n_variant_specific_assertions"]
             + metrics["n_ambiguous_copy_assertions"])
    rep.check(
        "the denominators RECONCILE: general + variant + ambiguous == occurrences",
        occ == parts, f"{parts} != {occ}")

    rep.check(
        "no metric is named `n_total_drug_assertions` while counting only the rankable "
        "subset",
        "n_total_drug_assertions" not in metrics
        or metrics.get("n_total_drug_assertions") == occ,
        f"n_total_drug_assertions={metrics.get('n_total_drug_assertions')!r} but there are "
        f"{occ} occurrences")
