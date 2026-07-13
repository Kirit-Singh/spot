"""PREPARED-INPUT VERIFICATION — the A-vs-B Direct binding and the source-input pins.

Two independent things are proven here.

THE A-vs-B BINDING IS NOT FAIL-OPEN
-----------------------------------
The matrices a run fits were prepared from ONE admitted Direct bundle (A, recorded in the
manifest's ``direct_binding``). The run then admits a bundle of its own (B). If A and B are
not the same bundle, the run would fit matrices from A while binding B's provenance. The
cross-check must therefore REQUIRE the binding (a missing one is a refusal, never a skip),
require every field present and nonempty on both sides, and refuse on the first disagreement.

THE SOURCE INPUTS ARE PINNED TO CODE LITERALS
--------------------------------------------
The manifest carries its own observed hashes; comparing them to the pins in THIS lane's code
(never to the manifest's copy of them) is what refuses matrices prepared from a re-pinned or
swapped NTC / DE readout.
"""
from __future__ import annotations

import fixtures_p2s as fx
import pytest
from p2s_arms import binding, config, prepare_inputs, prepared, stage1_canonical
from p2s_arms import disposition as D
from p2s_arms.w10 import file_sha256

CONDITION = "Stim48hr"

GOOD_BINDING = {
    "arm_bundle_run_id": "a" * 16,
    "arm_bundle_run_sha256": "b" * 64,
    "arm_rows_sha256": "c" * 64,
    "scorer_view_sha256": "d" * 64,
    "direct_bundle_artifact_map_sha256": "e" * 64,
    "target_identity_admitted_sha256": "f" * 64,
    "target_identity_canonical_sha256": "0" * 64,
}


# --------------------------------------------------------------------------- #
# THE A-vs-B binding, isolated. Every field must be PRESENT, NONEMPTY and EQUAL.
# --------------------------------------------------------------------------- #
def test_A_equals_B_passes_when_the_bundle_is_the_same():
    m = {"direct_binding": dict(GOOD_BINDING)}
    prepared._check_direct_binding_A_equals_B(m, dict(GOOD_BINDING))     # must not raise


def test_a_MISSING_direct_binding_block_is_REFUSED_not_skipped():
    with pytest.raises(D.RefusalError) as e:
        prepared._check_direct_binding_A_equals_B({}, dict(GOOD_BINDING))
    assert e.value.reason == D.REFUSE_PREPARED_PIN_DRIFT


@pytest.mark.parametrize("field", list(prepared._AB_BINDING_KEYS))
def test_DELETING_each_binding_field_is_REFUSED(field):
    db = dict(GOOD_BINDING)
    del db[field]
    with pytest.raises(D.RefusalError) as e:
        prepared._check_direct_binding_A_equals_B({"direct_binding": db}, dict(GOOD_BINDING))
    assert e.value.reason == D.REFUSE_PREPARED_PIN_DRIFT


@pytest.mark.parametrize("field", list(prepared._AB_BINDING_KEYS))
def test_an_EMPTY_binding_value_is_REFUSED(field):
    db = dict(GOOD_BINDING, **{field: ""})
    with pytest.raises(D.RefusalError) as e:
        prepared._check_direct_binding_A_equals_B({"direct_binding": db}, dict(GOOD_BINDING))
    assert e.value.reason == D.REFUSE_PREPARED_PIN_DRIFT


@pytest.mark.parametrize("field", list(prepared._AB_BINDING_KEYS))
def test_SWAPPING_A_from_bundle_A_to_bundle_B_is_REFUSED(field):
    """A != B on any single field: the inputs were prepared from a DIFFERENT admitted bundle."""
    b = dict(GOOD_BINDING, **{field: "9" * len(GOOD_BINDING[field])})
    with pytest.raises(D.RefusalError) as e:
        prepared._check_direct_binding_A_equals_B({"direct_binding": dict(GOOD_BINDING)}, b)
    assert e.value.reason == D.REFUSE_PREPARED_PIN_DRIFT


