"""The two NEBPI blockers, as permanent gates.

BLOCKER 1 — the same evidence multiset produced two different classes under ONE
scorecard_set_id, decided by which row happened to be first in the list. One cache key,
two scientifically different documents.

BLOCKER 2 — `not_detected` skipped the potency gate entirely and went straight to
Grossman's "little to no drug in NEB", so an IC50 from an unrelated disease could
underwrite an `impermeable` class. Table 2 footnote (a) — "Accounting for potency" — is
attached to that branch too.

Every case here is run through all three implementations that must agree: the engine, the
emit-time verifier, and the standalone verifier that imports no analysis code.
"""

from __future__ import annotations

import itertools
import tempfile

import pytest

from analysis.emit import emit
from analysis.evidence_records import (
    EvidenceType,
    NebpiCriterionId,
    NebpiObservation,
    ObservationState,
)
from analysis.ids import code_tree_sha256, derive_scorecard_set_id
from analysis.emit import environment_lock
from analysis.method_config import METHOD_DIR, load_method_bundle
from analysis.nebpi_reduce import CONFLICTING, observation_identity, reduce_criterion
from analysis.pipeline import run_pipeline
from analysis.verify import verify_output_dir
from fixtures import stage4_inputs
from verifier.checks import verify_release

METHOD = load_method_bundle()

CTX = "CTX-001B"
CAND = "FIXTURE-001"


def _prov(inputs):
    return next(o.provenance for o in inputs.nebpi_observations if o.context_id == CTX)


def absence(inputs, oid: str, criterion, adequate: bool = True) -> NebpiObservation:
    return NebpiObservation(
        observation_id=oid, candidate_id=CAND, context_id=CTX, criterion_id=criterion,
        state=ObservationState.OBSERVED_ABSENT, assessment_adequate=adequate,
        adequacy_rationale="synthetic invariance fixture",
        evidence_type=EvidenceType.HUMAN_CLINICAL, provenance=_prov(inputs),
    )


def censor(inputs, *, kind="lod", limit="1", units="nM", status="not_detected"):
    """Turn the fixture's NEB measurement into a censored one with a source-bound limit."""
    for i, m in enumerate(inputs.exposures):
        if m.measurement_id == "EXP-001C":
            payload = m.model_dump(mode="python")
            payload.update(detection_status=status, concentration_source_string=None,
                           concentration_units=None, quantitation_limit_kind=kind,
                           quantitation_limit_source_string=limit,
                           quantitation_limit_units=units)
            inputs.exposures[i] = type(m).model_validate(payload)
            return
    raise AssertionError("EXP-001C not found")


def repoint_potency(inputs, **changes):
    for i, p in enumerate(inputs.potencies):
        if p.potency_id == "POT-001":
            payload = p.model_dump(mode="python")
            payload.update(**changes)
            inputs.potencies[i] = type(p).model_validate(payload)
            return
    raise AssertionError("POT-001 not found")


def mec(inputs) -> tuple[str, str]:
    p = next(p for p in inputs.potencies if p.potency_id == "POT-001")
    return p.value_source_string, p.units


def decision(result):
    return next(d for c in result.candidates if c.candidate_id == CAND
                for d in c.nebpi if d.context_id == CTX)


def scorecard_id(inputs) -> str:
    return derive_scorecard_set_id(
        inputs.candidate_set, METHOD, inputs.evidence_lanes(), inputs.sources,
        environment_lock()["lock_sha256"], inputs.config,
        code_sha256=code_tree_sha256()[0],
    )[0]


def emit_and_verify(inputs, result) -> tuple[dict, dict, bytes]:
    """-> (emit-time report, standalone report, the scorecards.json bytes)."""
    with tempfile.TemporaryDirectory(prefix="spot-invariance-") as root:
        out_dir, _ = emit(inputs, result, METHOD, root)
        emit_report = verify_output_dir(out_dir, inputs, METHOD)
        standalone = verify_release(out_dir, METHOD_DIR)
        with open(f"{out_dir}/scorecards.json", "rb") as fh:
            payload = fh.read()
    return emit_report, standalone, payload


# ------------------------------------------------------------ BLOCKER 1: permutation

def impermeable_case(order: tuple[int, ...]):
    """A fully-supported impermeable context, with the observations in a chosen order."""
    inputs = stage4_inputs()
    censor(inputs)
    extra = [
        absence(inputs, "INV-PD", NebpiCriterionId.PD_IN_NEB),
        absence(inputs, "INV-RAD", NebpiCriterionId.RADIOGRAPHIC_RESPONSE_IN_NEB),
    ]
    rows = list(inputs.nebpi_observations) + extra
    inputs.nebpi_observations = [rows[i] for i in order]
    return inputs


