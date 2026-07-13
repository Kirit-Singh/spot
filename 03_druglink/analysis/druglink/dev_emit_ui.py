"""DEV PREVIEW emitter: real Stage-2 Direct arms + the admitted public universe -> UI JSON.

REAL DATA ONLY. No fixtures, no invented values. Every number here comes from a Stage-2 arms.parquet
or from the admitted ChEMBL/UniProt store, and every source is named with its exact path and hash.

The aggregate-receipt ceremony is BYPASSED for this preview, deliberately and visibly:
`admission.receipt_verified = false`. That is recorded in the artifact, not hidden in a comment —
a consumer can see exactly what was and was not checked.

DIRECTION. Stage-2 gives a signed `value` oriented to the arm's own `desired_change`. The sign, not
the modality, decides what a drug must do:

    value > +eps  the knockdown moved the program the DESIRED way
                  -> INHIBITING the target is observed-compatible; an inhibitor is supported
    value < -eps  the knockdown moved it the WRONG way
                  -> an INHIBITOR IS OPPOSED. An agonist is an UNTESTED INVERSE HYPOTHESIS:
                     CRISPRi never tested activation, so it is never "supported".
    |value| <= eps  no directional response
    not evaluable   not evaluated

A drug inhibiting a PROTEIN is not CRISPRi silencing a TRANSCRIPT. Every edge says so
(`evidence_relation`), and nothing here claims equivalence.
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any

import pandas as pd

from . import modality_rule as mr
from . import universe_rows as ur

SCHEMA = "spot.stage03_ui_drugs.v1"
SIGN_EPS = 1e-9                      # Stage-2 Direct config.py:186 — bound, not invented

# THE SIGN TOKENS AND THE MODALITY RULE ARE THE FROZEN ENGINE'S. No local copies.
SUPPORTED = mr.SIGN_SUPPORTS_DESIRED_CHANGE
OPPOSED = mr.SIGN_OPPOSES_DESIRED_CHANGE
NO_DIRECTION = mr.SIGN_NO_DIRECTIONAL_RESPONSE
NOT_EVALUABLE = mr.SIGN_NOT_EVALUABLE
MODALITY = mr.MODALITY_CRISPRI            # "CRISPRi_knockdown"


def _sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sign_state(value: Any, evaluable: Any) -> str:
    """The observed sign, oriented to the arm's own desired_change. SIGN_EPS is Stage-2's."""
    if not bool(evaluable) or value is None or pd.isna(value):
        return NOT_EVALUABLE
    if float(value) > SIGN_EPS:
        return SUPPORTED
    if float(value) < -SIGN_EPS:
        return OPPOSED
    return NO_DIRECTION


def compatibility(value: Any, evaluable: Any, action: str | None) -> dict[str, Any]:
    """THE FROZEN MODALITY RULE decides. Nothing here is hardcoded.

    I had stamped `evidence_relation: "putative_crispri_phenocopy"` on EVERY drug row. An AGONIST
    cannot be a CRISPRi phenocopy — it phenocopies nothing that was tested. The row was correctly
    `opposed` and simultaneously claimed to phenocopy the knockdown, which is a contradiction a
    reader would have to catch by hand.

    `modality_rule.classify` decides both, together, and the invariant it guarantees is the one
    that matters: `evidence_relation` is a phenocopy IFF `mechanism_phenocopies_modality` is true.
    """
    return mr.classify(action_type=action, modality=MODALITY,
                       sign_state=sign_state(value, evaluable),
                       origin_is_measured=True)


def _arm(df: pd.DataFrame, program: str, change: str, condition: str) -> pd.DataFrame:
    return df[(df.program_id == program) & (df.desired_change == change)
              & (df.condition == condition)].copy()


def load_identity(path: str) -> dict[str, dict[str, Any]]:
    """The REAL per-target identity Stage-2 emitted: symbol, namespace, modality. Not inferred."""
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    return {str(r["target_id"]): r for r in (doc.get("records") or [])}


def build(*, arms_parquet: str, identity_json: str, condition: str, store_dir: str,
          pathway_bundle: str | None, a_program: str, b_program: str,
          top_n: int = 200) -> dict[str, Any]:
    df = pd.read_parquet(arms_parquet)
    store = ur.load_store(store_dir)
    identity = load_identity(identity_json)

    # every typed identity the admitted store knows, and its drug assertions
    typed = {(r["target_id"], r["target_id_namespace"]) for r in store.typed_universe}
    ns_of = {r["target_id"]: r["target_id_namespace"] for r in store.typed_universe}
    # the store's public-source binding, taken from the store's own edges (it lives on the edge)
    probe = ur.rankable_edges(ur.drug_edges_for_targets(store, sorted(typed)[:400]))
    binding = probe[0]["release_binding"] if probe else {}

    arms: list[dict[str, Any]] = []
    for role, program, change in (("away_from_A", a_program, "decrease"),
                                  ("toward_B", b_program, "increase")):
        sub = _arm(df, program, change, condition)
        ev = sub[sub.evaluable & sub["value"].notna()]
        # RANK IS STAGE-2'S. We take the arm's own ordering; we do not invent one.
        ev = ev.sort_values("rank", na_position="last").head(top_n)

        targets = []
        for _, row in ev.iterrows():
            tid = str(row.target_id)
            ident = identity.get(tid) or {}
            # IDENTITY IS STAGE-2'S, not a lookup guess. Namespace and symbol come from the
            # target_identity.json it emitted; absent means UNKNOWN and is stated as such.
            ns = ident.get("target_id_namespace") or ns_of.get(tid)
            state = sign_state(row["value"], row.evaluable)
            drugs: list[dict[str, Any]] = []
            if ns and (tid, ns) in typed:
                for e in ur.rankable_edges(ur.drug_edges_for_targets(store, [(tid, ns)])):
                    action = e.get("action_type_source")
                    drugs.append({
                        "molecule_chembl_id": e.get("molecule_chembl_id"),
                        "pref_name": e.get("pref_name"),
                        "action_type_source": action,
                        "mechanism_of_action": e.get("mechanism_of_action"),
                        "max_phase_source": e.get("max_phase_source"),
                        "source_locator": f"chembl:{e['release_binding']['chembl_release']}"
                                          f":drug_mechanism/{e.get('source_row_id')}",
                        "source_release": e["release_binding"]["chembl_release"],
                        **compatibility(row["value"], row.evaluable, action),
                    })
            targets.append({
                "target_id": tid,
                "target_symbol": ident.get("target_symbol"),          # REAL, from Stage-2
                "target_id_namespace": ns,                            # None => UNKNOWN, stated
                "observed_perturbation_modality": ident.get("observed_perturbation_modality"),
                "in_admitted_universe": bool(ns and (tid, ns) in typed),
                "arm_value": None if pd.isna(row["value"]) else float(row["value"]),
                "arm_rank": None if pd.isna(row["rank"]) else int(row["rank"]),
                "evaluable": bool(row.evaluable),
                "observed_sign_state": state,
                "n_drugs": len(drugs),
                "drugs": drugs,
            })

        arms.append({
            "role": role, "arm_key": str(sub.arm_key.iloc[0]) if len(sub) else None,
            "program_id": program, "desired_change": change, "condition": condition,
            "n_rows": int(len(sub)), "n_evaluable": int(len(sub[sub.evaluable])),
            "n_shown": len(targets), "targets": targets,
        })

    # PATHWAY CONTEXT: honest, or empty. `pb["arms"]` are ARM SUMMARIES, not gene sets — reading
    # them as sets yields rows whose `set_id` is null, i.e. context that names nothing. Empty is
    # better than false context: a null set_id in the UI is a claim that a pathway was consulted
    # when none was.
    pathway_ctx: list[dict[str, Any]] = []
    pathway_note = "not_parsed_no_gene_sets_read"
    if pathway_bundle and os.path.exists(pathway_bundle):
        with open(pathway_bundle, encoding="utf-8") as fh:
            pb = json.load(fh)
        sets = pb.get("sets") or pb.get("gene_sets") or []
        for gs in sets[:50]:
            sid = gs.get("set_id") or gs.get("gene_set_id")
            if not sid:
                continue                     # no id -> no context. Never a null-id row.
            pathway_ctx.append({
                "set_id": sid,
                "source": gs.get("source") or "GO-BP",
                "n_leading_edge": len(gs.get("leading_edge") or []),
                "is_a_crispri_target_row": False,
                "may_be_matched_to_a_drug_as_a_target": False,
            })
        pathway_note = ("parsed" if pathway_ctx else
                        "the bundle carries arm summaries, not gene sets: no context emitted")

    doc: dict[str, Any] = {
        "schema_version": SCHEMA,
        "condition": condition,
        "analysis_mode": "within_condition",
        "question": f"{a_program} decrease -> {b_program} increase @ {condition}",
        "arms": arms,
        "pathway_contexts": pathway_ctx,
        "pathway_context_status": pathway_note,
        # DISPLAY TRUNCATION, not scientific filtering. The arm's full evaluable set is `n_evaluable`;
        # `n_shown` is the top `top_n` BY STAGE-2'S OWN RANK. Nothing was excluded on scientific
        # grounds, and the counts say so.
        "display": {"top_n": top_n,
                    "truncation_is_display_only_not_scientific_filtering": True,
                    "ordering": "stage2_arm_rank_ascending"},
        # NO ABSOLUTE PATHS. A served document names artifacts by ROLE and HASH; a filesystem path
        # is a fact about one machine, and it leaks the box's layout to every consumer.
        "sources": {
            "stage2_direct_arms": {"artifact": "arms.parquet",
                                   "sha256": _sha(arms_parquet)},
            "stage2_target_identity": {"artifact": "target_identity.json",
                                       "sha256": _sha(identity_json)},
            "stage2_pathway_bundle": (
                {"artifact": "arm_bundle.json", "sha256": _sha(pathway_bundle)}
                if pathway_bundle and os.path.exists(pathway_bundle) else None),
            "universe_store": {
                "store_id": store.store_id,
                "typed_universe_sha256": store.typed_universe_sha256,
                "chembl_release": binding.get("chembl_release"),
                "uniprot_release": binding.get("uniprot_release"),
                "chembl_license": binding.get("chembl_license"),
                "chembl_attribution": binding.get("chembl_required_attribution"),
            },
        },
        "direction_rule": {
            "sign_eps": SIGN_EPS,
            "rule": "value>+eps: inhibition observed-compatible; value<-eps: inhibitor OPPOSED and "
                    "activation is an UNTESTED inverse hypothesis (CRISPRi never tested it); "
                    "|value|<=eps: no directional response",
            "modality": "CRISPRi_knockdown",
            "claim_is_equivalence": False,
        },
        "admission": {
            "receipt_verified": False,
            "note": "dev preview: the Stage-2 aggregate receipt chain was not verified for this "
                    "artifact. Source paths and hashes are recorded above.",
        },
    }
    doc["content_sha256"] = hashlib.sha256(
        json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return doc


def sidecar(*, doc: dict[str, Any], arms_parquet: str, identity_json: str,
            store_dir: str, pathway_bundle: str | None) -> dict[str, Any]:
    """INTERNAL handoff only. Exact filesystem paths live here, never in the served document."""
    return {
        "schema_version": "spot.stage03_ui_drugs.sidecar.v1",
        "serves": {"content_sha256": doc["content_sha256"], "condition": doc["condition"]},
        "resolved_paths": {
            "stage2_direct_arms": os.path.abspath(arms_parquet),
            "stage2_target_identity": os.path.abspath(identity_json),
            "stage2_pathway_bundle": (os.path.abspath(pathway_bundle)
                                      if pathway_bundle else None),
            "universe_store": os.path.abspath(store_dir),
        },
    }


def write(doc: dict[str, Any], path: str) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1, sort_keys=True)
    return path
