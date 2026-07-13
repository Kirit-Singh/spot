"""THE INDEPENDENT CHECK ON A SELECTION PROJECTION. It re-derives the arms and rebuilds the rows.

It does not ask whether the artifact agrees with itself — a forgery can be made to agree with
itself. It reopens the SELECTION, re-derives the two arm keys from the biology, reopens the
ADMITTED STORES, and rebuilds every served row. Then it proves:

  * the arm keys are the ones the BIOLOGY implies — not the ones the contract declared;
  * each arm's rows ARE the native rows at those ranks, in the store that OWNS this mode;
  * a temporal question was NOT answered out of the Direct store;
  * every store it read was independently ADMITTED (in production);
  * the selection_id and question_id are the ones the selection actually carries;
  * NO combined, balanced, weighted, overall or joint score/rank exists anywhere;
  * NO p/q/FDR reaches the artifact;
  * no column appears that the native store does not have.

It restates the contract rather than importing the producer: a verifier that imports the thing
it checks agrees with it by construction.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SCHEMA = "spot.stage02_selection_projection.v1"
MODE_PRODUCTION = "production"

ROLES = ("away_from_A", "toward_B")
STORE_OF_MODE = {"within_condition": "direct", "temporal_cross_condition": "temporal"}

# RE-STATED. The frozen role x pole mapping: the arm is keyed on the CHANGE, never the pole.
CHANGE_OF = {("away_from_A", "high"): "decrease", ("away_from_A", "low"): "increase",
             ("toward_B", "high"): "increase", ("toward_B", "low"): "decrease"}

CAP_OF = {"direct": 100, "temporal": 100}

# EXACTLY the columns a served row may carry.
ROW_ALLOWED = frozenset({"target_id", "rank", "value",
                         "pareto_tier", "joint_status", "joint_ordering_method_id"})

FORBIDDEN = frozenset({
    # NOT `combined_objective`: that is the artifact's own DECLARATION that no such objective
    # exists, and it is checked separately for null. A denylist that refused the field which
    # says "there is no combined score" would refuse every honest artifact.
    "combined_score", "balanced_score", "weighted_score",
    "overall_score", "overall_rank", "joint_rank", "pair_rank", "headline_rank",
    "p_value", "q_value", "pval", "qval", "padj", "fdr", "significance",
})

G_SELF_HASH = "the_projection_hashes_to_what_it_says_it_does"
G_ARM_KEY = "the_arm_keys_are_the_ones_the_BIOLOGY_implies"
G_IDS = "the_question_id_and_selection_id_are_the_selections_own"
G_STORE = "the_store_that_ANSWERED_is_the_store_that_OWNS_this_analysis_mode"
G_UNADMITTED = "every_store_this_projection_read_was_independently_admitted"
G_ROW_IS_NATIVE = "each_served_row_IS_the_native_row_at_that_rank_in_the_admitted_store"
G_COUNTS = "the_counts_describe_the_WHOLE_arm_not_the_prefix"
G_UNKNOWN_COLUMN = "a_served_row_carries_a_column_the_native_store_does_not_have"
G_FORBIDDEN = "a_combined_ordering_or_an_inferential_statistic_reached_the_artifact"


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
    if isinstance(v, float) and v != v:
        return None
    return v


def _derive_arm_keys(sel: dict) -> dict:
    """The two arm keys, from the SELECTION'S BIOLOGY. Never from its declared `arms`."""
    c = sel.get("canonical_content") or sel
    mode = str(sel.get("analysis_mode") or c.get("analysis_mode"))
    conds = [str(x) for x in (sel.get("conditions") or c.get("conditions") or [])]
    poles = sel["poles"]
    frm, to = conds[0], conds[-1]
    cond_of = {"away_from_A": frm, "toward_B": to} if mode == "temporal_cross_condition" \
        else {"away_from_A": conds[0], "toward_B": conds[0]}

    out = {}
    for role, p in zip(ROLES, ("A", "B")):
        pole = poles[p]
        program = str(pole["program_id"])
        direction = str(pole.get("pole_direction", pole.get("direction")))
        change = CHANGE_OF[(role, direction)]
        cond = cond_of[role]
        out[role] = ("|".join(("temporal", program, change, frm, to))
                     if mode == "temporal_cross_condition"
                     else "|".join(("direct", program, change, cond)))
    return out


def _native_rows(store_dir: str, lane: str, arm_key: str) -> list:
    if lane == "direct":
        import pandas as pd
        path = os.path.join(store_dir, "arms.parquet")
        if not os.path.exists(path):
            return []
        df = pd.read_parquet(path)
        return [{"target_id": str(r["target_id"]), "rank": _num(r.get("rank")),
                 "value": _num(r.get("value")), "evaluable": bool(r.get("evaluable"))}
                for r in df[df["arm_key"] == arm_key].to_dict("records")]

    rdir, out = os.path.join(store_dir, "rankings"), []
    for fname in sorted(os.listdir(rdir)) if os.path.isdir(rdir) else []:
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(rdir, fname)) as fh:
            doc = json.load(fh)
        if str(doc.get("arm_key")) != arm_key:
            continue
        for r in (doc.get("records") or doc.get("ranked") or []):
            out.append({"target_id": str(r.get("target_id")), "rank": _num(r.get("rank")),
                        "value": _num(r.get("arm_value")),
                        "evaluable": bool(r.get("evaluable"))})
    return out


