"""Disk-backed admission of the Stage-2 -> Stage-3 BRIDGE. THE producer-side consumer.

WHY A BRIDGE EXISTS AT ALL
--------------------------
The native Stage-2 ranking row is exactly ``{target_id, arm_value, evaluable, rank}``. It says
NOTHING about who the target is (no namespace) and NOTHING about what was done to it (no
modality). Those two facts live ONLY in Stage-2's separate bridge, which is built AFTER the lanes
are admitted and is bound by hash to the native bytes it was rebuilt from.

Without it, Stage 3 would have to GUESS a namespace from the shape of an id — and the admitted
universe is heterogeneous (Ensembl gene ids AND bare gene symbols), so the guess would silently
attach the wrong gene to a drug — and DEFAULT a modality from a config constant, which is a
setting wearing the costume of an assay.

THE ONE RULE THAT MAKES A BRIDGE SAFE
-------------------------------------
**It may ADD facts the native bytes lack. It may never CHANGE a fact the native bytes state.**

So ``arm_value``, ``evaluable`` and ``rank`` are taken from the ADMITTED NATIVE RANKING and the
bridge is REQUIRED to agree with them. The bridge is trusted for identity and modality, and for
nothing else. Then the SIGN is re-derived from the NATIVE value and the bridge's own
``desired_target_modulation`` / ``phenocopy_class`` must equal what that re-derivation says. The
bridge's direction token is a CHECK, never an input.

WHAT ADMITS A BRIDGE. Not the bridge. The real one on disk declares ``admitted: false``,
``self_admitted: false`` and ``verdict: "pending_independent_verification"`` — correctly, because
a producer does not admit itself. Admission is the SEPARATE bridge verifier's report plus the
RECEIPT, which is the only artifact that binds the bridge bytes to the aggregate bytes::

    bundles -> lane admissions -> aggregate manifest -> aggregate report
            -> bridge -> bridge report -> RECEIPT

A SELF-HASH IS NECESSARY AND NOT SUFFICIENT: a forger who reseals recomputes it. What a reseal
cannot survive is the rebuild from bytes the forger does not own — every row below is checked
against the native ranking this process already admitted from the bundle bytes.

PATHS ARE NEVER READ AND NEVER REPUBLISHED. The real bridge's ``bindings`` carry the producer's
absolute machine paths (``/tmp/proto_…``). They are ignored: the bytes admitted here are the ones
at the paths the CALLER named, and :meth:`AdmittedBridge.binding` emits hashes and ids only.

THIS MODULE IS SOURCE-AGNOSTIC. It derives every expected row from the arms the independently
admitted aggregate hands it. It hardcodes no lane, no condition and no gene-set source, so a
future GO-BP-only topology needs no change here (see ``TODO_GO_ONLY_TOPOLOGY``).
"""
from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Mapping

from . import modality_contract as mc
from . import modality_rule as mr
from . import stage2_contract as C
from .hashing import file_sha256
from .stage2_contract import AdmittedAggregate, stage2_content_sha256

# The GO-only topology interface is NOT invented here. `admit_aggregate` still derives the
# 15-bundle / 300-slot topology from the release's own conditions + gene-set sources, and that
# contract is already admitted upstream. When Stage 2 ships a VERSIONED topology manifest (binding
# the source list, the expected bundle/arm keys and a topology hash), the aggregate admitter binds
# it and this module keeps working unchanged: it never enumerates a source, it only walks the arms
# the admitted aggregate gives it. Omission of a Reactome lane under the OLD 15-slot contract is a
# refusal upstream, not completion — and it is not this module's job to make it look like one.
TODO_GO_ONLY_TOPOLOGY = (
    "upstream interface still required: a versioned Stage-2 topology manifest (source list + "
    "expected bundle/arm keys + topology identity hash) that admits a complete GO-BP-only run "
    "and refuses a partial one relabelled as full")

BRIDGE_SCHEMA = "spot.stage02_stage3_bridge.v1"
BRIDGE_VERIFIER_ID = "spot.stage02.stage3_bridge.independent_verifier.v1"
RECEIPT_SCHEMA = "spot.stage02_stage3_receipt.v1"
ROW_SCHEMA = "spot.stage02_stage3_row.v1"
CONTEXT_SCHEMA = "spot.stage02_stage3_pathway_context.v1"

SELF_HASH_FIELD = "bridge_sha256"
RECEIPT_SELF_HASH_FIELD = "receipt_sha256"

# What the bridge must NAME. A bridge that binds nothing could have been built from anything —
# including nothing.
REQUIRED_BINDINGS = ("aggregate", "identity_source", "lane_admissions", "native_bundles",
                     "stage1")

