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


def _failed(rep, needle):
    return any(needle in c["check"] for c in rep["checks"] if c["status"] == "fail")


# --------------------------------------------------------------------------- #
# THE GRID — exactly 7 rows AND 7 unique slots (3 all_donor + 4 distinct LODO donors),
# and the reconstruction ships those same 7 fit slots. A set-only check misses duplicates
# and passes an empty table vacuously.
# --------------------------------------------------------------------------- #
def test_MUTATION_a_DUPLICATED_coefficient_row_is_REJECTED(run_dir):
    """8 rows / 7 unique slots must fail: a set-only grid check would pass it."""
    path = os.path.join(run_dir, "p2s_coefficients.parquet")
    df = pd.read_parquet(path)
    df = pd.concat([df, df.iloc[[0]]], ignore_index=True)     # duplicate one (arm, target, slot)
    df.to_parquet(path, index=False)

    rep = V.verify(run_dir)
    assert rep["verdict"] == V.REJECT
    assert _failed(rep, "7 OFAT slots")


def test_MUTATION_an_EMPTY_coefficient_table_is_REJECTED_not_vacuous(run_dir):
    """No keys is not 'nothing wrong'; the empty table is refused explicitly."""
    path = os.path.join(run_dir, "p2s_coefficients.parquet")
    df = pd.read_parquet(path)
    df.iloc[0:0].to_parquet(path, index=False)                # same columns, zero rows

    rep = V.verify(run_dir)
    assert rep["verdict"] == V.REJECT
    assert _failed(rep, "7 OFAT slots")


def test_MUTATION_a_MISSING_fit_slot_is_REJECTED(run_dir):
    """Drop one LODO donor's rows: 6 rows / 3 LODO donors per (arm, target) must fail."""
    path = os.path.join(run_dir, "p2s_coefficients.parquet")
    df = pd.read_parquet(path)
    lodo = sorted(s for s in df["donor_scope"].unique() if str(s).startswith("lodo_"))
    df = df[df["donor_scope"] != lodo[0]]
    df.to_parquet(path, index=False)

    rep = V.verify(run_dir)
    assert rep["verdict"] == V.REJECT
    assert _failed(rep, "7 OFAT slots")


def test_MUTATION_an_EXTRA_fit_slot_is_REJECTED(run_dir):
    """Add the forbidden log_fc+pca_off Cartesian cell: 8 unique slots must fail."""
    path = os.path.join(run_dir, "p2s_coefficients.parquet")
    df = pd.read_parquet(path)
    row = df.iloc[0].to_dict()
    row.update(effect_layer="log_fc", model_config="pca_off", donor_scope="all_donor")
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    df.to_parquet(path, index=False)

    rep = V.verify(run_dir)
    assert rep["verdict"] == V.REJECT
    assert _failed(rep, "7 OFAT slots")


# --------------------------------------------------------------------------- #
# THE KEY UNIVERSE — top-level program/condition/arm fields RE-DERIVE from the row keys.
# --------------------------------------------------------------------------- #
def test_MUTATION_dropping_ALL_sibling_rows_is_REJECTED(run_dir):
    """One arm with no sibling rows is not a valid pair — refused, not passed vacuously."""
    for f in ("p2s_arm_support.parquet", "p2s_coefficients.parquet",
              "p2s_reconstruction.parquet"):
        path = os.path.join(run_dir, f)
        df = pd.read_parquet(path)
        df = df[df["desired_change"] != "decrease"]           # strip every sibling row
        df.to_parquet(path, index=False)

    rep = V.verify(run_dir)
    assert rep["verdict"] == V.REJECT
    assert _failed(rep, "re-derive from the row keys")


def test_MUTATION_a_THIRD_program_in_the_rows_is_REJECTED(run_dir):
    """More than one program among the row keys must fail: this lane fits ONE."""
    path = os.path.join(run_dir, "p2s_arm_support.parquet")
    df = pd.read_parquet(path)
    row = df.iloc[0].to_dict()
    row.update(arm_key="direct|th1_like|increase|Stim48hr", program_id="th1_like")
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    df.to_parquet(path, index=False)

    rep = V.verify(run_dir)
    assert rep["verdict"] == V.REJECT
    assert _failed(rep, "re-derive from the row keys")


# --------------------------------------------------------------------------- #
# CONCRETE reproducibility attacks that a self-hash-only verifier ADMITTED.
# --------------------------------------------------------------------------- #
def test_MUTATION_a_NON_PROJECTED_support_column_is_caught_by_the_raw_rehash(run_dir):
    """primary_abs_coefficient is NOT in the canonical projection; editing it once ADMITTED.

    Changing it without resealing leaves every canonical hash intact, so only a RAW re-hash of
    the emitted file against the provenance artifact map catches it. This is the exact attack
    the neutral check reproduced (support value -> 987654.0, no hashes touched, still admit).
    """
    from p2s_arms import emit
    # the column really is outside the canonical support projection (or the test is moot)
    assert "primary_abs_coefficient" not in emit.canonical_support(
        [{"arm_key": "a", "target_id": "t", "n_runs": 1, "primary_coefficient": 1.0,
          "primary_sign": "supportive", "opposed": False,
          "sens_log_fc_sign_concordance": None, "sens_pca_off_sign_concordance": None,
          "lodo_sign_concordance": None}])[0]

    path = os.path.join(run_dir, "p2s_arm_support.parquet")
    df = pd.read_parquet(path)
    df.loc[0, "primary_abs_coefficient"] = 987654.0
    df.to_parquet(path, index=False)

    rep = V.verify(run_dir)
    assert rep["verdict"] == V.REJECT
    assert _failed(rep, "RAW-REHASHES to the provenance artifact map")


def test_MUTATION_a_FORGED_top_level_condition_is_REJECTED(run_dir):
    """p2s_support.json.condition -> FORGED_CONDITION without resealing once ADMITTED."""
    path = os.path.join(run_dir, "p2s_support.json")
    doc = json.load(open(path))
    doc["condition"] = "FORGED_CONDITION"
    json.dump(doc, open(path, "w"))

    rep = V.verify(run_dir)
    assert rep["verdict"] == V.REJECT
    # caught two ways: the raw re-hash of the edited doc, AND the row-key re-derivation
    assert _failed(rep, "RAW-REHASHES to the provenance artifact map")
    assert _failed(rep, "re-derive from the row keys")


def test_the_RECORDED_run_seed_is_checked_not_only_the_declared_wrapper_seed(run_dir):
    """A run fitted under an off-pin seed but declaring 42 in its method block is caught."""
    path = os.path.join(run_dir, "p2s_provenance.json")
    prov = json.load(open(path))
    prov["run_binding"]["seed"] = 7
    json.dump(prov, open(path, "w"))

    rep = V.verify(run_dir)
    assert rep["verdict"] == V.REJECT
    assert _failed(rep, "RUN recorded the pinned seed")


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
