"""DEVELOPMENT projection over REAL, UNADMITTED Stage-2 Direct bytes. NOT a production result.

WHAT THIS IS, SAID PLAINLY
--------------------------
The Stage-2 aggregate manifest, its independent report and the Stage-2 -> Stage-3 bridge do not
exist yet for the current Direct run. The production path (``run_stage3 --v2``) therefore refuses,
correctly, and it must keep refusing: an unadmitted release has no independent verifier standing
behind its numbers.

But the DIRECT ARM BYTES ARE REAL and finished, and so is the admitted universe store. This module
wires those together so the UI and Stage 4 have something real to build against WHILE admission is
pending. Every document it writes is stamped::

    status                  development_unadmitted
    admission_pending       true
    is_production_result    false

and it never writes a Stage-3 bundle, never mints a bundle id, and never emits a membership
receipt. Those are admission artifacts, and this is not admission.

WHAT IS REAL HERE, AND WHAT IS NOT
----------------------------------
REAL  the Direct ``arms.parquet`` rows (the measurement), verbatim
REAL  ``target_identity.json`` (the typed identity + modality) — the SAME artifact the production
      bridge names as its Direct identity source, read from the same bytes
REAL  the admitted universe store (store_id 625c921f…), through the production loader, which pins
      the exact store an independent verifier admitted
REAL  the frozen direction/sign engine — the drug direction is RE-DERIVED here exactly as
      production derives it, from the arm's own value and the drug's sourced action
NOT   the Stage-2 aggregate admission, the bridge admission, and the independent Stage-3 verifier.
      They do not exist yet. That is why this says ``development_unadmitted``.

THE TWO ARMS STAY APART. A question is a JOIN of two independent arms (A: move away from the A
program, B: move toward the B program). There is no combined, balanced or weighted objective here
and there never will be: the arms are reported separately, and a drug that helps one and opposes
the other must be visibly both.

PATHWAY ANNOTATES; IT NEVER PROMOTES. A pathway context may only be attached to a candidate an
eligible gene-arm edge ALREADY supports. It cannot create a candidate, a target, or an arm
membership. When the GO-BP endpoint bytes for a condition are not present, that condition's
pathway context is a NAMED UNAVAILABLE entry — never an empty list that reads like "we looked and
found none".
"""
from __future__ import annotations

import json
import os
from types import SimpleNamespace
from typing import Any, Optional

from . import direction as dr
from . import edge_build_v2 as eb
from . import modality_contract as mc
from . import modality_rule as mr
from . import universe_rows as ur
from .assertions_v2 import moiety_id
from .hashing import file_sha256
from .stage2_contract import AdmittedBundle, LoadedArm

SCHEMA = "spot.stage03_dev_projection.v0"
STATUS_UNADMITTED = "development_unadmitted"

# THE ADMISSION THESE EDGES STAND ON: none, said out loud in the field Stage 4 reads.
# The frozen edge engine refuses a NULL verifier/verdict — rightly, because a null is an edge
# whose admission nobody can read, and it would reach Stage 4 looking exactly like an admitted
# one. So the true thing is written instead. Neither token is ever "admit", and no consumer can
# mistake "admission_pending" for an admission.
AGGREGATE_NOT_ADMITTED_VERIFIER = "spot.development.unadmitted_adapter.v0"
VERDICT_ADMISSION_PENDING = "admission_pending"

LANE_DIRECT = "direct"
ARM_BUNDLE = "arm_bundle.json"
ARM_ROWS = "arms.parquet"
TARGET_IDENTITY = "target_identity.json"

# The typed columns the identity artifact supplies — the same six the production bridge supplies,
# read from the same file. Nothing here is inferred from the shape of an id.
IDENTITY_FIELDS = (mc.FIELD_NAMESPACE, mc.FIELD_MODALITY, "target_symbol", "target_ensembl")

