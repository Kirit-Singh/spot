"""The perturbation target universe is NOT homogeneous ENSG. Coverage must say so.

Independent source audit: the real universe is

    11,522 Ensembl-namespace targets
    +    4 SYMBOL-ONLY targets  (MTRNR2L1, MTRNR2L4, MTRNR2L8, OCLM)
    -------
    11,526 total

not 11,526 all-ENSG. Four targets were released by the screen under a *gene symbol*, with
no Ensembl id, because none exists in the released mapping. They were perturbed. They are
real measurements.

WHY THIS MATTERS FOR A DRUG CACHE
---------------------------------
Stage-3's public acquisition queries UniProt by Ensembl cross-reference
(``xref:ensembl-<ENSG>``). A symbol-only target has no ENSG, so it **cannot be queried**.
That is a limitation of the *acquisition route*, not a fact about the target.

The tempting move is to quietly drop the four and report coverage over 11,522. Then
coverage looks like 100% when it is 11,522/11,526, and four perturbed genes vanish from the
accounting entirely — not refused, not deferred, just gone. **An absence that nobody
recorded is indistinguishable from a target that was never measured.**

So instead:

* the four are **RETAINED**, carrying an explicit ``unsupported_namespace`` disposition;
* coverage denominators **SPLIT by namespace** — an Ensembl denominator and a symbol-only
  denominator — because averaging them into one number states a coverage that is true of
  neither population;
* ``unsupported_namespace`` means *"this acquisition route cannot reach it"*, and it never
  means *"no drug evidence exists"*. Nothing may read it as an absence of evidence.

This module OWNS the namespace arithmetic. It deliberately does not re-implement any
extractor: it consumes what the arm levers already carry
(``target_identity_state``/``target_ensembl``) and counts.
"""
from __future__ import annotations

from typing import Any, Iterable

UNIVERSE_ID = "spot.stage02.perturbation_target_universe.v1"

# Namespaces a released target may arrive in.
NS_ENSEMBL = "ensembl"
NS_SYMBOL_ONLY = "symbol_only"
NAMESPACES = (NS_ENSEMBL, NS_SYMBOL_ONLY)

# The audited universe. Pinned so a drift in the upstream release is loud, not silent.
N_ENSEMBL = 11_522
N_SYMBOL_ONLY = 4
N_UNIVERSE = N_ENSEMBL + N_SYMBOL_ONLY                      # 11,526

# The four, by name. They are not a rounding error; they are four perturbed genes.
SYMBOL_ONLY_TARGETS = ("MTRNR2L1", "MTRNR2L4", "MTRNR2L8", "OCLM")
assert len(SYMBOL_ONLY_TARGETS) == N_SYMBOL_ONLY

# The disposition a symbol-only target carries through Stage 3.
UNSUPPORTED_NAMESPACE = "unsupported_namespace"
UNSUPPORTED_NAMESPACE_REASON = (
    "released in a gene_symbol namespace with no Ensembl id; Stage-3 public acquisition "
    "resolves targets by UniProt Ensembl cross-reference, so this acquisition ROUTE cannot "
    "reach it. This is a limit of the route, NOT an absence of drug evidence, and nothing "
    "may read it as one."
)


class UniverseError(ValueError):
    """The released universe does not match the audited namespace split."""


def namespace_of(lever: dict[str, Any]) -> str:
    """Which namespace a target actually arrived in. Read, never guessed."""
    ensembl = lever.get("target_ensembl")
    return NS_ENSEMBL if ensembl else NS_SYMBOL_ONLY


def split(levers: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Partition the released targets by namespace. Nothing is dropped."""
    ensembl: set[str] = set()
    symbol_only: set[str] = set()
    for lever in levers:
        tid = lever["target_id"]
        if namespace_of(lever) == NS_ENSEMBL:
            ensembl.add(tid)
        else:
            symbol_only.add(tid)

    return {
        "universe_id": UNIVERSE_ID,
        "n_ensembl": len(ensembl),
        "n_symbol_only": len(symbol_only),
        "n_total": len(ensembl) + len(symbol_only),
        "ensembl_targets": sorted(ensembl),
        "symbol_only_targets": sorted(symbol_only),
        "namespaces_are_split": True,
        "universe_is_homogeneous_ensembl": False,
    }


def dispositions(levers: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """One explicit disposition per symbol-only target. None is silently dropped."""
    out = []
    for lever in levers:
        if namespace_of(lever) != NS_SYMBOL_ONLY:
            continue
        out.append({
            "subject_kind": "arm_lever_target",
            "subject_id": lever["target_id"],
            "state": UNSUPPORTED_NAMESPACE,
            "reason": UNSUPPORTED_NAMESPACE_REASON,
            "target_symbol": lever.get("target_symbol") or lever["target_id"],
            "acquisition_route_can_reach_it": False,
            "means_no_drug_evidence_exists": False,       # it does NOT. Ever.
        })
    return out


def coverage(levers: Iterable[dict[str, Any]],
             acquired_target_ids: Iterable[str]) -> dict[str, Any]:
    """Cache coverage, with the denominators SPLIT.

    One blended number would state a coverage that is true of neither population: the
    symbol-only targets can never be acquired by this route, so folding them into the
    denominator makes the Ensembl coverage look permanently short, while dropping them
    makes it look complete when four targets were never even attempted.
    """
    parts = split(levers)
    acquired = set(acquired_target_ids)

    n_ens = parts["n_ensembl"]
    n_sym = parts["n_symbol_only"]
    ens_hit = len([t for t in parts["ensembl_targets"] if t in acquired])
    sym_hit = len([t for t in parts["symbol_only_targets"] if t in acquired])

    if sym_hit:
        raise UniverseError(
            f"{sym_hit} symbol-only target(s) appear in the acquisition results, but the "
            "acquisition route resolves targets by Ensembl cross-reference and cannot "
            "reach them. Something acquired a target it had no id for.")

    return {
        "universe_id": UNIVERSE_ID,
        "by_namespace": {
            NS_ENSEMBL: {
                "denominator": n_ens,
                "acquired": ens_hit,
                "coverage": (ens_hit / n_ens) if n_ens else None,
                "route_can_reach": True,
            },
            NS_SYMBOL_ONLY: {
                "denominator": n_sym,
                "acquired": 0,
                "coverage": None,          # NOT 0.0 — it was never attempted
                "route_can_reach": False,
                "disposition": UNSUPPORTED_NAMESPACE,
            },
        },
        "n_total_targets": parts["n_total"],
        "blended_coverage_permitted": False,
        "blended_coverage_reason": (
            "a single coverage number over a mixed-namespace universe is true of neither "
            "population; the denominators are reported separately"),
    }


def check_against_audit(parts: dict[str, Any]) -> None:
    """The released universe must still be the audited 11,522 / 4. Drift is loud."""
    if parts["n_ensembl"] != N_ENSEMBL or parts["n_symbol_only"] != N_SYMBOL_ONLY:
        raise UniverseError(
            f"the released universe is {parts['n_ensembl']} ENSG + "
            f"{parts['n_symbol_only']} symbol-only; the audit pinned "
            f"{N_ENSEMBL} + {N_SYMBOL_ONLY}. Either the release changed or the split is "
            "being computed wrong — both need a human, not a silent re-pin.")