# THE TYPED ROW. Every field a Stage-3 edge needs, and not one more. Restated here rather than
# imported from the verifier: a producer that borrows the checker's contract cannot disagree
# with it.
REQUIRED_ROW_FIELDS = (
    "arm_key", "arm_value", "desired_target_modulation", "evaluable", "lane",
    "observed_perturbation_modality", "perturbation_target_effect", "phenocopy_class",
    "program_effect_direction", "program_id", "rank", "schema_version", "target_id",
    "target_id_namespace",
)

# The values the NATIVE bytes own. The bridge may not restate them differently.
NATIVE_OWNED_FIELDS = ("arm_value", "evaluable", "rank")

# The fields the bridge is trusted FOR — the only ones it contributes to a typed record.
BRIDGE_SUPPLIED = (mc.FIELD_NAMESPACE, mc.FIELD_MODALITY, mc.FIELD_MODULATION,
                   mc.FIELD_PHENOCOPY_CLASS, "target_symbol", "target_ensembl")

# Stage-2's phenocopy vocabulary, keyed by the modulation the SIGN implies. Restated so the class
# is RE-DERIVED rather than read.
PHENOCOPY_CLASS_OF = {
    mc.MOD_DECREASE: "inhibition_observed_compatible",
    mc.MOD_INCREASE: "inhibitor_opposed",
    mc.MOD_NO_DIRECTION: "no_directional_response",
    mc.MOD_NOT_EVALUATED: "not_evaluable",
}

# EXACTLY what a pathway context may carry, and exactly what it may NEVER carry. A pathway record
# is a GENE-SET ENRICHMENT: no target, no arm value, no modality, no rank. A context that smuggles
# one in is a set-level statistic being handed a direction it never had.
CTX_ALLOWED = frozenset({
    "arm_key", "context", "convergence_ref", "coverage", "enrichment_value", "gene_set_id",
    "is_a_crispri_target_row", "lane", "leading_edge", "links_to_targets_via",
    "may_be_matched_to_a_drug_as_a_target", "n_leading_edge", "n_leading_edge_joinable",
    "native_set_id_field", "program_id", "schema_version", "source", "source_artifact",
    "target_source_coverage",
})
CTX_FORBIDDEN = frozenset({
    "arm_value", "desired_target_modulation", "evaluable", "observed_perturbation_modality",
    "phenocopy_claim", "phenocopy_class", "program_effect_direction", "rank", "supported",
    "target_id",
})

GATE_BRIDGE_NOT_ON_DISK = "the_stage3_bridge_is_not_on_disk"
GATE_BRIDGE_NOT_NATIVE = "the_bridge_is_not_the_native_stage2_stage3_bridge_schema"
GATE_BRIDGE_SELF_HASH = "the_bridge_does_not_recompute_its_own_identity"
GATE_BRIDGE_BINDS_NOTHING = "the_bridge_binds_none_of_the_admitted_bytes_it_was_built_from"
GATE_BRIDGE_SELF_ADMITTED = "the_bridge_admits_itself"
GATE_BRIDGE_REPORT_NOT_INDEPENDENT = "the_bridge_report_is_not_the_separate_bridge_verifier"
GATE_BRIDGE_NOT_ADMITTED = "the_bridge_verifier_did_not_admit_the_bridge"
GATE_REPORT_JUDGED_OTHER_BYTES = "the_bridge_report_judged_bytes_that_are_not_the_bridge_on_disk"
GATE_RECEIPT_NOT_NATIVE = "the_receipt_is_not_the_native_stage2_stage3_receipt_schema"
GATE_RECEIPT_SELF_HASH = "the_receipt_does_not_recompute_its_own_identity"
GATE_RECEIPT_BINDS_ANOTHER_BRIDGE = "the_receipt_does_not_bind_these_exact_bridge_bytes"
GATE_RECEIPT_BINDS_ANOTHER_REPORT = "the_receipt_does_not_bind_this_exact_bridge_report"
GATE_RECEIPT_BINDS_ANOTHER_AGGREGATE = \
    "the_bridge_was_built_over_an_aggregate_this_process_did_not_admit"
GATE_BRIDGE_SELF_ADMISSION = "the_bridge_and_its_report_are_the_same_file"
GATE_BRIDGE_ROW_INCOMPLETE = "a_bridge_row_does_not_carry_the_typed_row_contract"
GATE_BRIDGE_DUPLICATE_ROW = "two_bridge_rows_claim_one_lane_arm_target_identity"
GATE_BRIDGE_ORPHAN_ROW = "a_bridge_row_the_admitted_native_bytes_do_not_produce"
GATE_BRIDGE_DROPPED_A_ROW = "the_native_bytes_produce_a_row_the_bridge_dropped"
GATE_BRIDGE_CHANGED_A_NATIVE_VALUE = \
    "the_bridge_restates_an_arm_value_the_admitted_native_bytes_already_state"