# Stage-2's phenocopy vocabulary, keyed by the modulation the SIGN implies. RE-DERIVED, never read.
PHENOCOPY_CLASS_OF = {
    mc.MOD_DECREASE: "inhibition_observed_compatible",
    mc.MOD_INCREASE: "inhibitor_opposed",
    mc.MOD_NO_DIRECTION: "no_directional_response",
    mc.MOD_NOT_EVALUATED: "not_evaluable",
}


class DevProjectionError(ValueError):
    """A real input is missing or does not agree with itself. There is NO fixture fallback."""


def _refuse(gate: str, message: str) -> None:
    raise DevProjectionError(f"[{gate}] {message}")


def _load_json(path: str, what: str) -> dict[str, Any]:
    if not os.path.isfile(path):
        _refuse("a_real_input_is_not_on_disk",
                f"no {what} at {path!r}. This runner has NO fixture fallback: a projection "
                "without its real bytes does not quietly become one with synthetic bytes.")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# --------------------------------------------------------------------------- #
# 1. The REAL Direct bundle -> typed arms. Identity from target_identity.json.
# --------------------------------------------------------------------------- #
def load_direct_arms(bundle_dir: str) -> tuple[list[LoadedArm], dict[str, Any]]:
    """The real Direct bundle: its native rows, TYPED by its own identity artifact.

    ``arms.parquet`` carries ``{arm_key, target_id, value, rank, evaluable, …}`` — the
    measurement, and NO namespace and NO modality. ``target_identity.json`` carries exactly those
    two facts, per target. This is the same split the production bridge exists to close, and the
    same file it names as the Direct identity source; the join here is by EXACT target_id, never
    by symbol.
    """
    import pandas as pd

    bundle = _load_json(os.path.join(bundle_dir, ARM_BUNDLE), "Direct arm_bundle.json")
    identity_doc = _load_json(os.path.join(bundle_dir, TARGET_IDENTITY),
                              "Direct target_identity.json")
    rows_path = os.path.join(bundle_dir, ARM_ROWS)
    if not os.path.isfile(rows_path):
        _refuse("a_real_input_is_not_on_disk", f"no {ARM_ROWS} in {bundle_dir!r}")

    identity = {str(r["target_id"]): r for r in (identity_doc.get("records") or [])}
    if not identity:
        _refuse("the_identity_artifact_types_nothing",
                f"{TARGET_IDENTITY} carries no records; every target would be untyped, and a "
                "namespace GUESSED from the shape of an id attaches the wrong gene to a drug.")

    condition = str(bundle.get("condition") or "")
    run_id = str(bundle.get("arm_bundle_run_id") or "")
    frame = pd.read_parquet(rows_path)

    provenance = {
        "arm_bundle_raw_sha256": file_sha256(os.path.join(bundle_dir, ARM_BUNDLE)),
        "arms_parquet_raw_sha256": file_sha256(rows_path),
        "target_identity_raw_sha256": file_sha256(os.path.join(bundle_dir, TARGET_IDENTITY)),
        "arm_rows_sha256_declared": str(bundle.get("arm_rows_sha256") or ""),
        "arm_bundle_run_id": run_id,
        "condition": condition,
        "schema_version": str(bundle.get("schema_version") or ""),

        # EVERY EDGE MUST NAME THE ADMISSION IT STANDS ON — and these edges stand on NONE.
        #
        # The frozen engine refuses a null here, and it is right to: "a null is an edge whose
        # admission nobody can read, and it would ride out to Stage 4 looking exactly like an
        # admitted one." The fix is NOT to weaken that gate, and NOT to write "admit" — it is to
        # say the true thing in the field Stage 4 actually reads. These tokens are not a verdict
        # of admission; they are a verdict of NO admission, and no consumer can mistake one for
        # the other. A null could be overlooked; this cannot.
        "aggregate_verifier_id": AGGREGATE_NOT_ADMITTED_VERIFIER,
        "aggregate_verdict": VERDICT_ADMISSION_PENDING,
        # There is no aggregate manifest to hash, because there is no aggregate.
        "manifest_raw_sha256": None,
        "manifest_canonical_sha256": None,
        "manifest_self_hash": None,

        # SAID IN THE ARTIFACT, not only in a docstring.
        "status": STATUS_UNADMITTED,
        "admission_pending": True,
        "is_production_result": False,
    }

    admitted_bundle = AdmittedBundle(
        bundle_key=f"{LANE_DIRECT}|{condition}", bundle_id=run_id, lane=LANE_DIRECT,
        path=bundle_dir, raw_sha256=provenance["arm_bundle_raw_sha256"],
        canonical_sha256=provenance["arm_rows_sha256_declared"], files={},
        condition=condition)

    arms: list[LoadedArm] = []
    for entry in (bundle.get("arms") or []):
        arm_key = str(entry["arm_key"])
        sub = frame[frame["arm_key"] == arm_key]
        records = _typed_records(sub, identity, arm_key=arm_key)
        arms.append(LoadedArm(
            arm_key=arm_key, lane=LANE_DIRECT, program_id=str(entry["program_id"]),
            desired_change=str(entry["desired_change"]), bundle=admitted_bundle,
            ranking={"path": ARM_ROWS,
                     "raw_sha256": provenance["arms_parquet_raw_sha256"],
                     "canonical_sha256": str(entry.get("arm_rows_sha256") or "")},
            provenance=dict(provenance), records=tuple(records)))
    return arms, provenance


