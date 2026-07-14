"""`--acquire-queue`: the one command that acquires the real candidate queue.

It is deliberately the most locked-down path in the layer, because it is the only one that touches
real candidates:

  * it REFUSES until Stage-3's own verifier (gate 2) has actually passed. `not_run` is not a pass,
    and a queue acquired against a bundle nobody independently verified would bind real evidence
    to unverified upstream bytes.
  * the moiety names come from the ADMITTED bundle's queued rows, in candidate order. Nothing is
    typed by hand, and nothing that Stage 3 did not queue is acquired.
  * concurrency is bounded and cannot change a record.
"""

from __future__ import annotations

import pytest

from _stage3_forge import PINNED_BUNDLE
from analysis import run_acquire
from analysis.firewall import Rejection
from analysis.run_acquire import queued_moiety_names
from analysis.stage3_admission import admit


def test_the_queue_names_come_from_the_admitted_bundle_in_candidate_order():
    names = queued_moiety_names(admit(PINNED_BUNDLE).tables)

    assert names == [
        "IPILIMUMAB", "INOLIMOMAB", "TREMELIMUMAB", "ZALIFRELIMAB",
        "CADONILIMAB", "QUAVONLIMAB", "ERFONRILIMAB",
    ]
    assert len(names) == 7                       # exactly what Stage 3 queued. Not one more.


def test_a_candidate_stage3_never_queued_is_not_in_the_queue():
    tables = admit(PINNED_BUNDLE).tables
    names = set(queued_moiety_names(tables))

    not_queued = {
        m["preferred_name"] for m in tables["active_moieties"]
        if m["active_moiety_id"] not in {
            c["active_moiety_id"] for c in tables["candidates"]
            if c.get("stage4_assessment_status") == "queued"
        }
    }
    assert names.isdisjoint(not_queued)
    assert "ANTI-TAC 90 Y-HAT" not in names      # present in the bundle, never queued


def test_acquiring_the_queue_is_refused_until_stage3s_own_verifier_has_passed(tmp_path, capsys):
    """THE GATE. Today gate 2 is `not_run` (it needs Stage-3's build context), so this refuses —
    which is exactly what must happen until the real, externally verified bundle lands."""
    code = run_acquire.main([
        "--stage3-annotation-bundle", PINNED_BUNDLE,
        "--run-root", str(tmp_path / "run"),
        "--acquire-queue", "--allow-network",
    ])
    assert code == 2
    err = capsys.readouterr().err
    assert "queue_acquisition_requires_external_verifier" in err
    assert "not_run" in err or "verifier" in err


def test_the_refusal_names_the_flag_that_makes_the_run_data_bound(tmp_path):
    with pytest.raises(Rejection) as exc:
        run_acquire.run(
            PINNED_BUNDLE, str(tmp_path / "run"), names=[], allow_network=True, setid=None,
            require_external_verifier=False, acquire_queue=True)
    assert exc.value.code == "queue_acquisition_requires_external_verifier"
    assert "--require-external-verifier" in exc.value.detail


def test_the_plan_still_works_without_the_verifier_because_it_acquires_nothing(tmp_path):
    """Planning is readiness, not acquisition — it must stay usable before gate 2 can run, or the
    lane could never be made ready in advance."""
    code, receipt = run_acquire.run(
        PINNED_BUNDLE, str(tmp_path / "run"), names=[], allow_network=False, setid=None,
        require_external_verifier=False, plan_only=True)

    assert code == 0
    assert receipt["plan"]["n_acquirable"] == 7
    assert receipt["acquisition"]["candidates_acquired"] == 0
    assert receipt["acquisition"]["transport"]["fetched"] == 0
