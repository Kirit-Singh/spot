"""A FIXTURE run must be able to RUN. Otherwise the firewall invites the fraud it exists to stop.

`v2_input_loader._require_admitted_aggregate` ended with an unconditional
`require_analysis(admitted)`, and `_v2_main` always passes `require_production=True`. So a run
declaring `--artifact-class fixture` was ALSO required to be an analysis, and refused at
`a_fixture_aggregate_cannot_enter_the_analysis_path`.

That is wrong twice over:

  * a fixture run became impossible to execute at all — the plumbing could never be exercised
    end to end, which is how a CLI's success path stays broken for a whole round; and
  * it created pressure to do the ONE thing the firewall exists to prevent: relabel a synthetic
    aggregate "analysis" just to make the command run.

The class check belongs where the class is DECLARED — `bundle_v2.build_document`, conditionally.
A fixture aggregate emits a FIXTURE bundle (barred from Stage 4 by its class); an ANALYSIS still
requires a genuinely admitted production aggregate.
"""
from __future__ import annotations

import inspect

from druglink import artifact_class as ac
from druglink import bundle_v2, run_stage3_v2, v2_input_loader as v2


def test_the_production_gate_asks_ONE_question_is_there_an_admitted_aggregate():
    """It must NOT also ask 'is this an analysis'. That conflation is the defect."""
    # AST, not a string search: a docstring may DISCUSS require_analysis (this one does, to
    # explain why it is gone). Only an actual CALL is the defect.
    import ast
    tree = ast.parse(inspect.getsource(v2._require_admitted_aggregate).lstrip())
    called = {n.func.attr for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert "require_analysis" not in called, (
        "the production gate calls require_analysis again — so a --artifact-class fixture run "
        "is refused for not being an analysis, and the only way to run the plumbing is to "
        "relabel a synthetic aggregate as real")


def test_the_class_firewall_lives_where_the_class_is_DECLARED():
    """build_document enforces it, and CONDITIONALLY — that is the right home for it."""
    src = inspect.getsource(bundle_v2.build_document)
    assert "require_analysis" in src
    assert "== ac.ANALYSIS" in src or "== ANALYSIS" in src, (
        "the firewall must fire only on the ANALYSIS path; unconditionally, it also blocks the "
        "fixture path it was never meant to touch")


def test_a_fixture_aggregate_STILL_cannot_become_an_analysis():
    """The firewall itself is untouched. Relabelling remains impossible."""
    from druglink import stage2_aggregate as sa
    assert hasattr(sa, "require_analysis")
    src = inspect.getsource(sa.require_analysis)
    assert "ANALYSIS" in src and "refuse" in src.lower()


def test_a_production_run_with_NO_admitted_aggregate_is_still_refused():
    """Removing require_analysis from the gate must not open the gate."""
    import pytest
    with pytest.raises(v2.ProductionConsumptionGated, match=v2.GATE_NO_ADMITTED_AGGREGATE):
        v2.load_admitted_stage2_inputs(require_production=True)


def test_v2_production_has_NO_live_source_code_boolean_gate():
    """`DETACHED_CLONE_MATRIX_GREEN` was a Boolean literal in Stage-3's own source: no upstream
    lane and no artifact on disk could flip it, so it asserted a state nothing had verified. The
    gate is now the artifact. This test exists to stop another one appearing."""
    import ast
    tree = ast.parse(inspect.getsource(run_stage3_v2))
    # a NAME reference in real code — not a mention inside a docstring or comment
    refs = [n for n in ast.walk(tree)
            if isinstance(n, ast.Attribute) and n.attr == "DETACHED_CLONE_MATRIX_GREEN"]
    refs += [n for n in ast.walk(tree)
             if isinstance(n, ast.Name) and n.id == "DETACHED_CLONE_MATRIX_GREEN"]
    assert not refs, (
        "a source-code Boolean gate is back on the v2 production path: no upstream lane and no "
        "artifact on disk can flip a constant in Stage-3's own source, so it would assert a "
        "state nothing had verified")


def test_both_artifact_classes_are_reachable_from_the_cli():
    assert set(ac.ARTIFACT_CLASSES) >= {"analysis", "fixture"}
    assert run_stage3_v2.bridge_consumer_ready() is True, (
        "the bridge consumer must exist, or --v2 refuses before it reads a single input")
