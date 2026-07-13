"""THE COMPACT DISPLAY PROJECTION: what a browser gets. Selection-independent, capped, proven.

WHAT THIS IS NOT
----------------
It is NOT the release. The admitted native artifacts — ``arms.parquet``, the temporal
rankings, the pathway records — remain the AUTHORITATIVE, downloadable bytes, and nothing
here replaces them. This is a VIEW: a small, deterministic, verifiable prefix of them.

WHY IT EXISTS
-------------
Serializing ~680k Direct rows plus every temporal and pathway row into served JSON is not a
performance problem to be tuned, it is a different artifact pretending to be a page. So the
view is CAPPED — and the cap is frozen in this module, at a value CHOSEN BEFORE ANY VALUE WAS
INSPECTED, because a cap picked after looking at the numbers is a result, not a policy.

    Direct / temporal   the first 100 NATIVE-RANKED, EVALUABLE target rows of EACH arm
    pathway             the first  50 gene-set rows of EACH arm, in the PRODUCER'S OWN
                        emission order, plus coverage/disposition counts over ALL sets

THE CAP IS METHOD-VERSIONED, NOT A UI KNOB. Changing it changes ``METHOD_VERSION`` and
therefore changes every projection's identity. A UI that could raise the cap could quietly
change what a reader believes the evidence is.

PATHWAY HAS NO NATIVE GENE-SET RANKING — and this module will not invent one
---------------------------------------------------------------------------
The native pathway record carries ``peak_rank`` (where the enrichment peak sat in the TARGET
ranking) and an ``enrichment_value``. It carries NO rank of gene sets against each other:
``pathway_arms`` emits them sorted by ``set_id``. Sorting them by ``enrichment_value`` here
would be THIS MODULE inventing the headline ranking — exactly the derived ordering the whole
design forbids. So the pathway prefix is the producer's own emission ORDER, it is labelled as
an order and not a ranking, and the coverage/disposition counts are computed over EVERY set in
the arm, not merely the ones that fit in the prefix. (Flagged to W12: if a native gene-set
rank is wanted, the PRODUCER must emit it.)

NO CROSS-ARM ORDER, EVER
------------------------
Every arm is projected on its own, and no field here can be sorted as if it were a combined
score. There is no pair, no balanced rank, no headline arm.

WHAT A VERIFIER CAN PROVE FROM THIS
-----------------------------------
Each emitted row carries its NATIVE rank, its NATIVE effect and its NATIVE ids, verbatim, and
the projection binds the raw + canonical hash of every artifact it read. So an independent
verifier can reopen those bytes and prove that the row emitted at rank *r* IS the native row
at rank *r* — not a row that merely looks plausible at that position.
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any

# --------------------------------------------------------------------------- #
# THE FROZEN CAP POLICY. Method-versioned. Never settable from a UI.
# --------------------------------------------------------------------------- #
# v2: target_symbol added to every target row (DISPLAY METADATA). No value, rank,
# cap or population changed — the science in v1 and v2 is byte-identical.
METHOD_VERSION = "spot.stage02.display_projection.v2"
CAP_POLICY_ID = "spot.stage02.display_projection.first_n_native_order.v1"

CAP_OF = {"direct": 100, "temporal": 100, "pathway": 50}

CAP_POLICY = {
    "cap_policy_id": CAP_POLICY_ID,
    "method_version": METHOD_VERSION,
    "caps": dict(CAP_OF),
    "chosen_before_inspecting_any_value": True,
    "configurable_from_the_ui": False,
    "configurable_only_by": "a change to this module, which changes METHOD_VERSION",
    "target_rule": ("the first N rows of each arm IN NATIVE RANK ORDER, over the arm's "
                    "EVALUABLE, RANKED population. A target the arm could not score is not "
                    "ranked and is not emitted — it is COUNTED"),
    "pathway_rule": ("the first N gene-set rows of each arm in the PRODUCER'S OWN EMISSION "
                     "ORDER. There is no native gene-set ranking, and this module does not "
                     "invent one: ordering them by enrichment_value would be a headline "
                     "ranking derived here"),
    "cross_arm_order_emitted": False,
    "combined_or_pair_ranking_emitted": False,
}

SCHEMA = "spot.stage02_display_projection.v2"
PROJECTION_FILE = "stage2_display_projection.json"

# The fields carried VERBATIM from the native row. Nothing is recomputed, rescaled or renamed.
TARGET_ROW_FIELDS = ("target_id", "target_symbol", "rank", "arm_value")
PATHWAY_ROW_FIELDS = ("set_id", "enrichment_value", "target_source_coverage",
                      "global_coverage_disposition", "n_leading_edge", "peak_rank")


class ProjectionError(ValueError):
    """The view cannot be built from these bytes. Refuse; never approximate."""


def _raw(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _canon(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode()).hexdigest()


def _jsonable(value: Any) -> Any:
    """pandas NaN -> null. A NaN is not a number and it is not equal to itself."""
    if value is None:
        return None
    if hasattr(value, "item"):
        try:
            value = value.item()
        except (AttributeError, ValueError):
            return value
    if isinstance(value, float) and value != value:
        return None
    return value


# --------------------------------------------------------------------------- #
# THE PREFIX. One arm at a time; never across arms.
# --------------------------------------------------------------------------- #
def target_arm_view(rows: list, *, lane: str, crosswalk: dict | None = None) -> dict[str, Any]:
    """ONE Direct/temporal arm: its counts, and its first N NATIVE-RANKED evaluable rows.

    The counts are over the WHOLE arm. The rows are a prefix. A reader must be able to see
    that a prefix is a prefix — otherwise 100 rows out of 11,526 reads as "the answer".
    """
    cap = CAP_OF[lane]
    evaluable = [r for r in rows if bool(r.get("evaluable"))]
    ranked = [r for r in evaluable if r.get("rank") is not None]

    # NATIVE RANK ORDER. The rank is the producer's; this only orders BY it, and a duplicate
    # rank within one arm means the native ranking is not a ranking.
    ranked.sort(key=lambda r: int(r["rank"]))
    seen = [int(r["rank"]) for r in ranked]
    if len(seen) != len(set(seen)):
        raise ProjectionError(
            "this arm's native ranking contains a duplicated rank; two rows cannot both be "
            "the same place in one order")

    from . import symbol_crosswalk as CW

    emitted = [{"target_id": str(r["target_id"]),
                # DISPLAY METADATA. Looked up in the frozen, bound crosswalk — never guessed,
                # never a live lookup, and NEVER the target_id relabelled as a symbol. An
                # unmapped target is an EXPLICIT null.
                "target_symbol": (CW.symbol_for(crosswalk, r["target_id"])
                                  if crosswalk else None),
                "rank": int(r["rank"]),
                "arm_value": _jsonable(r.get("arm_value", r.get("value")))}
               for r in ranked[:cap]]
    return {
        "n_rows_total": len(rows),
        "n_evaluable": len(evaluable),
        "n_ranked": len(ranked),
        "n_emitted": len(emitted),
        "cap": cap,
        "is_a_prefix": len(emitted) < len(ranked),
        "rows": emitted,
    }


def pathway_arm_view(records: list) -> dict[str, Any]:
    """ONE pathway arm: coverage/disposition counts over EVERY set, and the first N rows.

    The rows are in the PRODUCER'S emission order. That is an ORDER, not a RANKING, and it is
    labelled as one — there is no native gene-set rank, and inventing one here would make this
    module the author of the headline result.
    """
    cap = CAP_OF["pathway"]

    dispositions: dict[str, int] = {}
    n_covered = 0
    for rec in records:
        d = str(rec.get("global_coverage_disposition"))
        dispositions[d] = dispositions.get(d, 0) + 1
        if rec.get("target_source_coverage") is not None:
            n_covered += 1

    emitted = [{f: _jsonable(rec.get(f)) for f in PATHWAY_ROW_FIELDS}
               for rec in records[:cap]]
    return {
        "n_sets_total": len(records),
        "n_with_coverage": n_covered,
        # over EVERY set in the arm, not merely the ones that fit in the prefix
        "coverage_disposition_counts": dict(sorted(dispositions.items())),
        "n_emitted": len(emitted),
        "cap": cap,
        "is_a_prefix": len(emitted) < len(records),
        "row_order": "native_producer_emission_order",
        "rows_are_ranked": False,
        "why_not_ranked": ("the native pathway record carries no rank of gene sets against "
                           "each other; ordering them by enrichment_value would be a headline "
                           "ranking derived HERE"),
        "rows": emitted,
    }


# --------------------------------------------------------------------------- #
# THE ASSEMBLER. Native bytes in; one compact, bound document out.
# --------------------------------------------------------------------------- #
def _direct_rows_by_arm(bundle_dir: str) -> dict[str, list]:
    import pandas as pd

    path = os.path.join(bundle_dir, "arms.parquet")
    if not os.path.exists(path):
        raise ProjectionError(f"{bundle_dir}: no arms.parquet — Direct's rows live there")
    out: dict[str, list] = {}
    for rec in pd.read_parquet(path).to_dict("records"):
        out.setdefault(str(rec["arm_key"]), []).append(
            {k: _jsonable(v) for k, v in rec.items()})
    return out


def _temporal_rows_by_arm(bundle_dir: str) -> dict[str, list]:
    rdir = os.path.join(bundle_dir, "rankings")
    out: dict[str, list] = {}
    for fname in sorted(os.listdir(rdir)) if os.path.isdir(rdir) else []:
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(rdir, fname)) as fh:
            doc = json.load(fh)
        # the arm key is stored ONCE, at the top of the document
        arm_key = str(doc.get("arm_key") or "")
        if not arm_key:
            raise ProjectionError(f"{bundle_dir}/{fname}: the ranking carries no arm_key")
        out.setdefault(arm_key, []).extend(
            doc.get("records") if doc.get("records") is not None else (doc.get("ranked") or []))
    return out


def _pathway_records_by_arm(bundle_dir: str) -> dict[str, list]:
    with open(os.path.join(bundle_dir, "arm_bundle.json")) as fh:
        doc = json.load(fh)
    out: dict[str, list] = {}
    for rec in (doc.get("records") or []):
        out.setdefault(str(rec.get("pathway_arm_key")), []).append(rec)
    return out


def project(bundles_root: str, *, crosswalk_path: str = "") -> dict[str, Any]:
    """The whole release, as a compact view. It reads only ADMITTED native bytes."""
    from . import bundle_normalize as BN
    from . import symbol_crosswalk as CW

    crosswalk = CW.load(crosswalk_path) if crosswalk_path else None

    arms: dict[str, Any] = {}
    sources: dict[str, Any] = {}

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

        lane = norm["lane"]
        rel = os.path.relpath(base, bundles_root).replace(os.sep, "/")

        if lane == "direct":
            by_arm = _direct_rows_by_arm(base)
            read = ["arms.parquet"]
        elif lane == "temporal":
            by_arm = _temporal_rows_by_arm(base)
            read = [f"rankings/{f}" for f in sorted(os.listdir(
                os.path.join(base, "rankings")))] if os.path.isdir(
                    os.path.join(base, "rankings")) else []
        else:
            by_arm = _pathway_records_by_arm(base)
            read = ["arm_bundle.json"]

        for arm_key, rows in sorted(by_arm.items()):
            if arm_key in arms:
                raise ProjectionError(
                    f"arm {arm_key!r} appears in more than one bundle; an arm is projected "
                    "once, from the bundle that computed it")
            view = (pathway_arm_view(rows) if lane == "pathway"
                    else target_arm_view(rows, lane=lane, crosswalk=crosswalk))
            view.update({"lane": lane, "arm_key": arm_key,
                         "context": dict(norm["context"]),
                         "source_bundle": rel})
            arms[arm_key] = view

        # WHICH BYTES THIS VIEW WAS READ FROM — raw AND canonical, so a verifier can reopen
        # them and prove the row at rank r IS the native row at rank r.
        sources[rel] = {
            "lane": lane,
            "bundle_id": norm["bundle_id"],
            "files": {n: {"raw_sha256": _raw(os.path.join(base, n))}
                      for n in read if os.path.exists(os.path.join(base, n))},
        }

    doc = {
        "schema_version": SCHEMA,
        "method_version": METHOD_VERSION,
        # A COPY. The module-level policy was embedded BY REFERENCE, so a caller mutating the
        # returned document mutated the frozen cap policy for the whole process — and the next
        # projection was built under a cap somebody else had changed. A frozen policy a caller
        # can move is not frozen.
        "cap_policy": dict(CAP_POLICY, caps=dict(CAP_OF)),
        # SELECTION-INDEPENDENT: no selection, no analysis_mode, no A/B pair. This view is the
        # same view whatever question is later asked of the release.
        "selection_independent": True,
        "selection_id": None,
        "analysis_mode": None,
        "combined_objective": None,
        "cross_arm_score_or_order": None,
        "authoritative_artifacts_are_the_native_ones": True,
        "bindings": {
            "native_bundles": sources,
            # THE FROZEN CROSSWALK, bound by raw AND canonical hash, so a verifier can reopen
            # it and prove every symbol on every row.
            "symbol_crosswalk": (CW.binding(crosswalk) if crosswalk else None),
        },
        "n_arms": len(arms),
        "arms": dict(sorted(arms.items())),
    }
    doc["projection_sha256"] = _canon(doc)
    return doc


def write(bundles_root: str, out_path: str, *, crosswalk_path: str = "") -> dict[str, Any]:
    doc = project(bundles_root, crosswalk_path=crosswalk_path)
    with open(out_path, "w") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True, allow_nan=False)
    return doc


def main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(
        description="Assemble the COMPACT display projection from ADMITTED native bytes. "
                    "Selection-independent. Emits no combined or pair ranking, and the cap is "
                    "frozen in method-versioned config — never a UI parameter.")
    ap.add_argument("--bundles-root", required=True)
    ap.add_argument("--out", required=True, help="a FILE, not a directory")
    ap.add_argument("--symbol-crosswalk", default="",
                    help="the FROZEN Stage-1 effect_universe_gwcd4i.json. Its symbol_to_ensembl "
                         "map is inverted (one-to-one only) to label rows. DISPLAY METADATA: it "
                         "changes no value, no rank and no population.")
    args = ap.parse_args(argv)

    try:
        doc = write(args.bundles_root, args.out, crosswalk_path=args.symbol_crosswalk)
    except ProjectionError as exc:
        print(json.dumps({"projected": False, "error": str(exc)}, indent=2))
        return 1
    cw = (doc.get("bindings") or {}).get("symbol_crosswalk") or {}
    print(json.dumps({"projected": True, "n_arms": doc["n_arms"],
                      "symbol_crosswalk_raw_sha256": cw.get("raw_sha256"),
                      "n_one_to_one_symbols": cw.get("n_one_to_one"),
                      "cap_policy_id": CAP_POLICY_ID,
                      "method_version": METHOD_VERSION,
                      "projection_sha256": doc["projection_sha256"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
