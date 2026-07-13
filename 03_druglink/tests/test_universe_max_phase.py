"""Exact max_phase preservation for the universe store (NEW support).

The existing ``chembl.py`` coarsens max_phase into a development_state bucket and maps
0.5 -> None. The universe store instead keeps the EXACT value: a verbatim source string
plus a canonical decimal, with null / -1 / 0.5 / integer all DISTINCT, and it refuses a
raw Python float so no float-canonicalisation drift can enter. Context-only; never a gate.
"""
from __future__ import annotations

import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "analysis")))

from druglink import universe_max_phase as mp  # noqa: E402


def test_null_preserved_as_null():
    assert mp.max_phase_fields(None) == {"max_phase_source": None,
                                         "max_phase_canonical": None}


def test_all_stated_values_are_distinct():
    vals = ["-1", "0", "0.5", "1", "2", "3", "4"]
    canon = [mp.max_phase_fields(v)["max_phase_canonical"] for v in vals]
    assert len(set(canon)) == len(vals)                      # none collapse
    assert [mp.max_phase_fields(v)["max_phase_source"] for v in vals] == vals


def test_half_phase_not_collapsed_to_a_neighbour():
    half = mp.max_phase_fields("0.5")["max_phase_canonical"]
    assert half != mp.max_phase_fields("0")["max_phase_canonical"]
    assert half != mp.max_phase_fields("1")["max_phase_canonical"]
    assert half != mp.max_phase_fields(None)["max_phase_canonical"]


def test_minus_one_distinct_from_null_and_zero():
    m1 = mp.max_phase_fields("-1")
    assert m1["max_phase_canonical"] != mp.max_phase_fields(None)["max_phase_canonical"]
    assert m1["max_phase_canonical"] != mp.max_phase_fields("0")["max_phase_canonical"]


def test_raw_float_is_refused_no_drift():
    with pytest.raises(Exception):
        mp.max_phase_fields(0.5)      # a float must be refused: read the exact TEXT
    with pytest.raises(Exception):
        mp.max_phase_fields(4.0)


def test_bool_is_refused():
    with pytest.raises(Exception):
        mp.max_phase_fields(True)


def test_source_verbatim_but_equivalent_forms_share_canonical():
    a, b = mp.max_phase_fields("4"), mp.max_phase_fields("4.0")
    assert a["max_phase_source"] == "4" and b["max_phase_source"] == "4.0"   # verbatim
    assert a["max_phase_canonical"] == b["max_phase_canonical"]              # same phase


def test_round_trip_through_source_is_stable():
    for v in [None, "-1", "0.5", "4", "4.0"]:
        r1 = mp.max_phase_fields(v)
        r2 = mp.max_phase_fields(r1["max_phase_source"])
        assert r1 == r2
