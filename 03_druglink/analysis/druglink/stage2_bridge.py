"""Disk-backed ADMISSION of W3's Stage-2 -> Stage-3 bridge. THE typed-identity gate.

The tokens, the named gates and the :class:`AdmittedBridge` shape live in
:mod:`druglink.stage2_bridge_contract` (split at the 500-line gate). This module is the gate
itself: it re-hashes the bridge, REQUIRES the receipt, cross-binds to the aggregate Stage 3
admitted, and checks every typed row against the ADMITTED NATIVE ranking records.

THE ONE RULE THAT MAKES A BRIDGE SAFE
-------------------------------------
    **It may ADD facts the native bytes lack (namespace, modality).
      It may NEVER CHANGE a fact the native bytes already state (arm_value, rank, evaluable).**

So ``arm_value``, ``rank`` and ``evaluable`` come from the NATIVE RANKING RECORDS — the ones the
aggregate manifest bound by hash and Stage-2's own independent verifier admitted — and the bridge
is REQUIRED to agree. The drug direction is RE-DERIVED from that native value alone; the
serialized ``desired_target_modulation`` is a CHECK, never an input.

THE RECEIPT IS NOT OPTIONAL. W3's bridge report names the bytes it judged but nothing ties it to
an ADMITTED aggregate. The RECEIPT is the join, so a report without one is an ADMIT that names no
release.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import replace
from typing import Any, Mapping, Optional

from . import modality_v2 as mv2
from . import stage2_contract as C
from .stage2_bridge_contract import (  # noqa: F401  (one front door: re-exported)
    ADMIT,
    BRIDGE_SCHEMA,
    BRIDGE_SELF_HASH_FIELD,
    BRIDGE_SUPPLIED_FIELDS,
    BRIDGE_VERIFIER_ID,
    CTX_FORBIDDEN,
    GATE_ARM_KEY_CONFLICT,
    GATE_BRIDGE_BINDS_NOTHING,
    GATE_BRIDGE_IS_EMPTY,
    GATE_BRIDGE_NOT_NATIVE,
    GATE_BRIDGE_NOT_ON_DISK,
    GATE_BRIDGE_OVER_ANOTHER_AGGREGATE,
    GATE_BRIDGE_REPORT_NOT_NATIVE,
    GATE_BRIDGE_SELF_HASH,
    GATE_DUPLICATE_BRIDGE_ROW,
    GATE_DUPLICATE_NATIVE_ROW,
    GATE_MODULATION_DISAGREES_WITH_SIGN,
    GATE_PATHWAY_CONTEXT_IS_TARGET_EVIDENCE,
    GATE_PATHWAY_SOURCED_A_TYPED_ROW,
    GATE_RECEIPT_ABSENT,
    GATE_RECEIPT_BINDS_OTHER_BYTES,
    GATE_RECEIPT_NOT_NATIVE,
    GATE_RECEIPT_SELF_HASH,
    GATE_REPORT_JUDGED_OTHER_BYTES,
    GATE_REPORT_NOT_ADMIT,
    GATE_ROW_CHANGES_A_NATIVE_FACT,
    GATE_ROW_DROPPED,
    GATE_ROW_IDENTITY_NOT_TYPED,
    GATE_ROW_MODALITY_NOT_DECLARED,
    GATE_ROW_ORPHAN,
    MOD_DECREASE,
    MOD_INCREASE,
    MOD_NO_DIRECTION,
    MOD_NOT_EVALUATED,
    MODALITY_CRISPRI,
    NATIVE_FACTS,
    RECEIPT_SCHEMA,
    RECEIPT_SELF_HASH_FIELD,
    REQUIRED_BINDINGS,
    SIGN_EPS,
    AdmittedBridge,
    Stage2BridgeError,
    _refuse,
    bridge_provenance_rows,  # noqa: F401  (re-exported: bundle_v2 enumerates them)
)
from .stage2_contract import LANE_PATHWAY, MEASURED_LANES, AdmittedAggregate


# --- W3's hashing rule, re-derived. --------------------------------------------- #
def canonical_sha256(obj: Any) -> str:
    """The producer's canonical content hash: keys SORTED, compact, ASCII-escaped."""
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=True).encode("utf-8")).hexdigest()


