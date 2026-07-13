"""The production substitution runner stops NOW, and touches no network doing it.

Two things must be proved, not asserted in prose:

  1. **It refuses.** Gate 2 (`verifier.verify_stage3`) has never passed — Stage-3's build context
     does not exist — and a fixture-class bundle can never reach production. Both are refusals at
     STEP 1, and every later step is recorded `not_reached`, which is not `passed`.

  2. **No request reaches the wire.** Not "we think it stops before the fetch": the runner is
     driven with a transport that RAISES if it is called at all. If any step prefetched from an
     unadmitted bundle, these tests would fail loudly instead of quietly hitting the internet.

The bundle we actually hold declares `artifact_class: analysis` and
`data_status: acquired_public_responses` — so the honest reason it cannot go to production is
gate 2, not its class. Both refusals are covered anyway: the class refusal is what protects the
chain the day a fixture-class bundle is handed to it.
"""

from __future__ import annotations

import json
import os

import pytest

from _stage3_forge import PINNED_BUNDLE, copy_bundle, reseal_fully
from analysis import run_production
from analysis.run_production import STEPS, run_production as run_chain


class ExplodingTransport:
    """The wire, wired to a klaxon. Any request at all is a test failure."""

    clock = "2026-07-13T05:00:00Z"

    def __init__(self):
        self.calls: list[str] = []

    def __call__(self, url: str, timeout: int):
        self.calls.append(url)
        raise AssertionError(
            f"a request was put on the wire before admission passed: {url!r}. The production "
            "runner must not prefetch from an unadmitted bundle.")


@pytest.fixture()
def no_network():
    return ExplodingTransport()


def _client(transport):
    from analysis.acquire_http import Client

    # allow_network=True deliberately: if the chain were to fetch, nothing would stop it but the
    # transport itself. That is what makes "no request occurred" a PROOF rather than a policy.
    return Client(transport=transport, allow_network=True)


def _run(bundle, tmp_path, transport):
    return run_chain(
        bundle, str(tmp_path / "run"),
        out_bundle=str(tmp_path / "evidence.json"),
        outputs_root=str(tmp_path / "outputs"),
        client=_client(transport))


# ------------------------------------------------------- 1. it stops, and it stops at admission


def test_the_chain_stops_at_admission_because_gate_2_has_never_passed(tmp_path, no_network):
    run = _run(PINNED_BUNDLE, tmp_path, no_network)

    assert run.stopped_at == "admit"
    assert run.stop_code == "stage3_external_verifier_not_run"
    assert not run.produced_an_artifact


def test_every_later_step_is_recorded_not_reached_which_is_not_passed(tmp_path, no_network):
    run = _run(PINNED_BUNDLE, tmp_path, no_network)
    status = {s.step: s.status for s in run.steps}

    assert status["admit"] == "refused"
    for step in ("plan", "acquire", "materialize", "verify", "project"):
        assert status[step] == "not_reached"
    assert set(status) == set(STEPS)                      # nothing silently omitted


def test_no_artifact_of_any_kind_is_written_when_the_chain_refuses(tmp_path, no_network):
    _run(PINNED_BUNDLE, tmp_path, no_network)

    assert not os.path.exists(str(tmp_path / "evidence.json"))
    outputs = str(tmp_path / "outputs")
    assert not os.path.exists(outputs) or os.listdir(outputs) == []


# --------------------------------------------------------------- 2. no request reaches the wire


def test_not_one_request_is_put_on_the_wire(tmp_path, no_network):
    """The load-bearing proof. The transport raises on ANY call, and the client is even given
    network permission — so nothing but the chain's own ordering prevents a fetch."""
    _run(PINNED_BUNDLE, tmp_path, no_network)
    assert no_network.calls == []


def test_the_runner_does_not_prefetch_while_deciding_whether_to_admit(tmp_path, no_network):
    """A plan built from unadmitted tables would be a schedule over bytes nobody verified — and
    building it would mean reading the bundle before the gates ran."""
    run = _run(PINNED_BUNDLE, tmp_path, no_network)

    assert no_network.calls == []
    plan_step = next(s for s in run.steps if s.step == "plan")
    assert plan_step.status == "not_reached"              # the plan never ran at all


# ----------------------------------------------------------------- 3. the fixture-class refusal


def test_a_fixture_class_bundle_can_never_reach_production(tmp_path, no_network):
    """`artifact_class` is the class gate. A fixture bundle is refused however good it looks —
    and it is refused by the CONTRACT restatement, not by this runner's good intentions."""
    bundle = copy_bundle(tmp_path)
    path = os.path.join(bundle, "drug_annotation.json")
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    doc["artifact_class"] = "fixture"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)
    reseal_fully(bundle)                                  # an attacker repairs every hash

    run = run_chain(bundle, str(tmp_path / "run2"),
                    out_bundle=str(tmp_path / "e2.json"),
                    outputs_root=str(tmp_path / "o2"),
                    client=_client(no_network))

    assert run.stopped_at == "admit"
    # The refusal comes from GATE 1 (the contract restatement in stage3_contract_v2), not from
    # this runner's own belt-and-braces class check. The chain is protected by the contract even
    # if a future runner forgets to look.
    assert run.stop_code == "stage3_artifact_class_refused"
    assert "fixture" in run.stop_detail
    assert not run.produced_an_artifact
    assert no_network.calls == []                         # and still no request


# ------------------------------------------------------------------------------- the receipt


def test_the_receipt_says_where_it_stopped_and_that_nothing_was_produced(tmp_path, no_network):
    run = _run(PINNED_BUNDLE, tmp_path, no_network)
    doc = run.document()

    assert doc["produced_an_artifact"] is False
    assert doc["stopped_at"] == "admit"
    assert doc["chain"] == list(STEPS)
    rules = " ".join(doc["hard_rules"])
    assert "not `passed`" in rules and "no PK value is invented" in rules


def test_the_cli_exits_2_and_says_it_produced_nothing(tmp_path, no_network, capsys):
    code = run_production.main(
        ["--stage3-annotation-bundle", PINNED_BUNDLE,
         "--run-root", str(tmp_path / "run"),
         "--evidence-bundle-out", str(tmp_path / "evidence.json"),
         "--outputs-root", str(tmp_path / "outputs"),
         "--receipt-out", str(tmp_path / "receipt.json")],
        client=_client(no_network))

    assert code == 2
    err = capsys.readouterr().err
    assert "stage3_external_verifier_not_run" in err
    assert "No artifact was produced" in err
    assert no_network.calls == []

    with open(str(tmp_path / "receipt.json"), encoding="utf-8") as fh:
        assert json.load(fh)["produced_an_artifact"] is False


def test_there_is_no_flag_that_turns_a_gate_off():
    """The absence IS the feature. A production substitution that can be talked out of a gate is
    not a production substitution."""
    import argparse
    import contextlib
    import io

    for forbidden in ("--skip-verifier", "--force", "--allow-fixture", "--no-verify"):
        buf = io.StringIO()
        with pytest.raises(SystemExit), contextlib.redirect_stderr(buf), \
                contextlib.suppress(argparse.ArgumentError):
            run_production.main([forbidden, "--stage3-annotation-bundle", PINNED_BUNDLE,
                                 "--run-root", "/tmp/x", "--evidence-bundle-out", "/tmp/e.json",
                                 "--outputs-root", "/tmp/o"])
        assert "unrecognized arguments" in buf.getvalue() or "invalid" in buf.getvalue()
