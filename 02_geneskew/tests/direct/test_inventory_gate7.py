"""GATE 7: the production package contains ONLY production. Fail-closed.

`analysis/perturb2state/` and `analysis/temporal_exploration/` (incl.
`screen_th1_treg_temporal.py`) sat inside the production package while contributing NOTHING to
the producer's code identity — the digest root is `analysis/direct`. That combination is the
dangerous one: a file that can be discovered, imported or surfaced in the UI, but cannot move
the hash that is supposed to say what this system IS. Nobody notices it.

They are archived out. These tests are what stop the next one arriving.
"""
from __future__ import annotations

import os

import pytest
from direct import inventory

PACKAGE = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "analysis"))


class TestTheProductionPackageIsCLEAN:
    def test_it_holds_ONLY_production(self):
        result = inventory.verify(PACKAGE)
        assert result["clean"] is True
        assert result["unexpected"] == []

    def test_the_legacy_trees_are_GONE_from_the_package(self):
        entries = set(os.listdir(PACKAGE))
        assert "perturb2state" not in entries
        assert "temporal_exploration" not in entries

    def test_the_pair_captured_SCREEN_is_not_in_the_package(self):
        # screen_th1_treg_temporal.py names a fixed program pair in its own FILENAME; no
        # contract can talk a module out of a pair that is compiled into it
        hits = []
        for dirpath, _dirs, files in os.walk(PACKAGE):
            hits += [f for f in files if "th1" in f.lower() or "treg" in f.lower()]
        assert hits == []

    def test_the_ARCHIVE_still_has_them_they_were_moved_not_deleted(self):
        archive = os.path.join(os.path.dirname(PACKAGE), "archive")
        assert os.path.isdir(os.path.join(archive, "perturb2state"))
        assert os.path.isdir(os.path.join(archive, "temporal_exploration"))


class TestItFAILS_CLOSED:
    def test_a_NEW_pair_captured_tree_is_REFUSED(self, tmp_path):
        # the point of an ALLOWLIST: it refuses the next one too, not only the two we know
        pkg = tmp_path / "analysis"
        pkg.mkdir()
        for e in inventory.ALLOWED_ENTRIES:
            (pkg / e).mkdir() if "." not in e else (pkg / e).write_text("x")
        (pkg / "screen_treg_th1_v2").mkdir()          # tomorrow's legacy tree
        with pytest.raises(inventory.InventoryError) as exc:
            inventory.verify(str(pkg))
        assert exc.value.gate == inventory.REFUSE_UNEXPECTED_ENTRY
        assert "screen_treg_th1_v2" in str(exc.value)

    def test_a_RETURNING_legacy_tree_is_REFUSED_and_NAMED(self, tmp_path):
        pkg = tmp_path / "analysis"
        pkg.mkdir()
        for e in inventory.ALLOWED_ENTRIES:
            (pkg / e).mkdir() if "." not in e else (pkg / e).write_text("x")
        (pkg / "perturb2state").mkdir()
        with pytest.raises(inventory.InventoryError) as exc:
            inventory.verify(str(pkg))
        assert exc.value.gate == inventory.REFUSE_UNEXPECTED_ENTRY
        assert "pair-captured" in str(exc.value)

    def test_the_gate_is_an_ALLOWLIST_not_a_blocklist(self):
        # a blocklist names what we already know about and says nothing about the next one
        assert set(inventory.PRIMARY_ENTRIES) == {
            "direct", "run_stage2.sh", "stage02_solver_lock.txt"}
        # the secondary production lane is bound EXPLICITLY, and nothing else
        assert set(inventory.SECONDARY_PRODUCTION) == {"p2s_arms"}
        assert set(inventory.ALLOWED_ENTRIES) == (
            set(inventory.PRIMARY_ENTRIES) | set(inventory.SECONDARY_PRODUCTION))

    def test_the_legacy_modules_are_NOT_IMPORTABLE(self):
        # archiving a directory that is still on the import path moves the file, not the problem
        inventory.assert_legacy_not_importable()


class TestTheProducerCODE_IDENTITY_IsUnaffected:
    def test_the_legacy_trees_were_never_in_the_digest_and_still_are_not(self):
        # which is exactly why they were dangerous: runnable, discoverable, and invisible to
        # the hash that says what this system is
        from direct import code_digest
        root = os.path.join(PACKAGE, "direct")
        files = code_digest._iter_files(root)
        assert not [f for f in files
                    if "perturb2state" in f or "temporal_exploration" in f]


class TestTheSECONDARYlaneIsBOUND_explicitly:
    # p2s_arms is the W10-admitted secondary production lane. It is bound EXPLICITLY as
    # SECONDARY_PRODUCTION, not smuggled into a broad allowlist, and the gate stays fail-closed.
    def test_p2s_arms_is_classified_secondary_not_primary(self):
        assert "p2s_arms" in inventory.SECONDARY_PRODUCTION
        assert "p2s_arms" in inventory.ALLOWED_ENTRIES
        assert "p2s_arms" not in inventory.PRIMARY_ENTRIES

    def test_the_real_package_carrying_p2s_arms_is_CLEAN_and_reports_it(self):
        result = inventory.verify(PACKAGE)
        assert result["clean"] is True
        assert result["unexpected"] == []
        assert "p2s_arms" in result["secondary_production"]

    def test_binding_the_secondary_lane_did_NOT_open_the_gate(self, tmp_path):
        # fail-closed still holds: an undeclared look-alike beside p2s_arms is still REFUSED
        pkg = tmp_path / "analysis"
        pkg.mkdir()
        for e in inventory.ALLOWED_ENTRIES:
            (pkg / e).mkdir() if "." not in e else (pkg / e).write_text("x")
        (pkg / "p2s_arms_v2_shadow").mkdir()
        with pytest.raises(inventory.InventoryError) as exc:
            inventory.verify(str(pkg))
        assert exc.value.gate == inventory.REFUSE_UNEXPECTED_ENTRY
        assert "p2s_arms_v2_shadow" in str(exc.value)
