"""MUTATION 6 — an attempt to gate or reorder. Plus the end-to-end ADMIT.

The verifier imports nothing from ``p2s_arms`` and nothing from ``direct``. It reads the
shipped bytes off disk and re-derives every rule from its own copy of the spec, so it can
genuinely DISAGREE with the producer.
"""
from __future__ import annotations

import json
import os

import fixtures_p2s as fx
import pandas as pd
import pytest
from p2s_arms import verify_p2s_arms as V


@pytest.fixture
def run_dir(tmp_path, view, bundle_dir, w10_report, inputs):
    """A complete P2S run over the synthetic fixture, through the real producer."""
    out = fx.run_producer(tmp_path, view=view, bundle_dir=bundle_dir,
                          w10_report=w10_report, inputs=inputs)
    return out["out_dir"]


# --------------------------------------------------------------------------- #
# The clean artifact is ADMITTED — end to end, through the real producer.
# --------------------------------------------------------------------------- #
def test_a_clean_run_is_ADMITTED(run_dir):
    rep = V.verify(run_dir)
    assert rep["verdict"] == V.ADMIT, [c for c in rep["checks"] if c["status"] == "fail"]
    assert rep["n_failed"] == 0
    assert rep["n_checks"] > 20


def test_the_artifact_declares_itself_secondary_and_non_gating(run_dir):
    doc = json.load(open(os.path.join(run_dir, "p2s_support.json")))
    assert doc["lane_role"] == "secondary_non_gating"
    m = doc["method"]
    assert m["p2s_may_rank_or_gate"] is False
    assert m["combined_objective_permitted"] is False
    assert m["coefficients_are_causal_effects"] is False
    assert m["temporal_did_claimed"] is False
    assert m["validates_direct_by_agreement"] is False
    assert m["base_portable"] is True
    assert "production_eligible" not in json.dumps(doc)


def test_NO_temporal_artifact_exists(run_dir):
    """A DiD claim needs a field that is a function of BOTH endpoints. No file holds one."""
    for f in V.FORBIDDEN_FILES:
        assert not os.path.exists(os.path.join(run_dir, f))
    keys = pd.read_parquet(
        os.path.join(run_dir, "p2s_arm_support.parquet"))["arm_key"].unique()
    assert all(len(str(k).split("|")) == 4 for k in keys)
    assert all(str(k).startswith("direct|") for k in keys)


# --------------------------------------------------------------------------- #
# MUTATION 6 — attempt to gate or reorder.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("column", [
    "rank", "p2s_rank", "rank_away_from_A", "promoted", "gate_passed",
])
def test_MUTATION_a_rank_or_gate_column_is_REJECTED(run_dir, column):
    """Rejected by ABSENCE from the allowlist — not by a rule that must guess its name."""
    path = os.path.join(run_dir, "p2s_arm_support.parquet")
    df = pd.read_parquet(path)
    df[column] = 1
    df.to_parquet(path, index=False)

    rep = V.verify(run_dir)
    assert rep["verdict"] == V.REJECT
    assert any("allowlisted columns" in c["check"] or "rank column" in c["check"]
               for c in rep["checks"] if c["status"] == "fail")


@pytest.mark.parametrize("key,value", [
    ("p_value", 0.01),
    ("q_val", 0.05),
    ("fdr", 0.1),
    ("bh_significance", True),
    ("combined_arm_score", 1.0),
    ("balanced_skew", 0.5),
    ("weighted_objective", 2.0),
    ("nominal_p", 0.2),
])
def test_MUTATION_a_forbidden_STATISTIC_key_is_REJECTED_at_any_depth(run_dir, key, value):
    path = os.path.join(run_dir, "p2s_support.json")
    doc = json.load(open(path))
    doc["method"]["support"][key] = value          # buried two levels down
    json.dump(doc, open(path, "w"))

    rep = V.verify(run_dir)
    assert rep["verdict"] == V.REJECT


def test_MUTATION_flipping_a_negative_declaration_to_TRUE_fires_the_firewall(run_dir):
    """The exemption is held only while the declaration still says 'forbidden'."""
    path = os.path.join(run_dir, "p2s_support.json")
    doc = json.load(open(path))
    doc["method"]["combined_objective_permitted"] = True
    json.dump(doc, open(path, "w"))

    rep = V.verify(run_dir)
    assert rep["verdict"] == V.REJECT


def test_MUTATION_an_edited_support_row_breaks_the_content_address(run_dir):
    path = os.path.join(run_dir, "p2s_arm_support.parquet")
    df = pd.read_parquet(path)
    df.loc[0, "primary_coefficient"] = 99.0
    df.to_parquet(path, index=False)

    rep = V.verify(run_dir)
    assert rep["verdict"] == V.REJECT
    assert any("support_rows_sha256" in c["check"]
               for c in rep["checks"] if c["status"] == "fail")


