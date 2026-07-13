"""THE STAGE-2 -> STAGE-3 ROW CONTRACT: what was DONE, what was OBSERVED, what is IMPLIED.

TWO SEAMS, AND STAGE 3 READS THE SECOND ONE
-------------------------------------------
    SEAM A  RAW, PRODUCER-PRIVATE.   Every lane is different. Direct's arm_rows carry
                                     ``value``; temporal's carry ``arm_value`` and keep the
                                     target's identity somewhere else entirely; pathway does
                                     not carry target rows AT ALL.
    SEAM B  THE BOUND RANKING.       ``rankings/<program>__<change>.json`` ->
                                     ``{"records": [{target_id, arm_value, evaluable, rank}]}``
                                     for every lane (``arm_topology.ARM_RANKING_ROWS``). This
                                     is the artifact the aggregate BINDS and the independent
                                     verifier ADMITS.

**Stage 3 consumes SEAM B — the admitted, normalized rows — and never a raw producer shape.**
An earlier draft of this file read SEAM A and called it native: it declared Direct=``value``,
temporal=``arm_value``, pathway=``score``. That was a THIRD shape, invented, and it would
have read the number off exactly one lane and ``None`` off the others — and a ``None`` arm
value derives ``not_evaluated``, which is silent, plausible and wrong. The raw shapes are
still stated below, but ONLY as the adapter that produces SEAM B, never as what Stage 3 reads.

PATHWAY IS NOT A TARGET-EVIDENCE LANE
-------------------------------------
The pathway lane's native records are one per (pathway-arm x GENE SET), carrying an
``enrichment_value`` and a ``leading_edge`` — they are not per-target CRISPRi measurements.
Handing them to Stage 3 as target rows would let an ENRICHMENT SCORE be read as a target's
arm value, and a gene set be prescribed a drug. So pathway contributes typed pathway CONTEXT,
linked to targets through its leading edge and its convergence artifact. Target evidence comes
from Direct and temporal, and only from them.

THE INVERSION THIS EXISTS TO MAKE IMPOSSIBLE
--------------------------------------------
The arm key carries ``desired_change=increase|decrease``. That is the direction of the
**PROGRAM**. The perturbation behind every number here is a **CRISPRi knockdown** — the target
was only ever pushed DOWN. A Stage 3 that reads ``desired_change=increase`` as "we want more
of this target" hunts for AGONISTS on exactly the targets whose knockdown RAISED the program.
So the row states all three separately, and derives none of them from another:

    observed_perturbation_modality   WHAT WAS DONE.   CRISPRi_knockdown. From the joined
                                     identity record, not asserted by this module.
    program_effect_direction         THE PROGRAM AXIS. The arm's own desired_change.
    desired_target_modulation        WHAT IS IMPLIED.  Re-derived from the ORIENTED arm value
                                     and evaluability ALONE.

    value >  +eps  -> decrease  -> inhibition_observed_compatible   (the ONLY class an
                                   inhibitor may match, and the only SUPPORTED one)
    value <  -eps  -> increase  -> inhibitor_opposed. NOT an agonist recommendation: no CRISPRa
                                   arm was ever run, so there is no observation to phenocopy.
    |value|<= eps  -> no_direction_evidence
    not evaluable  -> not_evaluated

A CRISPRi phenocopy is a PHENOCOPY, never an EQUIVALENCE: an inhibitor is not a knockdown.

IDENTITY IS JOINED, NEVER SNIFFED
---------------------------------
The bound ranking row carries ``target_id`` and nothing about who that target IS. Identity
lives in a record the row JOINS to — temporal says so in its own bytes ("Stage-3 reads identity
from the base record it joins to", keyed by ``base_key``). The perturbed universe is 11,526
targets: 11,522 Ensembl accessions and FOUR bare symbols (MTRNR2L1/4/8, OCLM), and THREE of
those four carry an ENSG-looking RELEASE KEY belonging to a DIFFERENT GENE. So a namespace
guessed from the shape of a string attaches the wrong gene to a drug. It is joined, or the row
is REFUSED — never inferred, and never silently dropped: a dropped row and a row that was never
there look identical.
"""
from __future__ import annotations

from typing import Any, Optional

