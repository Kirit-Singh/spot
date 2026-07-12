"""A deterministic fixture gene-set bundle, and target-masked signature vectors.

The real bundle (pinned public Reactome + GO-BP releases) is being acquired separately.
Nothing in the lane knows which source it is: the loader is parameterised by release +
namespace + universe binding, so the fixture bundle is a bundle like any other and the
tests exercise the SAME code path the real one will.

The sets are built to make each rule visible on its own:

    SET_CONVERGENT     3 measured members whose signatures genuinely agree
    SET_SINGLE         exactly 1 measured member  -> single_target_support, never
                       convergent, however strong that one target looks
    SET_DIVERGENT      3 measured members whose signatures do NOT agree
    SET_TOO_SMALL      below MIN_SET_SIZE          -> emitted, untestable
    SET_UNMEASURED     members that exist in the universe but were never perturbed
"""
from __future__ import annotations

import json
import os
from typing import Any

from direct import genesets

RELEASE_ID = "fixture-2026-07-01"
SOURCE = "fixture"


def gene_set_doc(universe: list[str], targets: list[str],
                 effect_universe_sha256: str) -> dict[str, Any]:
    """A bundle over the given effect universe. Sets are drawn from real target ids."""
    t = list(targets)
    filler = [g for g in universe if g not in t]

    sets = [
        {"set_id": "FX:CONVERGENT", "name": "convergent pathway",
         "genes": t[0:3] + filler[0:2]},
        {"set_id": "FX:SINGLE", "name": "single-target pathway",
         "genes": [t[3]] + filler[2:6]},
        {"set_id": "FX:DIVERGENT", "name": "divergent pathway",
         "genes": t[4:7] + filler[6:8]},
        {"set_id": "FX:TOO_SMALL", "name": "too small to test",
         "genes": t[7:8]},
        {"set_id": "FX:UNMEASURED", "name": "never perturbed",
         "genes": filler[8:14]},
    ]
    return {
        "schema_version": genesets.SCHEMA_VERSION,
        "release": {"source": SOURCE, "release_id": RELEASE_ID},
        "gene_id_namespace": "ensembl_gene_id",
        "effect_universe_sha256": effect_universe_sha256,
        "sets": sets,
    }


def write_gene_sets(d: str, universe: list[str], targets: list[str],
                    effect_universe_sha256: str, mutate=None) -> str:
    doc = gene_set_doc(universe, targets, effect_universe_sha256)
    if mutate is not None:
        doc = mutate(doc)
    path = os.path.join(d, "gene_sets.fixture.json")
    with open(path, "w") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)
    return path


def masked_support(universe: list[str], target: str) -> list[str]:
    """THIS target's unmasked readout genes: the universe minus its own mask.

    The perturbed gene itself, plus a small neighbourhood, comes out — which is exactly
    what makes two targets' supports DIFFERENT, and why a similarity has to be computed
    on their intersection and reported with the size of it.
    """
    i = universe.index(target)
    masked = {target, universe[(i + 1) % len(universe)]}
    return [g for g in universe if g not in masked]


def signatures(universe: list[str], targets: list[str]) -> dict[str, dict[str, float]]:
    """Target-masked signature vectors, built so convergence is DECIDABLE by hand.

    Over the FULL readout universe, each with its OWN mask removed — so no two targets
    share their entire support, and the shared-support size is a real quantity.
    """
    out: dict[str, dict[str, float]] = {}

    def vec(target, pattern):
        support = masked_support(universe, target)
        return {g: pattern(universe.index(g)) for g in support}

    # CONVERGENT: t0, t1, t2 all respond in the same direction (cosine ~ 1)
    for k, t in enumerate(targets[0:3]):
        out[t] = vec(t, lambda i, k=k: (1.0 + 0.01 * k) if i % 2 == 0 else -1.0)

    # SINGLE: t3 — strong, and genuinely ALONE. Its direction is the INVERSE of the
    # convergent group, so nothing it does agrees with anything.
    #
    # It is deliberately not merely "strong": cosine similarity ignores magnitude (by
    # design — a weak-but-identical knockdown and a strong one converge, which is the
    # biology we are asking about), so a strong target pointing the SAME way as the
    # convergent group would cluster with it, correctly. To test that a cluster of one
    # is not a cluster, the target has to actually be on its own.
    out[targets[3]] = vec(targets[3], lambda i: -5.0 if i % 2 == 0 else 5.0)

    # DIVERGENT: t4, t5, t6 point in genuinely different directions
    out[targets[4]] = vec(targets[4], lambda i: 1.0 if i % 3 == 0 else -0.2)
    out[targets[5]] = vec(targets[5], lambda i: -1.0 if i % 3 == 0 else 0.2)
    out[targets[6]] = vec(targets[6],
                          lambda i: 1.0 if i % 4 == 0 else -0.1 * ((i % 5) - 2))

    for t, v in out.items():
        assert len(v) >= 10, f"{t}: masked support too small for MIN_SHARED_GENES"
    return out
