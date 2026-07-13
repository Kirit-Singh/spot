"""PRODUCTION INPUT PREPARATION — the real, pinned Marson inputs.

Until this lane existed, the ONLY things that could produce ``cells.npz``,
``effects.parquet`` and ``eligible.parquet`` were the synthetic builders. A lane whose inputs
can only be made up is not production-runnable, whatever its tests say.

The fixtures here are tiny but STRUCTURALLY REAL: CSR float32 storage, the real obs/var
layout, the real barcode format, symbols in the cell matrix and Ensembl in the readout. Only
the numbers are synthetic — the layout is the one preparation will actually meet.

The PINS are monkeypatched to the fixture bytes. The pin MECHANISM is what is under test (a
mismatch must refuse); pinning the real 3.8 GB matrix into a unit test would only prove that
two large files are equal to themselves.
"""
from __future__ import annotations

import json
import os

import fixtures_p2s as fx
import numpy as np
import pytest
from p2s_arms import config, prepare_cells, prepare_inputs, stage1_canonical
from p2s_arms import disposition as D
from p2s_arms.w10 import file_sha256

CONDITION = "Stim48hr"
REQUIRED_FLAGS = ("--ntc", "--stage1-scores", "--de-main", "--direct-bundle",
                  "--w10-report", "--env-lock", "--p2s-env-lock", "--stage1-release",
                  "--condition")


@pytest.fixture
def real_inputs(tmp_path, view, bundle_dir, w10_report, p2s_lock, monkeypatch):
    """The pinned public inputs, in their real shape — with the pins set to these bytes."""
    programs = list(view["admitted_program_ids"])
    ntc = fx.write_ntc_h5ad(str(tmp_path / "ntc.h5ad"))
    scores = fx.write_stage1_scores(str(tmp_path / "scores.parquet"), ntc, programs)
    de = fx.write_de_readout(str(tmp_path / "de.h5ad"), fx.target_ids())

    monkeypatch.setitem(prepare_inputs.PINS, "ntc", file_sha256(ntc))
    monkeypatch.setitem(prepare_inputs.PINS, "de_main", file_sha256(de))
    monkeypatch.setitem(prepare_inputs.PINS, "stage1_scores", file_sha256(scores))
    _pin_canonical(scores, monkeypatch)
    return {"ntc": ntc, "scores": scores, "de": de, "bundle": bundle_dir,
            "w10": w10_report, "programs": programs, "view": view, "p2s_lock": p2s_lock}


def _pin_canonical(scores_path, monkeypatch):
    """Point the canonical gate at THIS fixture table's own hash (the mechanism is the test)."""
    import pandas as pd
    df = pd.read_parquet(scores_path)
    monkeypatch.setattr(stage1_canonical, "EXPECTED",
                        stage1_canonical.canonical_scores_sha256(df))


def _argv(ri, tmp_path, **over):
    a = {
        "--ntc": ri["ntc"], "--stage1-scores": ri["scores"], "--de-main": ri["de"],
        "--direct-bundle": ri["bundle"], "--w10-report": ri["w10"],
        "--env-lock": fx.REAL_SOLVER_LOCK, "--p2s-env-lock": ri["p2s_lock"],
        "--stage1-release": "unused-in-fixture-lane",
        "--condition": CONDITION, "--out-root": str(tmp_path / "prepared"),
        "--lane": "synthetic", "--release-kind": "fixture",
    }
    a.update(over)
    out = []
    for k, v in a.items():
        if v is not None:
            out += [k, str(v)]
    return out


def _build(ri, tmp_path, view=None, **over):
    args = prepare_inputs.build_parser().parse_args(_argv(ri, tmp_path, **over))
    return prepare_inputs.build(args, release=fx.make_release(),
                                view=view if view is not None else ri["view"])


# --------------------------------------------------------------------------- #
# THE CLI CONTRACT.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("flag", REQUIRED_FLAGS)
def test_every_input_is_REQUIRED_not_defaulted(flag):
    action = next(a for a in prepare_inputs.build_parser()._actions
                  if flag in a.option_strings)
    assert action.required is True


