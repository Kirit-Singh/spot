"""Rebuild the v2 evidence: arm slots, edges, arm summaries, candidates, dispositions.

The second half of the independent reconstruction (:mod:`verifier.v2_reconstruct` admits the
Stage-2 aggregate; :mod:`verifier.v2_store` re-opens the admitted universe store and rebuilds
its source assertions). Imports NOTHING from ``druglink``.

THE SIGN IS RE-DERIVED HERE, NEVER READ
---------------------------------------
The producer serializes ``desired_target_modulation`` on every arm record. THIS MODULE DOES NOT
CLASSIFY FROM IT. It re-derives the sign state from the two facts Stage 2 actually measured —
the SIGNED ``arm_value`` and ``evaluable`` — under the verifier's OWN restatement of the rule
(:mod:`verifier.v2_sign`), and then REQUIRES the producer's token to equal what that
re-derivation says. A disagreement is a NAMED REFUSAL
(:data:`verifier.v2_sign.GATE_SERIALIZED_MODULATION_DISAGREES_WITH_THE_SIGN`), not something to
reconcile: one of the two has the orientation backwards, and admitting it would ship an entire
release of drugs matched to the wrong direction.

What replaced what: the retired ``translate()`` took the producer's modulation as an INPUT and
returned a verdict. It could only ever prove the producer agreed with itself.

Every join is by EXACT TYPED IDENTITY — ``(target_id, target_id_namespace)`` — and never by gene
symbol: a symbol join looks identical on the day it is written and silently re-attributes every
edge the first time a gene is renamed or a symbol reused.

EVERY ARM SLOT IS REBUILT, INCLUDING THE SILENT ONES. An arm no drug evidence reached is emitted
with ``n_edges=0`` and an evidence state that NAMES the absence. A reconstruction that quietly
skipped it would agree with a producer that quietly dropped it.

THE PATHWAY LANE CONTRIBUTES ZERO, AND THAT ZERO IS RECONSTRUCTED. Its records are gene-set
enrichments, it is not admitted (its verifier fails open), and it yields no edge, no context row,
no rank and no direction. The reconstruction says so by name rather than by omission.
"""
from __future__ import annotations

from typing import Any, Optional

from . import policy
from . import v2_admission as v2
from . import v2_contract as C
from . import v2_sign as S
from . import v2_rows as R
from .v2_rows import (  # noqa: F401  (one definition, one home)
    arm_context_sha256,
    arm_identity,
    disposition,
    n_ranked,
    upstream,
)
from . import v2_store as vs
from . import v2_tables as T
from .report import Report


def _gate(rep: Report, gate: str, sentence: str, ok: Any, detail: str = "") -> bool:
    return rep.check(f"[{gate}] {sentence}", ok, detail)


