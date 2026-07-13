"""The REUSABLE TEMPORAL ARM lane — the Stage-2 temporal production lane.

It differences two admitted within-condition Direct all-arm bundles by the frozen estimand
(a POPULATION-level difference-in-differences on program projections) and emits
content-addressed, all-program, pair-agnostic reusable temporal arm bundles.

SELF-CONTAINED. After the fixed-pair flat lane was retired, this subpackage owns the whole
production surface: the estimand arithmetic (``estimand``) and the estimator identity
(``config``) that used to live in the parent ``temporal`` package now live HERE. It reaches
UP only for shared ``direct`` infrastructure — hashing, ``arm_keys``, ``code_digest``, the
shared ``direct.admission`` key firewall — and the dependency runs ONE WAY: nothing in
``direct`` or ``direct.temporal`` imports ``direct.temporal.arms``.

WHAT LIVES HERE
---------------
``config``            the generic estimator identity + the temporal method hash the bridge binds
``estimand``          the DiD subtraction and the cross-condition status enum (pure arithmetic)
``arm_estimand``      the base temporal delta, the sign transform, the frozen rank rule
``arm_direct_source`` reads two admitted Direct all-arm bundles into temporal endpoints
``arm_programs``      the admitted program axis, DERIVED from the bound v3 scorer view
``arm_bundle``        one all-program, pair-agnostic bundle per ordered condition pair
``arm_admission``     the fail-closed allowlist + firewalls + independent re-derivation
``arm_emit``          deterministic, content-addressed emission
``arm_request``       the narrow adapter boundary for W18's bundle-scoped request object
``run_temporal_arms`` the production CLI the scheduler invokes
"""
from __future__ import annotations

__all__ = ["arm_admission", "arm_bundle", "arm_direct_source", "arm_emit", "arm_estimand",
           "arm_programs", "arm_request", "config", "estimand", "run_temporal_arms"]
