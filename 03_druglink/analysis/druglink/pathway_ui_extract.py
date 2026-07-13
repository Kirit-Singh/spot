"""Compact GO-BP pathway CONTEXT for two selected arms, from the REAL producer bytes.

NOT A PRODUCTION RESULT. The pathway bundle declares ``admitted: false`` and there is no
independent Stage-3 admission of it yet, so every document written here says so in
machine-readable fields (``development_unadmitted`` / ``admission_pending`` /
``is_production_result: false``). Nothing here claims independent admission.

WHAT A PATHWAY ROW IS, AND WHAT IT IS NOT
----------------------------------------
It is a GENE-SET ENRICHMENT: a statement about a SET, in one arm, in one condition. It is NOT a
measurement of a target under knockdown. So a context row may ANNOTATE a candidate an eligible
gene-arm edge already supports, and it may never create a target, a drug or an arm membership.
Nothing here promotes anything.

THE TWO ARMS STAY APART. Each selected arm is extracted, ordered and truncated INDEPENDENTLY.
There is no combined, balanced or weighted score and no joint ranking: a set that is strongly
enriched in one arm and absent from the other must be visibly exactly that.

ORDERING PRESERVES SIGN. Rows are ordered by ``enrichment_value`` DESCENDING — never by absolute
value. A strongly NEGATIVE enrichment is a real, opposite-direction fact about the set; ranking it
next to a strongly positive one would file two opposite findings under one heading.

TRUNCATION IS EXPLICIT. The display list is the top ``display_limit`` headline-rankable rows, and
the counts published alongside it are over the WHOLE arm — so a reader can always see how much was
left out. A silent top-N is a claim of completeness nobody made.

NO p/q/FDR. The producer emits none, and none is derived: significance stays behind Stage-2's own
firewall.
"""
from __future__ import annotations

import json
import os
from typing import Any

from .hashing import file_sha256

SCHEMA = "spot.stage03_pathway_context_ui.v0"
STATUS_UNADMITTED = "development_unadmitted"
SOURCE_GO_BP = "go_bp"

# The DISPLAY contract. Deterministic, and published in the artifact so the UI never has to guess.
DISPLAY_LIMIT = 100
DISPLAY_ORDER = "enrichment_value_descending_sign_preserved_never_absolute"

# EXACTLY the columns a context row may publish. An allowlist, so a field nobody agreed to (a
# p-value, a combined score) cannot arrive by being added upstream.
ROW_FIELDS = (
    "set_id", "set_name", "source", "condition", "program_id", "desired_change",
    "pathway_arm_key", "direct_arm_key", "enrichment_value", "arm_headline_rankable",
    "arm_coverage_disposition", "global_coverage_disposition", "global_coverage_policy_passed",
    "target_source_coverage", "arm_evaluable_source_coverage",
    "leading_edge", "leading_edge_side", "n_leading_edge", "n_hits_in_ranking",
    "n_genes_in_target_universe", "n_source_symbols", "min_arm_ranked_members",
    "peak_rank", "undefined_reason",
)

# Never emitted, at any depth. Restated here so a producer change cannot smuggle one in.
BANNED = ("p_value", "q_value", "pvalue", "qvalue", "pval", "qval", "fdr", "padj", "adj_p",
          "significan", "combined", "balanced", "weighted", "overall", "headline_score",
          "composite")


class PathwayExtractError(ValueError):
    """The real bytes are missing or do not carry the arms the selection names."""


