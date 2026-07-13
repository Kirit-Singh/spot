"""THE W3 BRIDGE CONTRACT: its tokens, its named gates, and what an ADMITTED bridge IS.

The lower layer. It answers "what IS this artifact, and what may it say?".
Whether the bytes on disk actually satisfy it is a separate question, asked by
:mod:`druglink.stage2_bridge` — which imports from here and re-exports these names, so a
consumer still binds ONE module. Split at the 500-line gate; the same seam
``stage2_contract`` / ``stage2_aggregate`` already draws.

ORIGINAL HEADER
---------------

WHY THE BRIDGE EXISTS AT ALL
----------------------------
A native Stage-2 ranking row is exactly ``{target_id, arm_value, evaluable, rank}``. It says
**nothing** about who the target IS (no namespace) and nothing about what was DONE to it (no
perturbation modality). Those two facts live only in the bridge.

Without them Stage 3 would have to:

  * infer the namespace from the SHAPE of an id — and this release's universe holds 11,522
    Ensembl accessions **and 4 bare symbols** (MTRNR2L1/4/8, OCLM), three of which carry an
    ENSG-looking release key belonging to a DIFFERENT gene. A shape guess mistypes those rows
    SILENTLY, and a mistyped row fails the exact-identity join by simply finding no drug; and
  * default the modality from a CONFIG CONSTANT — a setting: unhashed, unbound, uncheckable. A
    value that would look measured and never was.

So the bridge is what makes identity and assay hash-bound and checkable. This module is the
consumer, and it trusts nothing the bridge says about itself.

THE ONE RULE THAT MAKES A BRIDGE SAFE
-------------------------------------
    **It may ADD facts the native bytes lack (namespace, modality).
      It may NEVER CHANGE a fact the native bytes already state (arm_value, rank, evaluable).**

So ``arm_value``, ``rank`` and ``evaluable`` are taken from the NATIVE RANKING RECORDS — the ones
the aggregate manifest bound by hash and Stage-2's own independent verifier admitted — and the
bridge is required to AGREE with them. A row the native bytes do not produce is refused; a native
row the bridge dropped is refused (a dropped row and a row that never existed look identical).

...and the drug direction is RE-DERIVED here, from the native ``arm_value`` and ``evaluable``
alone (:data:`SIGN_EPS`, Stage-2 Direct ``config.py``). The serialized
``desired_target_modulation`` is a CHECK, never an input: if the two disagree, one of us has the
orientation backwards, and that is a whole release of drugs matched to the wrong direction.

THE RECEIPT IS NOT OPTIONAL
---------------------------
W3's bridge REPORT carries no ``bridge_sha256`` of its own — it names the bytes it judged in
``judged_bridge``, and nothing else ties it to an ADMITTED aggregate. The RECEIPT is the join: it
binds the aggregate (raw + canonical) AND the bridge (raw + canonical). A report WITHOUT a receipt
is an ADMIT that names no release. So the receipt is REQUIRED, reopened, and re-derived.

Every refusal is a NAMED gate. Fail closed. A missing field is a refusal, never a default.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from . import modality_v2 as mv2
from .stage2_contract import (
    Stage2AggregateError,
)

# W3's own tokens, restated (never imported: their package is not on Stage-3's path, and a
# consumer that imported the producer's constants would agree with them by construction).
BRIDGE_SCHEMA = "spot.stage02_stage3_bridge.v1"
RECEIPT_SCHEMA = "spot.stage02_stage3_receipt.v1"
BRIDGE_SELF_HASH_FIELD = "bridge_sha256"
RECEIPT_SELF_HASH_FIELD = "receipt_sha256"
BRIDGE_VERIFIER_ID = "spot.stage02.stage3_bridge.independent_verifier.v1"
ADMIT = "admit"

# What a bridge must NAME as the bytes it was built from. `stage3_inputs` is deliberately NOT
# here: Stage-2's source defines it, and the generated report does not emit it.
REQUIRED_BINDINGS = ("native_bundles", "lane_admissions", "stage1", "identity_source",
                     "aggregate")

# A pathway context carrying ANY of these is a target row wearing a gene set's clothes: an
# enrichment value is a statement about a SET, and a context that also carries an arm value and
# a drug direction would be prescribed against. W3's CTX_FORBIDDEN, exactly.
CTX_FORBIDDEN = frozenset({
    "arm_value", "desired_target_modulation", "phenocopy_class", "evaluable", "rank",
    "target_id", "observed_perturbation_modality", "program_effect_direction",
    "supported", "phenocopy_claim",
})

# The native facts the bridge may never move. It may ADD identity and modality; it may not
# restate the measurement.
NATIVE_FACTS = ("arm_value", "evaluable", "rank")

# ...and EXACTLY what it may ADD. The typed row a measured arm carries is the NATIVE ranking
# record plus these, and nothing else: the measurement stays the native one, always.
#
# The independent verifier restates this same set (`verifier.v2_rebuild.BRIDGE_SUPPLIED`). Neither
# side reads the other, and the emitted table hashes are what proves they agree — if either merged
# a field the other did not, the reconstruction would drift and the bundle would be refused.
BRIDGE_SUPPLIED_FIELDS = (mv2.FIELD_NAMESPACE, mv2.FIELD_MODALITY, mv2.FIELD_MODULATION,
                          mv2.FIELD_PHENOCOPY_CLASS, "target_symbol", "target_ensembl")

SIGN_EPS = mv2.SIGN_EPS                       # 1e-9 — Stage-2 Direct config.py:186
MODALITY_CRISPRI = mv2.MODALITY_CRISPRI

# Stage-2's own modulation tokens, re-derived from the ORIENTED arm value + evaluability ALONE.
# The value arrives PRE-ORIENTED to its arm's desired_change; Stage 3 never re-orients it.
MOD_DECREASE, MOD_INCREASE = mv2.MOD_DECREASE, mv2.MOD_INCREASE
MOD_NO_DIRECTION, MOD_NOT_EVALUATED = mv2.MOD_NO_DIRECTION, mv2.MOD_NOT_EVALUATED


# --- The named gates. Every refusal names one, so it can be grepped, tested and cited. ---- #
GATE_BRIDGE_NOT_ON_DISK = "the_stage3_bridge_artifact_is_not_on_disk"
GATE_BRIDGE_NOT_NATIVE = "the_bridge_is_not_the_native_stage2_stage3_bridge_schema"
GATE_BRIDGE_SELF_HASH = "the_bridge_does_not_recompute_its_own_bridge_sha256"
GATE_BRIDGE_BINDS_NOTHING = "the_bridge_names_neither_the_bytes_nor_the_admission_it_stands_on"
GATE_BRIDGE_IS_EMPTY = "the_bridge_carries_no_typed_rows_at_all"
GATE_BRIDGE_REPORT_NOT_NATIVE = "the_bridge_report_was_not_written_by_the_pinned_verifier"
GATE_REPORT_NOT_ADMIT = "the_bridge_verifier_did_not_admit_this_bridge"
GATE_REPORT_JUDGED_OTHER_BYTES = "the_bridge_report_judged_a_different_bridge"
GATE_RECEIPT_ABSENT = "the_release_ships_no_stage2_stage3_receipt"
GATE_RECEIPT_NOT_NATIVE = "the_receipt_is_not_the_native_stage2_stage3_receipt_schema"
GATE_RECEIPT_SELF_HASH = "the_receipt_does_not_recompute_its_own_receipt_sha256"
GATE_RECEIPT_BINDS_OTHER_BYTES = "the_receipt_binds_bytes_that_are_not_the_ones_on_disk"
GATE_BRIDGE_OVER_ANOTHER_AGGREGATE = "the_bridge_was_built_over_an_aggregate_stage3_did_not_admit"
GATE_ROW_ORPHAN = "a_bridge_row_the_admitted_native_bytes_do_not_produce"
GATE_ROW_DROPPED = "the_native_bytes_produce_a_row_the_bridge_dropped"
GATE_ROW_CHANGES_A_NATIVE_FACT = "a_bridge_row_restates_a_measurement_the_native_bytes_already_made"
GATE_ROW_IDENTITY_NOT_TYPED = "a_bridge_row_carries_no_usable_target_namespace"
GATE_ROW_MODALITY_NOT_DECLARED = "a_bridge_row_does_not_declare_what_the_assay_did"
GATE_MODULATION_DISAGREES_WITH_SIGN = \
    "the_serialized_modulation_disagrees_with_the_sign_re_derived_from_the_native_arm_value"
GATE_PATHWAY_SOURCED_A_TYPED_ROW = "the_pathway_lane_contributed_a_typed_target_row"
GATE_PATHWAY_CONTEXT_IS_TARGET_EVIDENCE = "a_pathway_context_carries_target_evidence_fields"
GATE_DUPLICATE_BRIDGE_ROW = "two_bridge_rows_claim_one_lane_arm_target_identity"
GATE_DUPLICATE_NATIVE_ROW = "two_native_ranking_records_claim_one_lane_arm_target_identity"
GATE_ARM_KEY_CONFLICT = "one_arm_declares_two_different_arm_keys"


class Stage2BridgeError(Stage2AggregateError):
    """The bridge on disk is not admissible. Refuse; never repair, and never drop."""


def _refuse(gate: str, message: str) -> None:
    raise Stage2BridgeError(f"[{gate}] {message}")


@dataclass(frozen=True)
class AdmittedBridge:
    """The bridge, ADMITTED: its typed rows, and the exact bytes they were checked against."""
    bridge_raw_sha256: str
    bridge_canonical_sha256: str
    bridge_self_hash: str
    report_raw_sha256: str
    receipt_raw_sha256: str
    verifier_id: str
    verdict: str
    n_rows: int
    n_pathway_contexts: int
    rows_by_arm: dict[str, tuple[dict[str, Any], ...]]
    schema_version: str = BRIDGE_SCHEMA
    rule_id: str = ""

    def rows_for(self, arm_key: str) -> tuple[dict[str, Any], ...]:
        return self.rows_by_arm.get(arm_key, ())

    def binding(self) -> dict[str, Any]:
        """The bytes this bridge IS — as the bundle id will commit to it.

        A bundle that named no bridge could be rebuilt from a DIFFERENT admitted bridge (different
        identities, a different assay) and come out byte-identical. So every hash in the chain is
        here, and it travels into the bundle id.
        """
        return {
            "schema_version": self.schema_version,
            "rule_id": self.rule_id,
            "bridge_raw_sha256": self.bridge_raw_sha256,
            "bridge_canonical_sha256": self.bridge_canonical_sha256,
            "bridge_sha256": self.bridge_self_hash,
            "bridge_report_raw_sha256": self.report_raw_sha256,
            "receipt_raw_sha256": self.receipt_raw_sha256,
            "independent_verifier_id": self.verifier_id,
            "verdict": self.verdict,
            "n_typed_rows": self.n_rows,
            "n_pathway_contexts": self.n_pathway_contexts,
            # The two facts the native ranking rows do not carry, and which exist ONLY here.
            "supplies": [mv2.FIELD_NAMESPACE, mv2.FIELD_MODALITY],
            "may_never_change_a_native_fact": list(NATIVE_FACTS),
            "receipt_is_required": True,
        }


BRIDGE_PROVENANCE = (
    ("stage2_stage3_bridge", "stage3_bridge", "bridge_raw_sha256", "bridge_canonical_sha256",
     "it supplies the target namespace and the perturbation modality, which the native ranking "
     "rows do not carry"),
    ("stage2_stage3_bridge_report", "stage3_bridge_verification", "bridge_report_raw_sha256",
     None, "the SEPARATE bridge verifier's report; it names the bridge bytes it judged"),
    ("stage2_stage3_receipt", "stage2_stage3_receipt", "receipt_raw_sha256", None,
     "THE JOIN: it binds the admitted aggregate and this bridge, raw and canonical. A bridge "
     "report without a receipt names no release"),
)


def bridge_provenance_rows(bound: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The three bridge artifacts, each addressable. A binding nobody can reopen is a claim."""
    return [{"kind": kind, "subject": subject, "raw_sha256": bound.get(raw),
             "canonical_sha256": bound.get(canonical) if canonical else None,
             "verifier_id": bound.get("independent_verifier_id"),
             "verdict": bound.get("verdict"),
             "detail": f"bridge_sha256={bound.get('bridge_sha256')}; {why}"}
            for kind, subject, raw, canonical, why in BRIDGE_PROVENANCE]
