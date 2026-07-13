"""ONE SELECTION, projected onto the ADMITTED all-arm stores. Two arms, kept apart.

WHAT IT DOES
------------
It takes ONE native Stage-1 v3 selection, derives its two arms from biology the gate has
already proved (never from the arm keys the contract declares — those are checked, not
trusted), and resolves each arm against the IMMUTABLE, INDEPENDENTLY ADMITTED store that owns
it. Then it emits a small artifact a UI can render.

THE STORES ARE READ-ONLY AND LANE-EXACT
---------------------------------------
    within_condition          the W10-ADMITTED Direct bundle for THAT condition
    temporal_cross_condition  a W11-ADMITTED temporal release, and NOTHING ELSE
    pathway annotations       W4-ADMITTED pathway bundles, or nothing at all

A temporal question may NEVER be answered out of the Direct store. The within-condition
estimator answers "how does this program's arm rank targets AT one time"; a temporal arm is a
DIFFERENCE BETWEEN TWO TIMES, estimated by a different method against a different population.
Borrowing one for the other would return numbers — plausible, well-formed, and about a
question nobody asked. It is refused by name.

The global all-arm stores are REUSABLE and are never mutated, never filtered in place, and
never re-ranked. This module reads them. A selection is a QUESTION asked of a release; it is
not an edit to it.

THE TWO ARMS STAY SEPARATE
--------------------------
There is no combined, balanced, weighted or overall score, and no joint rank. Each arm keeps
its own values and its own ranks, because a rank is a statement about a population and the two
arms rank different populations toward different ends. Any ordering a UI wants over the two
rank columns is a DISPLAY act: it is computed by ``display_order()`` at render time, it is
labelled, and it never enters this artifact. A number in the artifact is evidence; a number in
the UI is a convenience, and the two must not be confusable.

PARETO / JOINT_STATUS
---------------------
``pareto_tier`` / ``joint_status`` / ``joint_ordering_method_id`` are permitted by the DIRECT
CONTRACT — on ``screen.parquet``. The ADMITTED ALL-ARM BUNDLE does not ship that file
(``arm_artifacts.VERIFIED_PATHS``), and ``arms.parquet`` does not carry those columns. So they
are passed through VERBATIM when the native row has them and their ABSENCE IS DECLARED when it
does not. They are never synthesised here: a joint tier this module invented would be a
cross-arm ordering wearing a contract's name.
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from . import arm_keys as K
from . import lane_admission as LA
from . import stage1_v3 as S1
from .display_projection import CAP_OF

SCHEMA = "spot.stage02_selection_projection.v1"
METHOD_VERSION = "spot.stage02.selection_projection.v1"
ARTIFACT = "stage2_selection_projection.json"
RECEIPT = "stage2_selection_projection_receipt.json"

MODE_PRODUCTION = "production"
MODE_FIXTURE = "fixture"

# The lane that OWNS each analysis mode. Nothing else may answer it.
STORE_OF_MODE = {
    S1.MODE_WITHIN: "direct",
    S1.MODE_TEMPORAL: "temporal",
}

# Which independent admission clears each store.
ADMISSION_OF = {
    "direct": ("direct_admission_{condition}.json", "W10"),
    "temporal": ("temporal_arm_external_admission.json", "W11"),
    "pathway": ("pathway_arm_external_admission.json", "W4"),
}

# Passed through IF the native row has them. NEVER synthesised.
JOINT_FIELDS = ("pareto_tier", "joint_status", "joint_ordering_method_id")

# Nothing that is, or could be read as, a cross-arm result.
FORBIDDEN_KEYS = frozenset({
    # NOT `combined_objective`: that is the artifact's own DECLARATION that no such objective
    # exists, and it is checked separately for null. A denylist that refused the field which
    # says "there is no combined score" would refuse every honest artifact.
    "combined_score", "balanced_score", "weighted_score",
    "overall_score", "overall_rank", "joint_rank", "pair_rank", "headline_rank",
    "p_value", "q_value", "pval", "qval", "padj", "fdr", "significance",
})

# NAMED GATES.
G_LANE_MISSING = "the_store_this_analysis_mode_requires_is_not_in_the_release"
G_LANE_UNADMITTED = "the_store_is_present_but_no_independent_verifier_admitted_it"
G_LANE_MISMATCH = "the_store_does_not_cover_the_condition_this_selection_asks_about"
G_ESTIMATOR_BORROWED = "a_temporal_question_was_answered_out_of_the_within_condition_store"
G_ARM_NOT_IN_STORE = "a_derived_arm_key_resolves_to_no_arm_in_the_admitted_store"
G_FORBIDDEN = "a_forbidden_cross_arm_or_inferential_field_reached_the_artifact"
G_STAGE1_UNBOUND = "production_requires_the_stage1_identity_the_stores_must_have_been_built_on"


class SelectionProjectionError(ValueError):
    """This selection cannot be projected onto this release. Refuse; never approximate."""

    def __init__(self, gate: str, message: str):
        super().__init__(f"[{gate}] {message}")
        self.gate = gate


def _refuse(gate: str, message: str) -> None:
    raise SelectionProjectionError(gate, message)


def _raw(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _canon(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode()).hexdigest()


def _num(v: Any) -> Any:
    if v is None:
        return None
    if hasattr(v, "item"):
        try:
            v = v.item()
        except (AttributeError, ValueError):
            return v
    if isinstance(v, float) and v != v:       # NaN
        return None
    return v


# --------------------------------------------------------------------------- #
# THE STORES. Discovered by NATIVE SCHEMA, and cleared by an INDEPENDENT admission.
# --------------------------------------------------------------------------- #
def discover(bundles_root: str) -> dict[str, list]:
    """Every bundle in the release, by lane. The stores are read; they are never touched."""
    from . import bundle_normalize as BN

    out: dict[str, list] = {"direct": [], "temporal": [], "pathway": []}
    for base, dirs, files in os.walk(bundles_root):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        if "arm_bundle.json" not in files:
            continue
        try:
            with open(os.path.join(base, "arm_bundle.json")) as fh:
                doc = json.load(fh)
            norm = BN.normalize(doc)
        except (OSError, ValueError, BN.BundleShapeError):
            continue
        out[norm["lane"]].append({"dir": base, "norm": norm, "doc": doc})
    return out


def _admission(bundles_root: str, lane: str, *, bundle_dir: str, arm_key: str = "",
               condition: str = "", stage1: dict | None = None,
               mode: str) -> dict[str, Any]:
    """The lane's TYPED admission — a report that BINDS THESE BYTES, or a refusal.

    It used to accept any file at the expected name whose verdict said ADMIT, and store only
    that file's hash. `echo '{"verdict":"ADMIT"}' > direct_admission_Rest.json` beside an
    unadmitted store was accepted by the producer AND by the verifier. Production mode was
    self-attested. `lane_admission` now demands the real report, from the pinned verifier, with
    a full gate inventory, zero failures, recompute_mode=all, and a bound artifact that names
    the bundle ON DISK.
    """
    try:
        if lane == "direct":
            return LA.bind_direct(bundles_root, condition=condition, bundle_dir=bundle_dir,
                                  arm_key=arm_key, stage1=stage1 or {})
        return LA.bind_external(bundles_root, lane, bundle_dir=bundle_dir,
                                stage1=stage1 or {})
    except LA.AdmissionError as exc:
        if mode == MODE_PRODUCTION:
            _refuse(G_LANE_UNADMITTED, str(exc))
        # FIXTURE: the refusal is DECLARED, never papered over. Nothing claims admission.
        return {"admitted": False, "mode": MODE_FIXTURE, "owner": None, "report": None,
                "not_admitted_because": str(exc)}


# --------------------------------------------------------------------------- #
# THE ARMS, resolved against the store that OWNS this mode.
# --------------------------------------------------------------------------- #
def _direct_rows(bundle: dict, arm_key: str) -> list:
    import pandas as pd

    path = os.path.join(bundle["dir"], "arms.parquet")
    if not os.path.exists(path):
        _refuse(G_ARM_NOT_IN_STORE, f"{bundle['dir']}: no arms.parquet")
    df = pd.read_parquet(path)
    return [{k: _num(v) for k, v in rec.items()}
            for rec in df[df["arm_key"] == arm_key].to_dict("records")]


def _temporal_rows(bundle: dict, arm_key: str) -> list:
    rdir = os.path.join(bundle["dir"], "rankings")
    out: list = []
    for fname in sorted(os.listdir(rdir)) if os.path.isdir(rdir) else []:
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(rdir, fname)) as fh:
            doc = json.load(fh)
        if str(doc.get("arm_key")) != arm_key:
            continue
        out += (doc.get("records") if doc.get("records") is not None
                else (doc.get("ranked") or []))
    return out


def arm_view(rows: list, *, arm_key: str, lane: str, cap: int) -> dict[str, Any]:
    """ONE arm: its OWN values, its OWN ranks, its OWN counts. Never joined to the other."""
    if not rows:
        _refuse(G_ARM_NOT_IN_STORE,
                f"the derived arm key {arm_key!r} resolves to NO arm in the admitted "
                f"{lane} store. A selection that names an arm nobody computed cannot be "
                "answered, and answering it from a neighbouring arm would be worse")

    value_field = "value" if lane == "direct" else "arm_value"
    evaluable = [r for r in rows if bool(r.get("evaluable"))]
    ranked = sorted((r for r in evaluable if r.get("rank") is not None),
                    key=lambda r: int(r["rank"]))

    emitted = []
    for r in ranked[:cap]:
        row = {"target_id": str(r["target_id"]),
               "rank": int(r["rank"]),
               "value": _num(r.get(value_field))}
        # PASSED THROUGH IF PRESENT — never synthesised. See the module docstring.
        for f in JOINT_FIELDS:
            if f in r:
                row[f] = _num(r[f])
        emitted.append(row)

    dispositions: dict[str, int] = {}
    for r in rows:
        d = str(r.get("projection_status", r.get("temporal_status", "unknown")))
        dispositions[d] = dispositions.get(d, 0) + 1

    return {
        "arm_key": arm_key,
        "lane": lane,
        "n_rows_total": len(rows),
        "n_evaluable": len(evaluable),
        "n_ranked": len(ranked),
        "n_emitted": len(emitted),
        "cap": cap,
        "is_a_prefix": len(emitted) < len(ranked),
        "dispositions": dict(sorted(dispositions.items())),
        "joint_fields_present": sorted(f for f in JOINT_FIELDS if emitted and f in emitted[0]),
        "joint_fields_absent_because": (
            "the admitted all-arm bundle ships arms.parquet, which does not carry "
            "pareto_tier / joint_status; those live on screen.parquet, which "
            "arm_artifacts.VERIFIED_PATHS does not include. They are never synthesised here"),
        "rows": emitted,
    }


def _pathway_pointers(stores: dict, arm: dict, mode: str, bundles_root: str) -> list:
    """POINTERS to admitted pathway support. Never the pathway's numbers, and never a score."""
    out = []
    for b in stores["pathway"]:
        ctx = b["norm"]["context"]
        if str(ctx.get("condition")) != arm["condition"]:
            continue
        source = str(ctx.get("gene_set_source"))
        adm = _admission(bundles_root, "pathway", bundle_dir=b["dir"], mode=mode)
        if not adm["admitted"] and mode == MODE_PRODUCTION:
            continue
        out.append({
            "pathway_arm_key": "|".join((arm["pathway_arm_key_base"], source)),
            "gene_set_source": source,
            "bundle_id": b["norm"]["bundle_id"],
            "admitted": adm["admitted"],
            "admission_report": adm["report"],
        })
    return sorted(out, key=lambda p: p["pathway_arm_key"])


