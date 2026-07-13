"""The Stage-2 TEMPORAL CROSS-CONDITION estimator.

The production lane is the reusable-arm producer in the ``arms`` subpackage
(``direct.temporal.arms``): it differences two admitted within-condition Direct all-arm
bundles by the frozen estimand — a POPULATION-level difference-in-differences on program
projections, ``arm_value(to) - arm_value(from)`` — and emits content-addressed reusable
temporal arm bundles. It is NOT lineage tracing, NOT fate mapping, NOT a rate.

This package ships ONLY that subpackage plus this module. The earlier fixed-pair flat lane
(``run_temporal``/``verify_temporal`` and their config/policy/records) was retired; the
estimand arithmetic and the estimator identity it defined live on inside ``arms`` (in
``arms.estimand`` and ``arms.config``), and the p/q/combined-objective firewall it hosted
moved to the shared ``direct.admission`` where both this lane and the pathway lane use it.
"""