def self_hash(doc: Mapping[str, Any], field: str) -> str:
    """A document's OWN identity: the canonical hash of everything EXCEPT the claim."""
    return canonical_sha256({k: v for k, v in doc.items() if k != field})


def _load(path: str, what: str, gate: str) -> tuple[dict[str, Any], str]:
    if not path or not os.path.isfile(path):
        _refuse(gate, f"the {what} is not on disk at {path!r}. There is no fallback: Stage 3 "
                      "does not build a v2 analysis while ignoring the bridge, because the "
                      "native arms carry no namespace and no modality.")
    doc, raw = C.load_json(path, what)
    if not isinstance(doc, dict):
        _refuse(gate, f"the {what} at {path!r} is not a JSON object")
    return doc, raw


# --- 1. The bridge: its own identity, and what it says it was built from. -------- #
def _check_bridge(path: str) -> tuple[dict[str, Any], str, str]:
    doc, raw = _load(path, "Stage-2 -> Stage-3 bridge", GATE_BRIDGE_NOT_ON_DISK)
    if doc.get("schema_version") != BRIDGE_SCHEMA:
        _refuse(GATE_BRIDGE_NOT_NATIVE,
                f"the bridge declares schema_version={doc.get('schema_version')!r}; the native "
                f"contract is {BRIDGE_SCHEMA!r}. A document Stage 2 never emitted is not a "
                "handoff Stage 2 produced.")
    # RECOMPUTED, never read. A self-hash proves only that a document agrees with itself — and a
    # forgery can be made to agree with itself — but a document that cannot even do that is not
    # an artifact.
    declared, derived = doc.get(BRIDGE_SELF_HASH_FIELD), self_hash(doc, BRIDGE_SELF_HASH_FIELD)
    if declared != derived:
        _refuse(GATE_BRIDGE_SELF_HASH,
                f"the bridge declares {BRIDGE_SELF_HASH_FIELD}={str(declared)[:16]}… but its own "
                f"content hashes to {derived[:16]}…: these bytes were edited after they were "
                "sealed.")
    bindings = doc.get("bindings") or {}
    missing = [k for k in REQUIRED_BINDINGS if not bindings.get(k)]
    if missing:
        _refuse(GATE_BRIDGE_BINDS_NOTHING,
                f"the bridge binds no {missing}. A typed row that names neither the bytes it came "
                "from nor the admission that cleared them is a row from nowhere — it could have "
                "been built from anything, including nothing.")
    return doc, raw, derived


def _check_report(path: str, *, bridge_raw: str) -> tuple[dict[str, Any], str]:
    """The SEPARATE verifier's report — and it must have judged EXACTLY these bridge bytes."""
    doc, raw = _load(path, "Stage-2 bridge verification report", GATE_BRIDGE_NOT_ON_DISK)
    if doc.get("verifier_id") != BRIDGE_VERIFIER_ID:
        _refuse(GATE_BRIDGE_REPORT_NOT_NATIVE,
                f"the bridge report is signed {doc.get('verifier_id')!r}; the pinned independent "
                f"bridge verifier is {BRIDGE_VERIFIER_ID!r}.")
    if doc.get("generator_is_not_verifier") is not True:
        _refuse(GATE_BRIDGE_REPORT_NOT_NATIVE,
                "the bridge report does not assert generator_is_not_verifier=true. A producer "
                "agreeing with itself is the one thing an independent verifier rules out.")
    if doc.get("verdict") != ADMIT or doc.get("n_failed") != 0:
        _refuse(GATE_REPORT_NOT_ADMIT,
                f"the bridge verifier's verdict is {doc.get('verdict')!r} with "
                f"n_failed={doc.get('n_failed')!r}. Stage 3 consumes a bridge an independent "
                "verifier ADMITTED, or none.")
    # WHICH BYTES IT JUDGED. Without this an ADMIT can be pointed at a bridge it never saw.
    judged = (doc.get("judged_bridge") or {}).get("raw_sha256")
    if judged != bridge_raw:
        _refuse(GATE_REPORT_JUDGED_OTHER_BYTES,
                f"the bridge report judged bridge {str(judged)[:16]}…; the bridge on disk is "
                f"{bridge_raw[:16]}…. That report is a verdict on different bytes than the ones "
                "being handed to Stage 3.")
    return doc, raw