GATE_BRIDGE_ZERO_EVIDENCE = "a_bridge_with_no_evidence_is_not_a_bridge"
GATE_PATHWAY_LANE_CARRIES_TARGET_ROWS = "the_pathway_lane_carries_a_target_evidence_row"
GATE_CTX_UNKNOWN_FIELD = "a_pathway_context_carries_a_field_the_schema_does_not_have"
GATE_CTX_CARRIES_TARGET_EVIDENCE = "a_pathway_context_carries_a_target_evidence_field"
GATE_CTX_ORPHAN_ARM = "a_pathway_context_names_an_arm_the_admitted_aggregate_does_not_have"
GATE_COMBINED_OBJECTIVE = "the_bridge_carries_a_combined_objective"
GATE_PQ_FDR = "the_bridge_carries_a_p_value_q_value_or_fdr"
GATE_ABSOLUTE_ARTIFACT_REF = "the_bridge_names_an_artifact_by_an_absolute_or_traversing_path"

# STRUCTURAL, NOT A SINGLE FIELD. The whole point of reviving a combined objective is that it
# arrives as ONE new key, in a NESTED block, in a later writer — so the scan is by key SUBSTRING
# at ANY depth, and it runs on the bridge before a single row is read.
BANNED_COMBINED = ("combined", "balanced", "weighted", "overall", "headline", "composite",
                   "aggregate_score", "total_score", "final_score")
BANNED_PQ_FDR = ("p_value", "q_value", "pvalue", "qvalue", "pval", "qval", "fdr", "padj",
                 "adj_p", "significan")


class Stage2BridgeError(ValueError):
    """The bridge on disk and the admitted native bytes do not agree. Fail closed, by name."""


def _refuse(gate: str, message: str) -> None:
    raise Stage2BridgeError(f"[{gate}] {message}")


@dataclass(frozen=True)
class AdmittedBridge:
    """The bridge, ADMITTED from its own bytes. Hashes and ids only — never a path."""
    bridge_raw_sha256: str
    bridge_canonical_sha256: str
    bridge_self_hash: str
    report_raw_sha256: str
    report_canonical_sha256: str
    receipt_raw_sha256: str
    receipt_canonical_sha256: str
    receipt_self_hash: str
    verifier_id: str
    verdict: str
    rule_id: str
    # (lane, arm_key, target_id) -> the typed row
    rows: dict[tuple[str, str, str], dict[str, Any]] = field(default_factory=dict)
    contexts: tuple[dict[str, Any], ...] = ()
    counts: dict[str, Any] = field(default_factory=dict)

    def binding(self) -> dict[str, Any]:
        """What a RELEASABLE artifact may publish about the bridge. No paths, no clock."""
        return {
            "bridge_schema": BRIDGE_SCHEMA,
            "bridge_raw_sha256": self.bridge_raw_sha256,
            "bridge_canonical_sha256": self.bridge_canonical_sha256,
            "bridge_self_hash": self.bridge_self_hash,
            "bridge_report_raw_sha256": self.report_raw_sha256,
            "bridge_report_canonical_sha256": self.report_canonical_sha256,
            "receipt_schema": RECEIPT_SCHEMA,
            "receipt_raw_sha256": self.receipt_raw_sha256,
            "receipt_canonical_sha256": self.receipt_canonical_sha256,
            "receipt_self_hash": self.receipt_self_hash,
            "bridge_verifier_id": self.verifier_id,
            "bridge_verdict": self.verdict,
            "bridge_rule_id": self.rule_id,
            "typed_row_schema": ROW_SCHEMA,
            # Said out loud, because it is the rule the whole module exists to hold.
            "bridge_may_add_identity_and_modality_never_change_a_measurement": True,
            "pathway_context_may_never_source_a_drug_edge": True,
            **self.counts,
        }


def _load(path: str, what: str, gate: str) -> tuple[dict[str, Any], str]:
    if not path or not os.path.isfile(path):
        _refuse(gate,
                f"there is no {what} at {str(path)!r}. There is no fixture fallback: a Stage-3 "
                "run without the handoff that carries target identity and modality does not "
                "quietly become one with a synthetic handoff.")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError) as exc:
        _refuse(gate, f"the {what} at {str(path)!r} is not readable JSON: {exc}")
    if not isinstance(doc, dict):
        _refuse(gate, f"the {what} at {str(path)!r} is not a JSON object")
    return doc, file_sha256(path)


