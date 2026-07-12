"""The Stage-2 TEMPORAL CROSS-CONDITION estimator — a strictly ADDITIVE layer.

It sits ON TOP of the within-condition direct lane and reuses its machinery verbatim:
the same masked program projection, the same two arms, the same base QC, the same
ranks, the same Pareto tiers. It computes ONE new thing — the cross-condition
difference of two within-condition arm values — and it writes its own artifact.

It is a one-way dependency. Nothing in ``direct`` imports ``direct.temporal``, so the
within-condition ``code_tree_sha256`` (``runid.code_tree_sha256`` lists only the .py
files directly in the package directory) does not see this subpackage, and no
within-condition ``run_id``, score, rank or tier can move because this layer exists.
That is not an accident of layout — it is the property the invariance test enforces.
"""
