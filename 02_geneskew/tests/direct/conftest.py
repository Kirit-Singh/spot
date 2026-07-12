"""pytest fixtures for the Stage-2 direct lane.

The builders live in ``fixtures_direct`` / ``fixtures_evidence`` — uniquely named
modules, because a bare ``conftest`` collides with the Perturb2State test package's own
conftest when the whole Stage-2 suite is collected together.
"""
from __future__ import annotations

import os
import sys
from typing import Optional

import pytest

_ANALYSIS = os.path.join(os.path.dirname(__file__), "..", "..", "analysis")
sys.path.insert(0, os.path.abspath(_ANALYSIS))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fixtures_direct as F  # noqa: E402
import fixtures_evidence as E  # noqa: E402
import fixtures_io as IO  # noqa: E402
from fixtures_direct import (  # noqa: E402,F401
    RunArgs,
    TargetSpec,
    default_specs,
    derived_ids,
    write_selection,
    write_stage1_gates,
    write_stage1_release,
)
from fixtures_evidence import (  # noqa: E402,F401
    MANIFEST_NAME,
    RECORD_TABLE_NAME,
    REPLAY_REPORT_NAME,
    SOURCE_NAME,
    Evidence,
    contributing_guides,
    kept_proof,
    link_citations,
    main_ambiguous,
    manifest_doc,
    manifest_rows,
    raw_source_rows,
    source_record_doc,
    source_records,
    write_evidence,
    write_source_file,
)
from fixtures_spec import (  # noqa: E402,F401
    A_PANEL,
    B_PANEL,
    COMMON_UNIVERSE,
    CONDITION,
    CONTROLS,
    DONOR_PAIRS,
    DONORS,
    TARGET_GENES,
    UNIVERSE,
)

_write_registry = F._write_registry
_write_main = IO._write_main
_write_by_guide = IO._write_by_guide
_write_by_donors = IO._write_by_donors
_write_sgrna = IO._write_sgrna


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "release: reads the real pinned Marson release (tens of GB). OPT-IN via "
        "SPOT_STAGE2_RELEASE_TESTS=1; intended for tcefold, never the synthetic suite")


