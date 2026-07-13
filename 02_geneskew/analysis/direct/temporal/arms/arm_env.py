"""The committed Stage-2 solver-lock, bound into every temporal bundle's run identity.

A temporal output that does not name the environment it was solved under is not
reproducible: the same code and the same Stage-1 release can still compute different bytes
under a different solver lock. So every bundle and the root inventory bind ``env_lock_sha256``
— the sha256 of the actual lock file's BYTES, read and hashed here, never a supplied hash.

  * PRODUCTION: the runner passes the lock PATH; the bytes are read and hashed
    (``verified_from_bytes = true``). A missing lock is refused — identity may not be
    omitted — and a swapped lock (bytes that do not match an expected sha) is refused.
  * FIXTURE: an EXPLICITLY SYNTHETIC lock (``is_synthetic = true``) may stand in, but it
    still carries an ``env_lock_sha256`` — a fixture may be synthetic, it may not be
    identity-less.

Only the basename and the hash are carried; the machine-local path never enters the artifact
(the portability firewall would refuse it, and it is not reproducible off this host).
Reuses the shared ``runid.env_lock_block`` so the bytes are hashed the ONE way Stage-2 does.
"""
from __future__ import annotations

from typing import Any, Optional

from ... import runid

ENV_LOCK_RULE_ID = "spot.stage02.temporal.arm.env_lock.stage2_solver_lock_sha256.v1"


class EnvLockError(ValueError):
    """The environment lock is missing or swapped. Refuse; a run's env identity is required."""


def env_lock_block(path: Optional[str] = None, *, expect_sha256: Optional[str] = None,
                   synthetic_sha256: Optional[str] = None) -> dict[str, Any]:
    """The env-lock identity for a temporal bundle. Bytes verified, path never carried.

    Exactly one of ``path`` (production) or ``synthetic_sha256`` (fixture) is used. Passing
    neither is a refusal: a bundle with no environment identity cannot be reproduced.
    """
    if synthetic_sha256 is not None:
        return {
            "env_lock_sha256": str(synthetic_sha256),
            "env_lock_name": "SYNTHETIC_FIXTURE_LOCK",
            "env_lock_verified_from_bytes": False,
            "env_lock_is_synthetic": True,
            "env_lock_rule_id": ENV_LOCK_RULE_ID,
        }
    shared = runid.env_lock_block(path)          # reads the actual bytes when path exists
    sha = shared.get("sha256")
    if not sha:
        raise EnvLockError(
            "production temporal output must bind the committed Stage-2 solver-lock; the "
            f"env-lock is missing ({shared.get('status')!r}). Identity may not be omitted")
    if expect_sha256 and sha != str(expect_sha256):
        raise EnvLockError(
            f"the env-lock bytes hash to {sha[:16]}, not the expected "
            f"{str(expect_sha256)[:16]} — a swapped lock is refused")
    return {
        "env_lock_sha256": sha,
        "env_lock_name": shared.get("name"),
        "env_lock_verified_from_bytes": True,
        "env_lock_is_synthetic": False,
        "env_lock_rule_id": ENV_LOCK_RULE_ID,
    }


def env_lock_nulls(block: dict[str, Any]) -> list[str]:
    """Why this env-lock is not a usable identity. Empty means bound.

    ``env_lock_sha256`` is required in EVERY mode (a fixture may be synthetic but not
    identity-less). A NON-synthetic (production) lock must additionally have been verified
    from the actual bytes — a production run may not take an env identity on trust.
    """
    block = block or {}
    bad: list[str] = []
    if not block.get("env_lock_sha256"):
        bad.append("env_lock_sha256")
    if block.get("env_lock_is_synthetic") is not True \
            and block.get("env_lock_verified_from_bytes") is not True:
        bad.append("env_lock_verified_from_bytes")
    return bad
