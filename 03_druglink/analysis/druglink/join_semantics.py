"""The FROZEN cross-time join semantics, expressed as refusals.

Two selection modes exist, and they answer different questions:

``within_condition`` (same-time)
    The join is **two Direct arms** plus their **two condition-matched Pathway arms**.
    Everything is measured at one condition.

``temporal_cross_condition`` (cross-time)
    The gene ranking is **two Temporal DiD arms** — never same-time Direct gene ranks.
    The pathway panels are the **corresponding ENDPOINT Direct-Pathway contexts**:
    A at ``from_condition``, B at ``to_condition``. They are labelled **endpoint pathway
    context** and are NEVER temporal enrichment, temporal fate, or a longitudinal
    statistic. There is no pathway statistic computed ACROSS time, because none was
    measured across time — the endpoints are two within-condition results shown side by
    side, and saying otherwise would invent a longitudinal claim out of two static ones.

Stage-3 drug acquisition therefore consumes **the selected temporal gene arms** under a
cross-time selection.

WHAT THIS MODULE ACTUALLY DOES TODAY, AND WHY IT IS ONLY REFUSALS
----------------------------------------------------------------
Stage 3 **cannot yet consume temporal arms**. A temporal run emits ``temporal.parquet`` /
``endpoints.parquet``; the Stage-3 loader requires a Direct run's ``screen.parquet``. That
capability needs contract fields Stage-3's FROZEN schema does not have
(``analysis_mode``, ``from_condition``/``to_condition``, a pathway-context label), so it
is a deliberate v2 change, not something to smuggle in.

The DANGEROUS thing in the meantime is not the missing feature — it is the near-miss. A
Direct run has ``screen.parquet`` and loads perfectly. Hand one to Stage 3 under a
cross-time selection and it will cheerfully rank drugs on **same-time gene ranks** and
answer a question nobody asked, with no error anywhere. Nothing in the bundle would say
so.

So the semantics are frozen NOW as fail-closed refusals. A cross-time selection cannot
reach the same-time gene ranks by accident, and an endpoint pathway cannot be relabelled
temporal — long before anything can consume either.

A Direct run declares exactly ONE ``analysis_condition``. That is the proof it is a
same-time artifact: it is not a claim Stage 3 makes about the run, it is what the run says
about itself.
"""
from __future__ import annotations

from typing import Any, Optional

# --------------------------------------------------------------------------- #
# The two modes.
# --------------------------------------------------------------------------- #
WITHIN_CONDITION = "within_condition"
TEMPORAL_CROSS_CONDITION = "temporal_cross_condition"
SELECTION_MODES = (WITHIN_CONDITION, TEMPORAL_CROSS_CONDITION)

# Where the GENE ranking legitimately comes from, per mode. This is the whole point:
# a cross-time selection's genes come from the Temporal DiD arms and nowhere else.
GENE_ARM_SOURCE = {
    WITHIN_CONDITION: "direct_same_time_arms",
    TEMPORAL_CROSS_CONDITION: "temporal_did_arms",
}

# The pathway panel, per mode. Under cross-time these are the ENDPOINT within-condition
# Direct-Pathway contexts — A at from_condition, B at to_condition.
PATHWAY_CONTEXT = {
    WITHIN_CONDITION: "condition_matched_direct_pathway",
    TEMPORAL_CROSS_CONDITION: "endpoint_direct_pathway",
}

ENDPOINT_PATHWAY_CONTEXT = PATHWAY_CONTEXT[TEMPORAL_CROSS_CONDITION]

JOIN_SEMANTICS_ID = "spot.stage03.join_semantics.v1"

# --------------------------------------------------------------------------- #
# Vocabulary that would turn an endpoint reading into a longitudinal claim.
#
# These are refused at ANY nesting depth, in the document and in every table — the same
# firewall that refuses a combined objective, for the same reason: the forbidden thing is
# not the word, it is the claim the word smuggles in. Two within-condition enrichments
# shown side by side are not a statistic about change over time, and a field called
# `temporal_enrichment_score` asserts that they are.
# --------------------------------------------------------------------------- #
TEMPORAL_PATHWAY_CLAIMS = frozenset({
    "temporal_enrichment", "temporal_enrichment_score", "temporal_enrichment_value",
    "temporal_pathway_score", "temporal_pathway_statistic", "temporal_fate",
    "fate_trajectory", "pathway_trajectory", "trajectory_score",
    "longitudinal_enrichment", "longitudinal_statistic", "longitudinal_score",
    "longitudinal_pathway_score", "pathway_delta_score", "enrichment_delta",
    "enrichment_change_score", "cross_time_enrichment", "cross_time_pathway_score",
    "temporal_convergence", "temporal_signature_score",
})


class JoinSemanticsError(ValueError):
    """The selection mode and the artifacts handed to Stage 3 do not agree."""


def require_mode(mode: str) -> str:
    if mode not in SELECTION_MODES:
        raise JoinSemanticsError(
            f"unknown selection mode {mode!r}; Stage 3 knows {list(SELECTION_MODES)}")
    return mode


