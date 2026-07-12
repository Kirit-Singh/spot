"""Every reproduced trust/reproducibility attack, turned into a test.

Nothing here may pass by self-attestation: a forged value that is re-hashed by
its own forger must still fail.
"""
import json
import os
import shutil

import pandas as pd
import pytest

from direct import trust
from direct.manifest import ManifestError
from direct.run_screen import build_screen
from direct.selection import SelectionError
from direct.trust import TrustError
from direct.verify_run import main as verify_main

from fixtures_direct import (CONDITION, SOURCE_NAME, TARGET_GENES,
                             write_stage1_gates)


def _edit_json(path, fn):
    with open(path) as fh:
        doc = json.load(fh)
    doc = fn(doc) or doc
    with open(path, "w") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)


# --------------------------------------------------------------------------- #
# 1. Stage-1 trust is not forgeable.
# --------------------------------------------------------------------------- #
def test_a_registry_internal_self_hash_is_never_accepted_as_the_binding(synthetic_run):
    """A file cannot attest to itself. A contract that points at the registry's own
    self-declared hash must be refused: the binding is the INDEPENDENTLY DERIVED
    canonical content, which excludes the self-hash field entirely."""
    forged = "f" * 64
    args = synthetic_run()
    _edit_json(args.registry, lambda d: d.update({"registry_sha256": forged}) or d)
    _edit_json(args.selection,
               lambda d: d["hashes"].update({"registry_sha256": forged}) or d)
    with pytest.raises(SelectionError, match="internal self-hash is not a binding"):
        build_screen(args)


def test_the_derived_registry_binding_ignores_an_injected_self_hash(synthetic_run):
    """Injecting a self-hash field must not change the derived canonical content,
    so a correctly-bound contract keeps working and the forgery buys nothing."""
    from direct.trust import canonical_content_sha256
    args = synthetic_run()
    before = canonical_content_sha256(json.load(open(args.registry)))
    _edit_json(args.registry, lambda d: d.update({"registry_sha256": "f" * 64}) or d)
    after = canonical_content_sha256(json.load(open(args.registry)))
    assert after == before                 # the self-hash is not part of the content


def test_a_forged_selectable_boolean_cannot_make_a_pair_selectable(synthetic_run):
    """The registry's stored booleans are never read; the gate is re-derived."""
    args = synthetic_run(stage1_selectable=False,
                         registry_extra={"stage2_selectable": True,
                                         "production_selectable": True})
    with pytest.raises(SelectionError, match="NOT production-selectable"):
        build_screen(args)


def test_a_forged_validation_verdict_row_cannot_pass_the_gate(synthetic_run):
    """Validation rows carry a stored 'passed': true. It must be ignored and the
    metric re-compared against the gate spec."""
    args = synthetic_run(stage1_selectable=False)
    _edit_json(args.stage1_validation, lambda d: [
        r.update({"passed": True, "stage2_selectable": True}) for r in d["rows"]] and d)
    with pytest.raises(SelectionError, match="NOT production-selectable"):
        build_screen(args)


def test_the_frozen_zero_of_33_gate_refuses_every_pair(synthetic_run):
    args = synthetic_run(stage1_selectable=False)
    with pytest.raises(SelectionError) as exc:
        build_screen(args)
    assert "0/" in str(exc.value)          # 0 of N pairs pass


def test_an_unknown_gate_comparator_cannot_pass(tmp_path):
    d = str(tmp_path)
    val, gate = write_stage1_gates(d, selectable=True)
    _edit_json(gate, lambda doc: doc["thresholds"]["separability"].update(
        {"comparator": "always_true"}) or doc)
    with pytest.raises(TrustError, match="unknown comparator"):
        trust.load_fixture_release(os.path.join(d, "nope.json"), val, gate) \
            if False else trust.derive_selectable_pairs(
                json.load(open(val)), json.load(open(gate)))


def test_an_unmeasured_hard_gate_cannot_pass(tmp_path):
    d = str(tmp_path)
    val, gate = write_stage1_gates(d, selectable=True)
    _edit_json(val, lambda doc: doc.update(
        {"rows": [r for r in doc["rows"] if r["gate_id"] != "donor_stability"]}) or doc)
    pairs, ev = trust.derive_selectable_pairs(json.load(open(val)),
                                              json.load(open(gate)))
    assert pairs == frozenset()            # incomplete evidence never passes
    assert ev["n_production_selectable"] == 0


