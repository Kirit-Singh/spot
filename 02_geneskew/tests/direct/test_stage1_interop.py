"""Stage-1 -> Stage-2 interoperability: the lane namespace is on the RUN, not the biology.

Stage-1 emits frozen program ids (``treg_like``, ``th1_like``). Those are registry
keys: they are carried byte-for-byte, and prefixing them would rename the biology and
break the registry binding. What IS lane-scoped is the pair of run identifiers
(``question_id``, ``selection_id``), and isolation there stays fail-closed.

These tests use the canonical superset shape Stage-1 actually ships
(``spot.stage01_selection.v1``: top-level ``lane``, nested ``bridge``, ``A``/``B``,
``ids``, ``hashes``, plus frontend display mirrors), with the real biological ids.

Every negative test below breaks EXACTLY ONE invariant, and asserts on the message
that invariant alone can produce. That matters here: the fixture re-derives the run
ids from the contract's final content, so a test that alters the biology still ships
self-consistent ids and reaches the registry binding it means to test — while the
forgery test writes its ids verbatim, and so reaches the derivation check instead.
"""
import json
import os

import pandas as pd
import pytest

from direct import config, selection
from direct.run_screen import build_screen
from direct.selection import SelectionError

pytestmark = pytest.mark.filterwarnings("ignore")

# The frozen Stage-1 registry ids. Not namespaced. Not parsed. Not decorated.
BIO_IDS = ("treg_like", "th1_like")

# The research lane's run-id prefix, and the length of the derivation body under it.
RQ = "rq_"

# What the Stage-1 frontend also puts in the artifact. Stage-2 must ignore extras,
# never bind to them, and never let one stand in for a program id.
DISPLAY_MIRRORS = {
    "contrast_id": "treg_like__vs__th1_like",
    "program_a_label": "Treg-like",
    "program_b_label": "Th1-like",
    "dataset_id": "GWCD4i",
    "donor_scope": "all_donors",
    "artifact_status": "research_only",
    "program_registry_sha256": "0" * 64,
}


def _load(args):
    return selection.load_research_selection(args.selection)


def _reprefixed_ids(sel, prefix):
    """The EARNED id body, wearing the wrong lane prefix.

    Only the namespace is mutated: the 32-char derivation body is exactly the one
    this contract earned. So the research loader can only refuse it for the prefix
    -- never because the id was garbage.
    """
    return {"question_id": prefix + sel.question_id[len(RQ):],
            "selection_id": prefix + sel.selection_id[len(RQ):]}


# --------------------------------------------------------------------------- #
# It loads: exact biological ids, canonical rq_ run ids, superset shape.
# --------------------------------------------------------------------------- #
def test_the_canonical_research_bridge_loads_with_exact_biological_ids(synthetic_run):
    sel = _load(synthetic_run(lane="research_only", program_ids=BIO_IDS))
    assert (sel.a.program_id, sel.b.program_id) == BIO_IDS
    assert sel.lane == config.LANE_RESEARCH


def test_the_run_identifiers_recompute_from_the_contract(synthetic_run):
    sel = _load(synthetic_run(lane="research_only", program_ids=BIO_IDS))
    check = selection.recomputed_ids(sel)
    assert check["question_id_matches_declared"]
    assert check["selection_id_matches_declared"]
    assert check["question_id_recomputed"] == sel.question_id
    assert check["selection_id_recomputed"] == sel.selection_id
    # The namespace rides on the RUN ids -- and only on them.
    assert sel.question_id.startswith(RQ) and sel.selection_id.startswith(RQ)
    assert not any(p.startswith(RQ) for p in (sel.a.program_id, sel.b.program_id))


def test_frontend_display_mirrors_are_ignored_extras(synthetic_run):
    """Extras may ride along; they may not be read, and they may not change a run."""
    plain = _load(synthetic_run(lane="research_only", program_ids=BIO_IDS))
    with_extras = _load(synthetic_run(lane="research_only", program_ids=BIO_IDS,
                                      **DISPLAY_MIRRORS))
    assert (with_extras.a.program_id, with_extras.b.program_id) == BIO_IDS
    # An ignored extra is ignored: it cannot enter the run identity either. The
    # declared ids are derived over the WHOLE contract, extras included -- so an
    # extra that leaked into the derivation would move them off `plain`.
    assert with_extras.question_id == plain.question_id
    assert with_extras.selection_id == plain.selection_id
    check = selection.recomputed_ids(with_extras)
    assert check["question_id_matches_declared"]
    assert check["selection_id_matches_declared"]