def verify(artifact_path: str, *, selection_path: str, bundles_root: str) -> dict[str, Any]:
    failures: list[str] = []
    with open(artifact_path) as fh:
        art = json.load(fh)
    with open(selection_path) as fh:
        sel = json.load(fh)

    if art.get("schema_version") != SCHEMA:
        failures.append(f"{G_SELF_HASH}: schema {art.get('schema_version')!r}")
    claimed = art.get("projection_sha256")
    derived = _canon({k: v for k, v in art.items() if k != "projection_sha256"})
    if claimed != derived:
        failures.append(f"{G_SELF_HASH}: says {str(claimed)[:16]}; hashes to {derived[:16]}")

    # (1) THE IDS ARE THE SELECTION'S OWN.
    for field in ("question_id", "selection_id"):
        if art.get(field) != sel.get(field):
            failures.append(
                f"{G_IDS}: the artifact carries {field}={art.get(field)!r}; the selection it "
                f"names carries {sel.get(field)!r}. An artifact keyed to another question "
                "would be filed under a question nobody asked of it")

    mode = str(art.get("analysis_mode"))
    if mode != str(sel.get("analysis_mode")):
        failures.append(f"{G_IDS}: analysis_mode {mode!r} is not the selection's")

    # (2) THE STORE THAT ANSWERED OWNS THIS MODE. A temporal question answered out of the
    # within-condition store returns numbers about a question nobody asked.
    want_lane = STORE_OF_MODE.get(mode)
    if art.get("store_lane") != want_lane:
        failures.append(
            f"{G_STORE}: a {mode!r} selection was answered out of the "
            f"{art.get('store_lane')!r} store; only the {want_lane!r} store may answer it")

    # (3) THE ARM KEYS COME FROM THE BIOLOGY.
    try:
        want_keys = _derive_arm_keys(sel)
    except (KeyError, IndexError):
        want_keys = {}
        failures.append(f"{G_ARM_KEY}: the selection's biology cannot be read")

    for role in ROLES:
        arm = (art.get("arms") or {}).get(role)
        if arm is None:
            failures.append(f"{G_ARM_KEY}: the artifact carries no {role!r} arm")
            continue
        if want_keys and arm.get("arm_key") != want_keys[role]:
            failures.append(
                f"{G_ARM_KEY}: {role}: the artifact resolved {arm.get('arm_key')!r}; the "
                f"biology this selection names derives {want_keys[role]!r}")
            continue
        failures += _check_arm(art, role, arm, bundles_root, mode)

    # (4) EVERY STORE ADMITTED — AND THE ADMISSION RE-DERIVED FROM THE ORIGINAL REPORT.
    #
    # The producer's admission index is an INDEX. It is not evidence. The old check only
    # confirmed that the file the producer hashed still hashed to that value — so
    # `echo '{"verdict":"ADMIT"}' > direct_admission_Rest.json` was accepted by BOTH sides and
    # production mode was self-attested. Every edge of the index is now rebuilt HERE, from the
    # original report and the store bytes, by the same typed contract the producer used and
    # WITHOUT reading the producer's answer.
    if art.get("mode") == MODE_PRODUCTION:
        failures += _reverify_admissions(art, bundles_root, mode)

    # (5) NOTHING COMBINED, NOTHING INFERENTIAL — anywhere.
    failures += _forbidden(art)
    if art.get("combined_objective") is not None \
            or art.get("cross_arm_score_or_order") is not None \
            or art.get("joint_rank_emitted") is not False:
        failures.append(f"{G_FORBIDDEN}: the artifact declares a cross-arm result")

    return {
        "verifier_id": "spot.stage02.selection_projection.independent_verifier.v1",
        "generator_is_not_verifier": True,
        "rebuilt_from_admitted_stores": True,
        "question_id": art.get("question_id"),
        "selection_id": art.get("selection_id"),
        "n_failed": len(failures),
        "failures": failures[:50],
        "verdict": "admit" if not failures else "reject",
    }


