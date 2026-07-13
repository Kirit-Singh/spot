"""The REUSABLE TEMPORAL ARM layer. Strictly additive; invisible to what it stands on.

WHY THIS IS A SUBPACKAGE, AND NOT SIX FILES IN THE PARENT
--------------------------------------------------------
``runid.code_tree_sha256`` hashes the ``.py`` files DIRECTLY IN a package directory — a
flat listing, not a walk. The temporal run binds ``temporal_code_tree_sha256`` over its own
directory, so a module dropped beside ``run_temporal.py`` would change the temporal method
hash, and with it ``temporal_run_id`` and ``temporal_method_sha256`` on every row of the
EXISTING ``temporal.parquet`` — an artifact this layer must not be able to move.

Measured, not assumed: adding these modules to the parent directory moved the temporal
method hash from ``b3c9b969…`` to ``3afb2687…``. In a subdirectory it is unchanged.

This is the SAME idiom, one level down: ``direct``'s code tree does not see
``direct/temporal`` for exactly this reason, which is what makes the temporal lane a
strictly additive layer on the within-condition screen. The reusable-arm layer is a
strictly additive layer on the temporal lane, and the dependency runs ONE WAY —
``temporal.arms`` imports ``temporal`` and ``direct``; neither imports back.

The invariance is asserted, not asserted-ish, in ``test_temporal_arms.py``
(``TestLegacyByteInvariance``).

WHAT LIVES HERE
---------------
``arm_estimand``   the base temporal delta, the sign transform, the frozen rank rule
``arm_programs``   the admitted program axis, DERIVED from the bound v3 scorer view
``arm_bundle``     one all-program, pair-agnostic bundle per ordered condition pair
``arm_admission``  the fail-closed allowlist + firewalls + independent re-derivation
``arm_emit``       deterministic, content-addressed emission
``arm_request``    the narrow adapter boundary for W18's bundle-scoped request object
"""
from __future__ import annotations

__all__ = ["arm_admission", "arm_bundle", "arm_emit", "arm_estimand", "arm_programs",
           "arm_request"]
