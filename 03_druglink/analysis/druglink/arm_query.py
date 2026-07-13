"""v2 — the SELECTION-INDEPENDENT arm → drug query contract. PROVISIONAL.

An arm is a reusable, independently-verified object: *(program, desired_change, context)*.
It is **not** an "away_from_A arm" or a "toward_B arm" — those are ROLES, and a role is
something a *selection* assigns when it joins two arms into a question. The same arm serves
`away_from_A` in one pair and `toward_B` in another; baking a role into it would fuse two
different questions under one cache key.

So the query contract here takes **any** reusable arm — same-time Direct or cross-time
temporal — and answers "what drugs are direction-compatible with THIS arm", with no
selection anywhere in sight. The selection joins the answers afterwards.

  same-time   context = {condition}
  cross-time  context = {from_condition, to_condition}    (population-level DiD)

Everything else is identical, because it must be: a consumer that treats the two
differently is a consumer that will eventually treat one as the other.

PROVISIONAL — AND THE GATE THAT SAYS SO
---------------------------------------
This is built against W5's native temporal bundle at `cc82599` and W18's pathway v1
contract, **neither of which has been externally admitted yet** (W11 / W4 reports pending).
So nothing here runs on a real bundle without an explicit ``ExternalAdmission`` record
naming the verifier, the commit and the bytes it admitted. There is no default, no
``admitted=True`` fallback, and no "trust me" path: an un-admitted bundle raises.

That is deliberate. This lane has now watched three separate producers ship a component
that verified itself (B6, M4b, and the temporal bundle's original `verification_ref`).
Self-admission is the failure that keeps recurring, so Stage 3 refuses to be the fourth.

WHAT IS *NOT* NEGOTIABLE HERE
----------------------------
* **Exact target identity.** Joined on the immutable ``base_key``/``target_id``. Never on a
  symbol — symbols are ambiguous and mutable, and a symbol join is a silent mis-attribution
  waiting for a gene to be renamed.
* **Measured ≠ hypothesised.** A perturbed target is measured evidence. A pathway member
  nobody perturbed is a hypothesis. They never merge, and the UI must show them apart.
* **An unmeasured pathway node is INERT** unless it carries its own source-backed direction
  *with* a locator *and* a hash. Otherwise it cannot improve drug ordering. At all.
* **Every rank-null target is retained.** Unranked is a STATE, not an absence.
* **Endpoint pathway context is descriptive only.** Never temporal enrichment.
"""
from __future__ import annotations

from typing import Any, Optional

from . import join_semantics as js
from . import pathway_bridge as pb

QUERY_SCHEMA = "spot.stage03_arm_query.v2"
QUERY_METHOD_ID = "spot.stage03.arm_query.v2"

# The upstream bundles this query consumes. Both PROVISIONAL until externally admitted.
TEMPORAL_ARM_BUNDLE = "spot.stage02_temporal_arm_bundle.v1"
DIRECT_ARM_BUNDLE = "spot.stage02_direct_arm_bundle.v1"
ARM_BUNDLE_SCHEMAS = (DIRECT_ARM_BUNDLE, TEMPORAL_ARM_BUNDLE)

# The temporal lanes now have CLEAN HEADS — W5 62fbf8b, W11 61ee45b, W3 71f50f1 — but the
# independent detached-clone matrix is still RUNNING. A clean head is not a green report:
# the whole point of the matrix is that the lanes are checked against each other from a
# fresh clone, and "each lane's own suite passes" is exactly the self-consistency it exists
# to rule out. So the loader stays SHUT until that report is green, at which point Stage 3
# binds the exact inventory + root admission + aggregate identities.
TEMPORAL_HEADS = {"W5": "62fbf8b", "W11": "61ee45b", "W3": "71f50f1"}
DETACHED_CLONE_MATRIX_GREEN = False          # flipped only by the independent report

PROVISIONAL_SOURCES = {
    TEMPORAL_ARM_BUNDLE: (
        "W5 62fbf8b + W11 61ee45b + W3 71f50f1 — clean heads, but the independent "
        "detached-clone matrix report is still RUNNING. A clean head is not a green "
        "report."),
    DIRECT_ARM_BUNDLE: "W18 agent/stage2-direct-v3 (admission PENDING)",
    pb.PATHWAY_ARM_BUNDLE_SCHEMA: "W18/W4 pathway v1 (W4 admission PENDING)",
}

# The arm's own key components. Note what is absent: no role, no pole.
DESIRED_CHANGES = ("increase", "decrease")

SAME_TIME = "same_time"
CROSS_TIME = "cross_time"