def test_MUTATION_flipping_the_opposed_flag_off_its_primary_sign_is_REJECTED(run_dir):
    """`opposed` is EXACTLY the primary-sign-is-opposed fact; relabelling it cannot pass."""
    path = os.path.join(run_dir, "p2s_arm_support.parquet")
    df = pd.read_parquet(path)
    opp = df.index[df["primary_sign"] == "opposed"]
    assert len(opp) > 0, "the fixture must plant an opposed contributor"
    df.loc[opp[0], "opposed"] = False          # lie: opposed sign, opposed flag off
    df.to_parquet(path, index=False)

    rep = V.verify(run_dir)
    assert rep["verdict"] == V.REJECT
    assert any("support is continuous" in c["check"]
               for c in rep["checks"] if c["status"] == "fail")


def test_MUTATION_breaking_the_sign_transform_is_REJECTED(run_dir):
    """If the arms are not exact negations, the second arm was re-fitted."""
    path = os.path.join(run_dir, "p2s_coefficients.parquet")
    df = pd.read_parquet(path)
    dec = df.index[df["desired_change"] == "decrease"]
    df.loc[dec[0], "coefficient"] = float(df.loc[dec[0], "coefficient"]) + 0.5
    df.to_parquet(path, index=False)

    rep = V.verify(run_dir)
    assert rep["verdict"] == V.REJECT
    assert any("exact sign transforms" in c["check"]
               for c in rep["checks"] if c["status"] == "fail")


def test_MUTATION_a_machine_local_path_is_REJECTED(run_dir):
    path = os.path.join(run_dir, "p2s_provenance.json")
    prov = json.load(open(path))
    prov["run_binding"]["cells"] = "/home/tcelab/datasets/GWCD4i.h5ad"
    json.dump(prov, open(path, "w"))

    rep = V.verify(run_dir)
    assert rep["verdict"] == V.REJECT
    assert any("machine-local path" in c["check"]
               for c in rep["checks"] if c["status"] == "fail")


def test_MUTATION_a_missing_file_REJECTS_rather_than_passing_vacuously(run_dir):
    os.remove(os.path.join(run_dir, "p2s_coefficients.parquet"))
    rep = V.verify(run_dir)
    assert rep["verdict"] == V.REJECT


# --------------------------------------------------------------------------- #
# The verifier's own independence.
# --------------------------------------------------------------------------- #
def test_the_verifier_imports_NOTHING_from_the_generator_or_from_direct():
    """A verifier that read the producer's rules would ratify whatever they currently say."""
    src = open(V.__file__).read()
    for forbidden in ("from p2s_arms", "import p2s_arms", "from direct", "import direct",
                      "from . import", "from .."):
        assert forbidden not in src, f"the verifier imports {forbidden!r}"


def test_the_verifier_re_derives_the_frozen_role_x_pole_mapping():
    assert V.DESIRED_CHANGE_BY_ROLE_AND_POLE == {
        ("away_from_A", "high"): "decrease",
        ("away_from_A", "low"): "increase",
        ("toward_B", "high"): "increase",
        ("toward_B", "low"): "decrease",
    }


def test_the_verifier_refuses_a_temporal_or_pole_keyed_arm_key():
    with pytest.raises(ValueError):
        V.parse_arm_key("temporal|treg_like|increase|Stim8hr|Stim48hr")
    with pytest.raises(ValueError):
        V.parse_arm_key("direct|treg_like|high|Stim48hr")
    with pytest.raises(ValueError):
        V.parse_arm_key("direct|treg_like|toward_B|Stim48hr")


def test_the_verifier_exit_code_follows_the_verdict(run_dir, tmp_path, capsys):
    assert V.main(["--out-dir", run_dir]) == 0
    os.remove(os.path.join(run_dir, "p2s_support.json"))
    assert V.main(["--out-dir", run_dir]) == 1


def test_the_verifier_RULES_module_is_also_independent():
    """The spec the verifier checks against must not come from the code it is checking."""
    from p2s_arms import verify_p2s_rules as R

    src = open(R.__file__).read()
    for forbidden in ("from p2s_arms", "import p2s_arms", "from direct", "import direct",
                      "from . import", "from .."):
        assert forbidden not in src, f"the verifier's spec imports {forbidden!r}"

    # the pins are LITERALS here, not borrowed
    assert R.PINNED_SOLVER_LOCK_SHA256.startswith("2983d140")
    assert R.W10_VERIFIER_ID == "spot.stage02.direct.arm_bundle.verifier.v1"
    assert R.W10_VERDICT_ADMIT == "ADMIT"        # never transliterated
