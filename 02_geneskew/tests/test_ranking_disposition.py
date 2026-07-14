"""Row-order invariance, deterministic ranking, complete disposition, no p/q.

The artifact-level checks (against a generated screen.parquet) run only when
STAGE2_OUT_DIR points at an emitted output directory; the synthetic checks run
everywhere.
"""
import os

import pytest

from direct import projection as proj
from direct import disposition


def _row(tid, away, toward):
    dc = proj.direction_class(away, toward)
    return {"target_ensembl": tid, "away_from_A": away, "toward_b": toward,
            "balanced_skew": None if away is None else (away + toward) / 2,
            "direction_class": dc}


def test_row_order_invariance_and_deterministic_ranking():
    base = [
        _row("ENSG3", 0.2, 0.2),   # aligned_both, balanced 0.2
        _row("ENSG1", 0.5, 0.5),   # aligned_both, balanced 0.5  -> rank 1
        _row("ENSG2", 0.5, 0.5),   # tie with ENSG1 -> broken by id
        _row("ENSG4", -0.1, 0.9),  # one-sided
        _row("ENSG5", -0.5, -0.5), # opposed
    ]
    order1 = [r["target_ensembl"] for r in proj.rank_rows(list(base), "balanced_a_to_b")]
    order2 = [r["target_ensembl"] for r in proj.rank_rows(list(reversed(base)), "balanced_a_to_b")]
    assert order1 == order2
    # aligned_both first, tie broken by target id (ENSG1 before ENSG2)
    assert order1[:3] == ["ENSG1", "ENSG2", "ENSG3"]
    assert order1[-1] == "ENSG5"  # opposed last


def test_ranks_are_contiguous_and_unique():
    rows = [_row(f"ENSG{i}", i * 0.1, i * 0.1) for i in range(10)]
    ranked = proj.rank_rows(rows, "balanced_a_to_b")
    assert sorted(r["rank"] for r in ranked) == list(range(1, 11))


def test_eligibility_precedence_and_complete_states():
    # underpowered outranks eligible even with two guides
    st, reasons = disposition.classify_eligibility(
        row_present=True, projection_status="ok", mask_resolved=True,
        n_cells=5, low_target_gex=False, ontarget_significant=True, n_guides=2)
    assert st == "underpowered_cells"
    assert "eligible_two_guide" in reasons  # complete disposition retained

    st2, _ = disposition.classify_eligibility(
        row_present=True, projection_status="ok", mask_resolved=True,
        n_cells=500, low_target_gex=False, ontarget_significant=True, n_guides=2)
    assert st2 == "eligible_two_guide"

    st3, _ = disposition.classify_eligibility(
        row_present=True, projection_status="insufficient_axis_coverage",
        mask_resolved=True, n_cells=500, low_target_gex=False,
        ontarget_significant=True, n_guides=2)
    assert st3 == "insufficient_axis_coverage"


def test_desired_modulation_direction():
    assert disposition.desired_target_modulation(0.5) == "decrease"
    assert disposition.desired_target_modulation(-0.5) == "increase"
    assert disposition.desired_target_modulation(None) == "not_evaluated"


# --------------------------------------------------------------------------- #
# Artifact-level checks (optional, guarded by STAGE2_OUT_DIR).
# --------------------------------------------------------------------------- #
_OUT = os.environ.get("STAGE2_OUT_DIR")
needs_out = pytest.mark.skipif(not _OUT, reason="STAGE2_OUT_DIR not set")

_FORBIDDEN = {"p_value", "pvalue", "p_val", "pval", "q_value", "qvalue",
              "q_val", "qval", "padj", "adj_p_value", "fdr"}


@needs_out
def test_screen_has_no_pq_columns():
    import pandas as pd
    df = pd.read_parquet(os.path.join(_OUT, "screen.parquet"))
    bad = [c for c in df.columns if c.lower() in _FORBIDDEN]
    assert bad == [], f"forbidden p/q columns present: {bad}"


@needs_out
def test_screen_complete_disposition():
    import json
    import pandas as pd
    df = pd.read_parquet(os.path.join(_OUT, "screen.parquet"))
    # every target has an explicit eligibility state (no nulls, no blanks)
    assert df["eligibility_state"].notna().all()
    assert (df["eligibility_state"].astype(str).str.len() > 0).all()
    # every target has inference_status = not_calibrated
    assert (df["inference_status"] == "not_calibrated").all()
    # ranks are a contiguous permutation
    ranks = sorted(df["rank"].tolist())
    assert ranks == list(range(1, len(df) + 1))
    # verification.json agrees on row count
    v = json.load(open(os.path.join(_OUT, "verification.json")))
    assert v["row_count"] == len(df)
    assert v["no_pq_columns"] is True


@needs_out
def test_every_target_appears_once():
    import pandas as pd
    df = pd.read_parquet(os.path.join(_OUT, "screen.parquet"))
    assert df["target_ensembl"].is_unique
