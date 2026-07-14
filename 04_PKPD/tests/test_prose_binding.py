"""No unbound prose anywhere in the release. Zero, and it stays zero.

The named gap: `scorecards.json` is the document a human actually reads, and its SENTENCES were
bound by nothing. Everything scientific in it was reconstructed — components, classes, margins,
eligibility, criteria — but the prose was typed into the emitter, hashed into nothing, and
rebuilt by nothing. A resealed release could have inverted

    "CNS-MPO ... is not measured brain permeability ... It cannot satisfy any NEBPI branch."

or deleted

    "This is a statement about the search, NOT a finding of safety."

and every hash in the release would still have agreed. The machine-readable state beside the
sentence stayed honest; the sentence a reader believes did not. A neighbouring machine code does
not license unbound prose — the same argument that killed `rejection_reason` and `margin_reason`.

The rule, with no exemptions:

    every string Stage 4 emits is (A) declared in a method file -> hashed into the id,
    (B) a bound evidence-input cell, (C) part of the release identity, or
    (D) reconstructed cell-for-cell by `verifier/`.

`EXPLANATORY_COLUMNS` is `{}` and `unbound_prose()` is `{}`. These tests keep both true.
"""

from __future__ import annotations

import json
import os

import pytest

from analysis.evidence_inputs import EXPLANATORY_COLUMNS
from analysis.method_config import METHOD_DIR, load_method_bundle
from analysis.safety import EVIDENCE_STATE_DISPLAY
from provenance_helpers import both_verifiers, emit_run, failed
from verifier.prose import bound_strings, required_prose_failures, unbound_prose

import fixtures as fx

METHOD = load_method_bundle()


# --------------------------------------------------------- the invariant, and it is zero

def test_the_release_carries_no_unbound_prose(tmp_path):
    out_dir, _m, _r = emit_run(fx.stage4_inputs(), tmp_path)
    problems = unbound_prose(out_dir, METHOD_DIR)
    assert problems == {}, (
        "these strings are bound by nothing — not by the identity, not by a reconstruction. A "
        f"resealed release could rewrite any of them and no hash would move:\n{problems}")


def test_there_are_no_column_level_exemptions_either():
    """The parquet half of the same rule, closed in the previous pass. It stays closed."""
    assert EXPLANATORY_COLUMNS == {}


def test_both_verifiers_run_the_prose_check(tmp_path):
    inputs = fx.stage4_inputs()
    out_dir, _m, _r = emit_run(inputs, tmp_path)
    emit_time, standalone = both_verifiers(out_dir, inputs)
    assert standalone["status"] == "pass", failed(standalone)
    assert emit_time["status"] == "pass", failed(emit_time)
    assert any(c["check_id"] == "no_unbound_prose" for c in standalone["checks"])


# ------------------------------------------- the guard is not vacuous: invert a guard

@pytest.mark.parametrize("path,replacement", [
    # the sentence that stops a design-space score being read as brain exposure
    (("candidates", 0, "lanes", "cns_mpo", "interpretation_guard"),
     "CNS-MPO proves the drug is brain-penetrant."),
    # the sentence that stops "we looked and found nothing" reading as "it is safe"
    (("candidates", 0, "lanes", "safety", "scenario_matrix", 0, "display_text"),
     "No safety concerns were found for this item."),
    # the sentence that stops the lanes being combined into a score
    (("set_level", "lanes_are_independent"),
     "The lanes may be combined into an overall suitability score."),
    # the sentence that says Stage 4 does not rank
    (("ordering", "note"), "Candidates are ranked best-first."),
])
def test_inverting_a_guard_sentence_is_caught(path, replacement, tmp_path):
    """Each of these is a sentence a resealed release would WANT to rewrite."""
    out_dir, _m, _r = emit_run(fx.stage4_inputs(), tmp_path)
    assert unbound_prose(out_dir, METHOD_DIR) == {}

    scorecards = os.path.join(out_dir, "scorecards.json")
    with open(scorecards, encoding="utf-8") as fh:
        doc = json.load(fh)

    node = doc
    for key in path[:-1]:
        node = node[key]
    assert node[path[-1]] != replacement
    node[path[-1]] = replacement

    with open(scorecards, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)

    problems = unbound_prose(out_dir, METHOD_DIR)
    assert problems, f"rewriting {'.'.join(map(str, path))} went unnoticed"
    assert any(replacement in v for v in problems.values())


