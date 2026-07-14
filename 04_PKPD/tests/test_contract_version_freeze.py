"""v1 is frozen. v2 is an addition to it, never an edit of it.

This file exists because of a real regression. The v2 columns were first added to the SHARED
column declaration, so two things broke at once:

  * v1 CONTENT began hashing under a v2 SHAPE. `evidence_inputs_sha256` for the unchanged v1
    fixture set moved off 8999c5a3..., which is a contradiction in terms: a content digest that
    changes when the content did not is not a content digest.
  * the independent verifier began DEMANDING a `relation` column of releases emitted before that
    column existed, so a historical release became "unverifiable" — not wrong, just unreadable
    by its own successor.

Both had one cause: a single mutable declaration serving two contracts. The fix is not to
weaken v2 and not to pad v1 with null v2 columns; it is to make the contract version explicit
and carry BOTH declarations.

`historical_v1_release/fed2a8347d155a23` is a real release, emitted by the code at commit
e410d72 and verified by the verifier of that commit (212 checks, 0 failed). It is checked in
unchanged. If today's code cannot verify it, today's code has broken the contract.
"""

from __future__ import annotations

import json
import os

import pytest

from analysis.contract_v1_frozen import (
    DERIVED_COLUMNS_V1,
    INPUT_COLUMNS_V1,
    METHOD_FILES_V1,
    V1_FIXTURE_EVIDENCE_INPUTS_SHA256,
)
from analysis.contract_version import ContractVersion
from analysis.ids import evidence_inputs_digest
from analysis.method_config import METHOD_DIR
from verifier.checks import verify_release

HISTORICAL = os.path.join(os.path.dirname(__file__), "fixtures", "historical_v1_release",
                          "fed2a8347d155a23")

# The METHOD the historical release was BOUND to, shipped beside it. Verifying a historical
# artifact means recomputing it from ITS OWN bound inputs, not from today's.
#
# It is no longer identical to `method/`, and that is correct: W8's `9c857fb` corrected
# `sources.json`, which used to claim DailyMed was "Public domain (NLM DailyMed)" — an overclaim
# (source audit §4.6; DailyMed publishes no blanket licence). A method binding that did NOT move
# when the method changed would be worthless, so a release emitted before the correction cannot
# be reproduced from today's method. The alternative would be reverting a true statement about
# licensing, or forging a hash. This test's claim is about the CONTRACT — today's v2-aware
# verifier can still fully reconstruct a v1 release — not about the method being immutable.
HISTORICAL_METHOD_DIR = os.path.join(os.path.dirname(HISTORICAL), "method_at_e410d72")

# What the release ACTUALLY declared when it was written, at e410d72.
HISTORICAL_SCORECARD_SET_ID = "fed2a8347d155a23"


# --------------------------------------------------------- the v1 digest has not moved

def test_the_v1_fixture_still_hashes_to_the_frozen_v1_digest():
    """The headline regression, pinned.

    The v1 fixture set is unchanged evidence. Its content digest must therefore be the
    number it has always been.
    """
    import fixtures as fx

    inputs = fx.stage4_inputs()
    assert inputs.contract_version is ContractVersion.V1
    digest = evidence_inputs_digest(inputs.evidence_lanes())
    assert digest == V1_FIXTURE_EVIDENCE_INPUTS_SHA256, (
        f"v1 evidence_inputs_sha256 moved to {digest}. v1 content must hash under the v1 "
        "column set, whatever v2 adds."
    )


def test_a_v1_bundle_carries_no_v2_columns_at_all_not_even_null_ones():
    """"Backwards compatible" does not mean "v1 plus a column of nulls".

    A null v2 cell in a v1 row is still a v2 cell: it changes the row's shape, its digest and
    its meaning ("this row HAS a relation, and it is unknown" is not "this contract has no
    concept of a relation").
    """
    import fixtures as fx

    rows = fx.stage4_inputs().evidence_lanes()
    assert set(rows) == set(INPUT_COLUMNS_V1)
    for table, cols in INPUT_COLUMNS_V1.items():
        for row in rows[table]:
            assert set(row) == set(cols), (
                f"{table}: a v1 row carries {sorted(set(row) - set(cols))} — v2 columns must "
                "not appear in a v1 release, null or otherwise."
            )