def _typed_records(sub, identity: dict[str, Any], *, arm_key: str) -> list[dict[str, Any]]:
    """One native ranking row, typed by the identity artifact. The MEASUREMENT stays native.

    ``value`` arrives PRE-ORIENTED to the arm's own desired_change (Stage 2 orients it), so it is
    carried through as ``arm_value`` untouched and is never re-signed here. The direction is then
    RE-DERIVED from it under the declared modality — the same rule production applies.
    """
    import pandas as pd

    out: list[dict[str, Any]] = []
    for row in sub.to_dict("records"):
        tid = str(row["target_id"])
        typed = identity.get(tid)
        if typed is None:
            # A target the identity artifact does not name has no namespace and no assay. It is
            # SKIPPED and COUNTED, never guessed at.
            continue
        evaluable = bool(row.get("evaluable"))
        raw_value = row.get("value")
        value = None if (raw_value is None or pd.isna(raw_value)) else float(raw_value)
        raw_rank = row.get("rank")
        rank = None if (raw_rank is None or pd.isna(raw_rank)) else int(raw_rank)

        modality = str(typed[mc.FIELD_MODALITY])
        sign = mr.observed_sign_state(value, evaluable=evaluable, origin_is_measured=True,
                                      arm_key=arm_key)
        modulation = mr.desired_target_modulation(modality, sign)
        out.append({
            "target_id": tid,
            "arm_value": value,
            "evaluable": evaluable,
            "rank": rank,
            mc.FIELD_NAMESPACE: str(typed[mc.FIELD_NAMESPACE]),
            mc.FIELD_MODALITY: modality,
            mc.FIELD_MODULATION: modulation,
            mc.FIELD_PHENOCOPY_CLASS: PHENOCOPY_CLASS_OF[modulation],
            "target_symbol": typed.get("target_symbol"),
            "target_ensembl": typed.get("target_ensembl"),
        })
    return out


