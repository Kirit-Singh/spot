"""How a refusal is recorded: the GATE it failed at, where, and why.

Failures are COLLECTED, never raised one at a time. A reader chasing one refusal per run
cannot see the shape of what went wrong, and a verifier that stopped at the first problem
would make a broken release look like a nearly-working one.
"""
from __future__ import annotations

from typing import Any

from . import schema


class Failures:
    """Every failure, with the named gate it failed at."""

    def __init__(self) -> None:
        self.items: list[dict[str, str]] = []
        # EVERY gate that was actually evaluated. The published gate inventory: a reader
        # must be able to see what an "admit" covered, not merely that nothing failed.
        self.evaluated: set[str] = set()

    def check(self, gate: str, ok: bool, where: str = "", detail: str = "") -> bool:
        self.evaluated.add(gate)
        if not ok:
            self.items.append({"gate": gate, "where": str(where), "detail": str(detail)})
        return ok

    def extend(self, other: "Failures") -> None:
        self.items.extend(other.items)
        self.evaluated |= other.evaluated

    @property
    def gates(self) -> set[str]:
        return {f["gate"] for f in self.items}


def allowlist(f: Failures, obj: Any, allowed, gate: str, where: str) -> bool:
    """The exact key allowlist, as a gate. An unknown key is an unauthorised claim."""
    problems = schema.exact_keys(obj if isinstance(obj, dict) else {}, allowed, where)
    return f.check(gate, isinstance(obj, dict) and not problems, where,
                   "; ".join(problems) or "not an object")