@pytest.fixture
def synthetic_run(tmp_path):
    """Write a complete synthetic input set and return the orchestrator args.

    ``manifest=False`` writes NO contributor manifest, which is the fail-closed
    default state of the lane: no guide identity, so nothing is scoreable. The
    evidence bundle is still built on disk — a run given no manifest is a run that
    was not shown the evidence, not a run where the evidence does not exist.

    The ``*_fn`` hooks each forge ONE artifact and pin the forgery honestly, so a
    refusal must come from the content rather than from a hash mismatch.
    """
    counter = {"n": 0}

    def _build(specs: Optional[list[TargetSpec]] = None, *, manifest: bool = True,
               manifest_rows_fn=None, manifest_final_fn=None,
               manifest_sources=None, lane="synthetic",
               registry_extra=None, stage1_selectable=True, source_registry=True,
               program_prefix=None, source_record_table=None, program_ids=None,
               source_records_fn=None, source_records_recite=False,
               source_replay_fn=None, source_rows_fn=None,
               source_replay_report=None, strict_replay=None,
               conditions=(CONDITION,),
               **selection_overrides) -> RunArgs:
        specs = specs or default_specs()
        conditions = tuple(conditions)
        counter["n"] += 1
        d = os.path.join(str(tmp_path), f"run{counter['n']}")
        os.makedirs(d, exist_ok=True)
        default_prefix = {"synthetic": "fx_", "research_only": "rq_",
                          "production": ""}[lane]
        prefix = default_prefix if program_prefix is None else program_prefix
        registry = os.path.join(d, "registry.json")
        registry_sha = _write_registry(registry, extra=registry_extra, prefix=prefix,
                                       program_ids=program_ids)
        names = F.program_names(prefix, program_ids)
        # Stage-1 gate evidence: the hard gates are RE-DERIVED from these rows.
        val_path, gate_path = write_stage1_gates(
            d, selectable=stage1_selectable, program_ids=names,
            conditions=conditions)

        # THE contributor evidence, built in the one order the identity rule permits:
        # raw source -> its kept offset proof -> the records that carry it -> the ids
        # derived from it -> the manifest citations that name them.
        evidence = write_evidence(
            d, specs, manifest_rows_fn=manifest_rows_fn,
            manifest_final_fn=manifest_final_fn,
            records_fn=source_records_fn, recite=source_records_recite,
            replay_fn=source_replay_fn,
            source_rows_fn=source_rows_fn, manifest_sources=manifest_sources,
            source_record_table=source_record_table,
            source_replay_report=source_replay_report,
            conditions=conditions)

        release_path, release_hashes = None, None
        if lane in ("production", "research_only"):
            kind = "production" if lane == "production" else "research"
            release_path = write_stage1_release(d, registry, val_path, gate_path,
                                                kind=kind)
            from direct import trust as _T
            rel = (_T.load_production_release(release_path) if kind == "production"
                   else _T.load_research_release(release_path))
            release_hashes = {
                "registry_sha256": rel.hashes["registry_canonical_sha256"],
                "method_version": rel.method_version,
                "validation_sha256": rel.hashes["validation_raw_sha256"],
                "gate_spec_sha256": rel.hashes["gate_spec_raw_sha256"],
                "input_manifest_sha256": rel.hashes["input_manifest_raw_sha256"],
                "scores_sha256": rel.hashes["scores_raw_sha256"],
                "code_sha256": rel.hashes["code_raw_sha256"],
                "environment_sha256": rel.hashes["environment_raw_sha256"],
            }
            if kind == "production":
                release_hashes["selectability_pointer_sha256"] = \
                    rel.hashes["selectability_pointer_raw_sha256"]

        selection = os.path.join(d, "selection.json")
        if lane == "research_only":
            F.write_research_bridge(selection, registry_sha, release_hashes,
                                    prefix=prefix, program_ids=program_ids,
                                    **selection_overrides)
        else:
            write_selection(selection, registry_sha, lane=lane, prefix=prefix,
                            release_hashes=release_hashes, program_ids=program_ids,
                            **selection_overrides)
        de_main = os.path.join(d, "de.h5ad")
        by_guide = os.path.join(d, "by_guide.h5mu")
        by_donors = os.path.join(d, "by_donors.h5mu")
        sgrna = os.path.join(d, "sgrna.csv")
        _write_main(de_main, specs, conditions)
        _write_by_guide(by_guide, specs, conditions)
        _write_by_donors(by_donors, specs, conditions)
        _write_sgrna(sgrna, specs)

        # THE RELEASE GATE. production / research_only are release-grade lanes: they may
        # not stand on the pinned replay report, so by default they run a FRESH strict
        # replay against the fixture's own raw source. ``strict_replay=False`` is the
        # only way to attack the gate, and it must refuse — there is no artifact a run
        # can present in place of the replay.
        release_lane = lane in ("production", "research_only")
        strict = release_lane if strict_replay is None else strict_replay

        return RunArgs(stage1_release=release_path,
                       selection=selection, registry=registry, de_main=de_main,
                       by_guide=by_guide, by_donors=by_donors, sgrna=sgrna,
                       guide_manifest=(evidence.manifest_path if manifest else None),
                       lane=lane,
                       source_registry=(evidence.registry_path if source_registry
                                        else None),
                       stage1_validation=val_path, stage1_gate_spec=gate_path,
                       strict_replay=bool(strict),
                       pseudobulk=evidence.source_path,
                       out_root=os.path.join(d, "out"))
    return _build


@pytest.fixture
def temporal_run(synthetic_run):
    """A three-condition run bound to two REAL registry programs.

    Everything else is the ordinary synthetic lane: same evidence bundle, same manifest
    contract, same release gate. The only difference is that the release ships three
    culture conditions instead of one, which is the thing a cross-condition estimator
    needs and the single-condition fixture cannot express.
    """
    import fixtures_temporal as T

    def _build(specs=None, *, conditions=T.TEMPORAL_CONDITIONS,
               analysis_condition=T.REST, **kwargs):
        return synthetic_run(
            specs if specs is not None else T.temporal_specs(),
            conditions=conditions,
            program_ids=(T.PROGRAM_A, T.PROGRAM_B), program_prefix="",
            analysis_condition=analysis_condition, **kwargs)
    return _build


@pytest.fixture
def evidence_bundle(tmp_path):
    """The contributor-evidence bundle ALONE, for tests that attack it directly.

    Same builder the whole run uses, so a test can never prove a property of a
    bundle the lane would not have consumed.
    """
    counter = {"n": 0}

    def _build(specs: Optional[list[TargetSpec]] = None, **kwargs) -> Evidence:
        counter["n"] += 1
        d = os.path.join(str(tmp_path), f"evidence{counter['n']}")
        os.makedirs(d, exist_ok=True)
        return write_evidence(d, specs or default_specs(), **kwargs)
    return _build


@pytest.fixture
def gene_index():
    return {g: i for i, g in enumerate(UNIVERSE)}


@pytest.fixture
def axis():
    return {
        "A": {"program_id": "fx_program_a", "direction": "high", "sign": 1,
              "panel": A_PANEL, "control": CONTROLS},
        "B": {"program_id": "fx_program_b", "direction": "high", "sign": 1,
              "panel": B_PANEL, "control": CONTROLS},
    }