@pytest.mark.parametrize("path", [
    ("candidates", 0, "lanes", "cns_mpo", "interpretation_guard"),
    ("candidates", 0, "lanes", "transporters", "interpretation_guard"),
    ("set_level", "lanes_are_independent"),
    ("ordering", "note"),
])
def test_DELETING_a_guard_sentence_is_caught(path, tmp_path):
    """Silence is the cheapest way to lie, and `unbound_prose` alone cannot see it.

    Removing a guard leaves nothing unbound behind, and a resealed release would have agreeing
    hashes. So the guards are also REQUIRED: each must be present, verbatim, where the reader
    looks for it.
    """
    inputs = fx.stage4_inputs()
    out_dir, _m, _r = emit_run(inputs, tmp_path)
    assert required_prose_failures(out_dir, METHOD_DIR) == []

    scorecards = os.path.join(out_dir, "scorecards.json")
    with open(scorecards, encoding="utf-8") as fh:
        doc = json.load(fh)
    node = doc
    for key in path[:-1]:
        node = node[key]
    del node[path[-1]]
    with open(scorecards, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)

    # the prose guard sees nothing (nothing was ADDED) ...
    assert unbound_prose(out_dir, METHOD_DIR) == {}
    # ... and the required-guard check is what catches it
    assert required_prose_failures(out_dir, METHOD_DIR)


# ------------------------------------------ the catalog is the single source of truth

def test_every_guard_sentence_is_method_data_not_a_code_literal():
    """The sentences live in method/stage4_prose_v1.json, which is hashed into the id."""
    prose = METHOD.prose
    assert "not measured brain permeability" in prose["cns_mpo"]["interpretation_guard"]
    assert "does not rank" in prose["set_level"]["ordering_note"]
    assert "no combined score" in prose["set_level"]["lanes_are_independent"]
    assert "cannot satisfy an NEBPI branch" in prose["transporters"]["interpretation_guard"]
    assert "NOT a finding of safety" in (
        prose["safety"]["evidence_state_display"]["no_evidence_found"])
    assert "never 'impermeable'" in prose["nebpi"]["counterfactual"]["hard_rule"]
    assert "not a recommendation" in (
        prose["stage3_contract_status"]["assessment_is_not_promotion"])


def test_the_safety_display_map_is_loaded_from_the_method_not_typed_in_code():
    """`safety.py` reads it from the catalog, so the two can never disagree."""
    assert EVIDENCE_STATE_DISPLAY == METHOD.prose["safety"]["evidence_state_display"]
    # and no state renders as safe — not even `no_evidence_found`
    assert len(EVIDENCE_STATE_DISPLAY) == 5


def test_the_method_catalog_is_bound_into_the_scorecard_set_id():
    """A sentence declared in the catalog cannot change without moving every release's id."""
    assert "prose" in METHOD.method_file_sha256

    with open(os.path.join(METHOD_DIR, "stage4_prose_v1.json"), "rb") as fh:
        raw = fh.read()
    import hashlib
    assert METHOD.method_file_sha256["prose"] == hashlib.sha256(raw).hexdigest()


def test_the_bound_set_does_not_simply_swallow_everything(tmp_path):
    """A sanity check on the checker: a sentence nobody declared is NOT in the bound set."""
    out_dir, _m, _r = emit_run(fx.stage4_inputs(), tmp_path)
    bound = bound_strings(out_dir, METHOD_DIR)
    assert "This drug is safe and brain-penetrant." not in bound
    assert "CNS-MPO proves the drug is brain-penetrant." not in bound
    # ...while the real guard IS
    assert METHOD.prose["cns_mpo"]["interpretation_guard"] in bound
