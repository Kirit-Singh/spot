"""Exact, lossless ChEMBL ``max_phase`` for the universe store. Context-only.

The Stage-3 REST adapter (:mod:`druglink.adapters.chembl`) coarsens ``max_phase`` into a
development-state bucket and drops any non-integral value (``0.5 -> None``). That is fine
for the adapter's purpose but LOSES information: -1, 0.5 and a stated 4 all become either
a bucket or nothing.

The universe cache promises ``max_phase``, so it keeps it EXACTLY: the verbatim source
string plus a canonical decimal, with ``null``, ``-1``, ``0.5`` and integer phases all
distinct. A raw Python float is REFUSED — the value must arrive as the exact text SQLite
holds (``CAST(max_phase AS TEXT)``), so no float-canonicalisation drift can enter a hash.

``max_phase`` is carried as CONTEXT. It never gates admission and never orders a rank.
"""
from __future__ import annotations

from typing import Any, Optional

from .canonical_number import canonical_number

MAX_PHASE_POLICY_VERSION = "stage3-universe-max-phase-v1-exact"


def max_phase_fields(source: Any) -> dict[str, Optional[str]]:
    """(source_string, canonical_decimal) for a ChEMBL max_phase, losslessly.

    ``source`` must be the exact text SQLite holds (or an int, which is exact), or None.
    A raw ``float`` (or ``bool``) is refused: reading a float would already have lost the
    exact source rendering and risks canonicalisation drift.
    """
    if source is None:
        return {"max_phase_source": None, "max_phase_canonical": None}
    if isinstance(source, bool):
        raise TypeError(f"max_phase is not a bool: {source!r}")
    if isinstance(source, float):
        raise TypeError(
            "refusing a float max_phase; read the exact text (CAST(max_phase AS TEXT)) "
            f"so the source string is preserved and cannot drift (got {source!r})")
    if not isinstance(source, (str, int)):
        raise TypeError(f"max_phase must be text/int/None, not {type(source).__name__}")
    src = str(source)
    return {"max_phase_source": src, "max_phase_canonical": canonical_number(src)}