def test_omitting_an_input_is_a_parser_error():
    with pytest.raises(SystemExit):
        prepare_inputs.build_parser().parse_args(["--condition", CONDITION])


# --------------------------------------------------------------------------- #
# THE HAPPY PATH — and what it actually produced.
# --------------------------------------------------------------------------- #
def test_preparation_emits_the_four_inputs_the_producer_eats(real_inputs, tmp_path):
    out = _build(real_inputs, tmp_path)
    d = out["out_dir"]
    for f in prepare_inputs.ARTIFACT_FILES + (prepare_inputs.MANIFEST_FILE,):
        assert os.path.exists(os.path.join(d, f)), f
    # the directory NAME is the content hash of the binding
    assert os.path.basename(d) == out["p2s_inputs_run_id"]


def test_the_SCORES_are_READ_by_barcode_never_recomputed(real_inputs, tmp_path):
    """The one thing this lane must never do is compute a Stage-1 score."""
    import pandas as pd

    out = _build(real_inputs, tmp_path)
    z = np.load(out["paths"]["cells"], allow_pickle=False)
    src = pd.read_parquet(real_inputs["scores"]).set_index("barcode")

    bcs = [str(b) for b in z["barcodes"]]
    for p in real_inputs["programs"]:
        got = z[f"score__{p}"]
        want = src.loc[bcs, f"{p}{config.SCORE_FIELD_SUFFIX}"].to_numpy(dtype=float)
        assert np.array_equal(got, want), f"{p}: the score was not read verbatim"

    m = out["manifest"]
    assert m["barcode_join"]["scores_are_read_not_recomputed"] is True
    assert m["barcode_join"]["join_key"] == "barcode"
    assert m["barcode_join"]["n_cells_without_a_score_row"] == 0


def test_the_cells_are_in_the_READOUTS_namespace_not_the_matrixs(real_inputs, tmp_path):
    """The cell matrix is keyed on SYMBOLS; the arms are computed in ENSEMBL."""
    out = _build(real_inputs, tmp_path)
    z = np.load(out["paths"]["cells"], allow_pickle=False)
    gene_ids = [str(g) for g in z["gene_ids"]]

    assert gene_ids, "no gene survived the crossing"
    assert all(g.startswith("ENSG") for g in gene_ids)
    assert gene_ids == sorted(gene_ids)              # ONE canonical order

    ns = out["manifest"]["gene_namespace"]
    assert ns["cells"] == "symbol" and ns["readout"] == "ensembl"
    assert ns["ambiguous_symbols_are_dropped_never_guessed"] is True


def test_masks_and_eligibility_come_from_the_ADMITTED_BUNDLE_not_recomputed(real_inputs,
                                                                            tmp_path):
    """A mask this lane computed for itself would be a different mask with the same name."""
    import pandas as pd

    out = _build(real_inputs, tmp_path)
    got = pd.read_parquet(out["paths"]["masks"])
    src = pd.read_parquet(os.path.join(real_inputs["bundle"], "masks.parquet"))
    assert set(got["target_id"]) <= set(src["target_id"].astype(str))

    elig = pd.read_parquet(out["paths"]["eligible"])
    assert set(elig["state"]) <= set(config.QC_PASS_STATES)


