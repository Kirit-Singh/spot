"""Every probe from the independent post-remediation audit, as a regression test.

Each of these passed (wrongly) before the fix. They must now fail closed, and they
must keep failing even when the forger regenerates the bundle's own bookkeeping.
"""
import contextlib
import io
import json
import os

import pandas as pd
import pytest
from direct import config, disposition, trust
from direct.hashing import file_sha256
from direct.run_screen import build_screen
from direct.run_screen import main as cli_main
from direct.sources import SourceRecordError
from direct.verify_run import main as verify_main


def _verify(result, inputs_root) -> int:
    with contextlib.redirect_stdout(io.StringIO()):
        return verify_main(["--run-dir", result["out_dir"],
                            "--inputs-root", str(inputs_root)])


def _root(args) -> str:
    return os.path.dirname(args.selection)


# --------------------------------------------------------------------------- #
# Audit finding 1 — contributor identity must RESOLVE to a source record.
# --------------------------------------------------------------------------- #
def test_probe_source_record_id_does_not_exist_in_source(synthetic_run):
    """The exact audit mutation. It used to build 14 rows / 9 evaluable targets.

    The citation is overwritten AFTER it is minted: a pre-mint edit would simply be
    replaced by the honest producer doing its job, and would test nothing.
    """
    def attack(rows):
        return [dict(r, source_record_id="DOES_NOT_EXIST_IN_SOURCE")
                if r.get("evidence_state") == "determined" else r for r in rows]

    with pytest.raises(SourceRecordError, match="do not resolve to a source record"):
        build_screen(synthetic_run(manifest_final_fn=attack))


def test_a_record_that_resolves_to_a_different_guide_fails_closed(synthetic_run):
    """The locator exists, but the record names another guide."""
    def attack(rows):
        out = [dict(r) for r in rows]
        for r in out:
            if r.get("evidence_state") == "determined" and r["estimate_id"] == "main":
                r["guide_id"] = "g-IMPOSTOR"      # record still says the real guide
                break
        return out

    with pytest.raises((SourceRecordError, Exception)):
        build_screen(synthetic_run(manifest_rows_fn=attack))


def test_a_record_that_resolves_to_a_different_estimate_fails_closed(synthetic_run):
    """Cite ANOTHER row's real record. The record exists and its id derives perfectly;
    it simply does not describe THIS scope, and resolution is on the whole key."""
    def attack(rows):
        out = [dict(r) for r in rows]
        determined = [r for r in out if r.get("evidence_state") == "determined"]
        determined[0]["source_record_id"] = determined[-1]["source_record_id"]
        return out

    with pytest.raises(SourceRecordError, match="do not resolve to a source record"):
        build_screen(synthetic_run(manifest_final_fn=attack))


def test_a_manifest_without_a_source_record_table_fails_closed(synthetic_run):
    args = synthetic_run()
    with open(args.guide_manifest) as fh:
        doc = json.load(fh)
    doc.pop("source_record_table")
    with open(args.guide_manifest, "w") as fh:
        json.dump(doc, fh)
    with pytest.raises(Exception, match="source_record_table"):
        build_screen(args)


def test_the_verifier_also_resolves_contributor_evidence(synthetic_run):
    """Neither side may trust the manifest assertion alone."""
    import verify_run
    src = open(verify_run.__file__).read()
    assert "resolve_contributors" in src
    assert "source-record table present with bytes matching its pin" in src


# --------------------------------------------------------------------------- #
# Audit finding 2 — the verifier must certify the whole reconstruction.
# --------------------------------------------------------------------------- #
@pytest.fixture
def bundle(synthetic_run):
    args = synthetic_run()
    return build_screen(args), args


def test_probe_forged_arm_state_and_tier_is_rejected(bundle):
    """The audit forged A_state=evaluable + tier1 on a non-evaluable row; the old
    verifier returned 31/31 and exit 0."""
    result, args = bundle
    p = os.path.join(result["out_dir"], "screen.parquet")
    df = pd.read_parquet(p)
    i = df.index[~df["A_evaluable"].astype(bool)][0]
    df.loc[i, "A_state"] = "evaluable"
    df.loc[i, "A_evidence_tier"] = "tier1_guide_and_donor_split"
    df.to_parquet(p, index=False)
    assert _verify(result, _root(args)) == 1


def test_probe_forged_support_state_is_rejected(bundle):
    result, args = bundle
    p = os.path.join(result["out_dir"], "screen.parquet")
    df = pd.read_parquet(p)
    i = df.index[~df["B_evaluable"].astype(bool)][0]
    df.loc[i, "B_guide_replication_state"] = "replicated_concordant"
    df.loc[i, "B_guide_replication_supported"] = True
    df.to_parquet(p, index=False)
    assert _verify(result, _root(args)) == 1