def test_a_production_run_without_a_stage1_release_fails_closed(synthetic_run):
    # production-namespaced ids, so the run reaches the release gate
    args = synthetic_run(lane="production", program_prefix="")
    args.stage1_release = None
    with pytest.raises(SelectionError, match="requires --stage1-release"):
        build_screen(args)


def test_a_fixture_run_id_can_never_enter_production(synthetic_run):
    """The synthetic-to-production attack: the RUN-ID namespace IS the lane."""
    args = synthetic_run(lane="production", program_prefix="",
                         ids={"question_id": "fx_abc", "selection_id": "fx_def"})
    with pytest.raises(SelectionError, match="production loader refuses"):
        build_screen(args)


def test_a_research_run_id_can_never_enter_production(synthetic_run):
    args = synthetic_run(lane="production", program_prefix="",
                         ids={"question_id": "rq_abc", "selection_id": "rq_def"})
    with pytest.raises(SelectionError,
                       match="research-namespace|production loader refuses"):
        build_screen(args)


def test_a_production_run_id_cannot_run_as_a_fixture(synthetic_run):
    args = synthetic_run(lane="synthetic",
                         ids={"question_id": "q_plain", "selection_id": "s_plain"})
    with pytest.raises(SelectionError, match="fixture loader requires"):
        build_screen(args)


def test_a_production_release_manifest_missing_a_binding_is_fatal(tmp_path):
    d = str(tmp_path)
    path = os.path.join(d, "release.json")
    with open(path, "w") as fh:
        json.dump({"schema_version": trust.RELEASE_SCHEMA,
                   "method_version": "stage1-continuous-v3.0.1",
                   "artifacts": {"registry": {"path": "r.json",
                                              "raw_sha256": "0" * 64,
                                              "canonical_sha256": "0" * 64}}},
                  fh)
    with pytest.raises(TrustError, match="required bindings omitted"):
        trust.load_production_release(path)


def test_a_tampered_stage1_artifact_fails_its_raw_hash(tmp_path):
    d = str(tmp_path)
    reg = os.path.join(d, "r.json")
    with open(reg, "w") as fh:
        json.dump({"programs": [{"program_id": "p", "panel_ensembl": ["ENSG1"],
                                 "control_ensembl": ["ENSG2"]}]}, fh)
    from direct.hashing import file_sha256
    good_raw = file_sha256(reg)
    entry = {"path": "r.json", "raw_sha256": good_raw,
             "canonical_sha256": trust.canonical_content_sha256(json.load(open(reg)))}
    assert trust._verify_artifact("registry", entry, d)["raw_sha256"] == good_raw

    with open(reg, "a") as fh:             # tamper AFTER pinning
        fh.write(" ")
    with pytest.raises(TrustError, match="raw bytes do not match"):
        trust._verify_artifact("registry", entry, d)


def test_a_re_self_hashed_selection_contract_still_fails(synthetic_run):
    """Tamper with the science, then recompute the contract's own file hash. The
    ids are derived from the science, so the forgery cannot reproduce them."""
    args = synthetic_run()
    _edit_json(args.selection, lambda d: d["B"].update({"direction": "low"}) or d)
    with pytest.raises(SelectionError, match="identifier mismatch"):
        build_screen(args)


# --------------------------------------------------------------------------- #
# 2. Contributor identity is not self-declared.
# --------------------------------------------------------------------------- #
def test_a_manifest_without_a_trusted_source_registry_fails_closed(synthetic_run):
    args = synthetic_run(source_registry=False)
    with pytest.raises(ManifestError, match="no trusted source registry"):
        build_screen(args)