def test_every_permutation_of_the_observations_gives_byte_identical_output():
    """The decision is a function of the SET of rows, not of their order.

    Identical scorecard_set_id, class, status, criterion_states, branch proof AND emitted
    bytes — under the identity permutation, the reversal, and a spread of shuffles.
    """
    size = len(stage4_inputs().nebpi_observations) + 2
    orders = [tuple(range(size)), tuple(reversed(range(size)))]
    orders += [tuple(p) for p in itertools.islice(itertools.permutations(range(size)), 0, 40, 7)]

    seen: set[tuple] = set()
    payloads: set[bytes] = set()
    for order in orders:
        inputs = impermeable_case(order)
        assert len(inputs.nebpi_observations) == size  # the permutation lost no evidence
        result = run_pipeline(inputs, METHOD)
        d = decision(result)
        emit_report, standalone, payload = emit_and_verify(inputs, result)
        assert emit_report["status"] == "pass"
        assert standalone["status"] == "pass"
        seen.add((
            scorecard_id(inputs),
            d.nebpi_class,
            d.nebpi_status,
            tuple(sorted(d.criterion_states.items())),
            tuple(sorted(b.branch_id for b in d.branch_proof if b.satisfied)),
        ))
        payloads.add(payload)

    assert len(orders) >= 8
    assert len(seen) == 1, f"order changed the result: {seen}"
    assert len(payloads) == 1, "order changed the emitted bytes"
    assert next(iter(seen))[1] == "impermeable"


@pytest.mark.parametrize("adequate_first", [True, False])
def test_adequacy_disagreement_is_conflicting_in_both_orders(adequate_first):
    """Two `observed_absent` PD rows, one adequate and one not. The old code took rows[0]."""
    inputs = stage4_inputs()
    censor(inputs)
    good = absence(inputs, "INV-PD-GOOD", NebpiCriterionId.PD_IN_NEB, True)
    bad = absence(inputs, "INV-PD-BAD", NebpiCriterionId.PD_IN_NEB, False)
    rad = absence(inputs, "INV-RAD", NebpiCriterionId.RADIOGRAPHIC_RESPONSE_IN_NEB, True)
    pair = [good, bad] if adequate_first else [bad, good]
    inputs.nebpi_observations = list(inputs.nebpi_observations) + pair + [rad]

    result = run_pipeline(inputs, METHOD)
    d = decision(result)

    assert d.nebpi_class is None
    assert d.nebpi_status == "not_classifiable"
    assert d.criterion_states["pd_in_neb"] == CONFLICTING
    assert "conflicting_observations:pd_in_neb" in d.reason_codes

    emit_report, standalone, _ = emit_and_verify(inputs, result)
    assert emit_report["status"] == "pass" and standalone["status"] == "pass"


def test_two_agreeing_distinct_rows_are_also_conflicting():
    """No cross-study aggregation rule exists, so agreement is not confirmation either."""
    inputs = stage4_inputs()
    a = absence(inputs, "INV-A", NebpiCriterionId.PD_IN_NEB, True)
    b = absence(inputs, "INV-B", NebpiCriterionId.PD_IN_NEB, True)
    assert reduce_criterion([a, b], NebpiCriterionId.PD_IN_NEB).state == CONFLICTING
    assert reduce_criterion([b, a], NebpiCriterionId.PD_IN_NEB).state == CONFLICTING


def test_byte_identical_duplicates_collapse_and_add_no_evidence():
    """The same record twice IS the same record. It cannot vote twice."""
    inputs = stage4_inputs()
    row = absence(inputs, "INV-DUP", NebpiCriterionId.PD_IN_NEB, True)
    twin = row.model_copy(deep=True)
    assert observation_identity(row) == observation_identity(twin)

    one = reduce_criterion([row], NebpiCriterionId.PD_IN_NEB)
    two = reduce_criterion([row, twin], NebpiCriterionId.PD_IN_NEB)
    assert two.state == one.state == ObservationState.OBSERVED_ABSENT.value
    assert two.n_distinct_rows == 1


def test_a_conflicting_criterion_satisfies_no_branch():
    inputs = stage4_inputs()
    a = absence(inputs, "INV-A", NebpiCriterionId.PD_IN_NEB, True)
    b = absence(inputs, "INV-B", NebpiCriterionId.PD_IN_NEB, False)
    assert reduce_criterion([a, b], NebpiCriterionId.PD_IN_NEB).satisfies_branches is False


# --------------------------------------------------- BLOCKER 2: the censored-PK gate

def censored_case(**censor_kw):
    """A context that would be `impermeable` if the non-detect bounds the MEC."""
    inputs = stage4_inputs()
    censor(inputs, **censor_kw)
    inputs.nebpi_observations = list(inputs.nebpi_observations) + [
        absence(inputs, "INV-PD", NebpiCriterionId.PD_IN_NEB),
        absence(inputs, "INV-RAD", NebpiCriterionId.RADIOGRAPHIC_RESPONSE_IN_NEB),
    ]
    return inputs


