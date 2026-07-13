"""The v2 door: a bundle declares its contract, and the contract is enforced at the door.

A schema is not a gate. Until the loader knows what `spot.stage04_evidence_bundle.v2` means —
which lanes it carries, which profile it must satisfy, and that it may NOT be silently read as
v1 — the v2 contract is a document, not a rule.

Two failure modes are closed here:

  * a v2 bundle that declares v2 and carries none of it (acquisition-complete by assertion);
  * a v1 bundle that smuggles v2 rows, whose digest would not cover them.
"""

from __future__ import annotations

import json
import os

import pytest

from analysis.contract_version import ContractVersion
from analysis.evidence_bundle import (
    EVIDENCE_BUNDLE_SCHEMA_V1,
    EVIDENCE_BUNDLE_SCHEMA_V2,
    load_evidence_bundle,
)
from analysis.firewall import Rejection


def _write(tmp_path, doc) -> str:
    path = os.path.join(tmp_path, "bundle.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)
    return path


def _v1_doc() -> dict:
    return {"schema_id": EVIDENCE_BUNDLE_SCHEMA_V1, "contexts": [], "sources": {}}


def _v2_doc() -> dict:
    return {"schema_id": EVIDENCE_BUNDLE_SCHEMA_V2, "contexts": [], "sources": {},
            "fraction_unbound": [], "source_acquisition": []}


# ------------------------------------------------------------------- the version is read

def test_a_v1_bundle_loads_as_v1(tmp_path):
    b = load_evidence_bundle(_write(tmp_path, _v1_doc()))
    assert b["contract_version"] is ContractVersion.V1


def test_a_v2_bundle_loads_as_v2(tmp_path):
    b = load_evidence_bundle(_write(tmp_path, _v2_doc()))
    assert b["contract_version"] is ContractVersion.V2


def test_an_unknown_bundle_schema_is_still_refused(tmp_path):
    with pytest.raises(Rejection) as exc:
        load_evidence_bundle(_write(tmp_path, {"schema_id": "spot.stage04_evidence_bundle.v3"}))
    assert exc.value.code == "evidence_bundle_schema_unknown"


# --------------------------------------------------- v2 lanes exist only in the v2 door

def test_a_v1_bundle_carrying_a_v2_lane_is_refused(tmp_path):
    """The lane would be consumed by nothing and hashed by nothing: the v1 digest does not
    cover `source_acquisition`. Silently ignoring it would let a bundle claim an acquisition
    manifest that never entered the release's identity."""
    doc = _v1_doc()
    doc["source_acquisition"] = [{"acquisition_id": "ACQ-1"}]
    with pytest.raises(Rejection) as exc:
        load_evidence_bundle(_write(tmp_path, doc))
    assert exc.value.code == "evidence_bundle_unknown_lane"


def test_the_v2_lanes_are_readable_in_a_v2_bundle(tmp_path):
    b = load_evidence_bundle(_write(tmp_path, _v2_doc()))
    assert b["fraction_unbound"] == []
    assert b["source_acquisition"] == []


# ------------------------------------------------- the profile is enforced, not declared

def test_a_v2_bundle_that_carries_none_of_the_v2_contract_is_refused(tmp_path):
    """"Acquisition-complete" by assertion. This is the exact failure the audit described one
    schema version earlier: bytes that cannot show how they were obtained."""
    import fixtures as fx

    inputs = fx.stage4_inputs_v2()
    inputs.acquisitions = []  # declares v2, acquired nothing
    from analysis.contract_profile import contract_violations
    codes = {v.code for v in contract_violations(inputs)}
    assert "source_not_acquired" in codes


def test_the_run_refuses_a_v2_bundle_that_fails_its_own_profile(tmp_path):
    """The door, not just the model. `run_stage4` must not emit a release from a v2 bundle
    that does not satisfy the v2 contract."""
    import fixtures as fx
    from analysis.contract_profile import assert_contract_satisfied

    inputs = fx.stage4_inputs_v2()
    inputs.potencies = [p.model_copy(update={"assay_binding": None}) for p in inputs.potencies]
    with pytest.raises(Rejection) as exc:
        assert_contract_satisfied(inputs)
    assert exc.value.code == "evidence_contract_violation"


def test_a_satisfied_v2_bundle_passes_the_door():
    import fixtures as fx
    from analysis.contract_profile import assert_contract_satisfied

    assert_contract_satisfied(fx.stage4_inputs_v2())  # does not raise


def test_a_v1_bundle_passes_the_door_and_is_not_acquisition_complete():
    import fixtures as fx
    from analysis.contract_profile import assert_contract_satisfied, is_acquisition_complete

    inputs = fx.stage4_inputs()
    assert_contract_satisfied(inputs)
    assert is_acquisition_complete(inputs) is False
