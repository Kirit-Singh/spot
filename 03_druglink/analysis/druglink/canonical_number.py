"""ONE frozen canonical representation for every number that enters a hash.

Before this module there were three different numeric paths, and they did not agree:

  * ``json.dumps(doc, sort_keys=True)`` — Python's own float serialisation, used to hash
    the Stage-2 pathway document. Whatever ``repr`` happened to emit became the hash.
  * ``canonical_decimal(repr(float(x)))`` — a float -> str -> Decimal -> str round trip,
    used for enrichment values.
  * ``repr(value)`` — used for arm values.

Three paths means three chances to disagree, and a hash that depends on which one a
caller happened to reach is not a content address. There is now exactly one path.

THE RULE (frozen; its id is bound into every Stage-3 bundle)
------------------------------------------------------------
``ROUNDING_RULE_ID = spot.stage03.canonical_number.v1``

  A float64 is rendered by its SHORTEST ROUND-TRIP decimal (CPython ``repr``, which is
  exact: it is the unique shortest decimal that reads back to the identical float64),
  then normalised to a canonical exponential decimal string via ``Decimal``.

  **No rounding is applied, ever.** Nothing is truncated, nothing is scaled to a
  precision. 4.0e-7 and 4.9e-7 remain distinct strings and therefore distinct hashes.
  ``ROUNDING_RULE`` says exactly this, is emitted alongside every canonicalised number,
  and is what a downstream reader must apply to reproduce the bytes.

  Integers are rendered exactly. ``bool`` is NOT a number (Python says ``True == 1``;
  a canonicaliser that agrees with it will silently hash a flag as a magnitude).
  NaN and infinity have no canonical decimal and are refused.

Two surfaces, one rule:

  :func:`canonical_number`  a single value -> its exact canonical decimal STRING.
  :func:`canonical_bytes`   a whole object -> canonical UTF-8 bytes, JCS-style: keys
                            sorted, no insignificant whitespace, and EVERY number
                            replaced by its canonical decimal string, so a float can
                            never reach the serialiser and be rendered by chance.

:func:`canonical_sha256` is the only way anything numeric gets hashed.

``exact_source_string`` is the verbatim, lossless source rendering that Stage 3 stores
ALONGSIDE the canonical form (e.g. the arm value Stage 2 actually reported). It is
deliberately NOT the canonical form: the source string is what upstream said, the
canonical string is how we address it. Both are kept; neither is derived from a guess.
"""
from __future__ import annotations

import hashlib
import json
import math
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

ROUNDING_RULE_ID = "spot.stage03.canonical_number.v1"
ROUNDING_RULE = (
    "ieee754_float64_shortest_roundtrip_decimal_normalised_to_exponential_decimal; "
    "no rounding, no truncation, no precision scaling"
)
CANONICAL_FORM = "exact_decimal_string"


class CanonicalNumberError(TypeError):
    """A value has no canonical numeric representation, or is not a number at all."""


def is_number(value: Any) -> bool:
    """A bool is NOT a number. ``True == 1`` in Python; a canonicaliser must disagree."""
    return isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)


def canonical_number(value: Any) -> str:
    """One value -> its exact canonical decimal string. The only numeric path.

    Never rounds. A float64 goes through its shortest round-trip decimal (exact), so two
    distinct float64 values can never share a canonical string — and therefore never
    share a hash.
    """
    if isinstance(value, bool):
        raise CanonicalNumberError(
            f"refusing to canonicalise a bool as a number ({value!r}): Python says "
            "True == 1, and a flag is not a magnitude")
    if value is None:
        raise CanonicalNumberError("refusing to canonicalise None as a number")

    if isinstance(value, int):
        return _normalise(Decimal(value))
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise CanonicalNumberError(
                f"{value!r} has no canonical decimal representation")
        # repr() is the SHORTEST decimal that reads back to the identical float64.
        # It is exact: no information is lost, and none is invented.
        return _normalise(Decimal(repr(value)))
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise CanonicalNumberError(
                f"{value!r} has no canonical decimal representation")
        return _normalise(value)
    if isinstance(value, str):
        try:
            dec = Decimal(value.strip())
        except (InvalidOperation, ValueError) as exc:
            raise CanonicalNumberError(f"not a decimal: {value!r}") from exc
        if not dec.is_finite():
            raise CanonicalNumberError(f"non-finite decimal: {value!r}")
        return _normalise(dec)

    raise CanonicalNumberError(
        f"no canonical numeric representation for {type(value).__name__}: {value!r}")


def _normalise(dec: Decimal) -> str:
    return format(dec.normalize(), "E")


def exact_source_string(value: Any) -> str:
    """The lossless VERBATIM rendering, stored alongside the canonical form.

    This is what upstream actually said. It is not a canonical address and is never used
    as one — but it is exact, so nothing is lost by keeping both.
    """
    if isinstance(value, bool):
        raise CanonicalNumberError(f"a bool is not a number: {value!r}")
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise CanonicalNumberError(f"{value!r} has no exact source string")
        return repr(value)          # shortest round-trip: exact
    if isinstance(value, int):
        return str(value)
    return str(value)


def canonicalise(node: Any, path: str = "$") -> Any:
    """Every number becomes its canonical decimal STRING, recursively.

    After this, no float can reach the serialiser, so no float can be rendered by
    whatever the serialiser happened to feel like doing.
    """
    if isinstance(node, bool) or node is None:
        return node
    if is_number(node):
        return canonical_number(node)
    if isinstance(node, str):
        return node
    if isinstance(node, Mapping):
        return {str(k): canonicalise(v, f"{path}.{k}") for k, v in node.items()}
    if isinstance(node, (list, tuple)):
        return [canonicalise(v, f"{path}[{i}]") for i, v in enumerate(node)]
    raise CanonicalNumberError(
        f"uncanonicalisable type at {path}: {type(node).__name__}")


def canonical_bytes(obj: Any) -> bytes:
    """JCS-style canonical UTF-8 bytes: sorted keys, no whitespace, numbers as strings.

    Deterministic by construction — the same object always yields the same bytes, in the
    same process or a fresh one.
    """
    return json.dumps(canonicalise(obj), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def canonical_sha256(obj: Any) -> str:
    """The ONLY way anything numeric gets hashed."""
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def rule_block() -> dict[str, str]:
    """Emitted next to every canonicalised number, so a reader can reproduce the bytes."""
    return {
        "rounding_rule_id": ROUNDING_RULE_ID,
        "rounding_rule": ROUNDING_RULE,
        "canonical_form": CANONICAL_FORM,
    }
