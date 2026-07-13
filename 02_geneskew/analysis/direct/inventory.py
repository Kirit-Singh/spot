"""GATE 7: what the production package is ALLOWED to contain. Fail-closed.

The tree carried two pair-captured legacy trees — `analysis/perturb2state/` and
`analysis/temporal_exploration/` (`screen_th1_treg_temporal.py`) — inside the production
package. They were already outside the producer's CODE IDENTITY (the digest root is
`analysis/direct`), which is exactly what made them dangerous: they could be discovered,
imported, or surfaced in the UI while contributing nothing to the hash that is supposed to say
what this system IS. A file that can run but cannot change the code identity is the one file
nobody will notice.

They are archived out of the package. This gate is what stops the next one arriving.

WHY AN ALLOWLIST AND NOT A BLOCKLIST
------------------------------------
A blocklist names the legacy trees we already know about, and says nothing about the next
`analysis/screen_treg_th1_v2/` somebody adds in a hurry. So this ENUMERATES WHAT PRODUCTION IS
and refuses everything else. Adding to the package then requires editing this list — which is a
decision somebody makes on purpose, rather than a drift nobody sees.

The generic system takes its biology from a CONTRACT. A module that names a program pair in its
own filename has a fixed pair compiled into it, and no contract can talk it out of that.
"""
from __future__ import annotations

import os
from typing import Any

INVENTORY_RULE_ID = "spot.stage02.production_package.allowlist.v1"
INVENTORY_RULE = (
    "the production package contains EXACTLY the allowlisted entries; anything else is refused, "
    "so a new pair-captured tree cannot arrive unnoticed")

# WHAT THE PRODUCTION PACKAGE IS. Everything else is refused.
ALLOWED_ENTRIES = (
    "direct",                     # the generic producer
    "run_stage2.sh",              # the runbook
    "stage02_solver_lock.txt",    # the pinned environment
)

# Named so a refusal SAYS what it found rather than only that it found something.
KNOWN_LEGACY = (
    "perturb2state",              # legacy P2S, pair-captured
    "temporal_exploration",       # incl. screen_th1_treg_temporal.py
)

REFUSE_UNEXPECTED_ENTRY = "the_production_package_contains_an_entry_that_is_not_production"
REFUSE_LEGACY_IMPORTABLE = "a_legacy_pair_captured_module_is_importable_from_the_package"


class InventoryError(ValueError):
    def __init__(self, gate: str, message: str):
        super().__init__(f"[{gate}] {message}")
        self.gate = gate


def scan(package_root: str) -> dict[str, Any]:
    """Every entry in the production package, and whether it is allowed to be there."""
    entries = sorted(e for e in os.listdir(package_root)
                     if not e.startswith(("__pycache__", ".")))
    unexpected = [e for e in entries if e not in ALLOWED_ENTRIES]
    legacy = [e for e in unexpected if e in KNOWN_LEGACY]
    return {
        "inventory_rule_id": INVENTORY_RULE_ID,
        "entries": entries,
        "allowed": list(ALLOWED_ENTRIES),
        "unexpected": unexpected,
        "legacy_present": legacy,
        "clean": not unexpected,
    }


def verify(package_root: str) -> dict[str, Any]:
    """REFUSE a production package that carries anything but production."""
    result = scan(package_root)
    if result["unexpected"]:
        legacy = result["legacy_present"]
        why = (f" {legacy} is pair-captured legacy: it names a fixed program pair in its own "
               "code, and no contract can talk it out of that" if legacy else "")
        raise InventoryError(
            REFUSE_UNEXPECTED_ENTRY,
            f"the production package holds {result['unexpected']}, which is not production.{why} "
            "The generic system takes its biology from a CONTRACT; anything shipped beside the "
            "producer can be discovered, imported or surfaced without ever changing the code "
            "identity that is supposed to say what this system is")
    return result


def assert_legacy_not_importable() -> None:
    """The archived trees must not be reachable as modules from the production package."""
    import importlib.util
    found = [name for name in KNOWN_LEGACY
             if importlib.util.find_spec(name) is not None]
    if found:
        raise InventoryError(
            REFUSE_LEGACY_IMPORTABLE,
            f"{found} is importable. Archiving a directory that is still on the import path "
            "moves the file and not the problem")