def bridge_self_hash(doc: Mapping[str, Any]) -> str:
    """Stage-2's rule, RE-DERIVED: the canonical hash of the document EXCLUDING its own hash."""
    return stage2_content_sha256({k: v for k, v in doc.items() if k != SELF_HASH_FIELD})


def receipt_self_hash(doc: Mapping[str, Any]) -> str:
    return stage2_content_sha256({k: v for k, v in doc.items()
                                  if k != RECEIPT_SELF_HASH_FIELD})


def _keys_at_any_depth(node: Any, path: str = "$"):
    """Every key in the document, however deeply nested. A firewall that only reads the top level
    is a firewall the next writer walks around by adding one more level."""
    if isinstance(node, Mapping):
        for k, v in node.items():
            yield str(k), f"{path}.{k}"
            yield from _keys_at_any_depth(v, f"{path}.{k}")
    elif isinstance(node, (list, tuple)):
        for i, v in enumerate(node):
            yield from _keys_at_any_depth(v, f"{path}[{i}]")


def _check_no_banned_vocabulary(bridge: Mapping[str, Any]) -> None:
    """No combined objective, and no p/q/FDR — at ANY depth.

    Stage 2's arms are INDEPENDENT and Stage 3 never pools them; a bridge that arrived carrying a
    combined number would hand Stage 3 a ranking it never computed and cannot defend. And Stage-2
    keeps its FDR behind its own firewall: a q-value crossing into Stage 3 is a significance claim
    travelling into a pipeline that has no way to honour it.
    """
    for token, banned, gate, why in (
            ("combined", BANNED_COMBINED, GATE_COMBINED_OBJECTIVE,
             "the arms are INDEPENDENT and are never pooled: a combined objective is a ranking "
             "nobody computed and nobody can defend"),
            ("pq", BANNED_PQ_FDR, GATE_PQ_FDR,
             "significance stays behind Stage-2's own firewall: a q-value here is a claim this "
             "pipeline has no way to honour")):
        hits = sorted({p for k, p in _keys_at_any_depth(bridge)
                       if any(b in k.lower() for b in banned)})
        if hits:
            _refuse(gate, f"the bridge carries {len(hits)} such key(s) ({hits[:3]}) — {why}.")


def _row_key(row: Mapping[str, Any]) -> tuple[str, str, str]:
    return (str(row.get("lane")), str(row.get("arm_key")), str(row.get("target_id")))


def native_rows(aggregate: AdmittedAggregate) -> dict[tuple[str, str, str], dict[str, Any]]:
    """(lane, arm_key, target_id) -> the ADMITTED native ranking record, for the MEASURED arms.

    Taken from the arms already re-admitted from the bundle bytes — never from the bridge's own
    copy of them. This is the map the bridge is checked AGAINST.
    """
    out: dict[tuple[str, str, str], dict[str, Any]] = {}
    for arm in aggregate.arms:
        if arm.lane not in C.MEASURED_LANES:
            continue
        for rec in arm.records:
            out[(arm.lane, arm.arm_key, str(rec.get("target_id")))] = dict(rec)
    return out


# --- 1. Identity, and the SEPARATE verifier's admission. --------------------- #
def _check_identity(bridge: Mapping[str, Any]) -> str:
    if bridge.get("schema_version") != BRIDGE_SCHEMA:
        _refuse(GATE_BRIDGE_NOT_NATIVE,
                f"the handoff declares schema_version={bridge.get('schema_version')!r}; the "
                f"native Stage-3 bridge is {BRIDGE_SCHEMA!r}. A document Stage 2 never emitted "
                "is not evidence Stage 2 produced anything.")
    derived = bridge_self_hash(bridge)
    if bridge.get(SELF_HASH_FIELD) != derived:
        _refuse(GATE_BRIDGE_SELF_HASH,
                f"the bridge declares {SELF_HASH_FIELD}="
                f"{str(bridge.get(SELF_HASH_FIELD))[:16]}… but its own content hashes to "
                f"{derived[:16]}…. NECESSARY AND NOT SUFFICIENT: a forger who reseals recomputes "
                "this too, which is why every row below is rebuilt from bytes the forger does "
                "not own.")
    unbound = [k for k in REQUIRED_BINDINGS if not (bridge.get("bindings") or {}).get(k)]
    if unbound:
        _refuse(GATE_BRIDGE_BINDS_NOTHING,
                f"the bridge binds no {unbound}; it must NAME what it was built from "
                f"({list(REQUIRED_BINDINGS)}). A typed row that names neither the bytes it came "
                "from nor the admission that cleared them is a row from nowhere.")
    # A PRODUCER DOES NOT ADMIT ITSELF. The genuine bridge declares self_admitted=false and a
    # PENDING verdict, and is admitted by the SEPARATE report below. One that declares itself
    # admitted has skipped the only step that could have caught it.
    if bridge.get("self_admitted") is True or bridge.get("admitted") is True:
        _refuse(GATE_BRIDGE_SELF_ADMITTED,
                "the bridge declares itself admitted (self_admitted/admitted = true). Admission "
                "is granted by the SEPARATE bridge verifier's report and the receipt that binds "
                "these bytes, or not at all — a producer agreeing with itself is the one thing an "
                "independent verifier exists to rule out.")
    return derived


