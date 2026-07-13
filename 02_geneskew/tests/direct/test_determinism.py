"""Rerun identity, and the input-ORDER permutation attacks.

Two different failures hide here.

  * NON-DETERMINISM: a run that quietly depends on a timestamp, a path, a dict
    iteration order or a random seed produces a different run_id from the same
    science — and then no run_id means anything.
  * ORDER SENSITIVITY: a manifest that lists the same evidence in a different order
    is the SAME manifest. If reordering it changes run_id, the id is binding the
    producer's serialiser rather than the producer's evidence, and two honest
    parties can never agree on the id of one artifact.

Both must be impossible. What run_id binds is the manifest's CANONICAL content
(canonically ordered rows and sources) plus the byte hashes of the pinned upstream
artifacts — never the manifest's own file formatting.
"""
from __future__ import annotations

import copy
import json
import os
import re

import pandas as pd
import pytest
from direct import manifest as mf
from direct.hashing import file_sha256
from direct.run_screen import build_screen

pytestmark = pytest.mark.filterwarnings("ignore")

ARTIFACTS = ("screen.parquet", "masks.parquet", "contributing_guides.parquet",
             "guide_support.parquet", "donor_support.parquet", "axis.json",
             "gene_universe.json", "input_manifest.json")


def fingerprint(out_dir: str) -> dict[str, str]:
    """Every emitted artifact, by content. provenance.json is excluded: it carries
    created_at, which is a fact ABOUT the run, not an input to it."""
    return {name: file_sha256(os.path.join(out_dir, name)) for name in ARTIFACTS}


def screen_of(out_dir: str) -> pd.DataFrame:
    return pd.read_parquet(os.path.join(out_dir, "screen.parquet"))


# --------------------------------------------------------------------------- #
# Deterministic rerun.
# --------------------------------------------------------------------------- #
def test_the_same_inputs_rerun_to_the_same_run_id_and_the_same_artifacts(
        synthetic_run):
    """Built twice, in two directories, from the same science."""
    first = build_screen(synthetic_run())
    second = build_screen(synthetic_run())

    assert first["run_id"] == second["run_id"]
    assert fingerprint(first["out_dir"]) == fingerprint(second["out_dir"])


# A SHA-256 is hex, and hex digits include 0-9. So a digest can contain "2026" — and one now
# does: adding a file to the package moved `code_tree_sha256` to 0202655bac16… , whose second
# character onward reads "2026". The old check substring-searched the whole JSON blob, digests
# included, so it called that a leaked wall clock. It was a false positive waiting for whoever
# next added a module, and it fired on a run that carries no timestamp at all.
#
# The intent is worth keeping and the implementation was not: a wall clock is a KEY that names
# a time, or a VALUE that parses as one. So look for those, and do not read a content hash as
# if it were prose.
_CLOCK_KEYS = ("created_at", "timestamp", "generated_at", "date", "time")
_ISO_DATETIME = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")
_HEX_DIGEST = re.compile(r"^[0-9a-f]{16,}$")