def test_the_manifest_BINDS_hashes_dims_joins_programs_condition_and_code(real_inputs,
                                                                          tmp_path):
    m = _build(real_inputs, tmp_path)["manifest"]

    assert set(m["raw_input_sha256"]) == {"ntc_h5ad", "stage1_scores", "de_main"}
    assert all(len(v) == 64 for v in m["raw_input_sha256"].values())
    assert m["dims"]["n_cells"] > 0 and m["dims"]["n_genes"] > 0
    assert m["condition"] == CONDITION
    assert sorted(m["program_ids"]) == m["program_ids"]
    # the activation covariate is SCORED (for the design) but is NOT an arm: it appears in the
    # score programs and is excluded from the arm programs, so no run queues a guaranteed refusal.
    assert config.ACTIVATION_PROGRAM_ID in m["score_program_ids"]
    assert config.ACTIVATION_PROGRAM_ID not in m["program_ids"]
    assert m["code_identity"]["commit"]
    assert m["direct_binding"]["solver_lock_sha256"].startswith("2983d140")
    assert m["direct_binding"]["w10_verdict"] == "ADMIT"
    assert m["artifact_sha256"] and len(m["artifact_sha256"]) == 4


def test_preparation_is_DETERMINISTIC_and_content_addressed(real_inputs, tmp_path):
    a = _build(real_inputs, tmp_path)
    b = _build(real_inputs, tmp_path)
    assert a["p2s_inputs_run_id"] == b["p2s_inputs_run_id"]
    assert a["manifest"]["artifact_sha256"] == b["manifest"]["artifact_sha256"]


def test_the_prepared_inputs_LOAD_in_the_producer(real_inputs, tmp_path):
    """The whole point: the producer's own loaders must accept these bytes."""
    from p2s_arms import io_data

    out = _build(real_inputs, tmp_path)
    cells = io_data.load_cells(out["paths"]["cells"])
    effects = io_data.load_effects(out["paths"]["effects"])
    masks = io_data.load_masks(out["paths"]["masks"])
    elig = io_data.load_eligible(out["paths"]["eligible"])

    assert cells["n_cells"] > 0
    assert set(effects["layers"]) == {"zscore", "log_fc"}
    assert masks["rows"] and elig["targets"]
    # the readout universe is a subset of what the cells carry
    assert set(effects["gene_ids"]) >= set(cells["gene_ids"])


# --------------------------------------------------------------------------- #
# REFUSALS.
# --------------------------------------------------------------------------- #
def test_MUTATION_an_UNPINNED_input_is_refused(real_inputs, tmp_path, monkeypatch):
    monkeypatch.setitem(prepare_inputs.PINS, "ntc", "0" * 64)
    with pytest.raises(D.RefusalError) as e:
        _build(real_inputs, tmp_path)
    assert e.value.reason == D.REFUSE_INPUT_NOT_PINNED


def test_MUTATION_the_DE_pin_failure_names_the_tcedirector_read(real_inputs, tmp_path,
                                                                monkeypatch):
    """tcedirector reads DE_stats non-deterministically. Say so, or somebody blames the pin."""
    monkeypatch.setitem(prepare_inputs.PINS, "de_main", "0" * 64)
    with pytest.raises(D.RefusalError) as e:
        _build(real_inputs, tmp_path)
    assert e.value.reason == D.REFUSE_INPUT_NOT_PINNED
    assert "NON-DETERMINISTICALLY" in str(e.value) and "tcefold" in str(e.value)


def test_MUTATION_a_DUPLICATE_barcode_is_refused(tmp_path, view, bundle_dir, w10_report,
                                                 p2s_lock, monkeypatch):
    ntc = fx.write_ntc_h5ad(str(tmp_path / "ntc.h5ad"))
    scores = fx.write_stage1_scores(str(tmp_path / "s.parquet"),
                                    ntc, view["admitted_program_ids"], duplicate=True)
    de = fx.write_de_readout(str(tmp_path / "de.h5ad"), fx.target_ids())
    monkeypatch.setitem(prepare_inputs.PINS, "ntc", file_sha256(ntc))
    monkeypatch.setitem(prepare_inputs.PINS, "de_main", file_sha256(de))
    monkeypatch.setitem(prepare_inputs.PINS, "stage1_scores", file_sha256(scores))

    _pin_canonical(scores, monkeypatch)
    ri = {"ntc": ntc, "scores": scores, "de": de, "bundle": bundle_dir,
          "w10": w10_report, "view": view, "p2s_lock": p2s_lock}
    with pytest.raises(D.RefusalError) as e:
        _build(ri, tmp_path)
    assert e.value.reason == D.REFUSE_DUPLICATE_BARCODE


