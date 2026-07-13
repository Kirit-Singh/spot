"""THE FROZEN SYMBOL CROSSWALK: a target_id's PUBLIC LABEL, looked up — never guessed.

WHAT THIS IS FOR
----------------
The browser wants to write a gene name next to a point. That is DISPLAY METADATA. It is not a
new statistic, it changes no value and no rank, and it must never be derived by a live lookup
against whatever a service happens to return today: a label that can change under a plot is a
label that can relabel the science.

So the symbol comes from ONE frozen, public, hash-bound artifact — Stage-1's
``effect_universe_gwcd4i.json`` (``symbol_to_ensembl``) — and that artifact is BOUND into the
projection so an independent verifier can reopen it and prove every emitted symbol.

THE DIRECTION IS INVERTED, AND ONLY WHERE THE INVERSION IS SAFE
---------------------------------------------------------------
The artifact maps SYMBOL -> ENSEMBL. A row needs ENSEMBL -> SYMBOL. An inversion is only
meaningful where it is ONE-TO-ONE: if two symbols name the same Ensembl id, then that id has no
single public label, and picking one would be an editorial act performed silently, at render
time, on a plot. Ambiguous entries are therefore DROPPED from the inverse and the target is
left unlabelled.

(On the frozen artifact, 10,282 symbols invert to 10,282 distinct Ensembl ids with ZERO
collisions. The refusal is not hypothetical, though: it is what stops a future crosswalk from
quietly labelling a gene with a name it shares.)

TWO UNIVERSES — and this is why `null` is a real answer, not a gap
------------------------------------------------------------------
The crosswalk covers the DE-READOUT universe: the ~10,282 genes that were MEASURED. The rows it
labels are PERTURBATION TARGETS: 11,526 genes that were PERTURBED. Only ~9,497 are both. So
roughly 2,029 perturbed targets CANNOT have a symbol from this artifact — not because anything
is broken, but because they were never readout genes.

An unmapped target's symbol is therefore an EXPLICIT NULL. It is never the target_id wearing a
symbol's field: an ENSG string printed where a reader expects a gene name is a lie a plot tells
quietly, and it is exactly the kind of lie nobody checks.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

from .hashing import content_hash, file_sha256

CROSSWALK_ID = "spot.stage01.effect_universe_gwcd4i.symbol_to_ensembl.v1"
SOURCE_FILE = "effect_universe_gwcd4i.json"
SOURCE_FIELD = "symbol_to_ensembl"

# WHICH UNIVERSE the symbols come from. Naming it stops a reader assuming it is the other one.
SYMBOL_NAMESPACE = "hgnc_symbol"
TARGET_NAMESPACE = "ensembl_gene_id"
COVERAGE_UNIVERSE = "de_readout"          # NOT the perturbation-target universe

INVERSION_RULE_ID = "spot.stage02.symbol_crosswalk.invert_one_to_one_only.v1"
INVERSION_RULE = (
    "the frozen artifact maps SYMBOL -> ENSEMBL; the inverse is taken ONLY where it is "
    "one-to-one. An Ensembl id named by more than one symbol has no single public label, and "
    "choosing one would be an editorial act performed silently at render time")

UNMAPPED = None                            # explicit null. NEVER the target_id.


class CrosswalkError(ValueError):
    """The crosswalk cannot be trusted. Refuse; never guess a label."""


def load(path: str) -> dict[str, Any]:
    """Open the frozen artifact and BUILD THE SAFE INVERSE. Fail closed on ambiguity."""
    if not os.path.exists(path):
        raise CrosswalkError(
            f"no symbol crosswalk at {os.path.basename(path)}. A label with no bound source is "
            "a label nobody can check")
    with open(path) as fh:
        doc = json.load(fh)

    forward = doc.get(SOURCE_FIELD)
    if not isinstance(forward, dict) or not forward:
        raise CrosswalkError(f"{SOURCE_FILE}: no {SOURCE_FIELD!r} map")

    # THE INVERSE, one-to-one ONLY. A collision drops BOTH sides: the id is unlabelled.
    seen: dict[str, list] = {}
    for symbol, ensembl in forward.items():
        seen.setdefault(str(ensembl), []).append(str(symbol))
    inverse = {e: s[0] for e, s in seen.items() if len(s) == 1}
    ambiguous = {e: sorted(s) for e, s in seen.items() if len(s) > 1}

    return {
        "path": os.path.basename(path),     # a NAME. Never this host's directory layout.
        "crosswalk_id": CROSSWALK_ID,
        "raw_sha256": file_sha256(path),
        "canonical_sha256": content_hash(doc),
        "symbol_namespace": SYMBOL_NAMESPACE,
        "target_namespace": TARGET_NAMESPACE,
        "coverage_universe": COVERAGE_UNIVERSE,
        "inversion_rule_id": INVERSION_RULE_ID,
        "inversion_rule": INVERSION_RULE,
        "n_symbols": len(forward),
        "n_one_to_one": len(inverse),
        "n_ambiguous_dropped": len(ambiguous),
        "ambiguous_ensembl_ids": sorted(ambiguous)[:20],
        # provenance the ARTIFACT declares — minus any host path, which binds a machine
        "source": {k: v for k, v in (doc.get("provenance") or {}).items()
                   if k != "host_path"},
        "inverse": inverse,                 # ensembl -> symbol. NOT serialized into the view.
    }


def binding(cw: dict[str, Any]) -> dict[str, Any]:
    """What the PROJECTION carries: everything a verifier needs to reopen and re-derive it."""
    return {k: v for k, v in cw.items() if k != "inverse"}


def symbol_for(cw: dict[str, Any], target_id: Any) -> Optional[str]:
    """The target's public label, or an EXPLICIT NULL. Never the target_id relabelled."""
    return cw["inverse"].get(str(target_id), UNMAPPED)