# Evidence classes. Kept apart at the type level, not by convention.
MEASURED_PERTURBATION = "measured_perturbation"
PATHWAY_HYPOTHESIS = "pathway_hypothesis"
EVIDENCE_CLASSES = (MEASURED_PERTURBATION, PATHWAY_HYPOTHESIS)

# W5's modulation vocabulary → what Stage 3 may do with it.
SUPPORTS_INHIBITION = "supports_target_inhibition"
OPPOSED_NEEDS_ACTIVATION = "opposed_would_require_target_activation"
NO_DIRECTIONAL_RESPONSE = "no_directional_response"
NOT_EVALUABLE = "not_evaluable"

# An inhibitor is direction-compatible ONLY with a target whose knockdown moved the program
# the desired way. `opposed` says what would be NEEDED (activation) — never that a drug can
# do it, so it is NOT an activator lead. It is a refusal with a reason.
INHIBITOR_COMPATIBLE = frozenset({SUPPORTS_INHIBITION})
DRUG_ORDERING_ELIGIBLE = frozenset({SUPPORTS_INHIBITION})

PERTURBATION_MODALITY = "CRISPRi_knockdown"


class ArmQueryError(ValueError):
    """The arm bundle and Stage-3's v2 query contract do not agree."""


class ExternalAdmissionRequired(ArmQueryError):
    """Stage 3 will not read a bundle no independent verifier has admitted."""


# --------------------------------------------------------------------------- #
# The admission gate. No default. No fallback.
# --------------------------------------------------------------------------- #
class ExternalAdmission:
    """Proof that an INDEPENDENT verifier admitted these exact bytes.

    Deliberately not a bool. A bool can be defaulted to True by a caller in a hurry; a
    record cannot be produced without naming who admitted what.
    """

    def __init__(self, *, verifier_id: str, producer_commit: str,
                 bundle_sha256: str, verdict: str) -> None:
        if not verifier_id or "independent" not in verifier_id:
            raise ExternalAdmissionRequired(
                f"admission must come from an INDEPENDENT verifier; got "
                f"{verifier_id!r}. A bundle that verifies itself proves only that the "
                "producer agreed with itself.")
        if verdict != "admit":
            raise ExternalAdmissionRequired(
                f"the independent verifier did not admit these bytes (verdict="
                f"{verdict!r}); Stage 3 refuses them")
        if not producer_commit or not bundle_sha256:
            raise ExternalAdmissionRequired(
                "an admission must name the producer commit AND the bytes it admitted, "
                "or it is an opinion about some other artifact")
        self.verifier_id = verifier_id
        self.producer_commit = producer_commit
        self.bundle_sha256 = bundle_sha256
        self.verdict = verdict

    def as_binding(self) -> dict[str, str]:
        return {"external_verifier_id": self.verifier_id,
                "external_producer_commit": self.producer_commit,
                "external_bundle_sha256": self.bundle_sha256,
                "external_verdict": self.verdict}


def require_external_admission(bundle: dict[str, Any],
                               admission: Optional[ExternalAdmission]) -> ExternalAdmission:
    schema = bundle.get("schema_version")
    if schema not in ARM_BUNDLE_SCHEMAS:
        raise ArmQueryError(
            f"expected one of {list(ARM_BUNDLE_SCHEMAS)}, got {schema!r}")
    if admission is None:
        raise ExternalAdmissionRequired(
            f"{schema} is PROVISIONAL ({PROVISIONAL_SOURCES.get(schema, 'unadmitted')}). "
            "Stage 3 requires an explicit ExternalAdmission naming the independent "
            "verifier, the producer commit and the bytes. There is no default and no "
            "trust-me path.")
    js.refuse_temporal_pathway_claim(bundle, what="arm bundle")
    return admission


# --------------------------------------------------------------------------- #
# The arm, selection-independent.
# --------------------------------------------------------------------------- #
def arm_context(bundle: dict[str, Any]) -> dict[str, Any]:
    """same-time -> {condition}; cross-time -> {from_condition, to_condition}."""
    if bundle["schema_version"] == TEMPORAL_ARM_BUNDLE:
        ctx = bundle.get("context") or {}
        frm, to = ctx.get("from_condition"), ctx.get("to_condition")
        if not (frm and to):
            raise ArmQueryError("a temporal bundle must name BOTH endpoint conditions")
        return {"time_scope": CROSS_TIME, "from_condition": frm, "to_condition": to,
                "analysis_mode": js.TEMPORAL_CROSS_CONDITION}
    condition = bundle.get("condition") or (bundle.get("context") or {}).get("condition")
    if not condition:
        raise ArmQueryError("a same-time bundle must name its condition")
    return {"time_scope": SAME_TIME, "condition": condition,
            "analysis_mode": js.WITHIN_CONDITION}