def test_an_invented_source_not_in_the_trusted_registry_fails_closed(synthetic_run):
    args = synthetic_run(manifest_sources=[
        {"name": "invented_source.h5ad", "sha256": "a" * 64,
         "revision": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"}])
    with pytest.raises(ManifestError, match="not in the trusted source registry"):
        build_screen(args)


def test_a_source_whose_bytes_do_not_match_its_pin_fails_closed(synthetic_run):
    args = synthetic_run()
    src = os.path.join(os.path.dirname(args.source_registry), SOURCE_NAME)
    with open(src, "a") as fh:
        fh.write("tampered")               # bytes no longer hash to the pin
    with pytest.raises(ManifestError, match="raw bytes hash to"):
        build_screen(args)


def test_an_invented_identity_method_is_not_a_proof(synthetic_run):
    def attack(rows):
        for r in rows:
            if r["estimate_id"] == "main":
                r["identity_method"] = "i_promise_this_is_right"
        return rows

    with pytest.raises(ManifestError, match="is not one of"):
        build_screen(synthetic_run(manifest_rows_fn=attack))


def test_a_row_source_hash_that_does_not_match_its_source_fails_closed(synthetic_run):
    def attack(rows):
        rows[0]["source_sha256"] = "b" * 64
        return rows

    with pytest.raises(ManifestError, match="source_sha256 does not match"):
        build_screen(synthetic_run(manifest_rows_fn=attack))


def test_a_row_naming_an_unlisted_source_fails_closed(synthetic_run):
    def attack(rows):
        rows[0]["source_id"] = "some_other_file.h5ad"
        return rows

    with pytest.raises(ManifestError, match="not one of the manifest's verified"):
        build_screen(synthetic_run(manifest_rows_fn=attack))


def test_a_row_without_a_source_record_locator_fails_closed(synthetic_run):
    """The citation is stripped AFTER it is minted: a determined row that cites nothing
    has no evidence, and is refused rather than downgraded to ambiguous."""
    def attack(rows):
        for r in rows:
            if r.get("evidence_state") == "determined":
                r.pop("source_record_id")
                break
        return rows

    with pytest.raises(ManifestError, match="must bind 'source_record_id'"):
        build_screen(synthetic_run(manifest_final_fn=attack))


def test_a_quarantined_source_may_never_be_consumed(synthetic_run):
    args = synthetic_run(manifest_sources=[
        {"name": "contributing_guides.canonical.csv.gz", "sha256": "a" * 64,
         "revision": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"}])
    with pytest.raises(ManifestError, match="QUARANTINED"):
        build_screen(args)


def test_a_stale_manifest_schema_version_fails_closed(synthetic_run):
    args = synthetic_run()
    _edit_json(args.guide_manifest, lambda d: d.update(
        {"schema_version": "spot.stage02_contributor_manifest.v1"}) or d)
    # A superseded schema is not "an older but acceptable shape": its citations named
    # ids minted under the obsolete rule, so a record's evidence could be swapped
    # without changing the id that cites it. It is refused, never migrated in place.
    with pytest.raises(ManifestError, match="is SUPERSEDED"):
        build_screen(args)


# --------------------------------------------------------------------------- #
# 3. The standalone verifier is genuinely independent, and catches forgery.
# --------------------------------------------------------------------------- #
def test_the_verifier_imports_nothing_from_the_generator():
    import ast
    path = os.path.join(os.path.dirname(trust.__file__), "verify_run.py")
    tree = ast.parse(open(path).read())
    banned = {"selection", "projection", "ranking", "disposition", "emit", "runid",
              "trust", "arms", "masks", "guides", "donors", "universe", "hashing",
              "config", "manifest", "io_data", "run_screen"}
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[-1])
            if node.level:                        # relative import of the package
                imported.update(a.name for a in node.names)
        elif isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
    assert not (imported & banned), f"verifier imports generator modules: {imported & banned}"


@pytest.fixture
def bundle(synthetic_run):
    args = synthetic_run()
    result = build_screen(args)
    inputs_root = os.path.dirname(args.selection)
    return result, args, inputs_root


def test_the_verifier_passes_a_genuine_bundle(bundle):
    result, _args, inputs_root = bundle
    assert verify_main(["--run-dir", result["out_dir"],
                        "--inputs-root", inputs_root]) == 0


def test_the_verifier_rejects_a_tampered_screen_even_after_re_self_hashing(bundle):
    """Flip a score in screen.parquet, then rewrite verification.json's self hashes.
    The verifier rebuilds from the INPUTS, so the forgery cannot survive."""
    result, _args, inputs_root = bundle
    path = os.path.join(result["out_dir"], "screen.parquet")
    df = pd.read_parquet(path)
    df.loc[df["target_id"] == TARGET_GENES[0], "away_from_A"] = 999.0
    df.to_parquet(path, index=False)

    # re-self-hash: recompute every artifact hash the bundle records about itself
    from direct.hashing import file_sha256
    vpath = os.path.join(result["out_dir"], "verification.json")
    with open(vpath) as fh:
        ver = json.load(fh)
    ver["artifact_sha256"] = {
        fn: file_sha256(os.path.join(result["out_dir"], fn))
        for fn in ver.get("artifact_sha256", {})}
    with open(vpath, "w") as fh:
        json.dump(ver, fh, indent=2, sort_keys=True)

    assert verify_main(["--run-dir", result["out_dir"],
                        "--inputs-root", inputs_root]) == 1


def test_the_verifier_rejects_a_tampered_axis(bundle):
    result, _args, inputs_root = bundle
    _edit_json(os.path.join(result["out_dir"], "axis.json"),
               lambda d: d["A"].update({"sign": -1}) or d)
    assert verify_main(["--run-dir", result["out_dir"],
                        "--inputs-root", inputs_root]) == 1


def test_the_verifier_rejects_a_forged_rank(bundle):
    result, _args, inputs_root = bundle
    path = os.path.join(result["out_dir"], "screen.parquet")
    df = pd.read_parquet(path)
    df["rank_toward_B"] = df["rank_toward_B"].astype("Int64")
    # promote a NON-evaluable row into rank 1
    victim = df[~df["B_evaluable"].astype(bool)]["target_id"].iloc[0]
    df.loc[df["target_id"] == victim, "rank_toward_B"] = 1
    df.to_parquet(path, index=False)
    assert verify_main(["--run-dir", result["out_dir"],
                        "--inputs-root", inputs_root]) == 1


def test_the_verifier_rejects_an_extra_or_stale_output_file(bundle):
    result, _args, inputs_root = bundle
    with open(os.path.join(result["out_dir"], "stale_leftover.parquet"), "w") as fh:
        fh.write("x")
    assert verify_main(["--run-dir", result["out_dir"],
                        "--inputs-root", inputs_root]) == 1


def test_the_verifier_rejects_a_tampered_input(bundle):
    result, args, inputs_root = bundle
    with open(args.de_main, "ab") as fh:
        fh.write(b"\0")                     # the input no longer matches its pin
    assert verify_main(["--run-dir", result["out_dir"],
                        "--inputs-root", inputs_root]) == 1


def test_the_verifier_rejects_a_reintroduced_combined_objective(bundle):
    result, _args, inputs_root = bundle
    path = os.path.join(result["out_dir"], "screen.parquet")
    df = pd.read_parquet(path)
    df["combination"] = (df["away_from_A"].fillna(0) + df["toward_B"].fillna(0)) / 2
    df.to_parquet(path, index=False)
    assert verify_main(["--run-dir", result["out_dir"],
                        "--inputs-root", inputs_root]) == 1


# --------------------------------------------------------------------------- #
# 4/5. Code, config and environment mutation change the run identity.
# --------------------------------------------------------------------------- #
def test_a_config_mutation_changes_run_id(synthetic_run, monkeypatch):
    base = build_screen(synthetic_run())["run_id"]
    from direct import config
    monkeypatch.setattr(config, "ELIGIBILITY_POLICY",
                        dict(config.ELIGIBILITY_POLICY, n_cells_min=999))
    assert build_screen(synthetic_run())["run_id"] != base


def test_a_code_tree_mutation_changes_run_id(synthetic_run, monkeypatch):
    base = build_screen(synthetic_run())["run_id"]
    from direct import runid
    monkeypatch.setattr(runid, "code_tree_sha256", lambda _d: "0" * 64)
    assert build_screen(synthetic_run())["run_id"] != base


def test_an_environment_mutation_changes_run_id(synthetic_run, tmp_path):
    base = build_screen(synthetic_run())["run_id"]
    lock = tmp_path / "env.lock"
    lock.write_text("numpy==1.2.3\n")
    args = synthetic_run()
    args.env_lock = str(lock)
    assert build_screen(args)["run_id"] != base