def _check_report(report: Mapping[str, Any], *, bridge_raw: str, bridge_canonical: str,
                  bridge_self: str) -> tuple[str, str]:
    """The SEPARATE bridge verifier admitted THESE bytes. Every clause is a named gate."""
    verifier_id = str(report.get("verifier_id") or "")
    if verifier_id != BRIDGE_VERIFIER_ID or report.get("generator_is_not_verifier") is not True:
        _refuse(GATE_BRIDGE_REPORT_NOT_INDEPENDENT,
                f"the bridge report is signed {verifier_id!r} with generator_is_not_verifier="
                f"{report.get('generator_is_not_verifier')!r}; the pinned separate verifier is "
                f"{BRIDGE_VERIFIER_ID!r} and independence is a STRUCTURED FIELD, never a "
                "substring in a name.")
    verdict = str(report.get("verdict") or "")
    if (verdict != C.ADMIT or report.get("n_failed") != 0
            or report.get("reconstructs_from_admitted_native_bytes") is not True):
        _refuse(GATE_BRIDGE_NOT_ADMITTED,
                f"the bridge verifier's verdict is {verdict!r} with "
                f"n_failed={report.get('n_failed')!r} and reconstructs_from_admitted_native_bytes"
                f"={report.get('reconstructs_from_admitted_native_bytes')!r}. Stage 3 requires "
                f"EXACTLY {C.ADMIT!r}, zero failed gates, and a verifier that REBUILT the rows "
                "from the admitted native bytes rather than reading them — a self-hash alone "
                "admits nothing.")
    # THE REPORT MUST HAVE JUDGED THE BRIDGE ON DISK, not some other bridge.
    judged = report.get("judged_bridge") or {}
    if (judged.get("raw_sha256") != bridge_raw
            or judged.get("canonical_sha256") != bridge_canonical
            or judged.get(SELF_HASH_FIELD) != bridge_self):
        _refuse(GATE_REPORT_JUDGED_OTHER_BYTES,
                f"the report judged bridge raw={str(judged.get('raw_sha256'))[:16]}… / "
                f"canonical={str(judged.get('canonical_sha256'))[:16]}…, but the bridge on disk "
                f"is raw={bridge_raw[:16]}… / canonical={bridge_canonical[:16]}…. An ADMIT that "
                "names other bytes is an opinion about some other artifact.")
    return verifier_id, verdict


