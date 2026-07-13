"""THE Stage-2 solver lock, PINNED — and bound into the identity of every run.

Committing the lock file was necessary and not sufficient. `runid.env_lock_block` hashed
whatever path it was handed and reported `environment_lock_not_supplied` when it was handed
none: it never checked that the file WAS the lock, and it never refused. A lock that can be
swapped for another file, or simply left out, is not a lock — it is a filename.

So the expected digest is PINNED HERE, exactly as the Stage-1 v3 JSON schema is pinned: a lock
whose bytes are decided by whoever supplies them validates whatever the supplier wanted it to.
The pin is the whole mechanism.

  * a MISSING lock REFUSES  (`solver_lock_not_supplied`)
  * a SWAPPED lock REFUSES  (`solver_lock_is_not_the_pinned_stage2_lock`) — including the
    STAGE-1 lock, which is a real and easy mistake: it is a valid, honest, content-addressed
    solver lock for a DIFFERENT environment (conda `scvi_gpu`, Python 3.11.15, pyarrow 24.0.0),
    and a Stage-2 run executed under it is a run nobody can reproduce
  * an ADMITTED lock is bound into the run identity by its FULL sha256, so a result cannot be
    re-attributed to an environment it was not computed in.

Recording the lock beside a run says which environment the producer *had*. Binding it INTO the
run id says which environment the numbers *came from*. Only the second one survives a swap.
"""
from __future__ import annotations

import os
from typing import Any, Optional

from .hashing import file_sha256

# The pinned Stage-2 lock. 38 pins, conda --explicit (linux-64), env `spot-run`, Python
# 3.12.13. Verified byte-for-byte against W7's content-addressed handoff.
EXPECTED_SHA256 = "2983d140941f13d223dad93bae71434663882f23f25f6717c3debe59d2711abe"
LOCK_FILENAME = "stage02_solver_lock.txt"
LOCK_ID = "spot.stage02.solver_lock.v1"

# The Stage-1 lock is a DIFFERENT environment and is not interchangeable with this one. Named
# so a run that supplies it fails with an explanation instead of a hash mismatch.
STAGE1_LOCK_FILENAME = "stage01_solver_lock.txt"

REFUSE_ABSENT = "solver_lock_not_supplied"
REFUSE_MISMATCH = "solver_lock_is_not_the_pinned_stage2_lock"

_HERE = os.path.dirname(os.path.abspath(__file__))
# the lock lives beside the package, not inside it: analysis/stage02_solver_lock.txt
DEFAULT_PATH = os.path.join(os.path.dirname(_HERE), LOCK_FILENAME)


class EnvLockError(ValueError):
    """The environment lock is missing or is not the pinned one. Refuse; never proceed."""

    def __init__(self, gate: str, message: str):
        super().__init__(f"[{gate}] {message}")
        self.gate = gate


def verify(path: Optional[str]) -> dict[str, Any]:
    """The lock, CHECKED against the pin, as one hashable block. Fail-closed."""
    if not path:
        raise EnvLockError(
            REFUSE_ABSENT,
            "no --env-lock was supplied. Every production invocation binds the Stage-2 solver "
            "lock into its run identity: a result whose environment is unrecorded cannot be "
            f"reproduced, and one whose environment is unbound can be re-attributed. The "
            f"pinned lock is {LOCK_FILENAME} ({EXPECTED_SHA256[:16]}...)")
    if not os.path.exists(path):
        raise EnvLockError(
            REFUSE_ABSENT,
            f"the --env-lock at {os.path.basename(path)!r} does not exist")

    actual = file_sha256(path)
    if actual != EXPECTED_SHA256:
        stage1 = os.path.basename(path) == STAGE1_LOCK_FILENAME
        hint = (" — that is the STAGE-1 lock. It is a valid solver lock for a DIFFERENT "
                "environment (conda scvi_gpu, Python 3.11.15, pyarrow 24.0.0); the two lanes "
                "run different environments and their locks are not interchangeable"
                if stage1 else "")
        raise EnvLockError(
            REFUSE_MISMATCH,
            f"the supplied --env-lock hashes to {actual[:16]}..., not the pinned Stage-2 lock "
            f"{EXPECTED_SHA256[:16]}...{hint}. A lock whose bytes are decided by whoever "
            "supplies them pins whatever the supplier wanted it to")

    return {
        "lock_id": LOCK_ID,
        "name": os.path.basename(path),
        "sha256": actual,                 # the FULL digest, in the run identity
        "expected_sha256": EXPECTED_SHA256,
        "verified": True,
        "status": "locked",
    }


def block(path: Optional[str]) -> dict[str, Any]:
    """Verify, and return the block the run identity binds. Raises on a missing/swapped lock."""
    return verify(path)