# --------------------------------------------------------------------------- #
# THE PROJECTION.
# --------------------------------------------------------------------------- #
# THE STAGE-1 IDENTITY, in full. `stage1_release_raw_sha256` is the field W4 ACTUALLY BINDS
# (verify_pathway_release: binds.stage1_release_raw_sha256), and it is SUPPLIED — never
# inferred from an optional field, because a field that is optional is a check that is optional.
STAGE1_IDENTITY_FIELDS = ("stage1_release_raw_sha256",
                          "stage1_scorer_view_canonical_sha256",
                          "registry_scorer_projection_sha256")


def project(*, selection_path: str, schema_path: str, bundles_root: str,
            mode: str = MODE_PRODUCTION, producer_commit: str = "",
            stage1: dict | None = None) -> dict[str, Any]:
    with open(selection_path) as fh:
        doc = json.load(fh)
    bound = S1.validate(doc, S1.load_schema(schema_path))   # arms DERIVED, never trusted

    analysis_mode = bound["analysis_mode"]
    store_lane = STORE_OF_MODE[analysis_mode]
    stores = discover(bundles_root)

    # THE ESTIMATOR MAY NOT BE BORROWED.
    if not stores[store_lane]:
        gate = (G_ESTIMATOR_BORROWED if analysis_mode == S1.MODE_TEMPORAL
                else G_LANE_MISSING)
        _refuse(gate,
                f"this selection is {analysis_mode!r}, which is answered ONLY by the "
                f"{store_lane} store, and this release ships none. A temporal question "
                "answered out of the within-condition store would return numbers about a "
                "question nobody asked")

    # THE STAGE-1 IDENTITY this projection is bound to. A W10 report that verified a bundle
    # built against a DIFFERENT Stage-1 release verified a different release.
    #
    # It is SUPPLIED, and in production it is REQUIRED. Deriving it from the selection would
    # have meant that a selection which happened not to carry it silently SKIPPED the check —
    # a fail-open my own attack found, and the quietest kind: the gate is there, it runs, and
    # it compares nothing.
    stage1 = dict(stage1 or {})
    if mode == MODE_PRODUCTION and not all(stage1.get(f) for f in STAGE1_IDENTITY_FIELDS):
        _refuse(G_STAGE1_UNBOUND,
                f"production requires {list(STAGE1_IDENTITY_FIELDS)}: the identity of the "
                "Stage-1 release the admitted stores were BUILT ON. Without it, a report that "
                "verified a bundle built against a stale Stage-1 would be accepted — it "
                "verified a different release")

    arms_out: dict[str, Any] = {}
    admissions: dict[str, Any] = {}
    inputs: dict[str, Any] = {}

    for role in K.ROLES:
        arm = bound["arms"][role]
        if analysis_mode == S1.MODE_WITHIN:
            cond = arm["condition"]
            bundle = next((b for b in stores["direct"]
                           if str(b["norm"]["context"].get("condition")) == cond), None)
            if bundle is None:
                _refuse(G_LANE_MISMATCH,
                        f"this selection asks about condition {cond!r}; the release ships no "
                        "Direct bundle for it")
            admissions["direct"] = _admission(
                bundles_root, "direct", condition=cond, bundle_dir=bundle["dir"],
                arm_key=arm["direct_arm_key"], stage1=stage1, mode=mode)
            rows = _direct_rows(bundle, arm["direct_arm_key"])
            key, lane = arm["direct_arm_key"], "direct"
        else:
            frm, to = bound["conditions"][0], bound["conditions"][-1]
            bundle = next((b for b in stores["temporal"]
                           if str(b["norm"]["context"].get("from_condition")) == frm
                           and str(b["norm"]["context"].get("to_condition")) == to), None)
            if bundle is None:
                _refuse(G_LANE_MISMATCH,
                        f"this selection asks about the ordered pair {frm!r} -> {to!r}; the "
                        "release ships no temporal bundle for it")
            admissions["temporal"] = _admission(
                bundles_root, "temporal", bundle_dir=bundle["dir"], stage1=stage1, mode=mode)
            rows = _temporal_rows(bundle, arm["temporal_arm_key"])
            key, lane = arm["temporal_arm_key"], "temporal"

        view = arm_view(rows, arm_key=key, lane=lane, cap=CAP_OF[lane])
        view.update({"role": role, "program_id": arm["program_id"],
                     "pole_direction": arm["pole_direction"],
                     "desired_change": arm["desired_change"],
                     "condition": arm["condition"],
                     "pathway_support": _pathway_pointers(stores, arm, mode, bundles_root)})
        arms_out[role] = view
        # RELATIVE paths only. A binding carrying this host's directory layout would be a
        # binding to a machine, not to a release.
        inputs[os.path.relpath(bundle["dir"], bundles_root).replace(os.sep, "/")] = {
            "bundle_id": bundle["norm"]["bundle_id"], "lane": lane,
            "condition": arm["condition"], "arm_key": key}

    art = {
        "schema_version": SCHEMA,
        "method_version": METHOD_VERSION,
        "mode": mode,
        # WHICH QUESTION, and WHICH CONTRACT ASKED IT. Both, always, never one for the other.
        "question_id": bound["question_id"],
        "selection_id": bound["selection_id"],
        "analysis_mode": analysis_mode,
        "endpoints": bound["endpoints"],
        "conditions": list(bound["conditions"]),
        "arms_rule_id": bound["arms_rule_id"],
        "arms_are_derived_not_declared": True,
        "store_lane": store_lane,
        # THE TWO ARMS, SEPARATE.
        "arms": arms_out,
        "combined_objective": None,
        "cross_arm_score_or_order": None,
        "joint_rank_emitted": False,
        "ui_ordering_is_display_only_and_not_in_this_artifact": True,
        "bindings": {
            "producer_commit": producer_commit,
            "selection": {"path": os.path.basename(selection_path),
                          "raw_sha256": _raw(selection_path)},
            "schema": {"raw_sha256": _raw(schema_path)},
            "stores": inputs,
            "stage1": stage1,
            "admissions": admissions,
        },
    }
    _forbid(art)
    art["projection_sha256"] = _canon(art)
    return art