def _wall_clock_leaks(node, path=""):
    """Every place a wall clock could actually be hiding: a time-naming key, or a date value."""
    leaks = []
    if isinstance(node, dict):
        for key, value in node.items():
            if any(c in str(key).lower() for c in _CLOCK_KEYS):
                leaks.append(f"{path}.{key} (a key that names a time)")
            leaks += _wall_clock_leaks(value, f"{path}.{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            leaks += _wall_clock_leaks(value, f"{path}[{i}]")
    elif isinstance(node, str) and not _HEX_DIGEST.match(node):
        if _ISO_DATETIME.search(node):
            leaks.append(f"{path} = {node!r} (a value that parses as a datetime)")
    return leaks


def test_the_run_binding_carries_no_wall_clock(synthetic_run):
    result = build_screen(synthetic_run())
    prov = json.load(open(os.path.join(result["out_dir"], "provenance.json")))
    assert _wall_clock_leaks(prov["run_binding"]) == []


def test_the_wall_clock_check_would_actually_CATCH_one(synthetic_run):
    """The positive control. A check that cannot fail is not a check.

    The old one was passing for the wrong reason and failing for the wrong reason; this pins
    that the replacement still bites on a real leak, in both the shapes one can take.
    """
    result = build_screen(synthetic_run())
    prov = json.load(open(os.path.join(result["out_dir"], "provenance.json")))

    by_key = dict(prov["run_binding"], created_at="2026-07-13T01:02:03Z")
    assert _wall_clock_leaks(by_key)

    by_value = dict(prov["run_binding"], lane="built 2026-07-13T01:02:03Z")
    assert _wall_clock_leaks(by_value)

    # ...and a content hash that merely CONTAINS "2026" is not a wall clock
    assert _wall_clock_leaks(
        {"code_tree_sha256":
         "0202655bac16c6c6b87d870f4971a60fb5a60d2b847d5d57841c9c2f101d85ba"}) == []


# --------------------------------------------------------------------------- #
# Input-ORDER permutation: same evidence, different serialisation.
# --------------------------------------------------------------------------- #
def test_reversing_the_manifest_rows_changes_nothing(synthetic_run):
    """The same evidence, listed backwards. It is the same manifest."""
    baseline = build_screen(synthetic_run())
    permuted = build_screen(synthetic_run(manifest_rows_fn=lambda rows: rows[::-1]))

    assert permuted["run_id"] == baseline["run_id"]
    assert fingerprint(permuted["out_dir"]) == fingerprint(baseline["out_dir"])


def test_a_deterministic_shuffle_of_the_manifest_rows_changes_nothing(synthetic_run):
    """Not just reversal: an arbitrary (but fixed) permutation."""
    def shuffle(rows):
        out = copy.deepcopy(rows)
        # a fixed, seed-free stride permutation — no RNG, so the test is itself
        # deterministic
        return [out[(7 * i + 3) % len(out)] for i in range(len(out))]

    baseline = build_screen(synthetic_run())
    permuted = build_screen(synthetic_run(manifest_rows_fn=shuffle))

    assert permuted["run_id"] == baseline["run_id"]
    assert fingerprint(permuted["out_dir"]) == fingerprint(baseline["out_dir"])


def test_reordering_the_declared_sources_changes_nothing(synthetic_run):
    baseline = build_screen(synthetic_run())
    args = synthetic_run()
    doc = json.load(open(args.guide_manifest))
    doc["sources"] = list(reversed(doc["sources"]))
    with open(args.guide_manifest, "w") as fh:
        json.dump(doc, fh, indent=2)

    permuted = build_screen(args)
    assert permuted["run_id"] == baseline["run_id"]
    assert fingerprint(permuted["out_dir"]) == fingerprint(baseline["out_dir"])


def test_reformatting_the_manifest_file_changes_nothing(synthetic_run):
    """Different bytes, identical science: re-indented and key-reordered."""
    baseline = build_screen(synthetic_run())
    args = synthetic_run()
    doc = json.load(open(args.guide_manifest))
    with open(args.guide_manifest, "w") as fh:
        json.dump(doc, fh, indent=7, sort_keys=False, separators=(" ,", " : "))

    reformatted = build_screen(args)
    assert file_sha256(args.guide_manifest) != baseline["run_id"]      # new bytes...
    assert reformatted["run_id"] == baseline["run_id"]                 # ...same run
    assert fingerprint(reformatted["out_dir"]) == fingerprint(baseline["out_dir"])


def test_the_canonical_hash_is_order_independent_but_content_sensitive(synthetic_run):
    """It must ignore ORDER without ignoring CHANGE."""
    args = synthetic_run()
    doc = json.load(open(args.guide_manifest))
    rows = doc["rows"]

    assert (mf.canonical_rows(rows[::-1]) == mf.canonical_rows(rows)
            == sorted(rows, key=mf.canonical_row_key))

    # ...but a real edit to the evidence still moves it
    edited = copy.deepcopy(rows)
    determined = next(r for r in edited if r["evidence_state"] == "determined")
    determined["guide_id"] = "g-SOMETHING-ELSE"
    assert mf.canonical_rows(edited) != mf.canonical_rows(rows)


# --------------------------------------------------------------------------- #
# ...and a REAL change still moves the id.
# --------------------------------------------------------------------------- #
def test_a_semantic_change_to_the_evidence_still_changes_the_run_id(synthetic_run):
    """Order-invariance must not have bought itself by ignoring the rows."""
    from direct.manifest import ManifestError
    from fixtures_spec import TARGET_GENES

    baseline = build_screen(synthetic_run())

    def drop_a_guide(rows):
        return [r for r in rows
                if not (r["target_id"] == TARGET_GENES[0]
                        and r["guide_id"] == "g-T0-2")]

    # Dropping a contributor is no longer merely "a different run": the scope then
    # names fewer guides than the source kept for it, and the completeness gate
    # refuses the manifest outright. The strongest possible answer to a silently
    # shrunken contributor set is not a new run_id — it is no run at all.
    with pytest.raises(ManifestError):
        build_screen(synthetic_run(manifest_rows_fn=drop_a_guide))

    # Relabelling that scope AMBIGUOUS is not an admissible change either — and this
    # test used to say it was. The source still holds T0's two kept targeting guides, so
    # "the identity is unknown" is false, and the manifest may not assert it. The answer
    # is the same as for a dropped contributor: no new run_id, no run at all.
    def make_ambiguous(rows):
        out, seen = [], False
        for r in rows:
            if r["target_id"] != TARGET_GENES[0]:
                out.append(r)
                continue
            if seen:
                continue
            seen = True
            out.append({k: v for k, v in r.items()
                        if k not in ("identity_method", "source_id",
                                     "source_sha256")}
                       | {"evidence_state": "ambiguous", "guide_id": None,
                          "source_record_id": None})
        return out

    with pytest.raises(ManifestError, match="raw source can DETERMINE"):
        build_screen(synthetic_run(manifest_rows_fn=make_ambiguous))

    # The manifest now has almost no freedom left: it must mirror the source exactly, so
    # nearly every row-level edit is a refusal rather than a new run. What DOES still
    # move the id is a genuinely different body of evidence — a target the source itself
    # cannot prove. The run is admissible, and it is a different run.
    from dataclasses import replace as _replace

    from fixtures_direct import default_specs

    specs = [_replace(s, ambiguous_estimates=("main",))
             if s.target == TARGET_GENES[0] else s
             for s in default_specs()]
    changed = build_screen(synthetic_run(specs=specs))
    assert changed["run_id"] != baseline["run_id"]
    assert screen_of(changed["out_dir"]) is not None
