"""The production gate is an ARTIFACT, not a Boolean in Stage-3's own source.

`v2_input_loader` used to gate production on `arm_query.DETACHED_CLONE_MATRIX_GREEN` — a
module constant. No upstream lane and no artifact on disk could flip it; only a Stage-3 edit
could. So it recorded a Stage-3 *intention*, not an upstream *fact*, and the day someone
flipped it to True it would have reported green with nothing admitted behind it.

The gate is now `stage2_aggregate.admit_aggregate` reading real bytes off disk. These tests
hold that line, and — importantly — they EXERCISE the admitted branch. The first version of
the binding read fields that do not exist on `AdmittedAggregate`; the whole suite stayed
green because every test left the aggregate None, so the branch never ran. A gate nobody
walks through is not tested, it is merely present. Hence `test_the_binding_names_every_field`.

Every release built here is a SEALED NON-PRODUCTION plumbing input. It exercises wiring and
produces no candidate: no drug is named, no target is ranked, no science is asserted.
"""
from __future__ import annotations

import pytest

from druglink import stage2_aggregate as sa
from druglink import v2_input_loader as v2
from stage2_release_fixture import build_release


@pytest.fixture(scope="module")
def analysis_aggregate(tmp_path_factory):
    """The REAL admitted Stage-2 release, which STAGE 3 declares an analysis, so the
    production path can be walked end to end. It carries arm slots and no candidates."""
    paths = build_release(tmp_path_factory.mktemp("s2_prod"))
    return sa.admit_aggregate(**paths, artifact_class="analysis")


@pytest.fixture(scope="module")
def fixture_aggregate(tmp_path_factory):
    """The same REAL release, declared by Stage 3 as a fixture run."""
    paths = build_release(tmp_path_factory.mktemp("s2_fix"))
    return sa.admit_aggregate(**paths, artifact_class="fixture")


# --------------------------------------------------------------------------- #
# The constant is gone, and cannot come back.
# --------------------------------------------------------------------------- #
def test_the_loader_no_longer_gates_production_on_a_module_constant():
    src = (v2.__file__ or "")
    with open(src, encoding="utf-8") as fh:
        body = fh.read()
    call_sites = [ln for ln in body.splitlines()
                  if "DETACHED_CLONE_MATRIX_GREEN" in ln and not ln.lstrip().startswith("#")
                  and "replaces the module constant" not in ln]
    assert not call_sites, (
        "production is gated on a Boolean in Stage-3's own source again; it must be gated "
        f"on an admitted Stage-2 aggregate read from disk: {call_sites}")


def test_a_production_run_without_an_admitted_aggregate_is_refused_by_name():
    with pytest.raises(v2.ProductionConsumptionGated, match=v2.GATE_NO_ADMITTED_AGGREGATE):
        v2.load_admitted_stage2_inputs(require_production=True)


def test_a_fixture_aggregate_cannot_open_the_production_gate(fixture_aggregate):
    """The sealed plumbing input must not be launderable into a production run."""
    assert fixture_aggregate.artifact_class == "fixture"    # non-vacuous
    with pytest.raises(sa.Stage2AggregateError):
        v2.load_admitted_stage2_inputs(require_production=True,
                                       admitted_aggregate=fixture_aggregate)


# --------------------------------------------------------------------------- #
# The admitted branch is actually WALKED.
# --------------------------------------------------------------------------- #
def test_an_admitted_analysis_aggregate_opens_the_gate(analysis_aggregate):
    out = v2.load_admitted_stage2_inputs(require_production=True,
                                         admitted_aggregate=analysis_aggregate)
    assert out["production_consumption_gated"] is False
    # ...and it still invents nothing: no bundles were passed, so no lever exists.
    assert out["counts"]["n_measured_levers"] == 0
    assert out["counts"]["n_pathway_nodes"] == 0


def test_the_binding_names_every_field(analysis_aggregate):
    """Reads each field off the real dataclass. An attribute that does not exist raises
    here rather than on the first production run."""
    out = v2.load_admitted_stage2_inputs(require_production=True,
                                         admitted_aggregate=analysis_aggregate)
    binding = out["stage2_aggregate_binding"]
    assert binding is not None, "non-vacuous guard: the admitted branch must have run"

    # STAGE-3's own class. Stage 2 declares no artifact_class, and never did.
    assert binding["artifact_class"] == "analysis"
    assert binding["verdict"] == sa.ADMIT == "admit"
    # THE PINNED AGGREGATE VERIFIER — bound by IDENTITY, not by a substring. This assertion
    # used to read `"independent" in verifier_id`, which the real verifier's id does not
    # contain: it would have refused every genuine Stage-2 report and admitted any forgery
    # that merely named itself "…independent…". Independence is the STRUCTURED FIELD
    # generator_is_not_verifier, which admit_aggregate binds.
    assert binding["aggregate_verifier_id"] == sa.AGGREGATE_VERIFIER_ID
    assert "independent" not in binding["aggregate_verifier_id"]
    for key in ("manifest_raw_sha256", "manifest_canonical_sha256", "manifest_self_hash",
                "stage1_release_sha256"):
        assert len(binding[key]) == 64, f"{key} is not a sha256"
    # the topology the aggregate reconstructed, carried into the projection
    assert binding["n_bundles"] == sa.N_BUNDLES == 15
    assert binding["n_arms"] == sa.N_ARM_SLOTS == 300


def test_an_unadmitted_run_carries_no_aggregate_binding():
    out = v2.load_admitted_stage2_inputs()          # not a production run
    assert out["production_consumption_gated"] is True
    assert out["stage2_aggregate_binding"] is None