def run_all_three(inputs):
    result = run_pipeline(inputs, METHOD)
    d = decision(result)
    emit_report, standalone, _ = emit_and_verify(inputs, result)
    assert emit_report["status"] == "pass", "the emit-time verifier disagreed with the engine"
    assert standalone["status"] == "pass", "the standalone verifier disagreed with the engine"
    return d


def test_a_bounded_non_detect_below_the_mec_is_impermeable():
    """The one case that DOES classify: the assay could see far below the MEC, and saw nothing."""
    d = run_all_three(censored_case(limit="1"))  # MEC is 100 nM in the fixture
    assert d.nebpi_class == "impermeable"
    assert d.pk_derivation["derived_level"] == "pk_little_to_none_in_neb"
    assert d.pk_derivation["censored_bound_below_mec"] is True
    assert d.pk_derivation["censored_bound_kind"] == "lod"


def test_a_non_detect_with_no_numeric_limit_does_not_classify():
    """A non-detect from an assay of unknown sensitivity bounds nothing."""
    inputs = censored_case()
    for i, m in enumerate(inputs.exposures):
        if m.measurement_id == "EXP-001C":
            payload = m.model_dump(mode="python")
            payload.update(quantitation_limit_kind=None,
                           quantitation_limit_source_string=None,
                           quantitation_limit_units=None)
            inputs.exposures[i] = type(m).model_validate(payload)

    d = run_all_three(inputs)
    assert d.nebpi_class is None
    assert d.pk_derivation["derived_level"] == "pk_not_evaluated"
    assert d.pk_derivation["blocked_code"] == "no_source_bound_quantitation_limit"


def test_a_non_detect_bound_to_an_ic50_does_not_classify():
    """THE audit's bypass: an IC50 is not an MEC, and same-moiety is not the same question."""
    inputs = censored_case()
    repoint_potency(inputs, metric="IC50")

    d = run_all_three(inputs)
    assert d.nebpi_class is None
    assert d.pk_derivation["blocked_code"] == "potency_metric_not_a_target_concentration"


def test_a_non_detect_bound_to_another_tumour_context_does_not_classify():
    inputs = censored_case()
    repoint_potency(inputs, biological_context="OTHER-DISEASE")
    inputs.potency_context_links = []

    d = run_all_three(inputs)
    assert d.nebpi_class is None
    assert d.pk_derivation["blocked_code"] == "potency_context_not_relevant"


def test_a_non_detect_with_a_mismatched_binding_state_does_not_classify():
    inputs = censored_case()
    repoint_potency(inputs, binding_state="total")

    d = run_all_three(inputs)
    assert d.nebpi_class is None
    assert d.pk_derivation["blocked_code"] == "free_total_mismatch"


def test_a_non_detect_with_a_mismatched_unit_family_does_not_classify():
    """A molar MEC and a mass/volume detection limit are not comparable without an MW."""
    inputs = censored_case(units="ng/mL")

    d = run_all_three(inputs)
    assert d.nebpi_class is None
    assert d.pk_derivation["blocked_code"] == "unit_family_mismatch"


@pytest.mark.parametrize(
    "limit,expected_class,below",
    [
        ("99.999999", "impermeable", True),   # strictly below the 100 nM MEC
        ("100", None, False),                 # EXACTLY the MEC: excludes nothing
        ("100.000001", None, False),          # above it
        ("500", None, False),                 # a blunt assay: could not have seen the MEC
    ],
)
def test_the_bound_vs_mec_boundary_is_strict(limit, expected_class, below):
    """Only bound < MEC. At bound == MEC the true value could sit AT the MEC."""
    value, units = mec(stage4_inputs())
    assert (value, units) == ("100", "nM")

    d = run_all_three(censored_case(limit=limit))
    assert d.nebpi_class == expected_class
    assert d.pk_derivation["censored_bound_below_mec"] is below
    if not below:
        assert d.pk_derivation["blocked_code"] == "censored_bound_not_below_mec"


def test_below_lloq_must_be_bounded_by_an_lloq_not_an_lod():
    """A below-LLOQ value can still sit ABOVE the LOD, so an LOD does not bound it."""
    with pytest.raises(ValueError, match="must be bounded by an 'lloq'"):
        censor(stage4_inputs(), status="below_lloq", kind="lod", limit="1")


def test_below_lloq_with_an_lloq_below_the_mec_classifies():
    d = run_all_three(censored_case(status="below_lloq", kind="lloq", limit="2"))
    assert d.nebpi_class == "impermeable"
    assert d.pk_derivation["censored_bound_kind"] == "lloq"
