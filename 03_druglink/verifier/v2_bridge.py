"""THE W3 STAGE-3 BRIDGE, re-admitted independently. Imports NOTHING from ``druglink``.

WHY THERE IS A BRIDGE AT ALL
---------------------------
The native Stage-2 ranking row is exactly ``{target_id, arm_value, evaluable, rank}``. It carries
NO namespace and NO modality — so it cannot say WHO a target is, nor WHAT was done to it. Those
two facts live in W3's SEPARATE bridge (``stage3_bridge.json``), which is built AFTER the lanes
are admitted and is BOUND BY HASH to the native bytes it was rebuilt from.

The bridge is a CONSUMER of admitted bytes, never part of them: writing it into a bundle would
change that bundle's file topology after its own independent verifier had already cleared it. So
the chain only ever grows forward, and nothing upstream is ever re-sealed::

    bundles -> lane admissions -> aggregate manifest -> aggregate report
            -> bridge -> bridge report -> RECEIPT

THE ONE RULE THAT MAKES A BRIDGE SAFE
-------------------------------------
**It may ADD facts the native bytes lack. It may never CHANGE a fact the native bytes state.**

So this module takes ``arm_value``, ``evaluable`` and ``rank`` FROM THE NATIVE RANKING FILE and
REQUIRES the bridge to agree — the bridge is trusted for identity and modality, and for nothing
else. A bridge whose ``arm_value`` differs from the value in the admitted ranking it was rebuilt
from is a re-measured number wearing an admitted release's hashes, and it is REFUSED BY NAME.

Then the SIGN is re-derived from that NATIVE value (:mod:`verifier.v2_sign`) and the bridge's own
``desired_target_modulation`` / ``phenocopy_class`` are REQUIRED to equal what the re-derivation
says. Nothing here reads a direction; everything here checks one.

A SELF-HASH IS NECESSARY AND NOT SUFFICIENT. A forger who reseals recomputes it. What a reseal
cannot survive is the rebuild from bytes the forger does not own.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

from . import canon
from . import v2_contract as C
from . import v2_sign as S
from .report import Report

BRIDGE_FILE = "stage3_bridge.json"
BRIDGE_SCHEMA = "spot.stage02_stage3_bridge.v1"
BRIDGE_REPORT_FILE = "stage3_bridge_verification.json"
BRIDGE_VERIFIER_ID = "spot.stage02.stage3_bridge.independent_verifier.v1"
RECEIPT_FILE = "stage2_stage3_receipt.json"
RECEIPT_SCHEMA = "spot.stage02_stage3_receipt.v1"
SELF_HASH_FIELD = "bridge_sha256"

# What the bridge must NAME. A bridge that binds nothing could have been built from anything —
# including nothing.
REQUIRED_BINDINGS = ("native_bundles", "lane_admissions", "stage1", "identity_source",
                     "aggregate")

# THE TYPED ROW. Every field a Stage-3 edge needs, and not one more.
REQUIRED_ROW_FIELDS = (
    "schema_version", "lane", "arm_key", "program_id", "target_id", "target_id_namespace",
    "observed_perturbation_modality", "perturbation_target_effect",
    "program_effect_direction", "desired_target_modulation", "phenocopy_class",
    "arm_value", "evaluable", "rank",
)

# THE VALUES THE NATIVE BYTES OWN. The bridge may not restate them differently.
NATIVE_OWNED_FIELDS = ("arm_value", "evaluable", "rank")

# W3's phenocopy_class vocabulary, keyed by the modulation the sign implies. Restated so the
# verifier can re-derive the class rather than read it.
PHENOCOPY_CLASS_OF = {
    S.MOD_DECREASE: "inhibition_observed_compatible",
    S.MOD_INCREASE: "inhibitor_opposed",
    S.MOD_NO_DIRECTION: "no_directional_response",
    S.MOD_NOT_EVALUATED: "not_evaluable",
}

# EXACTLY what a pathway context may carry, and exactly what it may NEVER carry. W3 reached this
# firewall independently of Stage 3, and the two agree — so it is bound verbatim rather than
# re-derived loosely. A pathway record is a GENE-SET ENRICHMENT: it has no target, no arm value,
# no modality and no rank, and a context that smuggles one in is a set-level number being handed
# a direction it never had.
CTX_ALLOWED = frozenset({
    "schema_version", "lane", "arm_key", "program_id", "context", "gene_set_id",
    "native_set_id_field", "source", "enrichment_value", "coverage", "convergence_ref",
    "leading_edge", "n_leading_edge", "n_leading_edge_joinable",
    "is_a_crispri_target_row", "may_be_matched_to_a_drug_as_a_target", "links_to_targets_via",
})
CTX_FORBIDDEN = frozenset({
    "arm_value", "desired_target_modulation", "phenocopy_class", "evaluable", "rank",
    "target_id", "observed_perturbation_modality", "program_effect_direction",
    "supported", "phenocopy_claim",
})

GATE_BRIDGE_NOT_ON_DISK = "the_stage3_bridge_is_not_on_disk"
GATE_BRIDGE_NOT_NATIVE = "the_bridge_is_not_the_native_w3_stage3_bridge_schema"
GATE_BRIDGE_SELF_HASH = "the_bridge_does_not_recompute_its_own_identity"
GATE_BRIDGE_BINDS_NOTHING = "the_bridge_binds_none_of_the_admitted_bytes_it_was_built_from"
GATE_BRIDGE_REPORT_NOT_INDEPENDENT = "the_bridge_report_is_not_the_separate_bridge_verifier"
GATE_BRIDGE_NOT_ADMITTED = "the_bridge_verifier_did_not_admit_the_bridge"
GATE_RECEIPT_BINDS_ANOTHER_BRIDGE = "the_receipt_does_not_bind_these_exact_bridge_bytes"
GATE_RECEIPT_BINDS_ANOTHER_AGGREGATE = \
    "the_bridge_was_built_over_an_aggregate_this_verifier_did_not_admit"
GATE_BRIDGE_SOURCE_BYTES_MOVED = "the_bound_native_bytes_are_not_the_bytes_on_disk"
GATE_BRIDGE_CHANGED_A_NATIVE_VALUE = \
    "the_bridge_restates_an_arm_value_the_admitted_native_bytes_already_state"
GATE_BRIDGE_ORPHAN_ROW = "a_bridge_row_the_admitted_native_bytes_do_not_produce"
GATE_BRIDGE_DROPPED_A_ROW = "the_native_bytes_produce_a_row_the_bridge_dropped"
GATE_BRIDGE_ROW_INCOMPLETE = "a_bridge_row_does_not_carry_the_typed_row_contract"
GATE_BRIDGE_DUPLICATE_ROW = "two_bridge_rows_claim_one_lane_arm_target_identity"
GATE_CTX_CARRIES_TARGET_EVIDENCE = "a_pathway_context_carries_a_target_evidence_field"
GATE_CTX_UNKNOWN_FIELD = "a_pathway_context_carries_a_field_the_schema_does_not_have"
GATE_BRIDGE_ZERO_EVIDENCE = "a_bridge_with_no_evidence_is_not_a_bridge"


def _gate(rep: Report, gate: str, sentence: str, ok: Any, detail: str = "") -> bool:
    return rep.check(f"[{gate}] {sentence}", ok, detail)


def bridge_self_hash(doc: dict[str, Any]) -> str:
    """W3's rule, restated: the canonical hash of the document EXCLUDING its own hash."""
    return canon.sha256_hex(
        json.dumps({k: v for k, v in doc.items() if k != SELF_HASH_FIELD},
                   sort_keys=True, separators=(",", ":"), ensure_ascii=True))