from .arm_topology import ARM_RANKING_ROWS, LANE_DIRECT, LANE_PATHWAY, LANE_TEMPORAL
from .target_identity import SCHEMA_VERSION as TARGET_IDENTITY_SCHEMA
from .target_identity import TARGET_IDENTITY_FILE

# --------------------------------------------------------------------------- #
# SEAM B — THE ADMITTED, NORMALIZED ROW. The one Stage 3 reads.
# --------------------------------------------------------------------------- #
RANKING_RECORDS_KEY = ARM_RANKING_ROWS            # "records"
NORMALIZED_ROW_FIELDS = ("target_id", "arm_value", "evaluable", "rank")

# --------------------------------------------------------------------------- #
# SEAM A — the RAW producer-private shapes, and the adapter that normalizes them.
# Stated so the adapter is explicit; NEVER read by the Stage-3 row builder.
# --------------------------------------------------------------------------- #
RAW_PRODUCER_ROW = {
    LANE_DIRECT: {"value_field": "value", "evaluable_field": "evaluable"},
    LANE_TEMPORAL: {"value_field": "arm_value", "evaluable_field": "evaluable"},
    # pathway has NO raw target row. Its records are (arm x gene set), not (arm x target).
    LANE_PATHWAY: None,
}

# WHICH LANES CARRY TARGET EVIDENCE *IN PRINCIPLE* — pathway does not, and saying so is the
# point. But carrying target rows is not enough: a lane can only be BUILT from if it also
# binds an identity + assay source (below). Direct qualifies on grain and fails on source.
TARGET_EVIDENCE_LANES = (LANE_DIRECT, LANE_TEMPORAL)

PATHWAY_LANE_ROLE = {
    "lane": LANE_PATHWAY,
    "carries_crispri_target_rows": False,
    "record_grain": "one record per (pathway arm x gene set)",
    "record_fields": ("gene_set_id", "enrichment_value", "leading_edge"),
    "links_to_targets_via": ("leading_edge", "convergence"),
    "may_be_matched_to_a_drug_as_a_target": False,
    "why": ("an enrichment value is a statement about a GENE SET, not a measurement of a "
            "target under knockdown. Read as a target's arm value it would prescribe a drug "
            "for a pathway"),
}

# --------------------------------------------------------------------------- #
# WHAT WAS DONE. `config.CRISPRI_MODALITY`; pin-tested against it.
# --------------------------------------------------------------------------- #
OBSERVED_PERTURBATION_MODALITY = "CRISPRi_knockdown"
PERTURBATION_TARGET_EFFECT = "target_transcript_reduced"
PHENOCOPY_CLAIM = "putative_crispri_phenocopy"

PROGRAM_INCREASE = "increase"
PROGRAM_DECREASE = "decrease"
PROGRAM_EFFECT_DIRECTIONS = (PROGRAM_INCREASE, PROGRAM_DECREASE)

# The producers' own MOD_* tokens (disposition.py), byte for byte.
MOD_DECREASE = "decrease"
MOD_INCREASE = "increase"
MOD_NO_DIRECTION = "no_direction_evidence"
MOD_NOT_EVALUATED = "not_evaluated"
MODULATIONS = (MOD_DECREASE, MOD_INCREASE, MOD_NO_DIRECTION, MOD_NOT_EVALUATED)

SIGN_EPS = 1e-9                                   # config.SIGN_EPS

INHIBITION_COMPATIBLE = "inhibition_observed_compatible"
INHIBITOR_OPPOSED = "inhibitor_opposed"
NO_DIRECTIONAL_RESPONSE = "no_directional_response"
NOT_EVALUABLE = "not_evaluable"

PHENOCOPY_CLASS_OF = {
    MOD_DECREASE: INHIBITION_COMPATIBLE,
    MOD_INCREASE: INHIBITOR_OPPOSED,
    MOD_NO_DIRECTION: NO_DIRECTIONAL_RESPONSE,
    MOD_NOT_EVALUATED: NOT_EVALUABLE,
}

