"""Pure-python replication of the Stage-1 sparse-aware display transform (programs.html).

Mirrors `transformFor` / `normScore` exactly so the display-correction logic is testable
off the browser. Anchors are read from the FROZEN per-score quantiles (p02..p99 computed
once over the full 396k universe) — never recomputed from visible cells.

Rules (see docs/spot_buildout_plan.md §4.1):
  - p50 always maps to 0.5; the transform is monotonic.
  - upper anchor (-> 1.0): first stored quantile STRICTLY > p50, scanning p75,p90,p95,p98,p99.
  - lower anchor (-> 0.0): first stored quantile STRICTLY < p50, scanning p25,p10,p02.
  - if NO upper quantile exceeds p50 -> display_status = 'degenerate': the field carries no
    shadeable signal and is rendered NEUTRALLY (flat), never at max intensity.
  - direction='low' inverts the mapping (t -> 1 - t).
"""

UPPER = ("p75", "p90", "p95", "p98", "p99")
LOWER = ("p25", "p10", "p02")


def build_transform(d):
    """Build the frozen display transform from a field's quantile dict."""
    p50 = d["p50"]
    hi = next((d[k] for k in UPPER if d.get(k) is not None and d[k] > p50), None)
    lo = next((d[k] for k in LOWER if d.get(k) is not None and d[k] < p50), None)
    if hi is None:
        return {"status": "degenerate", "p50": p50, "anchors": {"lo": lo, "hi": None}}
    return {
        "status": "ok",
        "p50": p50,
        "lo": p50 if lo is None else lo,
        "hi": hi,
        "anchors": {"lo": lo if lo is not None else p50, "hi": hi},
    }


def norm_score(v, tf, direction="high"):
    """Map a raw score to [0,1]. Returns None for missing OR degenerate (no signal)."""
    if v is None:
        return None
    if tf["status"] == "degenerate":
        return None
    lo, p50, hi = tf["lo"], tf["p50"], tf["hi"]
    if v <= p50:
        t = 0.5 if lo == p50 else 0.5 * (v - lo) / (p50 - lo)
    else:
        t = 0.5 + 0.5 * (v - p50) / (hi - p50)
    t = max(0.0, min(1.0, t))
    return (1.0 - t) if direction == "low" else t


# ── quantile fixtures ────────────────────────────────────────────────────────────
NORMAL = {"p02": -0.486, "p10": -0.335, "p25": -0.156, "p50": 0.150,
          "p75": 0.544, "p90": 0.900, "p95": 1.113, "p98": 1.356, "p99": 1.527}
# th9_like_score as served: p02<p50 but every upper quantile collapses onto p50.
SPARSE = {"p02": -0.01897, "p10": -0.01078, "p25": -0.00629, "p50": 0.0,
          "p75": 0.0, "p90": 0.0, "p95": 0.0, "p98": 0.0, "p99": 0.0}
ALL_TIED = {k: 0.0 for k in ("p02", "p10", "p25", "p50", "p75", "p90", "p95", "p98", "p99")}


def test_normal_case_ok():
    tf = build_transform(NORMAL)
    assert tf["status"] == "ok"
    # first quantile strictly above/below p50 are the anchors
    assert tf["hi"] == NORMAL["p75"]
    assert tf["lo"] == NORMAL["p25"]


def test_p50_maps_to_exactly_half():
    tf = build_transform(NORMAL)
    assert norm_score(NORMAL["p50"], tf) == 0.5


def test_anchors_map_to_endpoints():
    tf = build_transform(NORMAL)
    assert norm_score(tf["lo"], tf) == 0.0
    assert norm_score(tf["hi"], tf) == 1.0


def test_monotonic_across_range():
    tf = build_transform(NORMAL)
    xs = [-1.0 + 0.05 * i for i in range(60)]  # spans below p02 to above p99
    ts = [norm_score(v, tf) for v in xs]
    assert all(b >= a - 1e-12 for a, b in zip(ts, ts[1:])), "transform must be monotonic non-decreasing"


def test_sparse_is_degenerate_and_neutral():
    tf = build_transform(SPARSE)
    assert tf["status"] == "degenerate"
    # neutral: no value is ever pushed to max intensity; present cells render flat (None sentinel)
    assert norm_score(0.0, tf) is None
    assert norm_score(SPARSE["p02"], tf) is None
    assert norm_score(1.0, tf) is None


def test_all_tied_is_degenerate():
    tf = build_transform(ALL_TIED)
    assert tf["status"] == "degenerate"


def test_low_direction_inverts():
    tf = build_transform(NORMAL)
    for v in (-0.4, 0.0, NORMAL["p50"], 0.5, 1.4):
        hi = norm_score(v, tf, "high")
        lo = norm_score(v, tf, "low")
        assert abs(lo - (1.0 - hi)) < 1e-12
    # p50 stays at 0.5 under inversion
    assert norm_score(NORMAL["p50"], tf, "low") == 0.5


def test_lower_half_collapses_but_upper_still_shades():
    # upper tail exists, no lower quantile below p50 -> not degenerate; lower half flattens to 0.5
    d = {"p02": 0.0, "p10": 0.0, "p25": 0.0, "p50": 0.0,
         "p75": 0.3, "p90": 0.6, "p95": 0.8, "p98": 1.0, "p99": 1.2}
    tf = build_transform(d)
    assert tf["status"] == "ok"
    assert norm_score(-5.0, tf) == 0.5      # nothing below p50 -> flat at midpoint
    assert norm_score(0.0, tf) == 0.5
    assert norm_score(tf["hi"], tf) == 1.0


if __name__ == "__main__":
    import sys
    fns = [g for n, g in sorted(globals().items()) if n.startswith("test_") and callable(g)]
    fails = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as e:
            fails += 1
            print(f"FAIL {fn.__name__}: {e}")
    print(f"\n{len(fns) - fails}/{len(fns)} passed")
    sys.exit(1 if fails else 0)