# --------------------------------------------------------------------------- #
# The edge. The SIGN decides; the modality only says what phenocopies what.
# --------------------------------------------------------------------------- #
def _edge(arm: dict[str, Any], rec: dict[str, Any], assertion: dict[str, Any],
          store: dict[str, Any], *, digest: str, modality_digest: str,
          namespace: str) -> dict[str, Any]:
    origin = C.ORIGIN_FOR_LANE[arm["lane"]]
    measured = origin in v2.MEASURED_ORIGINS
    binding = store["release_binding"]

    # WHAT WAS TESTED, and WHETHER IT HELPED — two facts, neither derived from the other.
    modality = S.declared_modality(rec, arm_key=arm["arm_key"])
    evaluable = S.evaluable_of(rec, arm_key=arm["arm_key"])
    sign = S.observed_sign_state(rec.get(S.FIELD_ARM_VALUE), evaluable=evaluable,
                                 origin_is_measured=measured, arm_key=arm["arm_key"])
    # THE CHECK, NOT THE INPUT. The producer's own token must equal the sign we re-derived.
    stage2_token = S.check_serialized_modulation(rec, sign, modality=modality,
                                                 arm_key=arm["arm_key"])
    phenocopy_class = S.phenocopy_class_of(rec, arm_key=arm["arm_key"])

    verdict = S.classify(action_type=assertion.get("action_type_source"), modality=modality,
                         sign_state=sign, origin_is_measured=measured)

    rank = rec.get("rank")
    source_string, canonical_decimal = C.value_strings(rec.get(S.FIELD_ARM_VALUE))
    mid = vs.moiety_id(assertion)
    edge = {
        **arm_identity(arm),
        "origin_type": origin,
        "origin_is_measured": measured,
        **verdict,
        "stage2_desired_target_modulation": stage2_token,
        "stage2_phenocopy_class": phenocopy_class,
        "target_id": rec.get("target_id"),
        "target_id_namespace": namespace,
        "on_target_evidence": rec.get("on_target_evidence"),
        "on_target_evidence_status": (T.STATED if rec.get("on_target_evidence") not in (None, "")
                                      else T.NOT_STATED),
        "target_symbol": rec.get("target_symbol"),
        "target_ensembl": rec.get("target_ensembl"),
        "released_estimate_id": rec.get("released_estimate_id"),
        "set_id": rec.get("set_id"),
        # The pathway lane is NOT ADMITTED, so it contextualizes nothing: zero refs, by name.
        "pathway_refs": [],
        "n_pathway_refs": 0,
        # A null rank is a STATE, and the state is SPOKEN: never 0, never last, never invented.
        "arm_rank": rank,
        "arm_rank_status": (T.NOT_APPLICABLE_INFERRED if not measured
                            else T.RANKED if rank is not None else T.UNRANKED),
        "arm_evaluable": evaluable,
        "arm_value_source_string": source_string,
        "arm_value_canonical_decimal": canonical_decimal,
        "arm_value_status": T.STATED if source_string not in (None, "") else T.NOT_STATED,
        "source_record_id": assertion.get("edge_id"),
        "source_locator": vs.source_locator(assertion, binding),
        "source_release": binding["chembl_release"],
        "mec_id": assertion.get("source_row_id"),
        "molecule_chembl_id": assertion.get("molecule_chembl_id"),
        "target_chembl_id": assertion.get("target_chembl_id"),
        "candidate_id": mid,
        "active_moiety_id": mid,
        "assertion_lane": assertion.get("lane"),
        "general_gene_rankable": assertion.get("general_gene_rankable"),
        "action_type_source": assertion.get("action_type_source"),
        "action_type_normalized": policy.normalize_action(
            assertion.get("action_type_source")),
        "max_phase_source": assertion.get("max_phase_source"),
        "max_phase_status": (T.STATED if assertion.get("max_phase_source") not in (None, "")
                             else T.NOT_STATED),
        "max_phase_is_context_only": True,
        "direction_vocabulary_digest": digest,
        "modality_vocabulary_digest": modality_digest,
        **upstream(arm, store),
    }
    edge["edge_id"] = R._short(edge, T.EDGE_COLUMNS, "edge_id")
    return edge


# --------------------------------------------------------------------------- #
# THE TYPED RECORD = the NATIVE measurement + the BRIDGE's identity and modality.
#
# The native ranking row is exactly {target_id, arm_value, evaluable, rank}: it cannot say WHO a
# target is nor WHAT was done to it. W3's bridge supplies those two facts, and NOTHING else —
# `verifier.v2_bridge` has already required the bridge to agree with the native bytes on every
# value they state (arm_value, evaluable, rank), so the merge below cannot let a bridge re-state
# a measurement. The bridge ADDS; it never CHANGES.
# --------------------------------------------------------------------------- #
# EXACTLY the fields the bridge ADDS to a native ranking row — and not one more. `target_symbol`
# and `target_ensembl` belong here too: they are the rest of the identity tuple the bridge joined,
# and an edge that dropped them would carry a typed target nobody could name.
#
# The producer merges the SAME set (`druglink.stage2_bridge.BRIDGE_SUPPLIED_FIELDS`). Both sides
# state it independently, and the table hashes are what proves they agree: if either side merged a
# field the other did not, the reconstruction would drift and this verifier would refuse.
BRIDGE_SUPPLIED = (S.FIELD_NAMESPACE, S.FIELD_MODALITY, S.FIELD_MODULATION,
                   S.FIELD_PHENOCOPY_CLASS, "target_symbol", "target_ensembl")