STAGE3_MATCHING_POLICY = {
    "policy_id": "spot.stage02.stage3_row.crispri_phenocopy_matching.v1",
    "observed_perturbation_modality": OBSERVED_PERTURBATION_MODALITY,
    "claim_strength": PHENOCOPY_CLAIM,
    "claim_is_equivalence": False,
    "target_evidence_lanes": list(TARGET_EVIDENCE_LANES),
    "pathway_lane_carries_target_rows": False,
    "inhibitory_or_downregulating_mechanisms_may_match": [INHIBITION_COMPATIBLE],
    "rankable_as_supported": [INHIBITION_COMPATIBLE],
    "must_flag_opposition": [INHIBITOR_OPPOSED],
    "agonist_promotion_from_sign_inversion": False,
    "agonist_promotion_rule": (
        "a negative arm value OPPOSES an inhibitor; it does not SUPPORT an agonist. "
        "Activation is an untested inverse-direction hypothesis — no CRISPRa arm was run, so "
        "there is no observation for an agonist to phenocopy, and it may never be ranked as "
        "supported evidence on the strength of a sign inversion alone"),
    "unresolved_namespace": "refuse_never_silently_drop",
    "consumes": "the ADMITTED normalized ranking records — never a raw producer shape",
}

# --------------------------------------------------------------------------- #
# TARGET IDENTITY. `identity.py`'s enum, byte for byte. JOINED, never sniffed.
# --------------------------------------------------------------------------- #
ENSEMBL_GENE_ID = "ensembl_gene_id"
GENE_SYMBOL = "gene_symbol"
NAMESPACES = (ENSEMBL_GENE_ID, GENE_SYMBOL)
UNRESOLVED_IDENTITY = "unresolved_target_identity"

# WHERE each lane's identity record lives, and WHAT the ranking row joins to it BY. Temporal
# says this in its own bytes: identity is carried on base_records, "never on the arm records
# that join to it".
# EACH LANE NAMES ITS EXACT BOUND SOURCE, the key it joins on, and — because the two lanes
# call it different things — the exact field the ASSAY is declared in. There is NO default:
# a joined record that does not declare the perturbation does not get one supplied for it.
# WHERE EACH LANE'S IDENTITY AND ASSAY ACTUALLY LIVE — in bytes the bundle BINDS.
#
# DIRECT HAS NO SUCH SOURCE TODAY, and this contract will not pretend otherwise. An earlier
# draft named `screen.parquet` / `bindings.screen`. **Neither exists in the native all-arm
# bundle.** `arm_artifacts.VERIFIED_PATHS` at fc9bdcd is exactly:
#
#     arm_bundle.json  provenance.json  arms.parquet  masks.parquet
#     contributing_guides.parquet  guide_support.parquet  donor_support.parquet
#     input_manifest.json  gene_universe.json
#
# `arms.parquet` carries `target_id` and nothing else about identity; masks and
# contributing_guides omit `target_id_namespace` and `target_symbol` entirely;
# `provenance.target_identity_map` is OPTIONAL mapping metadata plus a hash, not a bound
# per-target table; and `config.CRISPRI_MODALITY` is never emitted into method or provenance
# at all. So Direct cannot today say, in bound bytes, who a target is or what was done to it.
#
# Naming a file that does not exist would pass fixtures and fail on the release. So Direct is
# UNAVAILABLE, by name, with the exact producer requirement attached — and a Direct target row
# REFUSES until the producer emits and binds it.
IDENTITY_JOIN = {
    LANE_DIRECT: {
        # the PRODUCER-EMITTED artifact, read through the shared loader. One row per target,
        # unique, and exactly the targets the bundle scored — the loader refuses otherwise.
        "record": TARGET_IDENTITY_FILE,
        "join_on": "target_id",
        "unique_by": ("target_id",),
        "modality_field": "observed_perturbation_modality",
        "bound_as": f"bindings.{TARGET_IDENTITY_FILE}",
    },
    LANE_TEMPORAL: {
        # temporal says this in its own bytes: identity is carried on base_records, "never on
        # the arm records that join to it", and Stage 3 reads it from the record it joins to
        "record": "base_records",
        "join_on": "base_key",
        "unique_by": ("base_key",),
        "modality_field": "perturbation_modality",
        "bound_as": "arm_bundle.json:base_records",
    },
}