def _bound(receipt: Mapping[str, Any], *path_keys: str) -> dict[str, Any]:
    node: Any = receipt
    for key in path_keys:
        node = (node or {}).get(key)
    return node or {}


def _check_receipt(path: str, *, bridge_raw: str, bridge_canonical: str, report_raw: str,
                   aggregate: AdmittedAggregate, aggregate_report_path: str) -> tuple[dict, str]:
    """THE JOIN. It binds an ADMITTED aggregate to THIS bridge — those exact bytes, or neither."""
    doc, raw = _load(path, "Stage-2 -> Stage-3 receipt", GATE_RECEIPT_ABSENT)
    if doc.get("schema_version") != RECEIPT_SCHEMA:
        _refuse(GATE_RECEIPT_NOT_NATIVE,
                f"the receipt declares schema_version={doc.get('schema_version')!r}; the native "
                f"contract is {RECEIPT_SCHEMA!r}.")
    declared, derived = doc.get(RECEIPT_SELF_HASH_FIELD), self_hash(doc, RECEIPT_SELF_HASH_FIELD)
    if declared != derived:
        _refuse(GATE_RECEIPT_SELF_HASH,
                f"the receipt declares {RECEIPT_SELF_HASH_FIELD}={str(declared)[:16]}… but its "
                f"own content hashes to {derived[:16]}….")

    _, agg_report_raw = C.load_json(aggregate_report_path, "Stage-2 aggregate report")
    with open(aggregate_report_path, "r", encoding="utf-8") as fh:
        agg_report_canonical = canonical_sha256(json.load(fh))

    # EVERY referent, against the bytes Stage 3 actually admitted / actually holds. A receipt
    # binding other bytes is a receipt for another release.
    for what, node, want_raw, want_canonical in (
            ("the bridge", _bound(doc, "bridge"), bridge_raw, bridge_canonical),
            ("the bridge report", _bound(doc, "bridge_report"), report_raw, None),
            ("the aggregate manifest", _bound(doc, "aggregate", "manifest"),
             aggregate.manifest_raw_sha256, aggregate.manifest_canonical_sha256),
            ("the aggregate report", _bound(doc, "aggregate", "report"),
             agg_report_raw, agg_report_canonical)):
        got = node.get("raw_sha256")
        if got != want_raw:
            _refuse(GATE_RECEIPT_BINDS_OTHER_BYTES,
                    f"the receipt binds {what} at {str(got)[:16]}…; the bytes Stage 3 holds hash "
                    f"to {want_raw[:16]}…. A receipt that names a different artifact than the one "
                    "that is there joins a release nobody cleared to a handoff nobody checked.")
        if want_canonical and node.get("canonical_sha256") not in (None, want_canonical):
            _refuse(GATE_RECEIPT_BINDS_OTHER_BYTES,
                    f"the receipt's canonical hash for {what} does not match the bytes on disk.")
    return doc, raw


def _check_aggregate_crossbind(bridge: Mapping[str, Any], aggregate: AdmittedAggregate) -> None:
    """The bridge must be built over the aggregate STAGE 3 ADMITTED — not merely over AN aggregate.

    A bridge over a different (or a since-edited) aggregate is a Stage-3 handoff for a release
    that was never cleared. It looks exactly like one that was.
    """
    bound = _bound(bridge, "bindings", "aggregate", "manifest")
    got = bound.get("raw_sha256")
    if got != aggregate.manifest_raw_sha256:
        _refuse(GATE_BRIDGE_OVER_ANOTHER_AGGREGATE,
                f"the bridge was built over aggregate manifest {str(got)[:16]}…; Stage 3 admitted "
                f"{aggregate.manifest_raw_sha256[:16]}…. The typed rows in this bridge describe "
                "some other release's arms.")
    canonical = bound.get("canonical_sha256")
    if canonical not in (None, aggregate.manifest_canonical_sha256):
        _refuse(GATE_BRIDGE_OVER_ANOTHER_AGGREGATE,
                "the bridge's bound aggregate manifest has a different canonical hash than the "
                "manifest Stage 3 admitted.")