def test_the_canonical_contract_runs_end_to_end_and_binds_the_registry(synthetic_run):
    """The real proof of a registry key: it resolves to a real program."""
    result = build_screen(synthetic_run(lane="research_only", program_ids=BIO_IDS,
                                        **DISPLAY_MIRRORS))
    with open(os.path.join(result["out_dir"], "provenance.json")) as fh:
        prov = json.load(fh)

    axis = prov["axis"]
    assert (axis["A"]["program_id"], axis["B"]["program_id"]) == BIO_IDS
    # Bound, not merely echoed: a resolved registry program carries its real panel.
    assert axis["A"]["panel"] and axis["B"]["panel"]

    assert result["namespace"] == config.LANE_RESEARCH
    assert prov["namespace"] == config.LANE_RESEARCH
    assert axis["lane"] == config.LANE_RESEARCH
    assert prov["question_id"].startswith(RQ)
    assert prov["selection_id"].startswith(RQ)

    df = pd.read_parquet(os.path.join(result["out_dir"], "screen.parquet"))
    for arm in config.ARMS:
        assert arm in df.columns


@pytest.mark.parametrize("key, value", [
    ("objective", "balanced_a_to_b"),
    ("balanced_a_to_b", 1.0),
    ("combination_objective", "mean"),
])
def test_no_combined_objective_may_ride_in_on_the_superset(synthetic_run, key, value):
    """The one mutation is the forbidden key: the ids stay earned (the derivation
    reads the poles, condition and hashes -- never a stray top-level key)."""
    args = synthetic_run(lane="research_only", program_ids=BIO_IDS, **{key: value})
    with pytest.raises(SelectionError, match="non-executable keys") as excinfo:
        _load(args)
    assert key in str(excinfo.value)


# --------------------------------------------------------------------------- #
# Lane isolation still fails closed -- on the run identifiers.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("prefix", ["fx_", ""])
def test_a_wrong_run_id_prefix_is_refused_by_the_research_loader(synthetic_run, prefix):
    """Only the PREFIX is wrong -- the id body is the one the contract earned."""
    earned = _load(synthetic_run(lane="research_only", program_ids=BIO_IDS))
    args = synthetic_run(lane="research_only", program_ids=BIO_IDS,
                         ids=_reprefixed_ids(earned, prefix))
    with pytest.raises(SelectionError, match="namespace firewall") as excinfo:
        _load(args)
    assert "question_id" in str(excinfo.value)


def test_a_research_run_id_cannot_be_relabelled_as_a_fixture(synthetic_run):
    """Relabelling the lane does not launder the run: the fixture loader wants fx_."""
    args = synthetic_run(lane="research_only", program_ids=BIO_IDS)
    with pytest.raises(SelectionError,
                       match=r"load_fixture_selection: contract declares lane"):
        selection.load_fixture_selection(args.selection)


def test_a_research_contract_can_never_enter_the_production_loader(synthetic_run):
    """The production loader refuses on the declared LANE, before a namespace
    question can even arise. (The rq_/ra_ run-id firewall on a contract that claims
    lane=production is covered in test_production_firewall.py.)"""
    args = synthetic_run(lane="research_only", program_ids=BIO_IDS)
    with pytest.raises(SelectionError,
                       match=r"load_production_selection: contract declares lane"):
        selection.load_production_selection(args.selection)


def test_a_forged_run_identifier_does_not_recompute(synthetic_run):
    """An id is a derivation, not a label: you cannot write one you did not earn.

    The forged ids keep the rq_ prefix, so the namespace firewall stays silent and
    the ONLY thing wrong is the derivation.
    """
    args = synthetic_run(lane="research_only", program_ids=BIO_IDS,
                         ids={"question_id": RQ + "0" * 32,
                              "selection_id": RQ + "1" * 32})
    with pytest.raises(SelectionError, match="identifier mismatch") as excinfo:
        build_screen(args)
    msg = str(excinfo.value)
    assert "question_id" in msg
    assert "namespace firewall" not in msg


# --------------------------------------------------------------------------- #
# The biology: exact, or it does not resolve.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("bad_a", ["rq_treg_like", "treg_like_v2", "TREG_LIKE"])
def test_a_prefixed_or_altered_program_id_fails_the_registry_binding(synthetic_run,
                                                                     bad_a):
    """The namespace firewall does NOT fire here -- and it must not. A program id is
    checked against the registry, so a renamed one simply has no program.

    The altered biology is the ONLY mutation: the fixture re-derives the ids over it,
    so the contract is self-consistent and reaches the registry binding.
    """
    args = synthetic_run(lane="research_only", program_ids=BIO_IDS,
                         A={"program_id": bad_a, "direction": "high"})
    with pytest.raises(SelectionError,
                       match="is not in the bound Stage-1 registry") as excinfo:
        build_screen(args)
    msg = str(excinfo.value)
    assert bad_a in msg
    assert "namespace firewall" not in msg
    assert "identifier mismatch" not in msg