def typed_record(arm: dict[str, Any], rec: dict[str, Any],
                 bridge_rows: dict[tuple[str, str, str], dict[str, Any]]) -> dict[str, Any]:
    """One native ranking row, typed by the bridge row that names its identity and its assay."""
    key = (str(arm["lane"]), str(arm["arm_key"]), str(rec.get("target_id")))
    row = bridge_rows.get(key)
    if row is None:
        raise S.SignRuleError(
            C.GATE_ARM_IDENTITY_UNRESOLVED,
            f"arm {arm['arm_key']!r} scored target {rec.get('target_id')!r}, and the Stage-3 "
            "bridge carries no typed row for it. The native ranking states no namespace and no "
            "modality, so without the bridge row this target has no identity to join on and no "
            "experiment to phenocopy — and a namespace GUESSED from the shape of the id attaches "
            "the wrong gene to a drug")
    # The MEASUREMENT stays the native one, always. Only identity and modality come from the
    # bridge, and only after it has been proved to agree with the native bytes.
    return {**rec, **{f: row.get(f) for f in BRIDGE_SUPPLIED}}


def _typed_identity(arm: dict[str, Any], rec: dict[str, Any]) -> tuple[str, str]:
    tid = rec.get("target_id")
    if not tid:
        raise S.SignRuleError(C.GATE_ARM_IDENTITY_UNRESOLVED,
                              f"arm {arm['arm_key']!r} holds a record with target_id={tid!r}; a "
                              "record with no target names nothing and joins to nothing")
    return str(tid), S.namespace_of(rec, arm_key=arm["arm_key"])