# --- 2. The rows, against the NATIVE bytes the aggregate admitted. --------------- #
def native_index(aggregate: AdmittedAggregate) -> dict[tuple[str, str, str], dict[str, Any]]:
    """(lane, arm_key, target_id) -> the NATIVE ranking record. The measured lanes, only.

    These are the rows the aggregate manifest bound by hash and Stage-2's own independent verifier
    admitted. They are the fact the bridge may not move.

    A DUPLICATE IDENTITY IS A REFUSAL, not a last-write-wins. Two native records under one
    (lane, arm, target) key are two different statements about one measurement — and quietly
    keeping the last would cross-check the bridge against a row the release itself contradicts,
    while telling nobody the other one existed.
    """
    out: dict[tuple[str, str, str], dict[str, Any]] = {}
    for arm in aggregate.arms:
        if arm.lane not in MEASURED_LANES:
            continue
        for rec in arm.records:
            key = (arm.lane, arm.arm_key, str(rec.get("target_id")))
            if key in out and out[key] != dict(rec):
                _refuse(GATE_DUPLICATE_NATIVE_ROW,
                        f"{key}: the admitted ranking carries this identity TWICE, with different "
                        f"values ({out[key].get('arm_value')!r} and {rec.get('arm_value')!r}). "
                        "One of them is never checked, and a consumer counting rows reads one "
                        "measurement as two.")
            if key in out:
                _refuse(GATE_DUPLICATE_NATIVE_ROW,
                        f"{key}: the admitted ranking carries this identity twice. A join key "
                        "that is not unique silently multiplies every row it is joined to.")
            out[key] = dict(rec)
    return out


def rederive_modulation(arm_value: Optional[float], *, evaluable: bool) -> str:
    """THE SIGN, from the NATIVE oriented value and evaluability ALONE. Never from a token.

    The value arrives PRE-ORIENTED to its arm's desired_change — a positive value means the
    knockdown moved the program the way THIS arm wants — so it is never re-oriented here.
    """
    if not evaluable or arm_value is None:
        return MOD_NOT_EVALUATED
    value = float(arm_value)
    if value > SIGN_EPS:
        return MOD_DECREASE            # the knockdown helped -> an inhibitor may phenocopy it
    if value < -SIGN_EPS:
        return MOD_INCREASE            # ...and this is NOT an agonist recommendation
    return MOD_NO_DIRECTION


def _check_row(key: tuple[str, str, str], row: Mapping[str, Any],
               native: Mapping[str, Any]) -> None:
    """One typed row against the native record it claims to be about."""
    where = f"{key[0]}|{key[1]}|{key[2]}"

    # (a) IT MAY NEVER CHANGE A MEASUREMENT. arm_value / rank / evaluable are the native bytes'
    # to state, and the bridge's only to carry.
    for field in NATIVE_FACTS:
        if row.get(field) != native.get(field):
            _refuse(GATE_ROW_CHANGES_A_NATIVE_FACT,
                    f"{where}: the bridge says {field}={row.get(field)!r}; the ADMITTED native "
                    f"ranking record says {native.get(field)!r}. A bridge may ADD the facts the "
                    "native bytes lack — the namespace, the modality — and it may never restate "
                    "the measurement they already made.")

    # (b) IT MUST ADD THE TWO FACTS IT EXISTS FOR. Neither is guessed and neither is defaulted.
    namespace = row.get(mv2.FIELD_NAMESPACE)
    if namespace not in mv2.W3_NAMESPACES:
        _refuse(GATE_ROW_IDENTITY_NOT_TYPED,
                f"{where}: target_id_namespace={namespace!r} is not one of "
                f"{list(mv2.W3_NAMESPACES)}. A namespace-less id is a name, and names are not "
                "identities: this universe holds Ensembl accessions AND bare symbols, and three "
                "of the four symbols carry an ENSG-looking key belonging to a DIFFERENT gene.")
    modality = row.get(mv2.FIELD_MODALITY)
    if modality != MODALITY_CRISPRI:
        _refuse(GATE_ROW_MODALITY_NOT_DECLARED,
                f"{where}: the row declares observed_perturbation_modality={modality!r}, not "
                f"{MODALITY_CRISPRI!r}. The assay is never assumed: a perturbation nobody "
                "declared is not a perturbation anybody may prescribe against.")

    # (c) THE DIRECTION, RE-DERIVED FROM THE NATIVE VALUE — and the serialized token CHECKED
    # against it. Never obeyed: if the two disagree, one of us has the orientation backwards, and
    # a silent disagreement here is a whole release of drugs matched to the wrong direction.
    want = rederive_modulation(native.get("arm_value"),
                               evaluable=bool(native.get("evaluable")))
    got = row.get(mv2.FIELD_MODULATION)
    if got != want:
        _refuse(GATE_MODULATION_DISAGREES_WITH_SIGN,
                f"{where}: the bridge serializes desired_target_modulation={got!r}; re-derived "
                f"from the NATIVE arm_value={native.get('arm_value')!r} / "
                f"evaluable={native.get('evaluable')!r} (eps={SIGN_EPS}) it is {want!r}.")