# THE SHARED CONSTANTS, IMPORTED — never re-typed. `target_identity` owns the file's name and
# its schema; a second literal here is exactly how `.json` quietly becomes `.parquet` in
# somebody's test, and then a verifier checks a file nobody wrote.
#
# LANDED at 9bd5895: Direct emits `target_identity.json`, it is in arm_artifacts.VERIFIED_PATHS
# and in the producer file-set contract, and `target_identity.load()` is the ONE consumer entry
# point — it reopens the PRODUCER'S bytes in place, verifies them, and returns them with both
# hashes. Nobody re-derives identity from a mask, and nobody reads a target_id to guess what it
# is: four of this release's targets are bare SYMBOLS whose keys look nothing like the other
# 11,522, so a string heuristic is wrong for exactly the rows nobody thinks about.
DIRECT_IDENTITY = {
    "lane": LANE_DIRECT,
    "status": "EMITTED_AT_9bd5895_PENDING_W10_INDEPENDENT_GATE",
    "file": TARGET_IDENTITY_FILE,
    "schema_version": TARGET_IDENTITY_SCHEMA,
    "loader": "direct.target_identity.load",
    "records_key": "records",
    "producer_must_emit_and_bind": "a per-target identity + assay artifact",
    "required_columns": ("target_id", "target_id_namespace", "target_symbol",
                         "target_ensembl", "observed_perturbation_modality"),
    "must_be": ("unique per target_id", "listed in the bundle files map",
                "hash-bound", "covered by the lane's independent admission"),
    # SCOPE: a bundle covers ITS OWN CONDITION's targets, exactly — not the release. The three
    # conditions do not ship the same targets, so the 11,526-target universe is a RELEASE-level
    # fact and must never be used as a per-bundle expectation.
    "scope": "exactly the targets THIS condition scored — never the release universe",
    "why": ("`arms.parquet` has target_id only; masks/contributing_guides omit the namespace "
            "and symbol. Without this artifact a Direct target row could only get its "
            "namespace by sniffing the id — and three of the four symbol targets carry an "
            "ENSG-looking release key belonging to a DIFFERENT gene"),
}
DIRECT_IDENTITY_REQUIREMENT = DIRECT_IDENTITY      # the name the bridge already binds

IDENTITY_FIELDS = ("target_id_namespace", "target_symbol", "target_ensembl")

# THE PATHWAY LANE'S OWN FIELD NAME. Its records key gene sets by `set_id`; this contract
# calls them `gene_set_id`. One rename, stated once and adapted explicitly — not two words
# quietly meaning one thing, and not a `.get("gene_set_id")` that returns None forever.
# THE PATHWAY RECORD'S OWN FIELD NAMES. Read off `pathway_arms.enrichment_arms`, not guessed:
# the coverage is `target_source_coverage`, and a `.get("coverage")` against these bytes
# returns None on every record, forever, and nothing would ever say so.
PATHWAY_SET_ID_FIELD = "set_id"
PATHWAY_ENRICHMENT_FIELD = "enrichment_value"
PATHWAY_LEADING_EDGE_FIELD = "leading_edge"
PATHWAY_COVERAGE_FIELD = "target_source_coverage"
PATHWAY_CONVERGENCE_FIELD = "convergence_ref"
PATHWAY_SOURCE_FIELD = "source"
PATHWAY_ARM_KEY_FIELD = "pathway_arm_key"

# Documented expectation for the pin test — never the source a row's namespace is read from.
KNOWN_SYMBOL_TARGETS = ("MTRNR2L1", "MTRNR2L4", "MTRNR2L8", "OCLM")
EXPECTED_UNIVERSE = {"n_targets": 11526, "n_ensembl": 11522, "n_symbol": 4}

ROW_SCHEMA = "spot.stage02_stage3_row.v1"
ROW_RULE_ID = "spot.stage02.stage3_row.direction_and_namespace.v1"

REQUIRED_ROW_FIELDS = (
    "schema_version", "lane", "arm_key", "program_id", "target_id", "target_id_namespace",
    "observed_perturbation_modality", "perturbation_target_effect",
    "program_effect_direction", "desired_target_modulation", "phenocopy_class",
    "arm_value", "evaluable", "rank",
)


# The named refusals. Each says WHICH invariant broke.
G_MODALITY_ABSENT = "the_joined_record_does_not_declare_the_perturbation_modality"
G_NO_IDENTITY_SOURCE = "the_lane_binds_no_per_target_identity_and_assay_artifact"
G_IDENTITY_ABSENT = "no_identity_record_joined"
G_IDENTITY_WRONG_TARGET = "the_identity_join_landed_on_another_target"


