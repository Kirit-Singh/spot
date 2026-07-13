"""Perturb2State v2 — the SECONDARY, reusable-arm reconstruction-support lane.

It consumes ONE independently admitted reusable Direct arm

    direct | program_id | desired_change | condition

and emits reconstruction-support evidence keyed by it. There is no A/B pair anywhere: a pair
is a JOIN of two independently computed support lanes, done by the consumer.

``lane_role = secondary_non_gating``. It cannot promote, demote, rescue, admit, gate,
reorder or re-rank a Direct target, it cannot validate a Direct result by agreeing with it,
and it is not part of "complete Stage-2" (Direct + Pareto + temporal + pathway).

Coefficients are CONDITIONAL RECONSTRUCTION WEIGHTS. They are not p-values, not standard
errors, not causal effects and not validation.

The pair-bound v1 lane lives on, untouched, in ``analysis/perturb2state/``.
"""
