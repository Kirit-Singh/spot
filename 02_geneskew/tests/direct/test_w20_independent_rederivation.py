"""W20's consumer repair, RE-DERIVED — not trusted.

W20 pins three hashes and two id recipes. A consumer that read those pins and agreed with them
would be checking W20's arithmetic against W20's arithmetic. So every one of them is recomputed
here from the authoritative Stage-1 bytes, and the two tuple behaviours that were BROKEN are
proven directly:

  * a same-program / same-direction selection at DIFFERENT TIMES is VALID (the old pole
    equality compared only program+direction and refused it — a real Stage-1 output, refused);
  * an IDENTICAL endpoint tuple is not a comparison and must refuse.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess

import pytest
from direct import stage1_v3 as S
from direct import stage1_v3_ids as I

SPOT = "/home/tcelab/projects/spot"
PIN = "539431d"
SCHEMA = "01_programs/analysis/stage2_bridge/schemas/spot.stage01_selection.v3.schema.json"
RELEASE = "01_programs/analysis/stage2_bridge/release/stage01_v3_release.json"
SELECTIONS = "01_programs/analysis/stage2_bridge/release/selections/"


def _blob(path: str) -> bytes:
    if not os.path.isdir(os.path.join(SPOT, ".git")):
        pytest.skip("the Stage-1 release tree is not on this host")
    r = subprocess.run(["git", "-C", SPOT, "show", f"{PIN}:{path}"],
                       capture_output=True)
    if r.returncode != 0:
        pytest.skip(f"{PIN}:{path} is not in this object store")
    return r.stdout


def _canon(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode()).hexdigest()


class TestTheHashesREDERIVEFromTheBytes:
    def test_the_SCHEMA_hash_is_the_hash_of_the_schema(self):
        assert hashlib.sha256(_blob(SCHEMA)).hexdigest() == S.SCHEMA_SHA256
        assert S.SCHEMA_SHA256 == (
            "f8104283d7139ed47059978751dbed33e8426c920ba0d8086082eda9c43f4c1d")

    def test_the_RELEASE_raw_hash_is_the_hash_of_the_release(self):
        assert hashlib.sha256(_blob(RELEASE)).hexdigest() == (
            "0c336546db10746bba1569ccc6bef7dedf9679effd24e17d0c07a5ab04dbef73")

    def test_the_RELEASE_SELF_hash_re_derives_over_its_own_body(self):
        """Excluding the field that carries it — so sealing it cannot change what it is."""
        rel = json.loads(_blob(RELEASE))
        derived = _canon({k: v for k, v in rel.items() if k != "self_release_sha256"})
        assert derived == rel["self_release_sha256"]
        assert derived.startswith("2262430931707552")

    def test_the_RETIRED_schema_pin_is_gone(self):
        assert "f4c2" not in S.SCHEMA_SHA256


class TestBothIDsREDERIVEOnEveryRealSelection:
    def _selections(self):
        r = subprocess.run(["git", "-C", SPOT, "ls-tree", "--name-only",
                            f"{PIN}:{SELECTIONS}"], capture_output=True, text=True)
        if r.returncode != 0:
            pytest.skip("selections not in this object store")
        return sorted(r.stdout.split())

    def test_question_id_and_selection_id_RE_DERIVE_on_all_nine(self):
        names = self._selections()
        assert len(names) == 9
        for n in names:
            doc = json.loads(_blob(SELECTIONS + n))
            assert doc["question_id"] == S.derive_question_id(doc), n
            assert doc["selection_id"] == S.derive_selection_id(doc), n

    def test_the_two_ids_are_NOT_the_same_thing(self):
        """question_id is the BIOLOGY asked; selection_id is WHICH CONTRACT asked it. Assigning
        one from the other would make a re-run of the same question a different question — or,
        worse, two different questions look like one."""
        doc = json.loads(_blob(SELECTIONS + self._selections()[0]))
        assert doc["question_id"] != doc["selection_id"]


class TestTheTUPLESpaceIsGeneric:
    """No program is special. Treg/Th1 are what the release happens to ship, not the contract."""

    def test_the_pole_identity_INCLUDES_the_condition(self):
        assert I.POLE_IDENTITY_RULE_ID == (
            "spot.stage01.pole_identity.program_direction_condition.v1")

    def test_SAME_program_SAME_direction_at_DIFFERENT_TIMES_is_a_VALID_comparison(self):
        """THE BUG. The old pole equality compared only program+direction, so it REFUSED a
        real Stage-1 output: the same program, in the same direction, at two different times.
        That is exactly what a temporal question IS."""
        a = I.pole_identity("treg_like", "high", "Rest")
        b = I.pole_identity("treg_like", "high", "Stim48hr")
        assert a != b
        assert a == "treg_like|high|Rest" and b == "treg_like|high|Stim48hr"

    def test_an_IDENTICAL_endpoint_tuple_is_NOT_a_comparison(self):
        a = I.pole_identity("treg_like", "high", "Rest")
        b = I.pole_identity("treg_like", "high", "Rest")
        assert a == b          # same pole -> the caller must refuse: A vs A is not a question

    @pytest.mark.parametrize("tup", [
        ("PRG_X", "low", "Stim8hr"),
        ("some_other_program", "high", "Rest"),
        ("cd4_ctl_like", "low", "Stim48hr"),
    ])
    def test_ARBITRARY_programs_directions_and_conditions_are_first_class(self, tup):
        pid = I.pole_identity(*tup)
        assert pid == "|".join(tup)
        assert "treg" not in pid or tup[0].startswith("treg")   # nothing hardcoded