class RowContractError(ValueError):
    """A row cannot be handed to Stage 3. Refuse; never repair, and never drop."""


# --------------------------------------------------------------------------- #
# SEAM A -> SEAM B. The adapter, and the only place a raw shape is ever touched.
# --------------------------------------------------------------------------- #
def normalize_raw_row(lane: str, raw: dict[str, Any]) -> dict[str, Any]:
    """ONE raw producer row -> the normalized ranking record. NOT for pathway."""
    spec = RAW_PRODUCER_ROW.get(lane)
    if spec is None:
        raise RowContractError(
            f"[{lane}] has no raw TARGET row to normalize. {PATHWAY_LANE_ROLE['why']}"
            if lane == LANE_PATHWAY else f"[{lane}] is not a lane with a known raw row")
    return {
        "target_id": raw.get("target_id"),
        "arm_value": raw.get(spec["value_field"]),
        "evaluable": bool(raw.get(spec["evaluable_field"])),
        "rank": raw.get("rank"),
    }


# --------------------------------------------------------------------------- #
# THE RE-DERIVATIONS. The only place a direction is ever decided.
# --------------------------------------------------------------------------- #
def desired_target_modulation(arm_value: Optional[float], *, evaluable: bool) -> str:
    """The drug direction IMPLIED by ONE arm value, under CRISPRi knockdown.

    From the ORIENTED value and evaluability ONLY. It never sees the program direction —
    that is exactly the input whose influence would produce the inversion.
    """
    if not evaluable or arm_value is None:
        return MOD_NOT_EVALUATED
    value = float(arm_value)
    if value > SIGN_EPS:
        return MOD_DECREASE          # knockdown moved the program the desired way
    if value < -SIGN_EPS:
        return MOD_INCREASE          # ...and this is NOT an agonist recommendation
    return MOD_NO_DIRECTION


def phenocopy_class(modulation: str) -> str:
    """What Stage 3 may DO with this row. Total over the enum; never defaults."""
    if modulation not in PHENOCOPY_CLASS_OF:
        raise RowContractError(
            f"modulation {modulation!r} is not one of {list(MODULATIONS)}; a direction "
            "nobody can read is not a direction anybody may prescribe against")
    return PHENOCOPY_CLASS_OF[modulation]


def is_supported(row: dict[str, Any]) -> bool:
    """SUPPORTED = an inhibitor phenocopies what was actually observed. Nothing else is."""
    return row.get("phenocopy_class") == INHIBITION_COMPATIBLE