def _index_bases(bundle: dict[str, Any]) -> dict[str, dict[str, Any]]:
    bases = {b["base_key"]: b for b in bundle.get("base_records", [])}
    if not bases:
        raise ArmQueryError("the bundle ships no base_records; identity is unresolvable")
    return bases


def normalize_arm(arm: dict[str, Any], *, bundle: dict[str, Any],
                  admission: ExternalAdmission) -> list[dict[str, Any]]:
    """One reusable arm -> Stage-3 lever rows. Verified join. Role-free. Nulls retained."""
    bases = _index_bases(bundle)
    ctx = arm_context(bundle)
    modality = (bundle.get("perturbation") or {}).get(
        "perturbation_modality", PERTURBATION_MODALITY)

    rows: list[dict[str, Any]] = []
    for rec in arm["records"]:
        base = bases.get(rec["base_key"])
        if base is None:
            raise ArmQueryError(
                f"arm record points at base_key {rec['base_key']!r}, which resolves to "
                "nothing — referential integrity is not optional")
        # The join is CHECKED, not trusted. And it is never on a symbol.
        if base["target_id"] != rec["target_id"]:
            raise ArmQueryError(
                f"base_key {rec['base_key']!r} resolves to target "
                f"{base['target_id']!r} but the arm record says {rec['target_id']!r}")

        modulation = rec.get("desired_target_modulation", NOT_EVALUABLE)
        rows.append({
            # --- the arm, with NO role and NO pole ---
            "arm_key": arm["arm_key"],
            "program_id": arm["program_id"],
            "desired_change": arm["desired_change"],
            **ctx,
            # --- exact identity, from base_records (never duplicated, never a symbol join)
            "target_id": base["target_id"],
            "target_id_namespace": base.get("target_id_namespace"),
            "target_symbol": base.get("target_symbol"),
            "target_ensembl": base.get("target_ensembl"),
            "released_estimate_id": _estimate_id(base, ctx),
            # --- value + RETAINED rank ---
            "arm_value": rec.get("arm_value"),
            "arm_rank": rec.get("rank"),                 # null stays null. Always.
            "arm_evaluable": bool(rec.get("evaluable")),
            "arm_state": rec.get("temporal_status") or base.get("temporal_status"),
            # --- evidence: this target was PERTURBED ---
            "evidence_class": MEASURED_PERTURBATION,
            "crispri_modality": modality,
            "base_qc_state": base.get("from_base_qc_state") or base.get("base_qc_state"),
            "inference_status": "not_calibrated",
            # --- what the arm SUGGESTS, and what Stage 3 may do with it ---
            "arm_desired_target_modulation": modulation,
            "inhibitor_direction_compatible": modulation in INHIBITOR_COMPATIBLE,
            "may_improve_drug_ordering": modulation in DRUG_ORDERING_ELIGIBLE,
            "pharmacologic_reversibility_assumed": False,
            **admission.as_binding(),
        })
    return rows


def _estimate_id(base: dict[str, Any], ctx: dict[str, Any]) -> Any:
    """Same-time: one released estimate. Cross-time: the DiD stands on BOTH endpoints."""
    if ctx["time_scope"] == CROSS_TIME:
        return {"from": base.get("from_released_estimate_id"),
                "to": base.get("to_released_estimate_id")}
    return base.get("released_estimate_id") or base.get("from_released_estimate_id")


# --------------------------------------------------------------------------- #
# Drug ordering. The whole firewall, in one function.
# --------------------------------------------------------------------------- #
def orderable_levers(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Only measured, inhibitor-compatible levers may improve drug ordering.

    `opposed_would_require_target_activation` is NOT an activator lead — the screen cannot
    say a drug could activate anything. It is retained, visible, and inert.
    """
    return [r for r in rows if r.get("may_improve_drug_ordering")]


def assert_evidence_classes_never_merge(rows: list[dict[str, Any]]) -> None:
    """A measured lever and a pathway hypothesis must never share a row."""
    for r in rows:
        cls = r.get("evidence_class")
        if cls not in EVIDENCE_CLASSES:
            raise ArmQueryError(f"unknown evidence_class {cls!r}")
        if cls == PATHWAY_HYPOTHESIS and r.get("arm_rank") is not None:
            raise ArmQueryError(
                f"{r.get('target_id')!r} is a pathway hypothesis carrying a measured arm "
                "rank — nobody perturbed it, so it has no rank to carry")