@pytest.mark.parametrize("alias", ["balanced_score", "composite_score",
                                   "balanced_skew", "balanced_a_to_b",
                                   "combined_score", "rank"])
def test_probe_extra_combined_or_headline_column_is_rejected(bundle, alias):
    result, args = bundle
    p = os.path.join(result["out_dir"], "screen.parquet")
    df = pd.read_parquet(p)
    df[alias] = (df["away_from_A"].fillna(0) + df["toward_B"].fillna(0)) / 2
    df.to_parquet(p, index=False)
    assert _verify(result, _root(args)) == 1


def test_an_arbitrary_extra_score_column_is_rejected(bundle):
    """Not on any denylist — but not on the allowlist either."""
    result, args = bundle
    p = os.path.join(result["out_dir"], "screen.parquet")
    df = pd.read_parquet(p)
    df["my_new_score"] = 1.0
    df.to_parquet(p, index=False)
    assert _verify(result, _root(args)) == 1


def test_a_forgery_survives_neither_regenerated_hashes_nor_bookkeeping(bundle):
    """The forger also rewrites verification.json's self-hashes and its own claims."""
    result, args = bundle
    p = os.path.join(result["out_dir"], "screen.parquet")
    df = pd.read_parquet(p)
    df["composite_score"] = 1.0
    df.to_parquet(p, index=False)

    vp = os.path.join(result["out_dir"], "verification.json")
    with open(vp) as fh:
        ver = json.load(fh)
    ver["artifact_sha256"] = {
        f: file_sha256(os.path.join(result["out_dir"], f))
        for f in ver.get("artifact_sha256", {})}
    ver["columns_match_allowlist"] = True          # lie in the bookkeeping too
    ver["columns_off_allowlist"] = []
    with open(vp, "w") as fh:
        json.dump(ver, fh)

    assert _verify(result, _root(args)) == 1


def test_a_tampered_mask_row_is_rejected(bundle):
    result, args = bundle
    p = os.path.join(result["out_dir"], "masks.parquet")
    df = pd.read_parquet(p)
    df = df[df["masked_gene_ensembl"].isna() | (df.index != df.index[0])]
    df.to_parquet(p, index=False)
    assert _verify(result, _root(args)) == 1


def test_a_guide_support_value_that_appeared_from_nowhere_is_rejected(bundle):
    """Support is UNAVAILABLE, so every emitted support value is null.

    The tamper is therefore the reverse of the old one: instead of changing a number it
    INVENTS one where the contract says there can be none. A slot estimate was never
    projected — it has no mask and no contributor evidence — so any number in this
    column is fabricated. The verifier reconstructs null and refuses it.
    """
    result, args = bundle
    p = os.path.join(result["out_dir"], "guide_support.parquet")
    df = pd.read_parquet(p)
    assert df["value"].isna().all(), "an unavailable support estimate has no value"
    df.loc[df.index[0], "value"] = 999.0
    df.to_parquet(p, index=False)
    assert _verify(result, _root(args)) == 1


def test_a_tampered_contributing_guide_row_is_rejected(bundle):
    result, args = bundle
    p = os.path.join(result["out_dir"], "contributing_guides.parquet")
    df = pd.read_parquet(p)
    idx = df.index[df["guide_id"].notna()][0]
    df.loc[idx, "guide_id"] = "g-IMPOSTOR"
    df.to_parquet(p, index=False)
    assert _verify(result, _root(args)) == 1


def _package_dir():
    return os.path.dirname(os.path.abspath(trust.__file__))


# SHARED CONTRACT modules: the written admission/firewall contract a verifier reimplements
# AGAINST and reads its subject through (``load_shipped``, ``forbidden_keys``). Producers and
# verifiers use it alike; it generates nothing, so importing it does not make a verifier an
# echo of the producer. ``admission`` moved to the package root in the GATE-7 cleanup (it had
# lived in ``temporal.admission``, a subdir this flat scan never saw).
SHARED_CONTRACT = frozenset({"admission"})


def _module_stems():
    """Every module in the package, split into VERIFIER and PRODUCER by name.

    Discovered, never listed. The hand-written version of this guard named six verifier
    modules and eighteen producer modules, so it silently stopped covering the lane the
    moment either side grew — and both did. A guard whose scope is a literal is a guard
    that decays. Shared-contract modules are neither side and are excluded from both.
    """
    stems = [f[:-3] for f in sorted(os.listdir(_package_dir()))
             if f.endswith(".py") and f != "__init__.py"]
    verifiers = [s for s in stems if s.startswith("verify_")]
    producers = [s for s in stems
                 if not s.startswith("verify_") and s not in SHARED_CONTRACT]
    return verifiers, producers