def test_MUTATION_a_cell_with_NO_score_row_is_refused_never_imputed(
        tmp_path, view, bundle_dir, w10_report, p2s_lock, monkeypatch):
    """An absent score is not a score of zero."""
    ntc = fx.write_ntc_h5ad(str(tmp_path / "ntc.h5ad"))
    scores = fx.write_stage1_scores(str(tmp_path / "s.parquet"), ntc,
                                    view["admitted_program_ids"], drop_barcodes=5)
    de = fx.write_de_readout(str(tmp_path / "de.h5ad"), fx.target_ids())
    monkeypatch.setitem(prepare_inputs.PINS, "ntc", file_sha256(ntc))
    monkeypatch.setitem(prepare_inputs.PINS, "de_main", file_sha256(de))
    monkeypatch.setitem(prepare_inputs.PINS, "stage1_scores", file_sha256(scores))

    _pin_canonical(scores, monkeypatch)
    ri = {"ntc": ntc, "scores": scores, "de": de, "bundle": bundle_dir,
          "w10": w10_report, "view": view, "p2s_lock": p2s_lock}
    with pytest.raises(D.RefusalError) as e:
        _build(ri, tmp_path)
    assert e.value.reason == D.REFUSE_MISSING_BARCODE
    assert "not a score of zero" in str(e.value)


def test_MUTATION_a_program_the_release_admits_but_stage1_never_scored_is_refused(
        tmp_path, view, bundle_dir, w10_report, p2s_lock, monkeypatch):
    ntc = fx.write_ntc_h5ad(str(tmp_path / "ntc.h5ad"))
    scores = fx.write_stage1_scores(str(tmp_path / "s.parquet"), ntc,
                                    view["admitted_program_ids"],
                                    omit_program="th1_like")
    de = fx.write_de_readout(str(tmp_path / "de.h5ad"), fx.target_ids())
    monkeypatch.setitem(prepare_inputs.PINS, "ntc", file_sha256(ntc))
    monkeypatch.setitem(prepare_inputs.PINS, "de_main", file_sha256(de))
    monkeypatch.setitem(prepare_inputs.PINS, "stage1_scores", file_sha256(scores))
    # deliberately NOT pinning canonical: a table missing an admitted program's score column
    # is missing a canonical field, and the canonical recipe refuses it BY THAT REASON.
    ri = {"ntc": ntc, "scores": scores, "de": de, "bundle": bundle_dir,
          "w10": w10_report, "view": view, "p2s_lock": p2s_lock}
    with pytest.raises(D.RefusalError) as e:
        _build(ri, tmp_path)
    assert e.value.reason == D.REFUSE_PROGRAM_SET_MISMATCH


def test_MUTATION_an_AMBIGUOUS_symbol_is_DROPPED_not_guessed():
    """Picking one would attach the cell's expression to a gene nobody chose."""
    xw = prepare_cells.crosswalk_symbols(
        cell_symbols=["GOOD", "AMBIG", "UNKNOWN"],
        readout_gene_ids=["ENSG1", "ENSG2", "ENSG3"],
        readout_symbols=["GOOD", "AMBIG", "AMBIG"])          # AMBIG names two ids
    assert xw["symbol_to_ensembl"] == {"GOOD": "ENSG1"}
    assert xw["n_ambiguous_dropped"] == 1
    assert xw["n_absent_from_readout"] == 1
    assert "AMBIG" in xw["ambiguous_examples"]


def test_MUTATION_total_namespace_drift_is_refused():
    """Two files that share no gene are not describing the same organism."""
    with pytest.raises(D.RefusalError) as e:
        prepare_cells.crosswalk_symbols(
            cell_symbols=["A", "B"], readout_gene_ids=["ENSG1"], readout_symbols=["Z"])
    assert e.value.reason == D.REFUSE_NAMESPACE_DRIFT