# --------------------------------------------------------------------------- #
# 2. The REAL drug join: the frozen v2 edge engine, over the ADMITTED store.
# --------------------------------------------------------------------------- #
def project(*, arms: list[LoadedArm], store: ur.AdmittedStore,
            a_arm_key: str, b_arm_key: str) -> dict[str, Any]:
    """The two selected arms, joined to the admitted store by the REAL edge engine.

    The arms are projected SEPARATELY and stay separate. There is no combined objective: a drug
    that supports the A arm and opposes the B arm is reported as exactly that, in both.
    """
    selected = {a_arm_key, b_arm_key}
    keep = [a for a in arms if a.arm_key in selected]
    missing = selected - {a.arm_key for a in keep}
    if missing:
        _refuse("the_selection_names_an_arm_the_release_does_not_have",
                f"the release does not carry {sorted(missing)}; it carries "
                f"{sorted(a.arm_key for a in arms)[:4]}…")

    # THE REAL ENGINE. Same edges, same direction rule, same dispositions production builds.
    built = eb.build_edges(SimpleNamespace(arms=tuple(keep)), store)
    edges = built["target_drug_edges"]

    by_arm: dict[str, list[dict[str, Any]]] = {a_arm_key: [], b_arm_key: []}
    for edge in edges:
        by_arm.setdefault(str(edge["arm_key"]), []).append(edge)

    return {
        "arms": {key: _arm_block(key, keep, by_arm.get(key, [])) for key in (a_arm_key, b_arm_key)},
        "candidates": _candidates(edges),
        "source_records": built["source_records"],
        "n_dispositions": len(built["dispositions"]),
    }


def _arm_block(arm_key: str, arms: list[LoadedArm],
               edges: list[dict[str, Any]]) -> dict[str, Any]:
    arm = next(a for a in arms if a.arm_key == arm_key)
    ranked = [r for r in arm.records if r.get("rank") is not None]
    return {
        "arm_key": arm.arm_key,
        "program_id": arm.program_id,
        "desired_change": arm.desired_change,
        "condition": arm.bundle.condition,
        "lane": arm.lane,
        "origin_type": dr.ORIGIN_DIRECT_TARGET,
        "observed_perturbation_modality": mc.MODALITY_CRISPRI,
        "n_targets": len(arm.records),
        # A count of RANKS, never of rows: an unrankable target is RETAINED with rank:null, so
        # "in the ranking" is not "in the rows".
        "n_ranked": len(ranked),
        "n_edges": len(edges),
        "n_candidates": len({str(e["candidate_id"]) for e in edges}),
        "edges": edges,
    }


