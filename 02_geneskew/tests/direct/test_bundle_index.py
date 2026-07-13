"""Content-addressed bundles are DISCOVERED, never guessed.

A bundle's directory IS its run id — a hash of everything that produced it — so no runbook can
know it in advance. A guessed path (`direct-Rest/`) either finds nothing, or finds a STALE
bundle from an earlier run sitting where the guess happened to point. The second is worse: it
succeeds.
"""
from __future__ import annotations

import json
import os

import pytest
from direct import bundle_index as bi


def _bundle(root, run_id, condition, kind="direct", source=None):
    d = os.path.join(root, run_id)
    os.makedirs(d, exist_ok=True)
    binding = {"condition": condition}
    if source:
        binding["source"] = source
    doc = {bi.RUN_ID_BY_KIND[kind]: run_id, "run_binding": binding}
    with open(os.path.join(d, bi.PROVENANCE_BY_KIND[kind]), "w") as fh:
        json.dump(doc, fh)
    return d


class TestItFindsTheBundleByWhatItSAYSItIs:
    def test_it_finds_the_bundle_for_a_condition(self, tmp_path):
        root = str(tmp_path)
        want = _bundle(root, "aaaa1111bbbb2222", "Rest")
        _bundle(root, "cccc3333dddd4444", "Stim48hr")
        hit = bi.find(root, condition="Rest")
        assert hit["dir"] == want
        assert hit["run_id"] == "aaaa1111bbbb2222"

    def test_it_reads_the_CONDITION_from_the_binding_not_the_directory_name(self, tmp_path):
        # the directory is a hash; it does not spell the condition, and nothing may infer it
        root = str(tmp_path)
        d = _bundle(root, "0f1e2d3c4b5a6978", "Stim8hr")
        assert bi.find(root, condition="Stim8hr")["dir"] == d
        assert "Stim8hr" not in os.path.basename(d)


class TestItFailsCLOSEDAtBothEnds:
    def test_NO_match_is_REFUSED(self, tmp_path):
        _bundle(str(tmp_path), "aaaa1111bbbb2222", "Rest")
        with pytest.raises(bi.BundleIndexError) as exc:
            bi.find(str(tmp_path), condition="Stim48hr")
        assert exc.value.gate == bi.REFUSE_NOT_FOUND

    def test_an_EMPTY_root_is_REFUSED(self, tmp_path):
        with pytest.raises(bi.BundleIndexError) as exc:
            bi.find(str(tmp_path / "nothing"), condition="Rest")
        assert exc.value.gate == bi.REFUSE_NOT_FOUND

    def test_TWO_bundles_for_one_condition_is_REFUSED_and_NAMES_them(self, tmp_path):
        # two runs on disk; nothing here can know which was meant, and picking the newest
        # would be choosing between two scientific artifacts silently
        root = str(tmp_path)
        _bundle(root, "aaaa1111bbbb2222", "Rest")
        _bundle(root, "eeee5555ffff6666", "Rest")
        with pytest.raises(bi.BundleIndexError) as exc:
            bi.find(root, condition="Rest")
        assert exc.value.gate == bi.REFUSE_AMBIGUOUS
        assert "aaaa1111bbbb2222" in str(exc.value)
        assert "eeee5555ffff6666" in str(exc.value)

    def test_it_does_NOT_pick_the_newest(self, tmp_path):
        root = str(tmp_path)
        _bundle(root, "aaaa1111bbbb2222", "Rest")
        newer = _bundle(root, "eeee5555ffff6666", "Rest")
        os.utime(os.path.join(newer, "provenance.json"), (10**9, 10**9))
        with pytest.raises(bi.BundleIndexError):
            bi.find(root, condition="Rest")


class TestPathwayBundlesAreKeyedOnConditionAND_Source:
    def test_it_distinguishes_the_two_sources_of_one_condition(self, tmp_path):
        root = str(tmp_path)
        r = _bundle(root, "1111aaaa2222bbbb", "Rest", kind="pathway", source="reactome")
        g = _bundle(root, "3333cccc4444dddd", "Rest", kind="pathway", source="go_bp")
        assert bi.find(root, condition="Rest", kind="pathway",
                       source="reactome")["dir"] == r
        assert bi.find(root, condition="Rest", kind="pathway", source="go_bp")["dir"] == g

    def test_without_the_source_the_two_are_AMBIGUOUS(self, tmp_path):
        root = str(tmp_path)
        _bundle(root, "1111aaaa2222bbbb", "Rest", kind="pathway", source="reactome")
        _bundle(root, "3333cccc4444dddd", "Rest", kind="pathway", source="go_bp")
        with pytest.raises(bi.BundleIndexError) as exc:
            bi.find(root, condition="Rest", kind="pathway")
        assert exc.value.gate == bi.REFUSE_AMBIGUOUS


class TestTheCLI:
    def test_it_prints_the_directory_and_exits_zero(self, tmp_path, capsys):
        d = _bundle(str(tmp_path), "aaaa1111bbbb2222", "Rest")
        rc = bi.main(["--root", str(tmp_path), "--condition", "Rest"])
        assert rc == 0
        assert capsys.readouterr().out.strip() == d

    def test_a_missing_dependency_exits_NONZERO(self, tmp_path, capsys):
        rc = bi.main(["--root", str(tmp_path), "--condition", "Rest"])
        assert rc == 2
        assert bi.REFUSE_NOT_FOUND in capsys.readouterr().err