def _canonical(obj: Any) -> str:
    return canon.sha256_hex(json.dumps(obj, sort_keys=True, separators=(",", ":"),
                                       ensure_ascii=True))


def _load(rep: Report, path: str, what: str, gate: str) -> Optional[tuple[Any, str]]:
    if not path or not os.path.isfile(path):
        _gate(rep, gate,
              f"the {what} is on disk (there is no fixture fallback: a Stage-3 run without the "
              "handoff that carries target identity and modality does not quietly become one "
              "with a synthetic handoff)",
              False, f"not found: {path!r}")
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh), canon.file_sha256(path)
    except (OSError, ValueError) as exc:
        _gate(rep, gate, f"the {what} parses as JSON", False, f"{type(exc).__name__}: {exc}")
        return None


def _row_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (str(row.get("lane")), str(row.get("arm_key")), str(row.get("target_id")))


# --------------------------------------------------------------------------- #
# 1. The native rows the bridge CLAIMS to have been rebuilt from — re-read by us.
# --------------------------------------------------------------------------- #
def native_rows(aggregate: dict[str, Any]) -> dict[tuple[str, str, str], dict[str, Any]]:
    """(lane, arm_key, target_id) -> the ADMITTED native ranking record.

    Taken from the arms this verifier already re-admitted from the bundle bytes — never from the
    bridge's own copy of them. This is the map the bridge is checked AGAINST.
    """
    out: dict[tuple[str, str, str], dict[str, Any]] = {}
    for arm in aggregate["arms"]:
        for rec in arm["records"]:
            key = (str(arm["lane"]), str(arm["arm_key"]), str(rec.get("target_id")))
            out[key] = rec
    return out


