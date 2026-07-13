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
                 effect_universe_sha256: str,
                 target_universe_sha256: str | None = None) -> dict[str, Any]:
    """A bundle over BOTH universes. Sets are drawn from real target ids.

    A1: the loader is FAIL-CLOSED — a bundle that supplies a run with a target universe
    and declares none is refused. So the fixture declares both, like a real bundle must.
    When the caller gives no target universe the fixture derives it from the targets it
    was handed, which is exactly what the real builder does.
    """
    t = list(targets)
    filler = [g for g in universe if g not in t]

    raw = [
        ("FX:CONVERGENT", "convergent pathway", t[0:3] + filler[0:2]),
        ("FX:SINGLE", "single-target pathway", [t[3]] + filler[2:6]),
        ("FX:DIVERGENT", "divergent pathway", t[4:7] + filler[6:8]),
        ("FX:TOO_SMALL", "too small to test", t[7:8]),
        ("FX:UNMEASURED", "never perturbed", filler[8:14]),
    ]
    # This bundle names Ensembl ids directly (no re-keying), so it declares that it
    # retained every gene it names: n_source_symbols == the members. A bundle that cannot
    # say how much of a pathway it kept is DESCRIPTIVE-ONLY (B4), and that is the right
    # answer for one that will not say — but this one can.
    sets = [{"set_id": sid, "name": name, "genes": genes,
             "n_source_symbols": len(genes), "n_dropped_unmappable": 0}
            for sid, name, genes in raw]
    from direct.hashing import content_hash
    return {
        "schema_version": genesets.SCHEMA_VERSION,
        "release": {"source": SOURCE, "release_id": RELEASE_ID,
                    "license": genesets.SOURCE_LICENSE[SOURCE]},
        "gene_id_namespace": "ensembl_gene_id",
        "effect_universe_sha256": effect_universe_sha256,
        "target_universe_sha256": (target_universe_sha256
                                   or content_hash(sorted(set(targets)))),
        "sets": sets,
    }


def write_gene_sets(d: str, universe: list[str], targets: list[str],
                    effect_universe_sha256: str, mutate=None,
                    target_universe_sha256: str | None = None) -> str:
    doc = gene_set_doc(universe, targets, effect_universe_sha256,
                       target_universe_sha256)
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