@pytest.mark.parametrize("path", [
    "/data/fixtures/ntc.h5ad", "/x/synthetic/cells.h5ad", "/repo/tests/ntc.h5ad",
    "/tmp/mock_ntc.h5ad",
])
def test_MUTATION_a_FIXTURE_PATH_is_refused_by_name(path):
    with pytest.raises(D.RefusalError) as e:
        prepare_inputs.refuse_fixture_path("ntc", path)
    assert e.value.reason == D.REFUSE_FIXTURE_PATH


def test_an_ordinary_scratch_path_is_NOT_refused():
    """A firewall that refuses every working path is a firewall somebody turns off."""
    prepare_inputs.refuse_fixture_path("ntc", "/home/tcelab/.spot-runs/20260713Z/ntc.h5ad")
    prepare_inputs.refuse_fixture_path("ntc", "/tmp/staging/ntc.h5ad")


def test_MUTATION_the_wrong_CONDITION_for_the_admitted_bundle_is_refused(real_inputs,
                                                                         tmp_path):
    with pytest.raises(D.RefusalError) as e:
        _build(real_inputs, tmp_path, **{"--condition": "Rest"})
    assert e.value.reason == D.REFUSE_CONDITION_MISMATCH


def test_MUTATION_a_SUBSAMPLE_may_not_feed_a_production_run(real_inputs, tmp_path):
    """It produces real-looking numbers from a fraction of the cohort."""
    with pytest.raises(D.RefusalError) as e:
        _build(real_inputs, tmp_path, **{"--max-cells": "10", "--lane": "production"})
    assert e.value.reason == D.REFUSE_SUBSAMPLE_IN_PRODUCTION


def test_a_SMOKE_subsample_is_recorded_and_changes_the_content_id(real_inputs, tmp_path):
    full = _build(real_inputs, tmp_path)
    smoke = _build(real_inputs, tmp_path, **{"--max-cells": "20"})

    assert smoke["manifest"]["subsample"]["applied"] is True
    assert smoke["manifest"]["subsample"]["n_requested"] == 20
    assert smoke["manifest"]["dims"]["n_cells"] <= 20
    assert smoke["p2s_inputs_run_id"] != full["p2s_inputs_run_id"]
    assert full["manifest"]["subsample"]["applied"] is False


def test_the_CLI_refuses_with_exit_2_and_a_named_reason(real_inputs, tmp_path, monkeypatch,
                                                        capsys):
    """Exit 2 and a NAMED reason — a scheduler must tell "declined" from "crashed"."""
    monkeypatch.setitem(prepare_inputs.PINS, "ntc", "0" * 64)
    code = prepare_inputs.main(_argv(real_inputs, tmp_path))
    assert code == 2
    err = json.loads(capsys.readouterr().err)
    assert err["state"] == "refused"
    assert err["reason"] == D.REFUSE_INPUT_NOT_PINNED


def test_identity_comes_from_the_BOUND_target_identity_json_not_inferred(real_inputs,
                                                                          tmp_path):
    """A symbol-namespace target's null target_ensembl is legitimate BY DECLARATION.

    The producer's target_identity.json declares each target's namespace; the shared loader
    verifies a gene_symbol row carries no Ensembl id. So a null is authoritative, never
    inferred from a mask or a target_id heuristic.
    """
    m = _build(real_inputs, tmp_path)["manifest"]
    assert m["identity_inferred_from_mask_or_target_id"] is False
    ti = m["target_identity"]
    assert ti["schema_version"] == "spot.stage02_target_identity.v1"
    assert len(ti["raw_sha256"]) == 64 and len(ti["canonical_sha256"]) == 64
    assert ti["observed_perturbation_modality"] == "CRISPRi_knockdown"
    # the eligible rows carry the DECLARED namespace, not a guess
    import pandas as pd
    elig = pd.read_parquet(_build(real_inputs, tmp_path)["paths"]["eligible"])
    assert "target_id_namespace" in elig.columns
