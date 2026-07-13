"""Admission must test the PRODUCER's gate, not only its own.

I admitted store `b20ec29b` because MY verifier opened and hashed the provenance file and
found it correct. **That was the wrong test** — and the mistake is precisely the one this
lane has spent the whole round calling out in everyone else.

An external verifier catching a mutation does not repair a producer gate that returns True
on one. **Downstream consumers run the producer's verify path** — it is what ships with the
store. A fail-open producer gate is a hole in the product regardless of what my lane happens
to catch in its own process.

Proven against `0e349b1`: `universe_verify.verify_from_disk` opens `universe_store.rows.json`
and `target_eligibility_evidence.json` and **never opens** `source_provenance.public.json`:

    clean store                 -> ok=True  violations=[]
    provenance MUTATED          -> ok=True  violations=[]     <-- fail-open
    provenance DELETED entirely -> ok=True  violations=[]     <-- fail-open

A gate cannot catch a mutation to a file it never reads.
"""
from __future__ import annotations

import json
import os

from verifier import source_manifest as sm
from verifier.report import Report

PROV = [{"name": "uniprot_idmapping", "release": "2026_02",
         "acquired_sha256": "0741a549" + "0" * 56}]


def _failed(rep):
    return [n for n, ok, _ in rep.checks if not ok]


def _store(tmp_path):
    d = tmp_path / "store"
    d.mkdir()
    (d / sm.PROVENANCE_FILENAME).write_text(json.dumps(PROV))
    (d / "universe_manifest.json").write_text("{}")
    return str(d)


def _fail_open(*, store_dir, **kw):
    """The 0e349b1 shape: never opens the provenance file, so it cannot see the mutation."""
    return {"ok": True, "violations": []}


def _fail_closed(*, store_dir, **kw):
    """A correct gate: opens the provenance and checks it."""
    p = os.path.join(store_dir, sm.PROVENANCE_FILENAME)
    if not os.path.isfile(p):
        return {"ok": False, "violations": ["provenance_missing"]}
    with open(p) as fh:
        prov = json.load(fh)
    if prov != PROV:
        return {"ok": False, "violations": ["public_source_provenance_hash_drift"]}
    return {"ok": True, "violations": []}


# --------------------------------------------------------------------------- #
def test_a_FAIL_OPEN_producer_gate_is_refused(tmp_path):
    """The exact 0e349b1 defect, and the exact reason b20ec29b must not be admitted."""
    rep = Report()
    sm.check_producer_gate_rejects_provenance_mutation(
        rep, store_dir=_store(tmp_path), producer_verify=_fail_open, verify_kwargs={})
    failed = _failed(rep)
    assert len(failed) == 2, "both the mutated AND the deleted probe must fail"
    assert all(sm.GATE_PRODUCER_FAIL_OPEN in n for n in failed)


def test_a_FAIL_CLOSED_producer_gate_is_admitted(tmp_path):
    rep = Report()
    sm.check_producer_gate_rejects_provenance_mutation(
        rep, store_dir=_store(tmp_path), producer_verify=_fail_closed, verify_kwargs={})
    assert not _failed(rep)


def test_the_probe_reports_what_the_producer_gate_ACTUALLY_returned(tmp_path):
    rep = Report()
    sm.check_producer_gate_rejects_provenance_mutation(
        rep, store_dir=_store(tmp_path), producer_verify=_fail_open, verify_kwargs={})
    detail = next(d for n, ok, d in rep.checks if not ok)
    assert "ok=True" in detail


def test_a_gate_that_RAISES_on_a_deleted_file_counts_as_a_refusal(tmp_path):
    def raiser(*, store_dir, **kw):
        p = os.path.join(store_dir, sm.PROVENANCE_FILENAME)
        with open(p) as fh:                      # raises when deleted
            prov = json.load(fh)
        return {"ok": prov == PROV, "violations": []}

    rep = Report()
    sm.check_producer_gate_rejects_provenance_mutation(
        rep, store_dir=_store(tmp_path), producer_verify=raiser, verify_kwargs={})
    # mutation -> ok False; deletion -> raises, which IS a refusal
    assert not _failed(rep)


def test_a_probe_whose_CONTROL_fails_proves_nothing(tmp_path):
    """If the clean copy already fails, the mutation probe below is meaningless."""
    def always_false(*, store_dir, **kw):
        return {"ok": False, "violations": ["something else"]}

    rep = Report()
    sm.check_producer_gate_rejects_provenance_mutation(
        rep, store_dir=_store(tmp_path), producer_verify=always_false, verify_kwargs={})
    assert any("control" in n.lower() for n in _failed(rep))


def test_the_store_is_never_mutated_in_place(tmp_path):
    """The probe works on a scratch copy. The real store is not touched."""
    store = _store(tmp_path)
    before = open(os.path.join(store, sm.PROVENANCE_FILENAME)).read()
    rep = Report()
    sm.check_producer_gate_rejects_provenance_mutation(
        rep, store_dir=store, producer_verify=_fail_open, verify_kwargs={})
    assert open(os.path.join(store, sm.PROVENANCE_FILENAME)).read() == before