def _check_rows(bridge: Mapping[str, Any],
                aggregate: AdmittedAggregate) -> dict[str, list[dict[str, Any]]]:
    """Every bridge row against the native bytes; every native row against the bridge."""
    native = native_index(aggregate)
    rows = list(bridge.get("target_rows") or [])
    if not rows:
        _refuse(GATE_BRIDGE_IS_EMPTY,
                "the bridge carries 0 typed target rows. Nothing it says is false, because it "
                "says nothing — and a clean report over an empty handoff is the most dangerous "
                "artifact there is.")
    if not native:
        _refuse(GATE_BRIDGE_IS_EMPTY,
                "the ADMITTED aggregate carries no native ranking records on any measured lane, "
                "so there is nothing for the bridge to be checked against. A pass over an empty "
                "release is not a pass.")

    by_arm: dict[str, list[dict[str, Any]]] = {}
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        lane, arm_key = str(row.get("lane")), str(row.get("arm_key"))
        if lane == LANE_PATHWAY:
            _refuse(GATE_PATHWAY_SOURCED_A_TYPED_ROW,
                    f"the bridge carries a TARGET ROW on the pathway lane ({arm_key!r}). A "
                    "pathway record is a gene-set enrichment: nobody knocked down a set, so it "
                    "has no CRISPRi sign, and it is CONTEXT — never target evidence.")
        key = (lane, arm_key, str(row.get("target_id")))
        # A DUPLICATE ROW DOUBLE-COUNTS ITS OWN EVIDENCE. A consumer counting rows reads one
        # measurement as two, and the extra is indistinguishable from a second, independent
        # observation that was never made.
        if key in seen:
            _refuse(GATE_DUPLICATE_BRIDGE_ROW,
                    f"{key}: two bridge rows claim this one (lane, arm, target) identity. One of "
                    "them was never checked against anything, and the arm it belongs to now "
                    "carries a measurement nobody took.")
        record = native.get(key)
        if record is None:
            _refuse(GATE_ROW_ORPHAN,
                    f"{key}: the ADMITTED native bytes produce no such row. It agrees with "
                    "itself, and with nothing that was measured.")
        _check_row(key, row, record)
        seen.add(key)
        by_arm.setdefault(arm_key, []).append(dict(row))

    dropped = sorted(set(native) - seen)
    if dropped:
        _refuse(GATE_ROW_DROPPED,
                f"the admitted native bytes produce {len(dropped)} row(s) the bridge does not "
                f"carry (e.g. {dropped[:3]}). A dropped row and a row that never existed look "
                "identical — and the target it belongs to would silently find no drug.")
    return by_arm