def _check_receipt(receipt: Mapping[str, Any], *, bridge_raw: str, bridge_canonical: str,
                   report_raw: str, report_canonical: str, aggregate: AdmittedAggregate,
                   aggregate_report_raw: str) -> str:
    """THE JOIN. The receipt is the only artifact binding the bridge bytes to the aggregate
    bytes: the bridge report returns a verdict but names no aggregate, so a receipt over a
    DIFFERENT aggregate is a handoff for a release nobody cleared — and it looks exactly like one
    that was."""
    if receipt.get("schema_version") != RECEIPT_SCHEMA:
        _refuse(GATE_RECEIPT_NOT_NATIVE,
                f"the receipt declares schema_version={receipt.get('schema_version')!r}; the "
                f"native join is {RECEIPT_SCHEMA!r}.")
    derived = receipt_self_hash(receipt)
    if receipt.get(RECEIPT_SELF_HASH_FIELD) != derived:
        _refuse(GATE_RECEIPT_SELF_HASH,
                f"the receipt declares {RECEIPT_SELF_HASH_FIELD}="
                f"{str(receipt.get(RECEIPT_SELF_HASH_FIELD))[:16]}… but its own content hashes "
                f"to {derived[:16]}…: it was edited after it was addressed.")

    bridge = receipt.get("bridge") or {}
    if (bridge.get("raw_sha256") != bridge_raw
            or bridge.get("canonical_sha256") != bridge_canonical):
        _refuse(GATE_RECEIPT_BINDS_ANOTHER_BRIDGE,
                f"the receipt binds bridge raw={str(bridge.get('raw_sha256'))[:16]}… / "
                f"canonical={str(bridge.get('canonical_sha256'))[:16]}…, but the bridge on disk "
                f"is raw={bridge_raw[:16]}… / canonical={bridge_canonical[:16]}…. Raw AND "
                "canonical are both required: raw alone would miss a re-serialisation that "
                "changes meaning, canonical alone would let the shipped file differ from what "
                "was judged.")

    rep = receipt.get("bridge_report") or {}
    if (rep.get("raw_sha256") != report_raw
            or rep.get("canonical_sha256") != report_canonical):
        _refuse(GATE_RECEIPT_BINDS_ANOTHER_REPORT,
                f"the receipt binds bridge_report raw={str(rep.get('raw_sha256'))[:16]}…, but "
                f"the report presented hashes to {report_raw[:16]}…. The receipt must bind the "
                "verdict it travelled with, or an ADMIT could be swapped for another.")

    # THE CROSS-BIND. The bridge must stand on the aggregate THIS process admitted from disk.
    agg = receipt.get("aggregate") or {}
    manifest = agg.get("manifest") or {}
    report_b = agg.get("report") or {}
    if (manifest.get("raw_sha256") != aggregate.manifest_raw_sha256
            or manifest.get("canonical_sha256") != aggregate.manifest_canonical_sha256
            or report_b.get("raw_sha256") != aggregate_report_raw):
        _refuse(GATE_RECEIPT_BINDS_ANOTHER_AGGREGATE,
                f"the receipt binds aggregate manifest "
                f"raw={str(manifest.get('raw_sha256'))[:16]}… / "
                f"canonical={str(manifest.get('canonical_sha256'))[:16]}… and report "
                f"raw={str(report_b.get('raw_sha256'))[:16]}…, but the aggregate ADMITTED here "
                f"is raw={aggregate.manifest_raw_sha256[:16]}… / "
                f"canonical={aggregate.manifest_canonical_sha256[:16]}… with report "
                f"raw={aggregate_report_raw[:16]}…. A bridge over a different (or a "
                "since-edited) aggregate is a Stage-3 handoff for a release nobody cleared.")
    return derived