def test_the_frozen_v1_potency_and_exposure_columns_do_not_contain_the_v2_fields():
    assert "relation" not in INPUT_COLUMNS_V1["potency_evidence"]
    assert "assay_activity_id" not in INPUT_COLUMNS_V1["potency_evidence"]
    for f in ("pk_metric", "sampling_method", "residual_blood_correction", "kp_basis",
              "binding_state_basis", "paired_plasma_measurement_id"):
        assert f not in INPUT_COLUMNS_V1["exposure_evidence"], f
    assert "fraction_unbound" not in INPUT_COLUMNS_V1
    assert "source_acquisition" not in INPUT_COLUMNS_V1


def test_the_v1_derived_columns_are_frozen_too():
    assert DERIVED_COLUMNS_V1["potency_evidence"] == ("value_canonical_decimal",)
    assert "fraction_unbound" not in DERIVED_COLUMNS_V1


def test_the_v1_method_file_map_is_the_seven_files_a_v1_release_bound():
    """A v1 release recomputes exactly these seven hashes from method/ and compares them to
    the ones in its id. Editing any of them, or ADDING one to this map, breaks every release
    ever emitted. v2 method content goes in new files, in a v2 map."""
    assert set(METHOD_FILES_V1) == {
        "cns_mpo", "nebpi", "calculator_policy", "delivery_rules", "safety_taxonomy",
        "sources", "prose",
    }


@pytest.mark.parametrize("name", sorted(METHOD_FILES_V1.values()))
def test_every_v1_method_file_still_exists_unedited_on_disk(name):
    """A v1 release binds these files by hash. If one is edited, historical verification
    fails on `method_file_sha256_recomputed_from_the_method_files` — so v2 must ADD method
    files, never edit these."""
    assert os.path.exists(os.path.join(METHOD_DIR, name))


# ------------------------------------------- a real historical release still verifies

def test_the_historical_v1_release_is_the_one_that_was_emitted_at_e410d72():
    with open(os.path.join(HISTORICAL, "manifest.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)
    assert manifest["scorecard_set_id"] == HISTORICAL_SCORECARD_SET_ID
    assert manifest["evidence_inputs_sha256"] == V1_FIXTURE_EVIDENCE_INPUTS_SHA256
    # It predates the contract-version field entirely. Absent MUST mean v1, or every release
    # ever written becomes unreadable the moment a v2 exists.
    assert "evidence_contract_version" not in manifest


def test_todays_verifier_still_verifies_the_historical_v1_release():
    """The regression, as a test.

    This release was written before `relation`, `pk_metric`, `fraction_unbound` or
    `source_acquisition` existed. Today's verifier must reconstruct it on the v1 contract and
    pass — not report it unverifiable for lacking columns that did not exist when it was
    written.
    """
    report = verify_release(HISTORICAL, HISTORICAL_METHOD_DIR)
    failed = [c for c in report["checks"] if c["status"] == "fail"]
    assert report["status"] == "pass", f"historical v1 release no longer verifies: {failed}"
    assert report["scope"] == "full_reconstruction"


def test_the_historical_release_reconstructs_on_the_v1_contract_not_the_v2_one():
    report = verify_release(HISTORICAL, HISTORICAL_METHOD_DIR)
    ids = {c["check_id"]: c for c in report["checks"]}
    assert ids["release_reconstructable"]["status"] == "pass"
    assert ids["evidence_inputs_sha256_recomputed_from_the_release"]["status"] == "pass"
    assert ids["scorecard_set_id_rederived_from_its_own_inputs"]["status"] == "pass"