def load_bundle(path: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """(header, records) from ONE read. The real bundle is ~350 MB and is never parsed twice."""
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    return bundle_header(doc), list(doc.get("records") or [])


def bundle_header(doc: dict[str, Any]) -> dict[str, Any]:
    """The bundle's own identity, WITHOUT its records (and without any machine-local path)."""
    return {
        "schema_version": doc.get("schema_version"),
        "pathway_run_id": doc.get("pathway_run_id"),
        "condition": doc.get("condition"),
        "source": doc.get("source"),
        "convergence_ref": doc.get("convergence_ref"),
        "convergence_sha256": doc.get("convergence_sha256"),
        "records_sha256": doc.get("records_sha256"),
        "n_records": doc.get("n_records"),
        "n_arm_slots": doc.get("n_arm_slots"),
    }


def _clean(record: dict[str, Any]) -> dict[str, Any]:
    row = {k: record.get(k) for k in ROW_FIELDS}
    smuggled = sorted(k for k in record if any(b in k.lower() for b in BANNED))
    if smuggled:
        raise PathwayExtractError(
            f"[a_pathway_row_carries_a_banned_vocabulary] set {record.get('set_id')!r} carries "
            f"{smuggled}. Significance stays behind Stage-2's firewall, and there is no combined "
            "objective anywhere in this chain.")
    return row


def arm_block(records: list[dict[str, Any]], *, arm_key: str, role: str) -> dict[str, Any]:
    """ONE arm: its full counts, and its OWN top-N. Ordered and truncated independently."""
    rankable = [r for r in records if r.get("arm_headline_rankable") is True
                and r.get("enrichment_value") is not None]
    # SIGN-PRESERVING. Descending by the real value; a negative enrichment stays negative and
    # sorts where it belongs, at the bottom — it is not an "equally strong" hit.
    rankable.sort(key=lambda r: (-float(r["enrichment_value"]), str(r["set_id"])))
    shown = rankable[:DISPLAY_LIMIT]

    first = records[0] if records else {}
    return {
        "arm_key": arm_key,
        # The role is a property of THIS question, assigned at join time. It is never stored on a
        # reusable arm, and the arm key does not contain it.
        "selection_role": role,
        "program_id": first.get("program_id"),
        "desired_change": first.get("desired_change"),
        "condition": first.get("condition"),
        "source": SOURCE_GO_BP,
        "direct_arm_key": first.get("direct_arm_key"),
        "convergence_ref": first.get("convergence_ref"),

        # COUNTS OVER THE WHOLE ARM, so the truncation below is explicit rather than implied.
        "n_sets_in_arm": len(records),
        "n_headline_rankable": len(rankable),
        "n_enrichment_undefined": sum(1 for r in records if r.get("enrichment_value") is None),
        "display_limit": DISPLAY_LIMIT,
        "display_order": DISPLAY_ORDER,
        "n_shown": len(shown),
        "n_truncated": max(0, len(rankable) - len(shown)),

        "is_a_crispri_target_row": False,
        "may_be_matched_to_a_drug_as_a_target": False,
        "may_promote_a_target_or_drug": False,
        "terms": [_clean(r) for r in shown],
    }


def extract(*, bundle_path: str, condition: str, a_program: str, a_change: str,
            b_program: str, b_change: str) -> dict[str, Any]:
    """The two selected arms of one condition, from the real bytes. Nothing else."""
    if not os.path.isfile(bundle_path):
        raise PathwayExtractError(
            f"[the_real_pathway_bytes_are_not_on_disk] no arm_bundle.json at {bundle_path!r}. "
            "There is no fixture fallback.")

    a_key = f"pathway|{a_program}|{a_change}|{condition}|{SOURCE_GO_BP}"
    b_key = f"pathway|{b_program}|{b_change}|{condition}|{SOURCE_GO_BP}"
    wanted = {a_key: [], b_key: []}

    header, records = load_bundle(bundle_path)
    if str(header.get("condition")) != condition:
        raise PathwayExtractError(
            f"[the_bundle_is_not_the_condition_it_was_asked_for] the bundle declares condition "
            f"{header.get('condition')!r}, not {condition!r}.")

    for record in records:
        # EXACT key equality, never a prefix: `…|Rest|go_bp` and `…|Stim8hr|go_bp` differ only in
        # the tail, and a prefix match would show one condition's sets under another's question.
        key = str(record.get("pathway_arm_key"))
        if key in wanted:
            wanted[key].append(record)

    missing = [k for k, v in wanted.items() if not v]
    if missing:
        raise PathwayExtractError(
            f"[the_selection_names_an_arm_the_bundle_does_not_carry] {missing}")

    return {
        "schema_version": SCHEMA,
        "status": STATUS_UNADMITTED,
        "admission_pending": True,
        "is_production_result": False,
        "independent_admission_claimed": False,
        "admission_note": "the pathway bundle declares admitted=false and no independent Stage-3 "
                          "admission of it exists. This is context for development, not a result.",
        "condition": condition,
        "gene_set_source": SOURCE_GO_BP,
        "analysis_mode": "within_condition",
        "pathway_scope": "within_condition_endpoint",

        # NO DENIAL FIELDS. The served firewall scans for banned SUBSTRINGS, so a key named to
        # deny an FDR or a combined objective IS the string it refuses — and "significance_...is_
        # absent" trips it just as surely. The properties are held by the SCHEMA and the DATA: the
        # arms are separate objects, each ordered and truncated on its own, and no pooled value is
        # computed anywhere. A structure that cannot express the thing needs no field saying so.
        "arms_are_independent_and_never_pooled": True,
        "pathway_may_annotate_but_never_promote": True,

        # BOUND BY BYTES, not by path. A path names a place on one machine, not an artifact.
        "input_binding": {
            "arm_bundle_raw_sha256": file_sha256(bundle_path),
            "arm_bundle_file": os.path.basename(bundle_path),
            **header,
        },
        "arms": [
            arm_block(wanted[a_key], arm_key=a_key, role="away_from_A"),
            arm_block(wanted[b_key], arm_key=b_key, role="toward_B"),
        ],
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--arm-bundle", required=True)
    ap.add_argument("--condition", required=True)
    ap.add_argument("--a-program", default="treg_like")
    ap.add_argument("--a-change", default="decrease")
    ap.add_argument("--b-program", default="th1_like")
    ap.add_argument("--b-change", default="increase")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    try:
        doc = extract(bundle_path=args.arm_bundle, condition=args.condition,
                      a_program=args.a_program, a_change=args.a_change,
                      b_program=args.b_program, b_change=args.b_change)
    except PathwayExtractError as exc:
        print(f"REFUSED: {exc}")
        return 3

    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, sort_keys=True, indent=1)
        fh.write("\n")

    print(f"[{STATUS_UNADMITTED}] {args.condition} go_bp  "
          f"run={doc['input_binding']['pathway_run_id']}")
    for arm in doc["arms"]:
        print(f"  {arm['arm_key']:<44} {arm['selection_role']:<11} "
              f"sets={arm['n_sets_in_arm']:>6} rankable={arm['n_headline_rankable']:>6} "
              f"shown={arm['n_shown']:>4} truncated={arm['n_truncated']:>6}")
    print(f"  -> {args.out}")
    print(f"     sha256={file_sha256(args.out)}")
    return 0


if __name__ == "__main__":                                   # pragma: no cover
    raise SystemExit(main())