def direct_run_conditions(direct: Any) -> list[str]:
    """The condition(s) a Direct run declares about ITSELF (never inferred)."""
    axis = getattr(direct, "axis", None) or {}
    one = axis.get("analysis_condition")
    if one is None:
        return []
    return [one] if isinstance(one, str) else list(one)


def admit_gene_arm_source(mode: str, direct: Any) -> str:
    """Refuse a cross-time selection that is about to rank on SAME-TIME gene arms.

    This is the near-miss the whole module exists for. A Direct run loads fine and its
    arms look exactly like the arms a temporal selection wants — so without this, a
    cross-time question gets answered with same-time ranks and nothing anywhere says so.
    """
    require_mode(mode)
    conditions = direct_run_conditions(direct)

    if mode == WITHIN_CONDITION:
        if len(conditions) != 1:
            raise JoinSemanticsError(
                f"a {WITHIN_CONDITION} selection needs a Direct run measured at exactly "
                f"ONE condition; this run declares {conditions or 'none'}")
        return GENE_ARM_SOURCE[WITHIN_CONDITION]

    # temporal_cross_condition
    raise JoinSemanticsError(
        f"REFUSED: a {TEMPORAL_CROSS_CONDITION} selection ranks genes on the TEMPORAL "
        f"DiD arms ({GENE_ARM_SOURCE[TEMPORAL_CROSS_CONDITION]}), and this is a Direct "
        f"run measured at a single condition ({conditions or 'none'}) — its ranks are "
        "SAME-TIME. Stage 3 will not answer a cross-time question with same-time gene "
        "ranks. Stage 3 cannot yet consume temporal arms (a temporal run emits "
        "temporal.parquet/endpoints.parquet, not screen.parquet); that consumption is a "
        "v2 contract change, not something to approximate here.")


def admit_pathway_context(mode: str, declared: Optional[str] = None) -> str:
    """The pathway panel's context label for this mode.

    Under cross-time the panels are the ENDPOINT within-condition Direct-Pathway
    contexts. They are never temporal enrichment and never a fate claim.
    """
    require_mode(mode)
    expected = PATHWAY_CONTEXT[mode]
    if declared is not None and declared != expected:
        raise JoinSemanticsError(
            f"a {mode} selection's pathway panels are {expected!r}; the document "
            f"declares {declared!r}")
    return expected


def temporal_claims_in(obj: Any, path: str = "$") -> list[str]:
    """Every key, at any depth, that asserts a statistic ACROSS time. JSON-path'd."""
    hits: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(key, str) and key.lower() in TEMPORAL_PATHWAY_CLAIMS:
                hits.append(f"{path}.{key}")
            hits += temporal_claims_in(value, f"{path}.{key}")
    elif isinstance(obj, (list, tuple)):
        for i, item in enumerate(obj):
            hits += temporal_claims_in(item, f"{path}[{i}]")
    return hits


def refuse_temporal_pathway_claim(doc: Any, *, what: str = "pathway document") -> None:
    """A pathway artifact may not carry a statistic computed across time."""
    hits = temporal_claims_in(doc)
    if hits:
        raise JoinSemanticsError(
            f"REFUSED: this {what} carries a statistic computed ACROSS TIME "
            f"({hits[:5]}). Under a cross-time selection the pathway panels are the "
            f"{ENDPOINT_PATHWAY_CONTEXT} — two WITHIN-condition endpoint readings (A at "
            "from_condition, B at to_condition) shown side by side. Nothing was measured "
            "across time, so no longitudinal pathway statistic exists to report. Naming "
            "one invents it.")


# --------------------------------------------------------------------------- #
# The run topology. 15 PHYSICAL bundles carry 300 LOGICAL arm slots.
#
# The physical shape is not a compromise: the expensive step is the dense pooled-main
# read, one per condition, and all programs project off that single read. Collapsing the
# logical slots into the physical bundles is what makes 300 arms cost 3 dense reads
# instead of 420.
# --------------------------------------------------------------------------- #
N_PROGRAMS = 10
N_DESIRED_CHANGES = 2                 # the two arms; independent, never combined
N_CONDITIONS = 3                      # Rest, Stim8hr, Stim48hr
N_ORDERED_PAIRS = 6                   # ordered condition pairs (from -> to)
N_GENE_SET_SOURCES = 2                # Reactome, GO-BP

DIRECT_SLOTS = N_PROGRAMS * N_DESIRED_CHANGES * N_CONDITIONS               # 60
TEMPORAL_SLOTS = N_PROGRAMS * N_DESIRED_CHANGES * N_ORDERED_PAIRS          # 120
PATHWAY_SLOTS = (N_PROGRAMS * N_DESIRED_CHANGES
                 * N_CONDITIONS * N_GENE_SET_SOURCES)                      # 120
LOGICAL_ARM_SLOTS = DIRECT_SLOTS + TEMPORAL_SLOTS + PATHWAY_SLOTS          # 300

PHYSICAL_BUNDLES = N_CONDITIONS + N_ORDERED_PAIRS + (N_CONDITIONS * N_GENE_SET_SOURCES)
assert PHYSICAL_BUNDLES == 15                                              # 3 + 6 + 6
assert LOGICAL_ARM_SLOTS == 300