# --- 2. THE ROWS. Rebuilt from the native bytes; the bridge never restates a measurement. --- #
def _check_rows(bridge: Mapping[str, Any],
                aggregate: AdmittedAggregate) -> dict[tuple[str, str, str], dict[str, Any]]:
    shipped = list(bridge.get("target_rows") or [])
    native = native_rows(aggregate)
    keys = [_row_key(r) for r in shipped]

    duplicate = sorted({k for k, n in Counter(keys).items() if n > 1})
    if duplicate:
        _refuse(GATE_BRIDGE_DUPLICATE_ROW,
                f"{len(duplicate)} (lane, arm, target) identity claimed by two bridge rows "
                f"({duplicate[:3]}); two rows under one key means one of them was never checked.")

    incomplete = [(_row_key(r), [f for f in REQUIRED_ROW_FIELDS if f not in r])
                  for r in shipped if [f for f in REQUIRED_ROW_FIELDS if f not in r]]
    if incomplete:
        _refuse(GATE_BRIDGE_ROW_INCOMPLETE,
                f"{len(incomplete)} bridge row(s) do not carry the whole typed row contract "
                f"{list(REQUIRED_ROW_FIELDS)}: {incomplete[:2]}. A missing field is a refusal, "
                "never a default.")

    # A PATHWAY ARM MAY NEVER SHIP A TARGET-EVIDENCE ROW. An inferred gene-set arm that carries a
    # target row would let a set membership create a drug edge no measurement supports.
    pathway_arms = {a.arm_key for a in aggregate.arms if a.lane == C.LANE_PATHWAY}
    intruders = sorted({str(r.get("arm_key")) for r in shipped
                        if str(r.get("lane")) == C.LANE_PATHWAY
                        or str(r.get("arm_key")) in pathway_arms})
    if intruders:
        _refuse(GATE_PATHWAY_LANE_CARRIES_TARGET_ROWS,
                f"{len(intruders)} pathway arm(s) ship a TARGET row ({intruders[:3]}). A pathway "
                "record is a gene-set enrichment, not a measured per-target knockdown effect: it "
                "has no CRISPRi sign and can never source a drug edge. Pathway is CONTEXT, and "
                "context annotates evidence — it never creates it.")

    orphan = sorted(str(k) for k in keys if k not in native)
    if orphan:
        _refuse(GATE_BRIDGE_ORPHAN_ROW,
                f"{len(orphan)} bridge row(s) the admitted native bytes do not produce "
                f"({orphan[:3]}). A row the native ranking does not contain agrees with itself, "
                "and with nothing that was measured.")

    dropped = sorted(str(k) for k in native if k not in set(keys))
    if dropped:
        _refuse(GATE_BRIDGE_DROPPED_A_ROW,
                f"the native bytes produce {len(dropped)} row(s) the bridge dropped "
                f"({dropped[:3]}). A dropped row and a row that never existed look identical, "
                "and the dropped one is the one nobody checks.")

    changed: list[str] = []
    drift: list[str] = []
    for row in shipped:
        want = native[_row_key(row)]
        # *** THE BRIDGE MAY ADD FACTS. IT MAY NEVER CHANGE ONE. ***
        for f in NATIVE_OWNED_FIELDS:
            if row.get(f) != want.get(f):
                changed.append(f"{_row_key(row)}: the bridge says {f}={row.get(f)!r}, but the "
                               f"ADMITTED native ranking states {want.get(f)!r}")
        # THE SIGN, RE-DERIVED FROM THE NATIVE VALUE — never from the bridge's own token.
        modality = str(row.get(mc.FIELD_MODALITY))
        if modality in mc.MODALITY_PERFORMED_ACTION and isinstance(want.get("evaluable"), bool):
            sign = mr.observed_sign_state(want.get("arm_value"),
                                          evaluable=bool(want.get("evaluable")),
                                          origin_is_measured=True,
                                          arm_key=str(row.get("arm_key")))
            expect = mr.desired_target_modulation(modality, sign)
            if row.get(mc.FIELD_MODULATION) != expect:
                drift.append(f"{_row_key(row)}: the bridge says {mc.FIELD_MODULATION}="
                             f"{row.get(mc.FIELD_MODULATION)!r}, but the NATIVE arm_value "
                             f"{want.get('arm_value')!r} re-derives sign {sign!r}, which under "
                             f"{modality!r} means {expect!r}")
            elif row.get(mc.FIELD_PHENOCOPY_CLASS) != PHENOCOPY_CLASS_OF.get(expect):
                drift.append(f"{_row_key(row)}: {mc.FIELD_PHENOCOPY_CLASS}="
                             f"{row.get(mc.FIELD_PHENOCOPY_CLASS)!r} does not follow from "
                             f"{expect!r}")

    if changed:
        _refuse(GATE_BRIDGE_CHANGED_A_NATIVE_VALUE,
                f"{len(changed)} restatement(s): {'; '.join(changed[:2])}. The bridge ADDS "
                "identity and modality and CHANGES nothing — a bridge free to restate a "
                "measurement is a re-measured number wearing an admitted release's hashes, and "
                "every downstream sign would follow the forgery.")
    if drift:
        _refuse(mc.GATE_SERIALIZED_MODULATION_DISAGREES_WITH_THE_SIGN,
                f"{len(drift)} direction(s) the native value does not imply: "
                f"{'; '.join(drift[:2])}. The bridge's direction token is a CHECK, never an "
                "input.")

    if not shipped or not native:
        _refuse(GATE_BRIDGE_ZERO_EVIDENCE,
                f"the bridge carries {len(shipped)} row(s) against {len(native)} native row(s). "
                "A bridge with no rows claims nothing, so nothing it claims is false — and a "
                "clean report over an empty handoff is the most dangerous artifact of all. "
                "Evidence that is absent is not evidence that is fine.")
    return {_row_key(r): dict(r) for r in shipped}