def build_row(*, lane: str, record: dict[str, Any], identity: dict[str, Any], arm_key: str,
              program_id: str, program_effect_direction: str,
              context: dict[str, Any]) -> dict[str, Any]:
    """ONE Stage-3 row, from ONE ADMITTED NORMALIZED ranking record + its JOINED identity.

    ``record``   a SEAM-B row: {target_id, arm_value, evaluable, rank}.
    ``identity`` the record this row JOINS to (Direct: screen/identity map; temporal:
                 base_records via base_key). It is the ONLY source of the namespace and of
                 the perturbation modality — neither is asserted here, and neither is guessed.
    """
    if lane not in TARGET_EVIDENCE_LANES:
        raise RowContractError(
            f"[{lane}] is not a target-evidence lane; {list(TARGET_EVIDENCE_LANES)} are. "
            f"{PATHWAY_LANE_ROLE['why']}")
    join = IDENTITY_JOIN.get(lane)
    if join is None:
        raise RowContractError(
            f"{G_NO_IDENTITY_SOURCE}: [{lane}] binds no per-target identity + assay artifact, "
            f"so no truthful Stage-3 row can be built from it. "
            f"{DIRECT_IDENTITY_REQUIREMENT['why']} REQUIRED: the producer must emit and bind "
            f"{DIRECT_IDENTITY_REQUIREMENT['required_columns']}")
    if program_effect_direction not in PROGRAM_EFFECT_DIRECTIONS:
        raise RowContractError(
            f"program_effect_direction {program_effect_direction!r} is not one of "
            f"{list(PROGRAM_EFFECT_DIRECTIONS)}")

    missing = [f for f in NORMALIZED_ROW_FIELDS if f not in record]
    if missing:
        raise RowContractError(
            f"[{lane}] the ranking record is missing {missing}. Stage 3 consumes the ADMITTED "
            f"normalized rows ({list(NORMALIZED_ROW_FIELDS)}), never a raw producer shape")

    target_id = record["target_id"]
    if target_id is None:
        raise RowContractError(f"[{lane}] a ranking record with no target_id")

    # THE JOIN. Identity is read off the record this row joins to — never sniffed from the
    # shape of the id: three of the four symbol targets carry an ENSG-looking release key
    # belonging to a DIFFERENT gene.
    if not identity:
        raise RowContractError(
            f"{G_IDENTITY_ABSENT}: [{lane}] {target_id}: {UNRESOLVED_IDENTITY} — no identity "
            f"record joined (this lane joins on {join['join_on']!r} into "
            f"{join['record']!r}). REFUSE it: never infer the namespace from "
            "the id, and never drop the row — a dropped row and a row that never existed look "
            "identical")
    if str(identity.get("target_id")) != str(target_id):
        raise RowContractError(
            f"{G_IDENTITY_WRONG_TARGET}: [{lane}] {target_id}: joined an identity record for "
            f"{identity.get('target_id')!r} — a join that lands on another target attaches "
            "the wrong gene to a drug")

    namespace = identity.get("target_id_namespace")
    if namespace not in NAMESPACES:
        raise RowContractError(
            f"[{lane}] {target_id}: joined namespace {namespace!r} is not one of "
            f"{list(NAMESPACES)}")

    # WHAT WAS DONE. Read from the field the LANE declares it in, and NEVER defaulted.
    #
    # This defaulted to CRISPRi when the field was absent, which is a FAIL-OPEN and a bad one:
    # a row with its modality DELETED sailed through and was classed
    # `inhibition_observed_compatible`. The whole row exists to stop a drug direction being
    # assumed — and it was assuming the assay. A perturbation nobody declared is not a
    # perturbation anybody may prescribe against.
    modality_field = join["modality_field"]
    if modality_field not in identity:
        raise RowContractError(
            f"{G_MODALITY_ABSENT}: [{lane}] {target_id}: the joined {join['record']} record "
            f"does not declare {modality_field!r}. The assay is never assumed: an absent "
            "modality is REFUSED, not defaulted to CRISPRi")
    modality = identity[modality_field]
    if modality != OBSERVED_PERTURBATION_MODALITY:
        raise RowContractError(
            f"[{lane}] {target_id}: the joined record says the perturbation was {modality!r}, "
            f"not {OBSERVED_PERTURBATION_MODALITY!r}. Every number in this release came from "
            "one assay")

    value, evaluable = record["arm_value"], bool(record["evaluable"])
    modulation = desired_target_modulation(value, evaluable=evaluable)

    return {
        "schema_version": ROW_SCHEMA,
        "rule_id": ROW_RULE_ID,
        "lane": lane,
        "arm_key": arm_key,
        "program_id": program_id,
        "context": dict(context),
        # WHO the target is — JOINED, and carrying its namespace with it
        "target_id": str(target_id),
        "target_id_namespace": namespace,
        "target_symbol": identity.get("target_symbol"),
        "target_ensembl": identity.get("target_ensembl"),
        "identity_joined_on": join["join_on"],
        "identity_source": join["record"],
        # WHAT WAS DONE (the assay), kept separate from everything it implies
        "observed_perturbation_modality": modality,
        "perturbation_target_effect": PERTURBATION_TARGET_EFFECT,
        # THE PROGRAM AXIS — about the program, not about the target
        "program_effect_direction": program_effect_direction,
        # ...and WHAT IS IMPLIED FOR A DRUG, from the oriented value alone
        "desired_target_modulation": modulation,
        "phenocopy_class": phenocopy_class(modulation),
        "phenocopy_claim": PHENOCOPY_CLAIM,
        "claim_is_equivalence": False,
        # the signed evidence itself, and whether it could be ranked at all
        "arm_value": value,
        "evaluable": evaluable,
        "rank": record["rank"],
    }


