"""ONE canonical numeric representation, and it is deterministic across processes.

Stage 3 previously had three numeric paths into a hash — ``json.dumps``'s own float
rendering, a float->str->Decimal->str round trip, and bare ``repr``. Three paths is three
chances to disagree, and a content hash that depends on which path a caller happened to
reach is not a content address.

There is now one path. These tests hold it to what it claims:

  * it never rounds — near-identical floats keep distinct hashes;
  * a bool is not a number (Python says ``True == 1``; a canonicaliser must not agree);
  * NaN and infinity have no canonical decimal and are refused;
  * and the bytes are IDENTICAL across two clean, separate interpreter processes — the
    determinism claim is proved by a subprocess, not by calling the function twice in a
    warm process where a shared cache could hide the drift it exists to prevent.
"""
from __future__ import annotations

import json
import subprocess
import sys
from decimal import Decimal

import pytest

from druglink import canonical_number as cn

# A record with every awkward numeric shape the pipeline can actually carry.
FIXTURE_RECORD = {
    "zeta": {"enrichment_value": 3.7, "tiny": 4e-07, "tiny_neighbour": 4.9e-07},
    "alpha": [1, 2.5, -0.0001, 1e300],
    "int_like_float": 2.0,
    "big_int": 9007199254740993,
    "ratio": 1 / 3,
    "flag": True,                 # a bool stays a bool: it is not a magnitude
    "absent": None,
    "label": "away_from_A",
}


def test_the_rule_is_frozen_and_declared():
    assert cn.ROUNDING_RULE_ID == "spot.stage03.canonical_number.v1"
    assert cn.CANONICAL_FORM == "exact_decimal_string"
    assert "no rounding" in cn.ROUNDING_RULE
    assert cn.rule_block() == {
        "rounding_rule_id": cn.ROUNDING_RULE_ID,
        "rounding_rule": cn.ROUNDING_RULE,
        "canonical_form": cn.CANONICAL_FORM,
    }


# --------------------------------------------------------------------------- #
# It never rounds.
# --------------------------------------------------------------------------- #
def test_nothing_is_ever_rounded_so_near_neighbours_stay_distinct():
    """4.0e-7 and 4.9e-7 are different numbers, and must stay different hashes."""
    assert cn.canonical_number(4e-07) != cn.canonical_number(4.9e-07)
    assert cn.canonical_sha256({"v": 4e-07}) != cn.canonical_sha256({"v": 4.9e-07})

    # The smallest representable difference survives.
    a, b = 0.1 + 0.2, 0.30000000000000004
    assert a == b                                     # same float64...
    assert cn.canonical_number(a) == cn.canonical_number(b)   # ...so the same string.
    assert cn.canonical_number(0.3) != cn.canonical_number(0.1 + 0.2)


def test_a_float_survives_the_round_trip_exactly():
    """The canonical string must read back to the IDENTICAL float64. No loss."""
    for value in (3.7, 4e-07, 1 / 3, 1e300, -0.0001, 2.0, 1.7976931348623157e308):
        assert float(Decimal(cn.canonical_number(value))) == value


def test_int_and_float_of_equal_value_share_a_canonical_form():
    assert cn.canonical_number(2) == cn.canonical_number(2.0) == cn.canonical_number(
        Decimal("2.00"))


# --------------------------------------------------------------------------- #
# A bool is not a number. NaN and infinity are not numbers either.
# --------------------------------------------------------------------------- #
def test_a_bool_is_refused_as_a_magnitude():
    """Python says True == 1. A canonicaliser that agrees will hash a flag as a value."""
    for flag in (True, False):
        with pytest.raises(cn.CanonicalNumberError, match="bool"):
            cn.canonical_number(flag)
        assert cn.is_number(flag) is False

    # In a document, a bool stays a bool — it is not silently rendered as "1E+0".
    assert cn.canonicalise({"flag": True}) == {"flag": True}
    assert cn.canonical_sha256({"flag": True}) != cn.canonical_sha256({"flag": 1})