def _check_contexts(bridge: Mapping[str, Any]) -> int:
    """A pathway context may never wear a target's clothes."""
    contexts = list(bridge.get("pathway_contexts") or [])
    for ctx in contexts:
        smuggled = sorted(set(ctx) & CTX_FORBIDDEN)
        if smuggled:
            _refuse(GATE_PATHWAY_CONTEXT_IS_TARGET_EVIDENCE,
                    f"the pathway context {ctx.get('arm_key')!r}/{ctx.get('gene_set_id')!r} "
                    f"carries TARGET-EVIDENCE field(s) {smuggled}. An enrichment value is a "
                    "statement about a GENE SET; a context that also carries an arm value and a "
                    "drug direction is a target row wearing a pathway's clothes, ready to be "
                    "prescribed a drug.")
    return len(contexts)


# --- The gate. ------------------------------------------------------------------ #
def admit_bridge(*, bridge_path: str, report_path: str, receipt_path: str,
                 aggregate: AdmittedAggregate,
                 aggregate_report_path: str) -> AdmittedBridge:
    """Admit W3's bridge FROM DISK, against the aggregate Stage 3 ADMITTED, or refuse by name."""
    bridge, bridge_raw, bridge_hash = _check_bridge(bridge_path)
    bridge_canonical = canonical_sha256(bridge)
    report, report_raw = _check_report(report_path, bridge_raw=bridge_raw)
    _, receipt_raw = _check_receipt(
        receipt_path, bridge_raw=bridge_raw, bridge_canonical=bridge_canonical,
        report_raw=report_raw, aggregate=aggregate,
        aggregate_report_path=aggregate_report_path)
    _check_aggregate_crossbind(bridge, aggregate)

    by_arm = _check_rows(bridge, aggregate)
    n_contexts = _check_contexts(bridge)
    return AdmittedBridge(
        bridge_raw_sha256=bridge_raw, bridge_canonical_sha256=bridge_canonical,
        bridge_self_hash=bridge_hash, report_raw_sha256=report_raw,
        receipt_raw_sha256=receipt_raw, verifier_id=str(report.get("verifier_id")),
        verdict=str(report.get("verdict")),
        n_rows=sum(len(v) for v in by_arm.values()), n_pathway_contexts=n_contexts,
        rows_by_arm={k: tuple(v) for k, v in by_arm.items()},
        schema_version=str(bridge.get("schema_version")),
        rule_id=str(bridge.get("rule_id") or ""))


def typed_aggregate(aggregate: AdmittedAggregate, bridge: AdmittedBridge) -> AdmittedAggregate:
    """The admitted aggregate with its MEASURED arms carrying the bridge's TYPED rows — AND
    NAMING the bridge that typed them.

    This is the whole point of the bridge: the emitter needs a namespace and a modality on every
    measured row, and the native ranking records have neither. The pathway arms keep their native
    records — the pathway is CONTEXT and never sources an edge.

    THE TYPED ROW IS THE NATIVE ROW PLUS :data:`BRIDGE_SUPPLIED_FIELDS`, and nothing else. The
    measurement stays the native one, always — the bridge's own copy of ``arm_value`` never
    reaches the emitter, so even a bridge that somehow slipped a changed value past
    :func:`admit_bridge` could not put it in a bundle.

    ``bridge_binding`` travels with the aggregate so the emitted bundle can never be DETACHED from
    the bridge it was typed by. Swapping in a different admitted bridge must move the bundle id;
    if it did not, the binding would be decorative.
    """
    typed: dict[tuple[str, str, str], dict[str, Any]] = {
        (str(r.get("lane")), str(r.get("arm_key")), str(r.get("target_id"))): r
        for rows in bridge.rows_by_arm.values() for r in rows}

    arms = []
    for arm in aggregate.arms:
        if arm.lane not in MEASURED_LANES:
            arms.append(arm)
            continue
        records = []
        for rec in arm.records:
            row = typed[(arm.lane, arm.arm_key, str(rec.get("target_id")))]
            records.append(dict(rec, **{f: row.get(f) for f in BRIDGE_SUPPLIED_FIELDS}))
        arms.append(replace(arm, records=tuple(records)))
    return replace(aggregate, arms=tuple(arms), bridge_binding=bridge.binding())