def reconstruct(rep: Report, *, aggregate: dict[str, Any], store: dict[str, Any],
                bridge_rows: dict[tuple[str, str, str], dict[str, Any]],
                artifact_class: str, modality_digest: str) -> Optional[dict[str, Any]]:
    """Rebuild every arm slot, edge, arm summary, candidate and disposition. Independently.

    ``modality_digest`` is the content address of the sign contract every edge was classified
    under. It is RECOMPUTED by :func:`verifier.v2_checks.check_modality_vocabulary` from the
    vocabulary block the bundle PUBLISHES — never copied from the digest the bundle declares —
    and that block's SEMANTIC tables (which modality performs which action, which mechanisms
    phenocopy it, and which (modality, sign) pair yields which token) are compared field for
    field against this verifier's own restatement before it is used. What survives that is a
    block the verifier agrees with; the digest is then only its address.
    """
    digest = C.direction_vocabulary_digest()

    # THE STORE'S OWN NAMESPACE VOCABULARY MUST BE THE ROW CONTRACT'S. Read from the store's
    # BYTES, never from a constant — and a divergence is SURFACED, never translated away: an
    # alias layer is how two admitted artifacts drift apart while both look green.
    held = sorted({str(r.get("target_id_namespace")) for r in store["rows"]})
    if not _gate(rep, C.GATE_UNKNOWN_NAMESPACE,
                 f"the admitted store types its rows in exactly the typed row contract's "
                 f"namespaces {list(S.W3_NAMESPACES)} — there is NO alias layer between the two "
                 "vocabularies, here or anywhere",
                 set(held) == set(S.W3_NAMESPACES), f"the store holds {held}"):
        return None

    # The typed records, per MEASURED arm: the native measurement joined to the bridge row that
    # names its identity and its assay.
    typed: dict[str, list[dict[str, Any]]] = {}
    refusals: list[str] = []
    targets: set[tuple[str, str]] = set()
    for arm in aggregate["arms"]:
        origin = C.ORIGIN_FOR_LANE[arm["lane"]]
        for rec in arm["records"]:
            # THE NO-RANK RULE IS NOT CHECKED HERE. It used to be, and it fired on the wrong
            # rows: these are Stage-2's RAW NATIVE pathway ranking records, and they legitimately
            # carry ranks — a pathway arm ranks perturbation targets in order to COMPUTE its
            # enrichment. They are upstream INPUTS, not Stage-3's emitted inferred evidence.
            #
            # The rule ("an inferred node was never perturbed, so it has no rank to carry") is
            # about what Stage 3 EMITS. It is enforced on the emitted pathway_context rows, in
            # v2_table_checks.check_no_rank_on_emitted_inferred_evidence — which is also where
            # W3's CTX_FORBIDDEN firewall lives, so the two agree about the same rows.
            #
            # Checking it here refused an honest bundle over bytes Stage 3 never emitted, and the
            # only ways to "fix" it there would have been to strip or mutate a native rank — i.e.
            # to edit an upstream measurement so a downstream gate would pass.
            if origin not in v2.MEASURED_ORIGINS:
                continue
            try:
                row = typed_record(arm, rec, bridge_rows)
                typed.setdefault(arm["arm_key"], []).append(row)
                targets.add(_typed_identity(arm, row))
            except S.SignRuleError as exc:
                refusals.append(str(exc))

    ok = _gate(rep, C.GATE_SYMBOL_JOIN,
               "every measured arm record joins the store by EXACT typed identity (target_id AND "
               "its own per-row namespace token). A symbol join looks identical the day it is "
               "written and silently re-attributes every edge the first time a gene is renamed",
               not refusals, "; ".join(refusals[:2]))
    if not ok:
        return None

    # The store's assertions, joined ONCE per typed identity a MEASURED arm actually names.
    in_universe = sorted(t for t in targets if (t[1], t[0]) in store["index"])
    records: dict[tuple[str, str], list[dict[str, Any]]] = {
        t: vs.assertions_for(store, store["index"][(t[1], t[0])]) for t in in_universe}

    dispositions: dict[str, dict[str, Any]] = {}
    for tid, ns in sorted(targets - set(in_universe)):
        row = disposition(
            subject_kind="target", subject_id=f"{ns}:{tid}", target_id=tid,
            target_id_namespace=ns, state=C.STATE_NOT_IN_UNIVERSE,
            reason=C.GATE_TARGET_NOT_IN_ADMITTED_UNIVERSE,
            detail="the admitted store covers a fixed typed universe; a target outside it "
                   "was never looked up, which is not an absence of drug evidence")
        dispositions[row["disposition_id"]] = row

    edges: list[dict[str, Any]] = []
    sign_refusals: list[str] = []
    for arm in aggregate["arms"]:
        # A PATHWAY ARM YIELDS NO DRUG EDGES, EVER — and says so, by name. Its records are
        # gene-set enrichments, not per-target knockdown effects, and the lane is not admitted.
        if C.ORIGIN_FOR_LANE[arm["lane"]] in v2.INFERRED_ORIGINS:
            row = disposition(
                subject_kind="arm", subject_id=arm["arm_key"], arm_key=arm["arm_key"],
                origin_type=C.ORIGIN_FOR_LANE[arm["lane"]],
                state=C.STATE_PATHWAY_LANE_NOT_ADMITTED,
                reason=C.GATE_PATHWAY_LANE_NOT_ADMITTED,
                detail=C.PATHWAY_LANE_NOT_ADMITTED_DETAIL)
            dispositions[row["disposition_id"]] = row
            continue
        for rec in typed.get(arm["arm_key"], []):
            try:
                key = _typed_identity(arm, rec)
                for assertion in records.get(key, ()):
                    if assertion["general_gene_rankable"]:
                        edges.append(_edge(arm, rec, assertion, store, digest=digest,
                                           modality_digest=modality_digest,
                                           namespace=key[1]))
            except S.SignRuleError as exc:
                sign_refusals.append(str(exc))

    # THE CENTRAL GATE. The producer's serialized modulation must equal the sign this verifier
    # re-derived from the SIGNED arm_value it was supposedly derived FROM.
    if not _gate(rep, C.GATE_SERIALIZED_MODULATION_DISAGREES_WITH_THE_SIGN,
                 "every arm record's serialized desired_target_modulation EQUALS the direction "
                 "this verifier INDEPENDENTLY re-derives from the SIGNED arm_value and evaluable "
                 f"under its own restatement of Stage-2's rule (eps={S.SIGN_EPS!r}), against the "
                 "modality the row DECLARES. The token is a CHECK, never an input: a verifier "
                 "that classified FROM it could only prove the producer agreed with itself",
                 not sign_refusals, "; ".join(sorted(set(sign_refusals))[:2])):
        return None

    assertions = [a for t in in_universe for a in records[t]]
    source_records = {r["source_record_id"]: r
                      for r in (vs.source_record(a, store) for a in assertions)}

    for assertion in assertions:
        if not assertion["general_gene_rankable"]:
            row = disposition(
                subject_kind="source_assertion", subject_id=str(assertion["edge_id"]),
                source_record_id=assertion["edge_id"],
                candidate_id=vs.moiety_id(assertion),
                target_id=assertion["target_id"],
                target_id_namespace=assertion["target_id_namespace"],
                state=C.STATE_NON_RANKABLE, reason=str(assertion["lane"]),
                detail="preserved, and never rankable: a variant mechanism is evidence about "
                       "the variant, and a shared accession would make one mechanism look "
                       "like independent evidence for every gene it maps to")
            dispositions[row["disposition_id"]] = row

    for tid, ns in in_universe:
        if any(a["general_gene_rankable"] for a in records[(tid, ns)]):
            continue
        row = store["index"][(ns, tid)]
        unsupported = row.get("disposition") == C.DISP_UNSUPPORTED_NAMESPACE
        got = disposition(
            subject_kind="target", subject_id=f"{ns}:{tid}", target_id=tid,
            target_id_namespace=ns,
            state=(C.STATE_UNSUPPORTED_NAMESPACE if unsupported
                   else C.STATE_NO_DRUG_EVIDENCE),
            reason=str(row.get("disposition")),
            detail=("this acquisition route cannot reach the target's namespace; that is "
                    "never an absence of drug evidence" if unsupported else
                    "the admitted store holds no general-gene rankable assertion for this "
                    "target"))
        dispositions[got["disposition_id"]] = got

    summaries = R.arm_summaries(edges)
    candidates = R.candidates(artifact_class=artifact_class, edges=edges,
                              summaries=summaries,
                              source_records=list(source_records.values()))
    for candidate in candidates:
        if candidate["stage4_assessment_status"] == policy.NOT_QUEUED:
            row = disposition(
                subject_kind="candidate", subject_id=str(candidate["candidate_id"]),
                candidate_id=str(candidate["candidate_id"]), state=policy.NOT_QUEUED,
                reason=str(candidate["stage4_assessment_reason"]),
                detail=f"identity={candidate['identity_status']}")
            dispositions[row["disposition_id"]] = row

    # THE ARMS AS THE EMITTER SEES THEM: a measured arm's records are the NATIVE rows TYPED by the
    # bridge. Reconstructing from the untyped rows read a namespace of None on every measured row,
    # so every target fell out of the admitted universe and each arm rebuilt with zero coverage —
    # a reconstruction that would refuse an honest bundle and, worse, would ADMIT one that had
    # genuinely lost its identities.
    typed_arms = [dict(arm, records=typed.get(arm["arm_key"], []))
                  if C.ORIGIN_FOR_LANE[arm["lane"]] in v2.MEASURED_ORIGINS else arm
                  for arm in aggregate["arms"]]

    return {
        "arm_slots": R.arm_slots(typed_arms, store, edges, records),
        "target_drug_edges": sorted(edges, key=lambda e: str(e["edge_id"])),
        # THE UNADMITTED LANE CONTRIBUTES ZERO. Reconstructed as empty and COMPARED, so a single
        # context row the producer emitted from it is a refusal rather than a silence.
        "pathway_context": [],
        "arm_summaries": summaries,
        "candidates": candidates,
        "source_records": [source_records[k] for k in sorted(source_records, key=str)],
        "dispositions": [dispositions[k] for k in sorted(dispositions, key=str)],
        "direction_vocabulary_digest": digest,
        "modality_vocabulary_digest": modality_digest,
    }