def test_non_finite_numbers_have_no_canonical_decimal():
    for value in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(cn.CanonicalNumberError, match="canonical decimal"):
            cn.canonical_number(value)
    # ...and it is caught at the document level too, before the serialiser ever sees it.
    with pytest.raises(cn.CanonicalNumberError):
        cn.canonical_bytes({"v": float("nan")})


def test_none_is_not_a_number_but_survives_a_document():
    with pytest.raises(cn.CanonicalNumberError, match="None"):
        cn.canonical_number(None)
    assert cn.canonicalise({"v": None}) == {"v": None}


# --------------------------------------------------------------------------- #
# No float can reach the serialiser.
# --------------------------------------------------------------------------- #
def test_every_number_becomes_a_string_before_serialisation():
    """A float that reaches json.dumps is rendered by whatever json.dumps feels like."""
    encoded = json.loads(cn.canonical_bytes(FIXTURE_RECORD).decode("utf-8"))

    assert isinstance(encoded["zeta"]["enrichment_value"], str)
    assert isinstance(encoded["big_int"], str)
    assert all(isinstance(v, str) for v in encoded["alpha"])
    assert encoded["flag"] is True          # ...but a bool is untouched
    assert encoded["absent"] is None
    assert encoded["label"] == "away_from_A"

    # Keys sorted, no insignificant whitespace: JCS-style, byte-stable.
    raw = cn.canonical_bytes(FIXTURE_RECORD).decode("utf-8")
    assert '"alpha"' in raw and raw.index('"alpha"') < raw.index('"zeta"')
    assert ", " not in raw and ": " not in raw


def test_a_53_bit_integer_is_not_quietly_degraded_to_a_float():
    """9007199254740993 is not representable as a float64. It must not become …92."""
    assert cn.canonical_number(9007199254740993) == "9.007199254740993E+15"
    assert cn.canonical_number(9007199254740993) != cn.canonical_number(
        9007199254740992)


# --------------------------------------------------------------------------- #
# DETERMINISM, proved across two clean processes.
# --------------------------------------------------------------------------- #
_PROOF = """
import json, sys
sys.path.insert(0, {analysis!r})
from druglink import canonical_number as cn
record = json.loads({record!r})
record["zeta"]["enrichment_value"] = 3.7
record["zeta"]["tiny"] = 4e-07
record["zeta"]["tiny_neighbour"] = 4.9e-07
record["alpha"] = [1, 2.5, -0.0001, 1e300]
record["ratio"] = 1 / 3
print(json.dumps({{
    "bytes": cn.canonical_bytes(record).decode("utf-8"),
    "sha256": cn.canonical_sha256(record),
}}))
"""


def _clean_run(analysis_root, record, seed):
    """Serialise the fixture in a FRESH interpreter, with a different hash seed."""
    out = subprocess.run(
        [sys.executable, "-c", _PROOF.format(analysis=analysis_root,
                                             record=json.dumps(record))],
        capture_output=True, text=True, check=True,
        env={"PATH": "/usr/bin:/bin", "PYTHONHASHSEED": seed,
             "PYTHONDONTWRITEBYTECODE": "1"})
    return json.loads(out.stdout)


def test_two_clean_serialization_runs_are_byte_identical(analysis_root):
    """Two separate processes, different hash seeds — identical bytes, identical hash.

    Run in-process twice and a shared cache, a warm interned string or a stable dict
    order could all hide non-determinism. A fresh interpreter with a different
    PYTHONHASHSEED cannot.
    """
    first = _clean_run(analysis_root, FIXTURE_RECORD, seed="0")
    second = _clean_run(analysis_root, FIXTURE_RECORD, seed="12345")

    assert first["bytes"] == second["bytes"]
    assert first["sha256"] == second["sha256"]
    assert len(first["sha256"]) == 64

    # ...and this process agrees with both of them.
    here = dict(FIXTURE_RECORD)
    assert cn.canonical_sha256(here) == first["sha256"]
