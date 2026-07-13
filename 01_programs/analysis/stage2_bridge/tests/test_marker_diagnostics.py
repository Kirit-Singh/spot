"""Marker LOMO diagnostics v2: neutral, continuous, condition+donor STRATIFIED, not eligibility,
no binary label, no threshold."""
import json
import os

import canonical
import constituents as C
import emit_marker_diagnostics as md

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROGRAMS = os.path.dirname(os.path.dirname(HERE))
DATA = os.path.join(PROGRAMS, "app", "data")


def test_not_eligibility_and_bound_to_constituents():
    d = md.build_diagnostics()
    assert d["use_for_eligibility"] is False
    _, manifest = C.load_constituents(
        os.path.join(HERE, "_release_staging", "stage01_gate_constituents_v1.json.gz"),
        os.path.join(HERE, "_release_staging", "stage01_gate_constituents_v1.manifest.json"))
    assert d["source_constituent_content_sha256"] == manifest["content_canonical_sha256"]
    assert d["n_programs"] == 11 and d["conditions"] == list(C.CONDS) and d["donors"] == list(C.DONORS)


def test_neutral_continuous_names_no_label_no_threshold():
    blob = json.dumps(md.build_diagnostics()).lower()
    for banned in ("dominant", "dominance", "breadth", "threshold", "eligible", "pass", "fail"):
        assert banned not in blob, f"banned term {banned!r} present"
    # required neutral continuous names present
    for req in ("most_sensitive_removed_marker", "min_leave_one_marker_out_rho", "max_leave_one_marker_out_shift"):
        assert req in blob


def test_stratified_by_condition_and_donor():
    d = md.build_diagnostics()
    p = next(x for x in d["programs"] if x["program_id"] == "th1_like")
    m = p["markers"][0]
    conds = [bc["condition"] for bc in m["by_condition"]]
    assert conds == list(C.CONDS)                          # per-condition summaries
    for bc in m["by_condition"]:
        assert [dr["donor"] for dr in bc["donors"]] == list(C.DONORS)   # per-donor rows
        assert set(bc) == {"condition", "min_leave_one_marker_out_rho",
                           "max_leave_one_marker_out_shift", "n_undefined", "donors"}
    # per-condition program summary lets the SELECTED condition be evaluated (not one global worst)
    per = {x["condition"]: x["min_leave_one_marker_out_rho"] for x in p["per_condition"]}
    assert set(per) == set(C.CONDS)
    assert len({v for v in per.values() if v is not None}) >= 2   # conditions are NOT collapsed to one value


def test_deterministic_and_compact():
    d1, d2 = md.build_diagnostics(), md.build_diagnostics()
    assert json.dumps(d1, sort_keys=True) == json.dumps(d2, sort_keys=True)
    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                assert "note" not in k.lower()
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(d1)


def test_served_v2_matches_builder_and_v1_retired():
    d = md.build_diagnostics()
    served = json.load(open(os.path.join(DATA, "stage01_marker_diagnostics_v2.json")))
    assert canonical.canonical_content_sha256(served) == canonical.canonical_content_sha256(d)
    assert not os.path.exists(os.path.join(DATA, "stage01_marker_diagnostics_v1.json"))