LEADING_EDGE_NON_JOINABLE = "non_joinable_unresolved_target_identity"

# The EXACT allowlist for a pathway context. Anything else is refused — and in particular
# NOTHING that looks like target evidence or a drug direction may appear on one.
PATHWAY_CONTEXT_FIELDS = (
    "schema_version", "lane", "arm_key", "program_id", "context", "gene_set_id",
    "native_set_id_field", "source", "source_artifact", "enrichment_value",
    "target_source_coverage", "convergence_ref", "leading_edge", "n_leading_edge",
    "n_leading_edge_joinable", "is_a_crispri_target_row",
    "may_be_matched_to_a_drug_as_a_target", "links_to_targets_via",
)
# A context carrying ANY of these is a target row wearing a pathway's clothes.
PATHWAY_CONTEXT_FORBIDDEN = (
    "arm_value", "desired_target_modulation", "phenocopy_class", "evaluable", "rank",
    "target_id", "observed_perturbation_modality", "program_effect_direction",
)


def pathway_context(*, arm_key: str, program_id: str, record: dict[str, Any],
                    context: dict[str, Any], namespace_of: dict[str, str],
                    source_artifact: Any = None) -> dict[str, Any]:
    """The pathway lane's contribution: CONTEXT, and explicitly not a target row.

    ``record`` is the producer's NATIVE pathway record, which names its gene set ``set_id``.
    The rename is done HERE, once and explicitly — a ``.get("gene_set_id")`` against these
    bytes returns None on every record, forever, and nothing would ever say so.
    """
    if PATHWAY_SET_ID_FIELD not in record:
        raise RowContractError(
            f"a pathway record with no {PATHWAY_SET_ID_FIELD!r}: the pathway producer names "
            f"its gene sets by that field, and a context that names no set is a context for "
            "nothing")
    gene_set_id = record[PATHWAY_SET_ID_FIELD]

    # EVERY LEADING-EDGE TARGET CARRIES ITS OWN NAMESPACE — the same explicit mapping the
    # typed target evidence uses. This is what lets Stage 3 walk a pathway to its genes and
    # then to a drug. An unresolved one is marked NON-JOINABLE, explicitly, on the record: it
    # is never string-sniffed, and it is never quietly dropped so the pathway looks cleaner
    # than its evidence.
    # ...and the namespace is the CANONICAL one from target_identity.json — not merely "a
    # valid enum value". A leading-edge gene whose namespace disagrees with the target record
    # is a different gene, and it would be handed to a drug search as if it were this one.
    leading_edge = []
    for target_id in (record.get(PATHWAY_LEADING_EDGE_FIELD) or []):
        namespace = namespace_of.get(str(target_id))
        leading_edge.append({
            "target_id": str(target_id),
            "target_id_namespace": namespace if namespace in NAMESPACES else None,
            "joinable": namespace in NAMESPACES,
            "status": (LEADING_EDGE_NON_JOINABLE if namespace not in NAMESPACES
                       else "joinable"),
        })

    return {
        "schema_version": "spot.stage02_stage3_pathway_context.v1",
        "lane": LANE_PATHWAY,
        "arm_key": arm_key,
        "program_id": program_id,
        "context": dict(context),
        "gene_set_id": gene_set_id,
        "native_set_id_field": PATHWAY_SET_ID_FIELD,
        # EVERY provenance field comes off the NATIVE record. None is passed in by a caller:
        # a caller-supplied coverage is a coverage nobody measured.
        "source": record.get(PATHWAY_SOURCE_FIELD),
        "source_artifact": source_artifact,
        "enrichment_value": record.get(PATHWAY_ENRICHMENT_FIELD),
        "target_source_coverage": record.get(PATHWAY_COVERAGE_FIELD),
        "convergence_ref": record.get(PATHWAY_CONVERGENCE_FIELD),
        "leading_edge": leading_edge,
        "n_leading_edge": len(leading_edge),
        "n_leading_edge_joinable": sum(1 for e in leading_edge if e["joinable"]),
        # THE REFUSAL, carried ON the record
        "is_a_crispri_target_row": False,
        "may_be_matched_to_a_drug_as_a_target": False,
        "links_to_targets_via": list(PATHWAY_LANE_ROLE["links_to_targets_via"]),
    }