# --------------------------------------------------------------------------- #
# 2. The admission.
# --------------------------------------------------------------------------- #
def admit_bridge(rep: Report, *, bridge_root: str,
                 aggregate: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Re-open, re-hash and REBUILD W3's Stage-3 bridge. Trust nothing it says about itself."""
    loaded = _load(rep, os.path.join(str(bridge_root or ""), BRIDGE_FILE),
                   "W3 Stage-3 bridge", GATE_BRIDGE_NOT_ON_DISK)
    if loaded is None:
        return None
    doc, raw = loaded

    if not _gate(rep, GATE_BRIDGE_NOT_NATIVE,
                 f"the handoff IS W3's native Stage-3 bridge ({BRIDGE_SCHEMA}); a document W3 "
                 "never emitted is not evidence W3 produced",
                 isinstance(doc, dict) and doc.get("schema_version") == BRIDGE_SCHEMA,
                 f"declares {(doc or {}).get('schema_version')!r}"):
        return None

    derived = bridge_self_hash(doc)
    _gate(rep, GATE_BRIDGE_SELF_HASH,
          "the bridge recomputes its OWN identity from its own content. NECESSARY AND NOT "
          "SUFFICIENT: a forger who reseals recomputes this too, which is why every row below is "
          "REBUILT from bytes the forger does not own",
          doc.get(SELF_HASH_FIELD) == derived,
          f"declares {str(doc.get(SELF_HASH_FIELD))[:16]}…, hashes to {derived[:16]}…")

    bindings = doc.get("bindings") or {}
    unbound = [k for k in REQUIRED_BINDINGS if not bindings.get(k)]
    _gate(rep, GATE_BRIDGE_BINDS_NOTHING,
          f"the bridge NAMES what it was built from — {list(REQUIRED_BINDINGS)}. A typed row "
          "that names neither the bytes it came from nor the admission that cleared them is a "
          "row from nowhere",
          not unbound, f"binds no {unbound}")

    ok = _check_reports(rep, bridge_root=bridge_root, bridge_raw=raw,
                        bridge_canonical=_canonical(doc), aggregate=aggregate)
    rows = _check_rows(rep, doc, aggregate=aggregate)
    _check_contexts(rep, doc)

    if rows is None or not ok:
        return None
    return {"bridge": doc, "raw_sha256": raw, "bridge_sha256": derived, "rows": rows}


def _check_reports(rep: Report, *, bridge_root: str, bridge_raw: str, bridge_canonical: str,
                   aggregate: dict[str, Any]) -> bool:
    """The SEPARATE bridge verifier admitted it — and the RECEIPT binds THESE bytes to THIS
    aggregate.

    The bridge report names a verdict but NOT the bytes it judged; the RECEIPT is what binds the
    bridge (raw + canonical) to the aggregate (raw + canonical). So an ADMIT with no receipt is
    an opinion about some other artifact, and a receipt over another aggregate is a handoff for a
    release that was never cleared.
    """
    loaded = _load(rep, os.path.join(bridge_root, BRIDGE_REPORT_FILE),
                   "SEPARATE Stage-3 bridge verification report", GATE_BRIDGE_NOT_ADMITTED)
    if loaded is None:
        return False
    report, _raw = loaded

    ok = _gate(rep, GATE_BRIDGE_REPORT_NOT_INDEPENDENT,
               f"the bridge report is the SEPARATE bridge verifier's ({BRIDGE_VERIFIER_ID}) and "
               "ASSERTS generator_is_not_verifier — the bridge's own producer admits nothing, "
               "and a self-admission is a producer agreeing with itself",
               report.get("verifier_id") == BRIDGE_VERIFIER_ID
               and report.get("generator_is_not_verifier") is True,
               f"verifier_id={report.get('verifier_id')!r} "
               f"generator_is_not_verifier={report.get('generator_is_not_verifier')!r}")
    ok = _gate(rep, GATE_BRIDGE_NOT_ADMITTED,
               f"the bridge verifier's verdict is EXACTLY {C.ADMIT!r} with ZERO failed gates, and "
               "it states that it RECONSTRUCTED the rows from the admitted native bytes rather "
               "than reading them (a self-hash alone admits nothing)",
               report.get("verdict") == C.ADMIT and report.get("n_failed") == 0
               and report.get("reconstructs_from_admitted_native_bytes") is True,
               f"verdict={report.get('verdict')!r} n_failed={report.get('n_failed')!r}") and ok

    loaded = _load(rep, os.path.join(bridge_root, RECEIPT_FILE),
                   "Stage-2 -> Stage-3 receipt", GATE_RECEIPT_BINDS_ANOTHER_BRIDGE)
    if loaded is None:
        return False
    receipt, _ = loaded
    bridge_binding = receipt.get("bridge") or {}
    agg_binding = receipt.get("aggregate") or {}

    ok = _gate(rep, GATE_RECEIPT_BINDS_ANOTHER_BRIDGE,
               f"the receipt ({RECEIPT_SCHEMA}) binds THESE EXACT bridge bytes, by raw AND "
               "canonical hash. The bridge report names a verdict but no bytes; the receipt is "
               "the join, and an ADMIT that names no bytes is an opinion about some other "
               "artifact",
               receipt.get("schema_version") == RECEIPT_SCHEMA
               and bridge_binding.get("raw_sha256") == bridge_raw
               and bridge_binding.get("canonical_sha256") == bridge_canonical,
               f"receipt binds {str(bridge_binding.get('raw_sha256'))[:16]}…, the bridge on disk "
               f"is {bridge_raw[:16]}…") and ok

    # THE CROSS-BIND. The bridge must stand on the aggregate THIS verifier admitted — not a
    # different one, and not one edited after it was judged.
    manifest = (agg_binding.get("manifest") or {}) if isinstance(agg_binding, dict) else {}
    report_b = (agg_binding.get("report") or {}) if isinstance(agg_binding, dict) else {}
    ok = _gate(rep, GATE_RECEIPT_BINDS_ANOTHER_AGGREGATE,
               "the bridge was built over the EXACT Stage-2 aggregate this verifier just "
               "re-admitted from disk — its manifest AND its separate admission report, by raw "
               "and canonical hash. A bridge over a different (or a since-edited) aggregate is a "
               "Stage-3 handoff for a release nobody cleared, and it looks exactly like one that "
               "was",
               manifest.get("raw_sha256") == aggregate["manifest_raw_sha256"]
               and manifest.get("canonical_sha256") == aggregate["manifest_canonical_sha256"]
               and report_b.get("raw_sha256") == aggregate["report_raw_sha256"],
               f"receipt binds manifest {str(manifest.get('raw_sha256'))[:16]}…, this verifier "
               f"admitted {aggregate['manifest_raw_sha256'][:16]}…") and ok
    return ok


# --------------------------------------------------------------------------- #
# 3. THE ROWS. Rebuilt from the native bytes; the bridge never gets to restate a measurement.
# --------------------------------------------------------------------------- #
def _check_rows(rep: Report, doc: dict[str, Any],
                aggregate: dict[str, Any]) -> Optional[dict[tuple[str, str, str], dict]]:
    shipped = doc.get("target_rows") or []
    native = native_rows(aggregate)

    keys = [_row_key(r) for r in shipped]
    duplicate = sorted({k for k in keys if keys.count(k) > 1})
    _gate(rep, GATE_BRIDGE_DUPLICATE_ROW,
          "no two bridge rows claim one (lane, arm, target) identity (two rows under one key "
          "means one of them was never checked)",
          not duplicate, f"{len(duplicate)}: {duplicate[:3]}")

    incomplete = [_row_key(r) for r in shipped
                  if [f for f in REQUIRED_ROW_FIELDS if f not in r]]
    _gate(rep, GATE_BRIDGE_ROW_INCOMPLETE,
          f"every bridge row carries the whole typed row contract {list(REQUIRED_ROW_FIELDS)} — "
          "a missing field is a refusal, never a default",
          not incomplete, f"{len(incomplete)}: {incomplete[:3]}")

    changed: list[str] = []
    orphan: list[str] = []
    sign_drift: list[str] = []
    for row in shipped:
        key = _row_key(row)
        want = native.get(key)
        if want is None:
            orphan.append(str(key))
            continue
        # *** THE BRIDGE MAY ADD FACTS. IT MAY NEVER CHANGE ONE. ***
        for field in NATIVE_OWNED_FIELDS:
            if row.get(field) != want.get(field):
                changed.append(f"{key}: {field}={row.get(field)!r}, but the ADMITTED native "
                               f"ranking states {want.get(field)!r}")
        # THE SIGN, RE-DERIVED FROM THE NATIVE VALUE — never from the bridge's own token.
        modality = row.get(S.FIELD_MODALITY)
        if str(modality) in S.MODALITY_PERFORMED_ACTION \
                and isinstance(want.get("evaluable"), bool):
            sign = S.observed_sign_state(want.get("arm_value"),
                                         evaluable=bool(want.get("evaluable")),
                                         origin_is_measured=True, arm_key=str(row.get("arm_key")))
            expect = S.desired_target_modulation(str(modality), sign)
            if row.get(S.FIELD_MODULATION) != expect:
                sign_drift.append(
                    f"{key}: the bridge says {S.FIELD_MODULATION}="
                    f"{row.get(S.FIELD_MODULATION)!r}, but the NATIVE arm_value "
                    f"{want.get('arm_value')!r} re-derives sign {sign!r}, which under "
                    f"{modality!r} means {expect!r}")
            elif row.get("phenocopy_class") != PHENOCOPY_CLASS_OF.get(expect):
                sign_drift.append(
                    f"{key}: phenocopy_class={row.get('phenocopy_class')!r} does not follow from "
                    f"{expect!r}")

    _gate(rep, GATE_BRIDGE_ORPHAN_ROW,
          "every bridge row is one the ADMITTED native bytes actually produce (a row the native "
          "ranking does not contain agrees with itself, and with nothing that was measured)",
          not orphan, f"{len(orphan)}: {orphan[:3]}")
    _gate(rep, GATE_BRIDGE_CHANGED_A_NATIVE_VALUE,
          "the bridge ADDS identity and modality — and CHANGES nothing. arm_value, evaluable and "
          "rank are taken from the ADMITTED NATIVE RANKING and the bridge is REQUIRED to agree: "
          "a bridge free to restate a measurement is a re-measured number wearing an admitted "
          "release's hashes, and every downstream sign would follow the forgery",
          not changed, "; ".join(changed[:2]))
    _gate(rep, C.GATE_SERIALIZED_MODULATION_DISAGREES_WITH_THE_SIGN,
          "every bridge row's desired_target_modulation and phenocopy_class are what the SIGN of "
          f"the NATIVE arm_value re-derives under the row's DECLARED modality (eps={S.SIGN_EPS!r}, "
          "bound from Stage-2 Direct and never retuned; the value arrives PRE-ORIENTED to its "
          "arm's desired_change and is never re-oriented). The bridge's token is a CHECK, never "
          "an input",
          not sign_drift, "; ".join(sign_drift[:2]))

    dropped = sorted(str(k) for k in native if k not in set(keys))
    _gate(rep, GATE_BRIDGE_DROPPED_A_ROW,
          "the bridge carries EVERY row the admitted native bytes produce — a dropped row and a "
          "row that never existed look identical, and the dropped one is the one nobody checks",
          not dropped, f"{len(dropped)} dropped: {dropped[:3]}")

    _gate(rep, GATE_BRIDGE_ZERO_EVIDENCE,
          "the bridge carries EVIDENCE. A bridge with no rows claims nothing, so nothing it "
          "claims is false — and a clean report over an empty handoff is the most dangerous "
          "artifact of all. Evidence that is absent is not evidence that is fine",
          bool(shipped) and bool(native),
          f"{len(shipped)} bridge row(s), {len(native)} native row(s)")

    if orphan or changed or sign_drift or dropped or incomplete or duplicate or not shipped:
        return None
    return {_row_key(r): r for r in shipped}


def _check_contexts(rep: Report, doc: dict[str, Any]) -> None:
    """THE PATHWAY FIREWALL. A gene-set enrichment may never wear a target's clothes.

    W3 reached this allowlist independently of Stage 3, and the two agree exactly — so it is
    bound verbatim rather than re-derived loosely. A context carrying ``arm_value``, ``rank``,
    ``target_id``, a modality or a ``phenocopy_claim`` is a SET-LEVEL statistic being handed a
    direction it never had, and would let a gene set be prescribed a drug.
    """
    contexts = doc.get("pathway_contexts") or []
    unknown, smuggled, misdeclared = [], [], []
    for ctx in contexts:
        arm = str(ctx.get("arm_key"))
        unknown += [f"{arm}:{f}" for f in sorted(set(ctx) - CTX_ALLOWED)]
        smuggled += [f"{arm}:{f}" for f in sorted(set(ctx) & CTX_FORBIDDEN)]
        if ctx.get("is_a_crispri_target_row") is not False \
                or ctx.get("may_be_matched_to_a_drug_as_a_target") is not False:
            misdeclared.append(arm)

    _gate(rep, GATE_CTX_UNKNOWN_FIELD,
          "every pathway context carries ONLY pathway-context fields (a field nobody agreed to "
          "is a field no consumer can be expected to refuse)",
          not unknown, f"{len(unknown)}: {unknown[:3]}")
    _gate(rep, GATE_CTX_CARRIES_TARGET_EVIDENCE,
          "no pathway context carries a TARGET-EVIDENCE field — not an arm_value, a rank, a "
          "target_id, a modality, a modulation, a phenocopy class or a 'supported' flag. An "
          "enrichment value is a statement about a GENE SET, not a measurement of a target under "
          "knockdown: read as a target's arm value it would prescribe a drug for a pathway",
          not smuggled, f"{len(smuggled)}: {smuggled[:3]}")
    _gate(rep, GATE_CTX_CARRIES_TARGET_EVIDENCE,
          "every pathway context DECLARES ITSELF not a CRISPRi target row and not matchable to a "
          "drug as a target (the denial is a field a consumer reads, not a docstring it does not)",
          not misdeclared, f"{len(misdeclared)}: {misdeclared[:3]}")