def test_the_module_split_is_discovered_and_non_trivial():
    """A scan over an empty set passes vacuously."""
    verifiers, producers = _module_stems()
    assert len(verifiers) >= 8, verifiers
    assert len(producers) >= 20, producers
    # the modules the audit found missing from the old hardcoded list
    for must in ("verify_method", "verify_project", "verify_classification"):
        assert must in verifiers, f"{must} is not being scanned"
    for must in ("replay", "record_id", "identity", "domain", "gate", "preflight",
                 "manifest_schema", "manifest_validate", "manifest_replay",
                 "screen_row", "reissue", "cli"):
        assert must in producers, f"{must} is not banned for the verifier"


def _imports_of(stem):
    import ast

    tree = ast.parse(open(os.path.join(_package_dir(), f"{stem}.py")).read())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[-1])
            if node.level:                       # a relative import IS a package import
                imported.update(a.name for a in node.names)
        elif isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
    return imported


@pytest.mark.parametrize("stem", _module_stems()[0])
def test_no_verifier_module_imports_ANY_producer_module(stem):
    """EVERY verifier, against EVERY producer. The independence rule, enforced.

    The verifier reimplements the contract from the written spec. An import from the
    generator would make it an echo: it would agree with the producer by construction,
    whatever the producer happens to say today, and the whole point of a second
    implementation is that it can disagree.
    """
    _verifiers, producers = _module_stems()
    leaked = _imports_of(stem) & set(producers)
    assert not leaked, f"{stem}.py imports producer module(s): {sorted(leaked)}"


# --------------------------------------------------------------------------- #
# Audit finding 4 — missing QC is non-evaluable.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("field,expected_reason", [
    ("n_cells", "missing_qc:n_cells"),
    ("ontarget_significant", "missing_qc:ontarget_significant"),
    ("low_target_gex", "missing_qc:low_expression_flag"),
])
def test_probe_missing_qc_measurement_is_non_evaluable(field, expected_reason):
    base = dict(row_present=True, mask_resolved=True, n_cells=500.0,
                low_target_gex=False, ontarget_significant=True, n_guides=2.0)
    state, passed, reasons = disposition.base_qc(**{**base, field: None})
    assert state == "missing_qc_measurement"
    assert passed is False                      # never equal to favourable evidence
    assert expected_reason in reasons


def test_an_invalid_qc_measurement_is_non_evaluable():
    base = dict(row_present=True, mask_resolved=True, n_cells=500.0,
                low_target_gex=False, ontarget_significant=True, n_guides=2.0)
    state, passed, reasons = disposition.base_qc(**{**base, "n_cells": float("nan")})
    assert (state, passed) == ("invalid_qc_measurement", False)
    assert "invalid_qc:n_cells" in reasons


def test_the_verifier_applies_the_same_missing_qc_rule():
    import verify_rules as R
    state, passed = R.base_qc(mask_resolved=True, n_cells=None,
                              ontarget_significant=True, low_expression=False,
                              n_guides=2)
    assert (state, passed) == ("missing_qc_measurement", False)


# --------------------------------------------------------------------------- #
# Audit finding 5 — the CLI must work and report per-arm counts.
# --------------------------------------------------------------------------- #
def test_probe_cli_completes_and_reports_two_arm_populations(synthetic_run, capsys):
    args = synthetic_run()
    cli_main([
        "--selection", args.selection, "--registry", args.registry,
        "--de-main", args.de_main, "--by-guide", args.by_guide,
        "--by-donors", args.by_donors, "--sgrna", args.sgrna,
        "--guide-manifest", args.guide_manifest,
        "--source-registry", args.source_registry,
        "--stage1-validation", args.stage1_validation,
        "--stage1-gate-spec", args.stage1_gate_spec,
        "--lane", "synthetic", "--out-root", args.out_root,
    ])
    out = json.loads(capsys.readouterr().out)
    assert "n_ranked" not in out                 # the stale single-rank key is gone
    assert set(out["arms"]) == set(config.ARMS)
    for arm in config.ARMS:
        assert out["arms"][arm]["ranks_valid"] is True
        assert isinstance(out["arms"][arm]["n_ranked"], int)
    assert out["namespace"] == "synthetic"
    assert out["production_eligible"] is False
    assert out["no_combined_objective"] is True


def test_the_module_docstring_no_longer_claims_a_primary_endpoint():
    from direct import run_screen
    doc = run_screen.__doc__ or ""
    assert "primary endpoint is" not in doc.lower()
    assert "NO primary/headline" in doc