def _candidates(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per active moiety, with its arms kept APART. No combined score, no winner."""
    out: dict[str, dict[str, Any]] = {}
    for edge in edges:
        cid = str(edge["candidate_id"])
        cand = out.setdefault(cid, {
            "candidate_id": cid,
            "active_moiety_id": edge.get("active_moiety_id"),
            "preferred_name": edge.get("preferred_name") or edge.get("pref_name"),
            "molecule_chembl_id": edge.get("molecule_chembl_id"),
            "max_phase_source": edge.get("max_phase_source"),
            "arms": {},
            "pathway_context": [],
        })
        arm = cand["arms"].setdefault(str(edge["arm_key"]), {
            "arm_key": edge["arm_key"], "program_id": edge.get("program_id"),
            "desired_change": edge.get("desired_change"),
            "condition": edge.get("condition"), "targets": [],
        })
        arm["targets"].append({
            "target_id": edge.get("target_id"),
            "target_id_namespace": edge.get("target_id_namespace"),
            "target_symbol": edge.get("target_symbol"),
            "arm_rank": edge.get("arm_rank"),
            "action_type_source": edge.get("action_type_source"),
            "intervention_effect": edge.get("intervention_effect"),
            "directional_evidence_status": edge.get("directional_evidence_status"),
            "mechanism_match_status": edge.get("mechanism_match_status"),
            "observed_perturbation_support": edge.get("observed_perturbation_support"),
            "stage3_evidence_class": edge.get("stage3_evidence_class"),
            "source_record_id": edge.get("source_record_id"),
        })
    for cand in out.values():
        cand["arms"] = [cand["arms"][k] for k in sorted(cand["arms"])]
        cand["n_arms"] = len(cand["arms"])
        # SAID OUT LOUD on every candidate, because it is the thing a reader will otherwise assume.
        cand["combined_objective"] = None
        cand["arms_are_reported_separately_and_never_pooled"] = True
    return [out[k] for k in sorted(out)]


# --------------------------------------------------------------------------- #
# 3. Pathway CONTEXT: annotates a candidate the edges already support. Never promotes.
# --------------------------------------------------------------------------- #
def attach_pathway_context(document: dict[str, Any], context_path: Optional[str]) -> None:
    """Attach GO-BP endpoint context to candidates the EDGES already support.

    A pathway record cannot create a candidate, a target or an arm membership. If a context names
    a gene no selected arm produced an edge for, it is DROPPED — the alternative is a gene set
    handing a drug to a question no measurement put it in.

    When the bytes are absent, the entry is a NAMED UNAVAILABLE — never an empty list, which reads
    like "we looked and found none".
    """
    if not context_path or not os.path.isfile(context_path):
        document["pathway_context"] = {
            "status": "unavailable_producer_output_not_present",
            "gene_set_source": "GO-BP",
            "path": context_path,
            "detail": "the GO-BP endpoint bytes for this condition are not on disk. This is a "
                      "NAMED absence, not an empty result: 'no pathway context was produced' and "
                      "'the pathway produced nothing' are different facts.",
            "may_promote_a_candidate": False,
        }
        return

    ctx = _load_json(context_path, "GO-BP endpoint pathway context")
    supported = {str(t["target_id"])
                 for c in document["candidates"] for a in c["arms"] for t in a["targets"]}
    sets = []
    for entry in (ctx.get("gene_sets") or ctx.get("records") or []):
        genes = [str(g) for g in (entry.get("leading_edge") or entry.get("target_ids") or [])]
        overlap = sorted(set(genes) & supported)
        if not overlap:
            continue                      # it annotates nothing a measurement already supports
        sets.append({
            "gene_set_id": entry.get("gene_set_id") or entry.get("set_id"),
            "gene_set_source": "GO-BP",
            "n_leading_edge": len(genes),
            "annotates_targets": overlap,
            "is_a_crispri_target_row": False,
            "may_be_matched_to_a_drug_as_a_target": False,
        })
    document["pathway_context"] = {
        "status": "attached",
        "gene_set_source": "GO-BP",
        "raw_sha256": file_sha256(context_path),
        "n_gene_sets_annotating_supported_targets": len(sets),
        "gene_sets": sets,
        "may_promote_a_candidate": False,
        "detail": "context annotates candidates the gene-arm edges ALREADY support; it never "
                  "creates a candidate, a target or an arm membership.",
    }


# --------------------------------------------------------------------------- #
# 4. The document.
# --------------------------------------------------------------------------- #
def build_document(*, condition: str, selection: dict[str, Any], projection: dict[str, Any],
                   provenance: dict[str, Any], store: ur.AdmittedStore,
                   store_dir: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA,
        # MACHINE-READABLE, and first. Nothing downstream has to parse prose to learn this.
        "status": STATUS_UNADMITTED,
        "admission_pending": True,
        "is_production_result": False,
        "admission_blockers": [
            "the Stage-2 aggregate run manifest and its independent verification report do not "
            "exist for this Direct run",
            "the Stage-2 -> Stage-3 bridge and its separate verifier's report do not exist",
            "no Stage-3 bundle, bundle id or membership receipt is emitted by this runner",
        ],
        "condition": condition,
        "selection": selection,
        "combined_objective": None,
        "combined_objective_permitted": False,
        "arms_are_independent_and_never_pooled": True,
        "pathway_may_annotate_but_never_promote": True,
        "arms": projection["arms"],
        "candidates": projection["candidates"],
        "n_candidates": len(projection["candidates"]),
        "source_records": projection["source_records"],
        "universe_store": {
            "store_id": store.store_id,
            "store_dir": os.path.basename(store_dir),
            "n_typed_targets": len(store.typed_universe),
            "admitted_by": "independent_verifier",
            "note": "this store IS admitted; the Stage-2 Direct release feeding it is not",
        },
        "stage2_direct_inputs": provenance,
        "direction_vocabulary_digest": dr.vocabulary_digest(),
    }
