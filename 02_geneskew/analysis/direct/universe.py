"""The effect-gene universe every projection is taken over.

WHICH universe depends on WHAT IS PROJECTED, and that is the whole point.

``common_gene_universe`` intersects the pooled matrix with the support matrices. It
exists because the released objects do NOT agree on their gene sets: if the pooled and
donor-pair estimates were each projected on their own genes, their scores would be means
over DIFFERENT genes, and sign-comparing them to grant donor support would compare two
things that were never measured on the same axis. That intersection is the right
universe for a run that projects support — and only for such a run.

``primary_universe`` is the pooled object's own gene axis, and it is what this release
pass uses. Support carries no contributor evidence here, so it is never projected, and
there is nothing to hold a common axis WITH. Intersecting anyway would discard pooled
genes to match matrices no score is ever taken over — a real change to every primary
score, bought for nothing. The universe is content-hashed and bound into run_id, so
which of the two a run used is part of what the run is.
"""
from __future__ import annotations

from typing import Iterable, Sequence

from .hashing import content_hash

# What the universe was built from. Bound into run_id: a run that silently changed its
# gene axis would be a different scientific claim wearing the same id.
BASIS_POOLED_MAIN = "pooled_main_only"
BASIS_COMMON_INTERSECTION = "pooled_main_and_support_intersection"

# An intersection smaller than this fraction of the pooled universe means the
# objects are not the same assay; refuse rather than project on a rump.
MIN_INTERSECTION_FRACTION = 0.90


class UniverseError(ValueError):
    """The effect objects do not share a usable gene universe."""


def primary_universe(pooled_gene_ids: Sequence[str]) -> dict:
    """The pooled object's own gene axis: the universe when only main is projected."""
    if not pooled_gene_ids:
        raise UniverseError("the pooled effect object has an empty gene universe")
    ordered = list(pooled_gene_ids)
    return {
        "gene_ids": ordered,
        "n_genes": len(ordered),
        "sha256": content_hash(ordered),
        "basis": BASIS_POOLED_MAIN,
        "object_sizes": {"__reference__": len(ordered)},
        "retained_fraction_of_reference": 1.0,
        "order": "pooled effect object order",
    }


def common_gene_universe(
    reference_gene_ids: Sequence[str],
    other_gene_id_sets: dict[str, Iterable[str]],
    min_fraction: float = MIN_INTERSECTION_FRACTION,
) -> dict:
    """Intersect the pooled universe with every support object's universe.

    Returns the ordered common ids (pooled order preserved), the hash, and the
    per-object sizes. Raises ``UniverseError`` if the intersection is empty or
    implausibly small.
    """
    if not reference_gene_ids:
        raise UniverseError("the pooled effect object has an empty gene universe")

    common = set(reference_gene_ids)
    sizes = {"__reference__": len(reference_gene_ids)}
    for name, ids in other_gene_id_sets.items():
        ids = set(ids)
        sizes[name] = len(ids)
        if not ids:
            raise UniverseError(f"effect object {name!r} has an empty gene universe")
        common &= ids
        if not common:
            raise UniverseError(
                f"effect object {name!r} shares no gene with the pooled universe")

    ordered = [g for g in reference_gene_ids if g in common]      # pooled order
    fraction = len(ordered) / len(reference_gene_ids)
    if fraction < min_fraction:
        raise UniverseError(
            f"common gene universe is only {len(ordered)} of "
            f"{len(reference_gene_ids)} pooled genes ({fraction:.1%} < "
            f"{min_fraction:.0%}): the effect objects are not compatible")

    return {
        "gene_ids": ordered,
        "n_genes": len(ordered),
        "sha256": content_hash(ordered),
        "basis": BASIS_COMMON_INTERSECTION,
        "object_sizes": sizes,
        "retained_fraction_of_reference": round(fraction, 6),
        "order": "pooled effect object order",
    }


def restrict(gene_ids: Iterable[str], universe: Iterable[str]) -> list[str]:
    """Restrict a panel / control gene list to the common universe.

    Every estimate's panel and control means are then taken over exactly the same
    genes, whichever object the estimate came from.
    """
    allowed = set(universe)
    return [g for g in gene_ids if g in allowed]
