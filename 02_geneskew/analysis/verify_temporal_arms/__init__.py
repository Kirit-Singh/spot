"""The INDEPENDENT verifier for the Stage-2 reusable temporal ARM release.

generator != evaluator. This package checks the six ordered-pair temporal arm bundles by
REOPENING THEM FROM DISK and re-deriving every claim in them from the bound Stage-1 v3
release and from its own separately-stated rules. It imports nothing from the lane that
produced them: not the sign map, not the arm-key grammar, not the rank rule, not the
canonical serialiser. A checker that reuses the producer's arithmetic to check the
producer's arithmetic has measured nothing, and the producer's own admission report — a
self-report — is never sufficient here.

It lives OUTSIDE ``analysis/direct`` on purpose. The direct and temporal run identities
bind a FLAT listing of their package directory, so a verifier module placed beside them
would silently move the method hash of every artifact it exists to check.
"""
from __future__ import annotations

RULE_LANE_ID = "spot.stage02.temporal.arm.independent_verifier.v1"