def _check_contexts(bridge: Mapping[str, Any],
                    aggregate: AdmittedAggregate) -> tuple[dict[str, Any], ...]:
    """THE PATHWAY FIREWALL. A gene-set enrichment may never wear a target's clothes."""
    contexts = list(bridge.get("pathway_contexts") or [])
    known = {a.arm_key for a in aggregate.arms if a.lane == C.LANE_PATHWAY}
    unknown, smuggled, misdeclared, orphan, absolute = [], [], [], [], []
    for ctx in contexts:
        arm = str(ctx.get("arm_key"))
        unknown += [f"{arm}:{f}" for f in sorted(set(ctx) - CTX_ALLOWED)]
        smuggled += [f"{arm}:{f}" for f in sorted(set(ctx) & CTX_FORBIDDEN)]
        if (ctx.get("is_a_crispri_target_row") is not False
                or ctx.get("may_be_matched_to_a_drug_as_a_target") is not False):
            misdeclared.append(arm)
        if arm not in known:
            orphan.append(arm)
        # A ref is a NAME inside the bundle. An absolute path names a place on one machine, and
        # `..` names a place outside the bundle entirely.
        ref = str(((ctx.get("source_artifact") or {}) if isinstance(
            ctx.get("source_artifact"), Mapping) else {}).get("path") or "")
        if ref and (os.path.isabs(ref) or ".." in ref.split("/")):
            absolute.append(f"{arm}:{ref}")

    if absolute:
        _refuse(GATE_ABSOLUTE_ARTIFACT_REF,
                f"{len(absolute)} pathway context(s) name a source artifact by an absolute or "
                f"traversing path ({absolute[:3]}). A releasable ref is bundle-relative: an "
                "absolute path names a place on one machine, not an artifact.")

    if smuggled:
        _refuse(GATE_CTX_CARRIES_TARGET_EVIDENCE,
                f"{len(smuggled)} pathway context field(s) carry TARGET EVIDENCE ({smuggled[:3]}"
                "). An enrichment value is a statement about a GENE SET, not a measurement of a "
                "target under knockdown: read as a target's arm value it would prescribe a drug "
                "for a pathway.")
    if misdeclared:
        _refuse(GATE_CTX_CARRIES_TARGET_EVIDENCE,
                f"{len(misdeclared)} pathway context(s) do not DECLARE themselves a non-CRISPRi, "
                f"non-drug-matchable row ({misdeclared[:3]}). The denial is a field a consumer "
                "reads, not a docstring it does not.")
    if unknown:
        _refuse(GATE_CTX_UNKNOWN_FIELD,
                f"{len(unknown)} pathway context field(s) the schema does not have "
                f"({unknown[:3]}). A field nobody agreed to is a field no consumer can be "
                "expected to refuse.")
    if orphan:
        _refuse(GATE_CTX_ORPHAN_ARM,
                f"{len(orphan)} pathway context(s) name an arm the admitted aggregate does not "
                f"have ({sorted(set(orphan))[:3]}). A context for an arm nobody ran contextualizes "
                "nothing.")
    return tuple(dict(c) for c in contexts)


# --- The gate. -------------------------------------------------------------- #
def admit_bridge(*, bridge_path: str, report_path: str, receipt_path: str,
                 aggregate: AdmittedAggregate,
                 aggregate_report_path: str) -> AdmittedBridge:
    """Admit the Stage-2 -> Stage-3 bridge FROM DISK, against the aggregate already admitted.

    The BYTES on disk are the input. A caller-supplied in-memory dict is not accepted and cannot
    be: every hash below is taken from the file at the path the caller named, so a clean dict
    handed alongside altered bytes admits the altered bytes or nothing.
    """
    if os.path.realpath(bridge_path or "") == os.path.realpath(report_path or ""):
        _refuse(GATE_BRIDGE_SELF_ADMISSION,
                "the bridge and its verification report are the SAME file. A producer does not "
                "admit itself: the report is a separate artifact from a separate verifier.")

    bridge, bridge_raw = _load(bridge_path, "Stage-3 bridge", GATE_BRIDGE_NOT_ON_DISK)
    report, report_raw = _load(report_path, "separate Stage-3 bridge verification report",
                               GATE_BRIDGE_NOT_ADMITTED)
    receipt, receipt_raw = _load(receipt_path, "Stage-2 -> Stage-3 receipt",
                                 GATE_RECEIPT_BINDS_ANOTHER_BRIDGE)

    self_hash = _check_identity(bridge)
    _check_no_banned_vocabulary(bridge)
    bridge_canonical = stage2_content_sha256(bridge)
    report_canonical = stage2_content_sha256(report)

    verifier_id, verdict = _check_report(report, bridge_raw=bridge_raw,
                                         bridge_canonical=bridge_canonical,
                                         bridge_self=self_hash)
    receipt_self = _check_receipt(
        receipt, bridge_raw=bridge_raw, bridge_canonical=bridge_canonical,
        report_raw=report_raw, report_canonical=report_canonical, aggregate=aggregate,
        aggregate_report_raw=file_sha256(aggregate_report_path)
        if os.path.isfile(aggregate_report_path or "") else "")

    rows = _check_rows(bridge, aggregate)
    contexts = _check_contexts(bridge, aggregate)

    return AdmittedBridge(
        bridge_raw_sha256=bridge_raw, bridge_canonical_sha256=bridge_canonical,
        bridge_self_hash=self_hash, report_raw_sha256=report_raw,
        report_canonical_sha256=report_canonical, receipt_raw_sha256=receipt_raw,
        receipt_canonical_sha256=stage2_content_sha256(receipt),
        receipt_self_hash=receipt_self, verifier_id=verifier_id, verdict=verdict,
        rule_id=str(bridge.get("rule_id") or ""), rows=rows, contexts=contexts,
        counts={"n_target_rows": len(rows), "n_pathway_contexts": len(contexts),
                "n_measured_arms_typed": len({k[1] for k in rows})})