def _forbid(obj: Any, where: str = "") -> None:
    """Nothing that is — or could be read as — a cross-arm result reaches the artifact."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in FORBIDDEN_KEYS:
                _refuse(G_FORBIDDEN,
                        f"{where}{k!r} may not appear in a selection projection. The two arms "
                        "rank different populations toward different ends; a number that "
                        "combined them would be a result nobody computed")
            _forbid(v, f"{where}{k}.")
    elif isinstance(obj, list):
        for v in obj:
            _forbid(v, where)


def display_order(artifact: dict, *, by: str = "away_from_A") -> list:
    """A DISPLAY-ONLY ordering over the two rank columns. It is NOT in the artifact.

    The UI may want one list. The science does not have one: a rank is a statement about a
    population, and the two arms rank different populations. So this is computed at RENDER
    time, from the two rank columns that ARE evidence, and it is never written into the
    scientific bytes — where a reader could mistake it for a result.
    """
    rows = {r["target_id"]: r["rank"] for r in artifact["arms"][by]["rows"]}
    return [t for t, _ in sorted(rows.items(), key=lambda kv: kv[1])]


def receipt(artifact: dict, *, verifier_report: dict | None = None) -> dict[str, Any]:
    doc = {
        "schema_version": "spot.stage02_selection_projection_receipt.v1",
        "question_id": artifact["question_id"],
        "selection_id": artifact["selection_id"],
        "analysis_mode": artifact["analysis_mode"],
        "mode": artifact["mode"],
        "projection_sha256": artifact["projection_sha256"],
        "bindings": artifact["bindings"],
        "verifier_report": verifier_report,
        "verdict": "pending_independent_verification",
        "admitted": False,
        "self_admitted": False,
    }
    doc["receipt_sha256"] = _canon(doc)
    return doc


def main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(
        description="Project ONE native Stage-1 v3 selection onto the ADMITTED all-arm "
                    "stores. Derives its two arms from biology, resolves them against the "
                    "store that OWNS its analysis mode, and keeps the arms separate. Emits no "
                    "combined, balanced, weighted or overall score.")
    ap.add_argument("--selection", required=True)
    ap.add_argument("--schema", required=True)
    ap.add_argument("--bundles-root", required=True)
    ap.add_argument("--out-root", required=True)
    ap.add_argument("--mode", choices=(MODE_PRODUCTION, MODE_FIXTURE),
                    default=MODE_PRODUCTION,
                    help="production REQUIRES an independent admission for every store it "
                         "reads. fixture is for tests only and says so in the artifact.")
    ap.add_argument("--producer-commit", default="")
    ap.add_argument("--stage1-scorer-view-sha256", default="",
                    help="REQUIRED in production: the Stage-1 scorer-view identity the "
                         "admitted stores were built on")
    ap.add_argument("--stage1-scorer-projection-sha256", default="",
                    help="REQUIRED in production")
    ap.add_argument("--stage1-release-raw-sha256", default="",
                    help="REQUIRED in production: the RAW sha256 of the Stage-1 v3 release. "
                         "This is the field W4's pathway admission actually binds.")
    args = ap.parse_args(argv)

    try:
        art = project(selection_path=args.selection, schema_path=args.schema,
                      bundles_root=args.bundles_root, mode=args.mode,
                      producer_commit=args.producer_commit,
                      stage1={"stage1_release_raw_sha256": args.stage1_release_raw_sha256,
                              "stage1_scorer_view_canonical_sha256":
                              args.stage1_scorer_view_sha256,
                              "registry_scorer_projection_sha256":
                              args.stage1_scorer_projection_sha256})
    except (SelectionProjectionError, S1.SelectionV3Error) as exc:
        print(json.dumps({"projected": False, "error": str(exc),
                          "gate": getattr(exc, "gate", getattr(exc, "reason", None))},
                         indent=2))
        return 1

    os.makedirs(args.out_root, exist_ok=True)
    with open(os.path.join(args.out_root, ARTIFACT), "w") as fh:
        json.dump(art, fh, indent=2, sort_keys=True, allow_nan=False)
    with open(os.path.join(args.out_root, RECEIPT), "w") as fh:
        json.dump(receipt(art), fh, indent=2, sort_keys=True, allow_nan=False)

    print(json.dumps({"projected": True, "question_id": art["question_id"],
                      "selection_id": art["selection_id"],
                      "analysis_mode": art["analysis_mode"],
                      "store_lane": art["store_lane"],
                      "arm_keys": {r: a["arm_key"] for r, a in art["arms"].items()},
                      "projection_sha256": art["projection_sha256"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
