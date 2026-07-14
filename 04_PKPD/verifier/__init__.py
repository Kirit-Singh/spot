"""Independent Stage-4 verifier.

Reconstructs every derived claim (CNS-MPO transforms, exposure margins, the NEBPI
decision path, identity/context joins, eligibility) from the emitted evidence tables and
the declared method, then insists the generator's JSON and parquet agree with the rebuild
and with each other.

INVARIANT: nothing under `verifier/` may import `analysis/`. A verifier that reuses the
generator's logic can only prove the generator is self-consistent. This one is enforced
by a test (`test_verifier_is_independent`).
"""

from .checks import verify_release

__all__ = ["verify_release"]
