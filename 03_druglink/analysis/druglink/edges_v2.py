"""The v2 EDGE layer: one reusable arm x one typed origin x one typed target x one assertion.

Split out of :mod:`druglink.candidates_v2` (the CANDIDATE layer) at the 500-line gate — the
same seam ``universe_rows`` and ``universe_edges`` already draw between target identity and
source assertion. Audit blocker **B7**.

Arms are REUSABLE: ``lane | program_id | desired_change | context``. A ROLE
(``away_from_A``/``toward_B``) is not a property of an arm — it is what a *selection* gives an
arm at join time — so **nothing here assigns one, and there is no field for one**.

An edge BINDS: the reusable arm key and its context, the typed origin, the exact typed target,
the source assertion's own identity (``mec_id`` — the ChEMBL mechanism row), the digest of the
direction vocabulary it was classified under, the intervention effect and its reason, the
directional status, the observed-support flag, the evidence class, the NULLABLE source arm
rank, and every upstream admission hash it stands on.

Direction is recomputed HERE, at build time, from the frozen Stage-3 vocabulary
(:mod:`druglink.direction`) against the arm's own desired modulation. The store carries
``action_type`` verbatim and no verdict: a cached verdict is one nobody can re-derive, and it
outlives the vocabulary that produced it.

THE THREE TYPED ORIGINS, AND WHAT EACH MAY CARRY:

  ``direct_target``                 same-condition measured perturbation.
  ``temporal_cross_time_measured``  cross-time DiD — measured, and a DISTINCT estimand, never
                                    fused with the same-condition effect.
  ``endpoint_pathway_context``      INFERRED. Nobody perturbed it, so it can never carry a
                                    measured rank and can never carry observed support — and a
                                    direction taken from mere set MEMBERSHIP is inert.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional, Sequence

from . import direction as dr
from . import modality_v2 as mv2
from . import pathway_context_v2 as pc2
from . import stage2_aggregate as sa
from . import universe_rows as ur
from .assertions_v2 import (  # noqa: F401  (the one front door: re-exported for consumers)
    GATE_ABSENCE_NOT_STATED,
    GATE_NO_SOURCE_LOCATOR,
    GATE_NO_SOURCE_RELEASE,
    MISSINGNESS_STATES,
    NO_DRUG_EVIDENCE,
    NOT_APPLICABLE_INFERRED,
    NOT_STATED,
    RANKED,
    SOURCE_RECORD_COLUMNS,
    SOURCE_RECORD_KEY,
    STATED,
    UNRANKED,
    AssertionV2Error,
    check_edge_absence,
    identity_status,
    moiety_id,
    rankable,
    release_binding,
    source_locator,
    source_record,
    stated,
)
from .dispositions_v2 import (  # noqa: F401  (re-exported: edges_v2 is the front door)
    DISPOSITION_COLUMNS,
    DISPOSITION_KEY,
    STATE_NO_DRUG_EVIDENCE,
    STATE_NON_RANKABLE,
    STATE_NOT_IN_UNIVERSE,
    STATE_PATHWAY_IS_TYPED_CONTEXT,
    STATE_PATHWAY_LANE_NOT_ADMITTED,
    STATE_UNSUPPORTED_NAMESPACE,
    disposition,
)
from .canonical_number import canonical_number
from .hashing import canonical_json, content_hash, short_id

# Lane -> the typed origin its evidence carries. DERIVED from the lane, never declared by the
# row: a row that can name its own origin can name the wrong one.
ORIGIN_FOR_LANE = {
    sa.LANE_DIRECT: dr.ORIGIN_DIRECT_TARGET,
    sa.LANE_TEMPORAL: dr.ORIGIN_TEMPORAL_CROSS_TIME,
    sa.LANE_PATHWAY: dr.ORIGIN_ENDPOINT_PATHWAY,
}
V2_ORIGINS = tuple(dr.V2_ORIGIN_TYPES)

# THE DIRECTION IS DECLARED BY STAGE 2, NEVER INFERRED HERE. The three declared fields, the
# modality->modulation gate, the DERIVED compatible-mechanism set and the phenocopy label all
# live in :mod:`druglink.modality_v2`. Stage 3 reads what Stage 2 serialized and refuses what
# it did not: there is no translation table here to drift, and no default to fall back to.

# The roles a SELECTION assigns at join time. They may never appear in this bundle.
SELECTION_ROLES = ("away_from_A", "toward_B")

# Named gates. Every refusal cites one, so it can be grepped, tested and quoted.
GATE_UNKNOWN_MODULATION = "stage2_modulation_vocabulary_is_not_the_one_stage3_translates"
GATE_STAGE2_ADMISSION_NOT_CARRIED = "an_edge_carries_no_stage2_verifier_identity_or_verdict"
GATE_UNKNOWN_LANE = "an_arm_arrived_on_a_lane_with_no_typed_origin"
GATE_INFERRED_ORIGIN_HAS_A_RANK = "an_inferred_pathway_edge_carries_a_measured_rank"
GATE_INFERRED_ORIGIN_HAS_SUPPORT = "an_inferred_pathway_edge_carries_observed_support"
GATE_MEASURED_ORIGIN_NOT_MEASURED = "a_measured_origin_lost_its_perturbation_modality"
GATE_ORIGIN_LANE_DISAGREE = "an_edge_origin_disagrees_with_the_lane_it_came_from"
GATE_ROLE_IN_A_REUSABLE_ARM = "a_selection_role_was_baked_into_a_reusable_arm"
GATE_UNTYPED_TARGET = "an_arm_record_carries_no_typed_target_identity"

# Table contracts. The writer DERIVES its columns from these rather than restating them, so a
# table and the rows it holds cannot drift apart.
ARM_IDENTITY_COLUMNS: tuple[str, ...] = (
    "arm_key", "lane", "program_id", "desired_change",
    "condition", "from_condition", "to_condition", "pathway_source",
    "arm_context_sha256",
)

# The NATIVE provenance keys. `stage2_aggregate.admit_aggregate` emits `aggregate_verifier_id`
# and `aggregate_verdict`; the retired columns read `independent_verifier_id` /
# `independent_verdict`, which the loader has never emitted — so EVERY edge carried a null
# verifier identity and a null verdict, and nothing crashed. The verifier read the same wrong
# keys, so producer and verifier AGREED on None and the reconstruction matched. A binding both
# sides get wrong in the same way is a binding nobody has.
UPSTREAM_COLUMNS: tuple[str, ...] = (
    "stage2_manifest_raw_sha256", "stage2_manifest_canonical_sha256",
    "stage2_manifest_self_hash", "stage2_aggregate_verifier_id",
    "stage2_aggregate_verdict", "stage1_release_sha256",
    "bundle_key", "bundle_raw_sha256", "bundle_canonical_sha256",
    "ranking_raw_sha256", "ranking_canonical_sha256",
    "universe_store_id", "typed_universe_sha256",
)

EDGE_COLUMNS: tuple[str, ...] = (
    ("edge_id",)
    + ARM_IDENTITY_COLUMNS
    + ("origin_type", "origin_is_measured",
       # THE TWO FACTS, IN SEPARATE FIELDS. The modality says WHAT WAS TESTED and stands alone;
       # the sign says whether doing it HELPED. `desired_target_modulation` is DERIVED from both
       # — never from the modality alone — and is cross-checked against Stage-2's own token.
       "observed_perturbation_modality", "observed_sign_state", "desired_target_modulation",
       "stage2_desired_target_modulation", "stage2_phenocopy_class",
       # What the observation supports doing, and what it merely raises as an untested inverse.
       # On an opposing sign the compatible action is NULL: the screen supports nothing.
       "observed_compatible_action", "untested_inverse_action",
       "pharmacologic_reversibility_assumed",
       # PHENOCOPY, NOT EQUIVALENCE — as FIELDS, because Stage 4 reads fields. An agonist on a
       # CRISPRi arm carries the UNTESTED-INVERSE relation, never a phenocopy relation.
       "evidence_relation", "evidence_relation_caveat", "evidence_is_equivalence",
       "mechanism_phenocopies_modality",
       # The row's OWN namespace token, verbatim. No alias layer, no release-level default.
       "target_id", "target_id_namespace",
       "target_symbol", "target_ensembl",
       "released_estimate_id", "set_id",
       # PATHWAY CONTEXT, on an edge whose evidence is MEASURED. The pathway says which set this
       # target sits in; it contributed no direction and sourced no claim.
       "pathway_refs", "n_pathway_refs",
       # A nullable magnitude ALWAYS travels with the status that says why it is absent.
       "arm_rank", "arm_rank_status", "arm_evaluable",
       "arm_value_source_string", "arm_value_canonical_decimal", "arm_value_status",
       # WHETHER THE KNOCKDOWN WAS SHOWN TO WORK. An arm asserting a perturbation with no
       # on-target evidence is FLAGGED, never silently trusted.
       "on_target_evidence", "on_target_evidence_status",
       # How the sourced mechanism stands to the arm, and if it does not support it, WHY.
       "mechanism_match_status",
       "source_record_id", "source_locator", "source_release",
       "mec_id", "molecule_chembl_id", "target_chembl_id",
       # candidate_id IS the active moiety id, carried byte-identically into every table
       # that references a candidate. Stage 4 joins on it.
       "candidate_id", "active_moiety_id", "assertion_lane", "general_gene_rankable",
       "action_type_source", "action_type_normalized",
       "max_phase_source", "max_phase_status", "max_phase_is_context_only",
       "direction_vocabulary_digest", "modality_vocabulary_digest",
       "intervention_effect", "intervention_effect_reason",
       "directional_evidence_status", "directional_evidence_reason",
       "observed_perturbation_support", "stage3_evidence_class")
    + UPSTREAM_COLUMNS
)
EDGE_KEY: tuple[str, ...] = ("edge_id",)



class CandidatesV2Error(ValueError):
    """A named, fail-closed refusal. Never a fixture fallback, never a partial answer."""

    def __init__(self, gate: str, message: str) -> None:
        super().__init__(f"[{gate}] {message}")
        self.gate = gate


# --- 1. The reusable arm: key + context, and no role anywhere. --------------- #
def arm_context(arm: sa.LoadedArm) -> dict[str, Any]:
    """A condition, an ORDERED from->to pair, or a condition x gene-set source.

    Read from the BUNDLE the arm came from — the one place Stage 2 states it. A context copied
    onto the arm is a context that can disagree with the bundle it was loaded from.
    """
    bundle = arm.bundle
    return {"condition": bundle.condition, "from_condition": bundle.from_condition,
            "to_condition": bundle.to_condition, "pathway_source": bundle.pathway_source}


def arm_identity(arm: sa.LoadedArm) -> dict[str, Any]:
    """arm_key | lane | program_id | desired_change | context. NO role, NO pole, NO score."""
    if arm.lane not in ORIGIN_FOR_LANE:
        raise CandidatesV2Error(
            GATE_UNKNOWN_LANE,
            f"arm {arm.arm_key!r} arrived on lane {arm.lane!r}, which has no typed origin. "
            f"Known lanes: {sorted(ORIGIN_FOR_LANE)}")
    ctx = arm_context(arm)
    return {"arm_key": arm.arm_key, "lane": arm.lane, "program_id": arm.program_id,
            "desired_change": arm.desired_change, **ctx,
            "arm_context_sha256": content_hash({"lane": arm.lane, **ctx})}


def upstream(arm: sa.LoadedArm, store: ur.AdmittedStore) -> dict[str, Any]:
    """Every hash the edge stands on. An edge nobody can trace is an edge nobody can check.

    The Stage-2 verifier identity and verdict are REQUIRED, not merely copied. Reading a key the
    loader does not emit yields None, and a None here is silent: the edge still builds, the
    bundle still verifies, and every row carries a null where its admission ought to be.
    """
    prov = arm.provenance
    verifier = prov.get("aggregate_verifier_id")
    verdict = prov.get("aggregate_verdict")
    if not verifier or not verdict:
        raise CandidatesV2Error(
            GATE_STAGE2_ADMISSION_NOT_CARRIED,
            f"arm {arm.arm_key!r} carries aggregate_verifier_id={verifier!r} / "
            f"aggregate_verdict={verdict!r}. Every edge must name the verifier that admitted the "
            "Stage-2 release it stands on — a null there is an edge whose admission nobody can "
            "read, and it would ride out to Stage 4 looking exactly like an admitted one")
    return {
        "stage2_manifest_raw_sha256": prov.get("manifest_raw_sha256"),
        "stage2_manifest_canonical_sha256": prov.get("manifest_canonical_sha256"),
        "stage2_manifest_self_hash": prov.get("manifest_self_hash"),
        "stage2_aggregate_verifier_id": verifier,
        "stage2_aggregate_verdict": verdict,
        "stage1_release_sha256": prov.get("stage1_release_sha256"),
        "bundle_key": arm.bundle.bundle_key,
        "bundle_raw_sha256": arm.bundle.raw_sha256,
        "bundle_canonical_sha256": arm.bundle.canonical_sha256,
        "ranking_raw_sha256": arm.ranking.get("raw_sha256"),
        "ranking_canonical_sha256": arm.ranking.get("canonical_sha256"),
        "universe_store_id": store.store_id,
        "typed_universe_sha256": store.typed_universe_sha256,
    }


# --- 2. Direction: DECLARED by Stage 2, read and gated. Never inferred here. -- #
#
# The whole contract lives in :mod:`druglink.modality_v2`. What matters at this seam:
# `declared_direction` REFUSES a row that does not carry all three fields, refuses a modulation
# that disagrees with the declared modality, and refuses a modulation carrying the PROGRAM's
# vocabulary — which is exactly what deriving it from `program_effect_direction` would produce.
def _estimate_id(record: Mapping[str, Any]) -> Optional[str]:
    """Same-time: one released estimate id. Cross-time: the DiD stands on BOTH endpoints."""
    est = record.get("released_estimate_id")
    if est is None or isinstance(est, str):
        return est
    return canonical_json(est)


def _value_strings(record: Mapping[str, Any]) -> tuple[Optional[str], Optional[str]]:
    """The arm value as an exact SOURCE string + its canonical decimal. Never a float."""
    value = record.get("arm_value")
    if value is None or isinstance(value, bool):
        return None, None
    return repr(value) if isinstance(value, float) else str(value), canonical_number(value)


# --- 3. The edge. ----------------------------------------------------------- #
def modality_digest() -> str:
    """A content address for the DECLARED direction contract itself."""
    return content_hash(mv2.vocabularies())


def build_edge(arm: sa.LoadedArm, record: Mapping[str, Any], assertion: Mapping[str, Any],
               *, store: ur.AdmittedStore, digest: str, namespace: str,
               pathway_refs: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
    ident = arm_identity(arm)
    origin = ORIGIN_FOR_LANE[arm.lane]
    measured = origin in dr.MEASURED_ORIGINS

    # A DRUG DIRECTION MAY ONLY COME FROM A MEASURED LANE.
    #
    # A pathway record is a GENE-SET ENRICHMENT — an enrichment value over a set, with a leading
    # edge. It is not a per-target knockdown effect and it carries no CRISPRi sign. Building a
    # drug edge from it would take a set-level statistic, hand it a sign it never had, and let it
    # support a drug direction as though a knockdown had been measured on that gene: guilt by
    # association wearing the costume of a measurement.
    if not measured:
        raise CandidatesV2Error(
            mv2.GATE_INFERRED_ORIGIN_PRODUCED_A_DRUG_EDGE,
            f"arm {arm.arm_key!r} is an {origin} arm; nobody perturbed these nodes. Pathway "
            "evidence is TYPED CONTEXT — never a measured lever, never rankable as support, and "
            "never a source of drug direction. A direction is not inherited from set membership")

    # A SET-LEVEL STATISTIC MAY NEVER SOURCE AN EDGE. Checked on the record that is actually
    # about to source one, not merely on the lane it arrived by.
    pc2.check_no_set_level_source(record, arm_key=arm.arm_key)

    # WHAT WAS TESTED, and WHETHER IT HELPED. Two separate facts, neither derived from the other.
    modality = mv2.declared_modality(record, arm_key=arm.arm_key)
    evaluable = mv2.evaluable_of(record, arm_key=arm.arm_key)
    sign = mv2.observed_sign_state(record.get(mv2.FIELD_ARM_VALUE), evaluable=evaluable,
                                   origin_is_measured=measured, arm_key=arm.arm_key)
    # Stage-2's OWN token, used to CHECK the orientation — never to drive the classification.
    stage2_token = mv2.check_serialized_modulation(record, sign, modality=modality,
                                                  arm_key=arm.arm_key)
    phenocopy_class = mv2.phenocopy_class_of(record, arm_key=arm.arm_key)

    action_source = assertion.get("action_type_source")
    # THE SIGN DECIDES. An incompatible mechanism is an EXPLICIT non-match carrying its reason —
    # never dropped, never merely ranked lower.
    verdict = mv2.classify(action_type=action_source, modality=modality, sign_state=sign,
                           origin_is_measured=measured)

    source_string, canonical = _value_strings(record)
    binding = release_binding(store)
    rank = record.get("rank")
    mid = moiety_id(assertion)
    edge = {
        **ident,
        "origin_type": origin,
        "origin_is_measured": measured,
        **verdict,
        "stage2_desired_target_modulation": stage2_token,
        "stage2_phenocopy_class": phenocopy_class,
        "target_id": record.get("target_id"),
        "target_id_namespace": namespace,
        "on_target_evidence": record.get("on_target_evidence"),
        "on_target_evidence_status": stated(record.get("on_target_evidence")),
        "target_symbol": record.get("target_symbol"),
        "target_ensembl": record.get("target_ensembl"),
        "released_estimate_id": _estimate_id(record),
        "set_id": record.get("set_id"),
        # CONTEXT, not evidence: which pathway(s) this MEASURED target sits in. It contributed
        # no direction, no rank and no support — the sign above did all of that.
        "pathway_refs": [dict(r) for r in pathway_refs],
        "n_pathway_refs": len(pathway_refs),
        # A null rank is a STATE, and the state is SPOKEN: never 0, never last, never
        # invented. An inferred node has no rank because nobody perturbed it — which is a
        # different fact from a measured target the source left unranked.
        "arm_rank": rank,
        "arm_rank_status": (NOT_APPLICABLE_INFERRED if not measured
                            else RANKED if rank is not None else UNRANKED),
        "arm_evaluable": evaluable,
        "arm_value_source_string": source_string,
        "arm_value_canonical_decimal": canonical,
        "arm_value_status": stated(source_string),
        "source_record_id": assertion.get("edge_id"),
        # The exact ChEMBL row this edge stands on, and the release it lives in.
        "source_locator": source_locator(assertion, binding),
        "source_release": binding["chembl_release"],
        "mec_id": assertion.get("source_row_id"),
        "molecule_chembl_id": assertion.get("molecule_chembl_id"),
        "target_chembl_id": assertion.get("target_chembl_id"),
        "candidate_id": mid,
        "active_moiety_id": mid,
        "assertion_lane": assertion.get("lane"),
        "general_gene_rankable": assertion.get("general_gene_rankable"),
        "action_type_source": action_source,
        "action_type_normalized": dr.normalize_action_type(action_source),
        "modality_vocabulary_digest": modality_digest(),
        # CONTEXT only, and the row says so. It may never gate or rank.
        "max_phase_source": assertion.get("max_phase_source"),
        "max_phase_status": stated(assertion.get("max_phase_source")),
        "max_phase_is_context_only": True,
        # WHICH vocabulary this classification was computed under. Move a term between sets and
        # the digest moves with it, instead of a drug quietly starting to rank.
        "direction_vocabulary_digest": digest,
        **upstream(arm, store),
    }
    edge["edge_id"] = short_id({k: edge[k] for k in EDGE_COLUMNS if k != "edge_id"})
    # The sign gates, on the row that was actually built.
    mv2.check_edge_relation(edge)
    mv2.check_sign_rule(edge)
    return edge


def check_edges(edges: Iterable[Mapping[str, Any]]) -> None:
    """The invariants an edge may never violate, re-asserted on the ROWS themselves.

    Checked on the rows and not merely inside the builder: the builder is one caller, and a
    property nobody re-checks on the emitted bytes is a property the next writer can drop.
    """
    for edge in edges:
        origin, lane = edge.get("origin_type"), edge.get("lane")
        if origin not in V2_ORIGINS:
            raise CandidatesV2Error(
                GATE_ORIGIN_LANE_DISAGREE,
                f"edge {edge.get('edge_id')!r} carries origin {origin!r}, which is not one of "
                f"the three typed v2 origins {list(V2_ORIGINS)}")
        if ORIGIN_FOR_LANE.get(str(lane)) != origin:
            raise CandidatesV2Error(
                GATE_ORIGIN_LANE_DISAGREE,
                f"edge {edge.get('edge_id')!r} came from lane {lane!r} but is stamped "
                f"{origin!r}. Direct and temporal are distinct estimands and are never fused, "
                "and an inferred node is never a measurement")
        if origin in dr.INFERRED_ORIGINS:
            # A pathway enrichment record may never become a drug edge at all — it has no
            # CRISPRi sign to give one a direction.
            raise CandidatesV2Error(
                mv2.GATE_INFERRED_ORIGIN_PRODUCED_A_DRUG_EDGE,
                f"edge {edge.get('edge_id')!r} claims origin {origin!r}. Nobody perturbed this "
                "node: pathway evidence is typed CONTEXT and never a source of drug direction")
        if edge.get("observed_perturbation_modality") not in mv2.MODALITY_PERFORMED_ACTION:
            raise CandidatesV2Error(
                GATE_MEASURED_ORIGIN_NOT_MEASURED,
                f"edge {edge.get('edge_id')!r} is a MEASURED {origin} edge declaring "
                f"observed_perturbation_modality="
                f"{edge.get('observed_perturbation_modality')!r}; what the screen DID is not "
                "optional context, and it is never defaulted")
        # THE SIGN GATES, re-asserted on the emitted row. A property nobody re-checks on the
        # bytes is a property the next writer can drop.
        mv2.check_edge_relation(edge)
        mv2.check_sign_rule(edge)
        if not (edge.get("target_id") and edge.get("target_id_namespace")):
            raise CandidatesV2Error(
                GATE_UNTYPED_TARGET,
                f"edge {edge.get('edge_id')!r} carries target_id={edge.get('target_id')!r} in "
                f"namespace {edge.get('target_id_namespace')!r}; the join is by exact typed "
                "identity and never degrades to a symbol")
        arm = canonical_json({k: edge.get(k) for k in ARM_IDENTITY_COLUMNS})
        for role in SELECTION_ROLES:
            if role in arm:
                raise CandidatesV2Error(
                    GATE_ROLE_IN_A_REUSABLE_ARM,
                    f"edge {edge.get('edge_id')!r} carries the selection role {role!r} in its "
                    "reusable arm identity. A role is assigned by a SELECTION at join time; "
                    "baking one in fuses two different questions under one key")
        check_edge_absence(edge)