# --------------------------------------------------------------------------- #
# THE WHOLE CHAIN, over REAL prepared inputs. A-vs-B passes for the SAME bundle,
# the source pins are checked against code literals, and a swapped bundle B refuses.
# --------------------------------------------------------------------------- #
@pytest.fixture
def prepared_run(tmp_path, view, bundle_dir, w10_report, p2s_lock, monkeypatch):
    """Real prepared inputs, with config pins pointed at the fixture bytes (the mechanism)."""
    programs = list(view["admitted_program_ids"])
    ntc = fx.write_ntc_h5ad(str(tmp_path / "ntc.h5ad"))
    scores = fx.write_stage1_scores(str(tmp_path / "scores.parquet"), ntc, programs)
    de = fx.write_de_readout(str(tmp_path / "de.h5ad"), fx.target_ids())

    monkeypatch.setitem(prepare_inputs.PINS, "ntc", file_sha256(ntc))
    monkeypatch.setitem(prepare_inputs.PINS, "de_main", file_sha256(de))
    monkeypatch.setitem(prepare_inputs.PINS, "stage1_scores", file_sha256(scores))
    import pandas as pd
    monkeypatch.setattr(stage1_canonical, "EXPECTED",
                        stage1_canonical.canonical_scores_sha256(pd.read_parquet(scores)))

    argv = ["--ntc", ntc, "--stage1-scores", scores, "--de-main", de,
            "--direct-bundle", bundle_dir, "--w10-report", w10_report,
            "--env-lock", fx.REAL_SOLVER_LOCK, "--p2s-env-lock", p2s_lock,
            "--stage1-release", "unused", "--condition", CONDITION,
            "--out-root", str(tmp_path / "prepared"), "--lane", "synthetic",
            "--release-kind", "fixture"]
    args = prepare_inputs.build_parser().parse_args(argv)
    out = prepare_inputs.build(args, release=fx.make_release(), view=view)

    # point the CODE LITERALS at the fixture's own recorded hashes: load_and_verify compares
    # the manifest to config, and here config IS the fixture (the comparison is the mechanism).
    m = out["manifest"]
    monkeypatch.setattr(config, "NTC_H5AD_SHA256", m["raw_input_sha256"]["ntc_h5ad"])
    monkeypatch.setattr(config, "DE_MAIN_SHA256", m["raw_input_sha256"]["de_main"])
    monkeypatch.setattr(config, "STAGE1_SCORES_RAW_SHA256",
                        m["stage1_scores"]["raw_sha256"])
    monkeypatch.setattr(config, "STAGE1_SCORES_CANONICAL_SHA256",
                        m["stage1_scores"]["canonical_scores_sha256"])

    admission = binding.admit_inputs(
        bundle_dir=bundle_dir, w10_report=w10_report,
        env_lock=fx.REAL_SOLVER_LOCK, lane="synthetic")["admission"]
    return {"out_dir": out["out_dir"], "manifest": m, "admission": admission}


def test_the_whole_prepared_chain_VERIFIES_for_the_same_bundle(prepared_run):
    got = prepared.load_and_verify(prepared_run["out_dir"], condition=CONDITION,
                                   lane="synthetic", admitted=prepared_run["admission"])
    assert got["artifact_sha256_verified"] is True
    assert got["self_id_rederived"] is True


def test_a_swapped_NTC_pin_is_REFUSED(prepared_run, monkeypatch):
    monkeypatch.setattr(config, "NTC_H5AD_SHA256", "0" * 64)
    with pytest.raises(D.RefusalError) as e:
        prepared.load_and_verify(prepared_run["out_dir"], condition=CONDITION,
                                 lane="synthetic", admitted=prepared_run["admission"])
    assert e.value.reason == D.REFUSE_PREPARED_PIN_DRIFT


def test_a_swapped_DE_pin_is_REFUSED(prepared_run, monkeypatch):
    monkeypatch.setattr(config, "DE_MAIN_SHA256", "0" * 64)
    with pytest.raises(D.RefusalError) as e:
        prepared.load_and_verify(prepared_run["out_dir"], condition=CONDITION,
                                 lane="synthetic", admitted=prepared_run["admission"])
    assert e.value.reason == D.REFUSE_PREPARED_PIN_DRIFT


def test_inputs_prepared_from_bundle_A_refuse_to_run_under_bundle_B(prepared_run, tmp_path,
                                                                    view):
    """The run admits a DIFFERENT bundle than the inputs were prepared from — refused."""
    d2 = fx.write_full_bundle(str(tmp_path / "d2"), view, condition="Rest")
    r2 = fx.write_w10_report(str(tmp_path / "r2.json"), d2, view, condition="Rest")
    admission_B = binding.admit_inputs(
        bundle_dir=d2, w10_report=r2, env_lock=fx.REAL_SOLVER_LOCK,
        lane="synthetic")["admission"]

    with pytest.raises(D.RefusalError) as e:
        prepared.load_and_verify(prepared_run["out_dir"], condition=CONDITION,
                                 lane="synthetic", admitted=admission_B)
    assert e.value.reason == D.REFUSE_PREPARED_PIN_DRIFT
