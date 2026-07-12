"""THE SOURCE CLASSIFICATION RULE — part of the STANDALONE verifier.

INDEPENDENCE RULE (test-enforced): imports nothing from the generator.

Whether a released scope is DETERMINED or AMBIGUOUS is not the manifest's to say. The
manifest asserting "this identity is unknown" is a claim like any other, and it was the
only claim in the lane that nothing ever checked: completeness was verified for scopes
already labelled ``determined``, and an ``ambiguous`` label was skipped by every rule on
both sides. Relabelling one scope therefore deleted its evidence for free — its mask,
its score and its rank — while every count, hash and cross-document comparison still
balanced, because the producer regenerated them all honestly.

The source settles it, and only the source can:

    provable(scope) = { g : the source kept a row for this (target, condition)
                            whose guide_type is TARGETING }

    non-empty -> DETERMINABLE. ``determined`` is mandatory, and the named guide set must
                 be exactly provable(scope) (that is COMPLETENESS, next door).
    empty     -> genuinely non-determinable. ``ambiguous`` is the only honest label.

Restated here rather than imported: an expectation taken from the generator agrees with
the generator by construction, whatever the generator happens to say today.
"""
from __future__ import annotations

import numpy as np
import verify_rules as R  # noqa: E402
from verify_source import (  # noqa: E402
    CONDITION_COL,
    GUIDE_COL,
    GUIDE_TYPE_COL,
    KEEP_COL,
    TARGET_COL,
    TARGETING,
    _excluded,
    _is_pooled,
    _source_scope,
)


def source_determinable_scopes(cols):
    """Which scopes the RAW SOURCE can determine, and with which guides.

    Independently restated: a scope is determinable iff the source kept at least one
    row for it whose ``guide_type`` is targeting. Nothing about the manifest enters
    this — not its rows, not its labels, not its counts. That is the entire point.

    The verifier used to take ``evidence_state`` on trust exactly as the generator did:
    an ambiguous-labelled scope was added to a set and ``continue``d past, and the only
    thing ever compared was ``len(determined) + len(ambiguous) == n_released``, which is
    invariant under moving a scope from one side to the other. A downgraded scope
    therefore passed the strict verifier with 31/31 checks green.
    """
    guide, target = cols[GUIDE_COL], cols[TARGET_COL]
    cond, keep, gtype = cols[CONDITION_COL], cols[KEEP_COL], cols[GUIDE_TYPE_COL]
    provable: dict[tuple, set] = {}
    for i in np.flatnonzero(np.asarray(keep, dtype=bool)):
        i = int(i)
        if str(gtype[i]) != TARGETING:
            continue
        provable.setdefault((str(target[i]), str(cond[i])), set()).add(str(guide[i]))
    return provable


def check_source_classification(manifest_doc, provable, rep):
    """EVERY scope's claimed state, against the state the SOURCE proves.

    Two distinct lies, named separately because they are not the same act:

      * a DOWNGRADE deletes evidence the source holds. The scope has kept targeting
        guides; the manifest calls its identity unknown. The scope loses its mask, its
        score and its rank, and every count in the report still balances.
      * an OVERCLAIM invents evidence the source does not hold. The scope has no kept
        targeting guide; the manifest names one anyway.
    """
    claimed: dict[tuple, str] = {}
    for row in manifest_doc["rows"]:
        if not _is_pooled(row):
            continue
        scope = _source_scope(row)
        if str(row.get("evidence_state")) == R.DETERMINED and not _excluded(row) \
                and not R.is_null(row.get("guide_id")):
            claimed[scope] = R.DETERMINED
        else:
            claimed.setdefault(scope, R.AMBIGUOUS)

    downgraded = sorted(sc for sc, state in claimed.items()
                        if (provable.get(sc) or set()) and state != R.DETERMINED)
    overclaimed = sorted(sc for sc, state in claimed.items()
                         if not (provable.get(sc) or set())
                         and state == R.DETERMINED)

    rep.check("STRICT: no scope the SOURCE can determine is labelled ambiguous",
              not downgraded,
              f"{len(downgraded)} scope(s) whose kept targeting guides the source holds "
              f"are labelled ambiguous (first: {downgraded[0] if downgraded else None}); "
              "an ambiguous label there deletes evidence that exists")
    rep.check("STRICT: no scope the SOURCE cannot determine is labelled determined",
              not overclaimed,
              f"{len(overclaimed)} scope(s) are determined but the source kept no "
              f"targeting guide (first: {overclaimed[0] if overclaimed else None})")
    return {"n_determinable": sum(1 for sc in claimed if provable.get(sc)),
            "n_non_determinable": sum(1 for sc in claimed if not provable.get(sc))}