def _check_arm(art: dict, role: str, arm: dict, bundles_root: str, mode: str) -> list:
    bad: list[str] = []
    lane = STORE_OF_MODE[mode]

    store_dir = None
    for rel, s in ((art.get("bindings") or {}).get("stores") or {}).items():
        if s.get("lane") == lane:
            cand = os.path.join(bundles_root, rel)
            if _native_rows(cand, lane, arm["arm_key"]):
                store_dir = cand
                break
    if store_dir is None:
        return [f"{G_ROW_IS_NATIVE}: {role}: no bound {lane} store holds {arm['arm_key']!r}"]

    native = _native_rows(store_dir, lane, arm["arm_key"])
    evaluable = [r for r in native if r["evaluable"]]
    ranked = sorted((r for r in evaluable if r["rank"] is not None),
                    key=lambda r: int(r["rank"]))
    want = ranked[:CAP_OF[lane]]

    for field, value in (("n_rows_total", len(native)), ("n_evaluable", len(evaluable)),
                         ("n_ranked", len(ranked)), ("n_emitted", len(want))):
        if arm.get(field) != value:
            bad.append(f"{G_COUNTS}: {role}: {field}={arm.get(field)!r}; the admitted store "
                       f"says {value!r}")

    rows = arm.get("rows") or []
    if [r.get("rank") for r in rows] != [r["rank"] for r in want]:
        bad.append(f"{G_ROW_IS_NATIVE}: {role}: the served rows are not the first "
                   f"{CAP_OF[lane]} in native rank order")

    shown = 0
    for i, (got, exp) in enumerate(zip(rows, want)):
        extra = sorted(set(got) - ROW_ALLOWED)
        if extra:
            bad.append(f"{G_UNKNOWN_COLUMN}: {role}[{i}]: carries {extra}, which the native "
                       "store does not have")
        if shown >= 3:
            continue
        if got.get("target_id") != exp["target_id"] or got.get("rank") != exp["rank"] \
                or got.get("value") != exp["value"]:
            bad.append(f"{G_ROW_IS_NATIVE}: {role}[{i}]: served "
                       f"{got.get('target_id')!r}/rank {got.get('rank')!r}/value "
                       f"{got.get('value')!r}; natively it is {exp['target_id']!r}/"
                       f"{exp['rank']!r}/{exp['value']!r}")
            shown += 1
    return bad


def _reverify_admissions(art: dict, bundles_root: str, mode: str) -> list:
    """Rebuild every admission from the ORIGINAL report + the store bytes. Index-free."""
    # THE VERIFIER'S OWN RESTATEMENT. It must NOT import `direct.lane_admission`: calling the
    # producer's admission implementation to "re-derive" the admission is not a second opinion,
    # it is the same opinion twice — any bug in it would be reproduced exactly by the thing
    # meant to catch it, and the two could never disagree.
    import verify_admission_rules as LA

    bad: list[str] = []
    lane = STORE_OF_MODE[mode]
    stores = (art.get("bindings") or {}).get("stores") or {}
    stage1 = (art.get("bindings") or {}).get("stage1") or {}

    for rel, s in stores.items():
        if s.get("lane") != lane:
            continue
        bundle_dir = os.path.join(bundles_root, rel)
        try:
            if lane == "direct":
                LA.check_direct(bundles_root, condition=str(s.get("condition")),
                                bundle_dir=bundle_dir, arm_key=str(s.get("arm_key")),
                                stage1=stage1)
            else:
                LA.check_external(bundles_root, lane, bundle_dir=bundle_dir, stage1=stage1)
        except LA.AdmissionError as exc:
            bad.append(f"{G_UNADMITTED}: {rel}: {exc}")
        except (OSError, ValueError, KeyError) as exc:
            bad.append(f"{G_UNADMITTED}: {rel}: the admission could not be re-derived: {exc}")

    if not bad and not stores:
        bad.append(f"{G_UNADMITTED}: this projection names no store it read")
    return bad


def _forbidden(obj: Any, where: str = "") -> list:
    bad: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in FORBIDDEN:
                bad.append(f"{G_FORBIDDEN}: {where}{k!r} — the two arms rank different "
                           "populations toward different ends; a number combining them would "
                           "be a result nobody computed")
            bad += _forbidden(v, f"{where}{k}.")
    elif isinstance(obj, list):
        for v in obj:
            bad += _forbidden(v, where)
    return bad


def main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(
        description="Re-derive the arms from the SELECTION and rebuild every row from the "
                    "ADMITTED stores. Trusts nothing the artifact says about itself.")
    ap.add_argument("--projection", required=True)
    ap.add_argument("--selection", required=True)
    ap.add_argument("--bundles-root", required=True)
    ap.add_argument("--report", required=True)
    args = ap.parse_args(argv)

    rep = verify(args.projection, selection_path=args.selection,
                 bundles_root=args.bundles_root)
    with open(args.report, "w") as fh:
        json.dump(rep, fh, indent=2, sort_keys=True)
    print(json.dumps({k: v for k, v in rep.items() if k != "failures"}, indent=2))
    for f in rep["failures"][:10]:
        print(f"  - {f}")
    return 0 if rep["verdict"] == "admit" else 1


if __name__ == "__main__":
    raise SystemExit(main())
