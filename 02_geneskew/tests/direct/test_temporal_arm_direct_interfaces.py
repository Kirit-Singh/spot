"""Regression tests for the three native interfaces exposed by the frozen W11 replay."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pandas as pd
import pytest

_ANALYSIS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..",
                                         "analysis"))
if _ANALYSIS not in sys.path:
    sys.path.insert(0, _ANALYSIS)
if os.path.dirname(os.path.abspath(__file__)) not in sys.path:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fixtures_arm_verifier as FX  # noqa: E402
from verify_temporal_arms import direct_source  # noqa: E402
from verify_temporal_arms.failures import Failures  # noqa: E402


def _row(change: str, *, evaluable: bool, value, base_delta: float = 2.0) -> dict:
    return {
        "arm_key": f"direct|FIXTURE_PROGRAM|{change}|FixRest",
        "program_id": "FIXTURE_PROGRAM",
        "desired_change": change,
        "condition": "FixRest",
        "target_id": "FIXTURE_TARGET",
        "base_delta": base_delta,
        "value": value,
        "rank": 1 if evaluable else None,
        "evaluable": evaluable,
        "projection_status": "ok",
        "base_state": "qc_pass_multi_guide" if evaluable else "low_target_expression",
        "base_passed": evaluable,
        "n_panel_surviving": 4,
        "n_control_surviving": 3,
        "arm_bundle_run_id": "fixture-run",
    }


def _endpoint(delta: float, *, evaluable: bool = True) -> dict:
    return {
        "base_delta": delta,
        "evaluable": evaluable,
        "base_passed": evaluable,
        "projection_status": "ok",
        "base_state": "qc_pass_multi_guide" if evaluable else "low_target_expression",
        "n_panel_surviving": 4,
        "n_control_surviving": 3,
    }


def _temporal_record(*, from_present: bool, to_present: bool,
                     from_endpoint=None, to_endpoint=None, base_delta=None) -> dict:
    out = {"program_id": "FIXTURE_PROGRAM", "target_id": "FIXTURE_TARGET",
           "from_present": from_present, "to_present": to_present,
           "base_delta": base_delta}
    for side, present, endpoint in (("from", from_present, from_endpoint),
                                    ("to", to_present, to_endpoint)):
        endpoint = endpoint or {}
        out.update({
            f"{side}_delta": endpoint.get("base_delta") if present else None,
            f"{side}_evaluable": endpoint.get("evaluable", False) if present else False,
            f"{side}_projection_status": endpoint.get("projection_status") if present else None,
            f"{side}_base_qc_passed": endpoint.get("base_passed") if present else None,
            f"{side}_base_qc_state": endpoint.get("base_state") if present else None,
            f"{side}_n_panel_surviving": endpoint.get("n_panel_surviving") if present else None,
            f"{side}_n_control_surviving": endpoint.get("n_control_surviving") if present else None,
        })
    return out


def failed(failures: Failures) -> set[str]:
    return {item["gate"] for item in failures.items}


def test_parquet_rehashes_through_the_exact_w10_admitted_view(tmp_path):
    bundles, _ = FX.stage_direct_bundles(tmp_path)
    for bundle_dir in bundles.values():
        rows, columns = direct_source._rows(bundle_dir)
        allowed = set(direct_source.ARM_ROW_COLUMNS) | \
            set(direct_source.ARM_ROW_EXTRA_COLUMNS)
        assert set(columns) == allowed
        with open(os.path.join(bundle_dir, "arm_bundle.json")) as fh:
            declared = json.load(fh)["arm_rows_sha256"]
        assert direct_source.rows_sha256(rows) == declared


def test_arm_value_is_not_an_alias_for_the_real_direct_value_field():
    rows = [_row("increase", evaluable=True, value=None),
            _row("decrease", evaluable=True, value=-2.0)]
    rows[0]["arm_value"] = 2.0
    failures = Failures()
    direct_source._dedupe(failures, rows, "mutation")
    assert "every_direct_arm_value_is_the_sign_transform_of_its_base_delta" in \
        failed(failures)


def test_non_evaluable_direct_rows_require_null_value_but_retain_the_raw_base_delta():
    rows = [_row("increase", evaluable=False, value=None),
            _row("decrease", evaluable=False, value=None)]
    failures = Failures()
    base = direct_source._dedupe(failures, rows, "control")
    assert not failures.items
    endpoint = base["FIXTURE_PROGRAM"]["FIXTURE_TARGET"]
    assert endpoint["base_delta"] == 2.0
    assert endpoint["evaluable"] is False


def test_an_arm_value_column_is_refused_as_outside_the_w10_schema(tmp_path):
    bundles, reports = FX.stage_direct_bundles(tmp_path)
    condition = FX.CONDITIONS[0]
    path = os.path.join(bundles[condition], "arms.parquet")
    frame = pd.read_parquet(path)
    frame["arm_value"] = frame["value"]
    frame.to_parquet(path)
    failures = Failures()
    assert direct_source.load(failures, condition, bundles[condition], reports[condition],
                              w10_pins=FX.w10_pins()) is None
    assert "the_direct_rows_use_the_exact_w10_admitted_schema" in failed(failures)


def test_declared_endpoint_absence_is_proved_not_misreported_as_missing_coverage():
    from_endpoint = _endpoint(1.0)
    record = _temporal_record(from_present=True, to_present=False,
                              from_endpoint=from_endpoint, base_delta=None)
    failures = Failures()
    count = direct_source.recompute(
        failures, {"base_records": [record]},
        {"FIXTURE_PROGRAM": {"FIXTURE_TARGET": from_endpoint}},
        {"FIXTURE_PROGRAM": {}}, "FixRest__to__FixStim")
    assert count == 1
    assert not failures.items
    assert "the_temporal_endpoint_presence_flags_exactly_match_the_direct_bundles" in \
        failures.evaluated


def test_a_present_direct_row_cannot_be_hidden_behind_an_absent_flag():
    from_endpoint = _endpoint(1.0)
    to_endpoint = _endpoint(2.0, evaluable=False)
    record = _temporal_record(from_present=True, to_present=False,
                              from_endpoint=from_endpoint, base_delta=None)
    failures = Failures()
    direct_source.recompute(
        failures, {"base_records": [record]},
        {"FIXTURE_PROGRAM": {"FIXTURE_TARGET": from_endpoint}},
        {"FIXTURE_PROGRAM": {"FIXTURE_TARGET": to_endpoint}}, "mutation")
    assert "the_temporal_endpoint_presence_flags_exactly_match_the_direct_bundles" in \
        failed(failures)


def test_temporal_endpoint_deltas_are_checked_against_the_actual_direct_rows():
    from_endpoint, to_endpoint = _endpoint(1.0), _endpoint(2.0)
    record = _temporal_record(from_present=True, to_present=True,
                              from_endpoint=from_endpoint, to_endpoint=to_endpoint,
                              base_delta=1.0)
    record["from_delta"] = 99.0
    failures = Failures()
    direct_source.recompute(
        failures, {"base_records": [record]},
        {"FIXTURE_PROGRAM": {"FIXTURE_TARGET": from_endpoint}},
        {"FIXTURE_PROGRAM": {"FIXTURE_TARGET": to_endpoint}}, "mutation")
    assert "the_temporal_endpoint_delta_matches_the_admitted_direct_row" in \
        failed(failures)


def test_real_frozen_direct_rows_redifference_every_temporal_union_record_when_supplied():
    """Opt-in replay of the actual immutable W10/W11 artifacts, never copied fixtures.

    The full CLI replay additionally validates every bundle/report/code binding. This test
    isolates the three repaired Direct interfaces and is enabled in the release audit with
    paths to the frozen artifact roots; ordinary developer runs skip when those external
    immutable artifacts are not mounted.
    """
    direct_root = os.environ.get("SPOT_FROZEN_DIRECT_BUNDLE_ROOT")
    temporal_root = os.environ.get("SPOT_FROZEN_TEMPORAL_BUNDLE_ROOT")
    if not direct_root or not temporal_root:
        pytest.skip("set the two SPOT_FROZEN_*_BUNDLE_ROOT paths for the real replay")

    bases = {}
    failures = Failures()
    for parquet in sorted(Path(direct_root).glob("*/arms.parquet")):
        bundle_dir = parquet.parent
        with open(bundle_dir / "provenance.json") as fh:
            binding = json.load(fh)["run_binding"]
        condition = str(binding["condition"])
        rows, columns = direct_source._rows(str(bundle_dir))
        allowed = set(direct_source.ARM_ROW_COLUMNS) | \
            set(direct_source.ARM_ROW_EXTRA_COLUMNS)
        assert set(columns) == allowed
        assert direct_source.rows_sha256(rows) == binding["arm_rows_sha256"]
        bases[condition] = direct_source._dedupe(failures, rows, f"direct:{condition}")

    total, expected = 0, 0
    for bundle_path in sorted(Path(temporal_root).glob("*/arm_bundle.json")):
        with open(bundle_path) as fh:
            doc = json.load(fh)
        from_condition = str(doc["from_condition"])
        to_condition = str(doc["to_condition"])
        expected += len(doc["base_records"])
        total += direct_source.recompute(
            failures, doc, bases[from_condition], bases[to_condition],
            bundle_path.parent.name)

    assert total == expected
    assert not failures.items, failures.items[:3]
