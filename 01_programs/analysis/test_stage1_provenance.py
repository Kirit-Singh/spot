"""Mutation / forgery tests for the Stage-1 primary-source provenance integration.

Adversary model: an attacker edits a marker_provenance record (and, in the sophisticated case, recomputes
registry_sha256) so a naive integrity check would pass. This is still caught because verify_stage1_provenance
INDEPENDENTLY re-derives the 53-pair coverage from the raw source CSVs and re-checks the scoring projection.

Every test operates on an in-memory copy of the real registry (+ a temp copy of the source dir for the
changed-checksum case), so the suite is self-contained and path-independent. A clean registry must pass;
every mutation must be rejected; and the pre/post scoring projection must be exactly equal.
"""
import copy, hashlib, json, os, shutil, sys
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "app", "data")
SRC = os.path.join(HERE, "provenance_sources")
sys.path.insert(0, HERE)
import verify_stage1_provenance as V  # noqa: E402


def _reg():
    return json.load(open(os.path.join(DATA, "stage01_program_registry_v3.json")))


def _reseal(reg):
    """Sophisticated attacker: recompute registry_sha256 after tampering so self-integrity passes."""
    d = {k: v for k, v in reg.items() if k != "registry_sha256"}
    reg["registry_sha256"] = hashlib.sha256(
        json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
    return reg


def _has(fails, prefix):
    return any(f.split(":")[0] == prefix for f in fails)


# ---- clean registry passes ----
def test_clean_registry_passes():
    assert V.run_checks(_reg(), SRC) == []


# ---- S1-M2: a resealed Tier-2 display-label reinsert is rejected by the STANDALONE verifier ----
def test_tier2_display_field_reinsert_rejected():
    reg = _reg()
    reg["programs"][0]["display_label"] = "INJECTED TIER-2 LABEL"
    fails = V.run_checks(_reseal(reg), SRC)   # reseal re-hashes registry_sha256 so the self-integrity check passes
    assert _has(fails, "tier2_field_in_tier1_registry")


# ---- missing locator ----
def test_missing_locator_rejected():
    reg = _reseal(_reg())
    reg["programs"][0]["marker_provenance"][reg["programs"][0]["panel_genes_measured"][0]]["exact_locator"] = ""
    fails = V.run_checks(_reseal(reg), SRC)
    assert _has(fails, "missing_locator")


# ---- swapped program/gene (forged pmid/locator under the wrong program) ----
def test_swapped_program_gene_rejected():
    reg = _reg()
    # give th1_like::CXCR3 the locator/pmid that actually belongs to a checkpoint gene
    donor = next(p for p in reg["programs"] if p["program_id"] == "diff_checkpoint")["marker_provenance"]["TOX"]
    victim = next(p for p in reg["programs"] if p["program_id"] == "th1_like")["marker_provenance"]["CXCR3"]
    victim["pmid"], victim["exact_locator"] = donor["pmid"], donor["exact_locator"]
    fails = V.run_checks(_reseal(reg), SRC)
    assert _has(fails, "source_field_mismatch")


# ---- unresolvable inherited alias ----
def test_unresolvable_actadj_alias_rejected():
    reg = _reg()
    lane = reg["sensitivity_lanes"][0]
    lane["marker_provenance"]["GNLY"]["base_marker_provenance_ref"] = "cd4_ctl_like.marker_provenance.NOT_A_GENE"
    fails = V.run_checks(_reseal(reg), SRC)
    assert _has(fails, "unresolvable_alias")


def test_unresolvable_predictor_alias_rejected():
    reg = _reg()
    ap = reg["sensitivity_lanes"][0]["activation_predictor"]
    ap["predictor_provenance"]["CD69"]["base_program_id"] = "nonexistent_program"
    fails = V.run_checks(_reseal(reg), SRC)
    assert _has(fails, "unresolvable_predictor_alias")


# ---- Masopust attached as marker support ----
def test_masopust_as_marker_source_rejected():
    reg = _reg()
    rec = reg["programs"][0]["marker_provenance"][reg["programs"][0]["panel_genes_measured"][0]]
    rec["source_title"] = "Masopust naming framework 2026"
    fails = V.run_checks(_reseal(reg), SRC)
    assert _has(fails, "masopust_as_marker_source")


# ---- inflated denominator (count an intended-only or alias as a measured pair) ----
def test_inflated_panel_provenance_denominator_rejected():
    reg = _reseal(_reg())
    reg["panel_provenance"]["measured_marker_pairs_total"] = 54
    reg["panel_provenance"]["measured_marker_pairs_with_primary_locator"] = 54
    fails = V.run_checks(_reseal(reg), SRC)
    assert _has(fails, "panel_provenance_denominator_inflated_or_wrong")


def test_hla_dra_promoted_to_measured_rejected():
    reg = _reg()
    da = next(p for p in reg["programs"] if p["program_id"] == "diff_activated")
    # attacker adds HLA-DRA to the measured panel to close a citation row -> denominator 54, no source row
    da["panel_genes_measured"].append("HLA-DRA")
    fails = V.run_checks(_reseal(reg), SRC)
    assert _has(fails, "denominator_not_53") or _has(fails, "unexpected_measured_pair_or_swap")


# ---- changed input checksum (tamper a temp copy of a source CSV) ----
def test_changed_source_checksum_rejected(tmp_path):
    tmp_src = tmp_path / "provenance_sources"
    shutil.copytree(SRC, tmp_src)
    p = tmp_src / "state_ctl_primary_source_completion.csv"
    p.write_bytes(p.read_bytes() + b"\n# tampered\n")
    fails = V.run_checks(_reg(), str(tmp_src))
    assert _has(fails, "source_checksum_changed")


# ---- a forged scoring field (drop a control) must be caught by the projection check ----
def test_scoring_projection_change_rejected():
    reg = _reg()
    p0 = reg["programs"][0]
    bin_key = next(iter(p0["controls_by_bin"]))
    p0["controls_by_bin"][bin_key] = p0["controls_by_bin"][bin_key][:-1]   # drop one control gene
    fails = V.run_checks(_reseal(reg), SRC)
    assert _has(fails, "scoring_projection_changed")


# ---- pre/post scoring projection exact equality (provenance-only keys dropped) ----
def test_pre_post_scoring_projection_equal():
    post = _reg()
    proj_hash = V._canon(V._scoring_projection(post))
    assert proj_hash == V.PRE_SCORING_PROJECTION_SHA256
    # dropping provenance-only keys must leave a projection independent of the provenance edits:
    stripped = V._scoring_projection(post)
    for prog in stripped["programs"]:
        assert "marker_provenance" not in prog and "selection_rationale" not in prog
    assert "panel_provenance" not in stripped


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-q"]))
