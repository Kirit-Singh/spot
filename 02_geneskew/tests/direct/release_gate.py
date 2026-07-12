"""The OPT-IN gate for tests that touch the real pinned release.

The ordinary ``tests/direct`` suite is synthetic-only, by construction. It must stay
that way on every host, including the ones where the release happens to be sitting on
local disk — and that is the whole point of this module.

A ``skipif(not os.path.exists(...))`` gate is NOT opt-in. It is opt-OUT by accident of
filesystem layout: on a host where the 44 GB pseudobulk and the 16 GB DE object exist,
it silently ENABLES a multi-minute, many-gigabyte read on every plain ``pytest`` run.
That is how a fixture suite quietly turns into a data job, and it is the reason the
gate is now an explicit flag that the machine's contents cannot flip:

    SPOT_STAGE2_RELEASE_TESTS=1 pytest tests/direct -m release

Both conditions must hold — the flag AND the file. The flag alone cannot conjure the
data; the data alone can no longer conjure the run.

These tests keep their scientific coverage: they are the only thing proving the replay
and identity rules hold against the artifact the adapter actually ships against. They
are meant to run on tcefold, where the cores, the RAM and the data belong.
"""
from __future__ import annotations

import os

import pytest

ENV_FLAG = "SPOT_STAGE2_RELEASE_TESTS"

# The pinned release, if this host happens to hold it. Presence is NOT permission.
RELEASE_DIR = os.path.expanduser("~/datasets/marson2025_gwcd4_perturbseq")
PSEUDOBULK = os.path.join(RELEASE_DIR, "GWCD4i.pseudobulk_merged.h5ad")   # ~44 GB
DE_STATS = os.path.join(RELEASE_DIR, "GWCD4i.DE_stats.h5ad")              # ~16 GB


def opted_in() -> bool:
    return os.environ.get(ENV_FLAG, "").strip().lower() in ("1", "true", "yes")


def needs(path: str):
    """Mark a test as a real-release integration test: opt-in flag AND the bytes.

    Order matters in the message: a developer who ran the suite on a host that holds
    the data should be told they did NOT accidentally skip a synthetic test.
    """
    if not opted_in():
        return pytest.mark.skip(
            reason=f"real-release integration test; set {ENV_FLAG}=1 to run it "
                   "(intended for tcefold — this reads tens of GB and is never part "
                   "of the synthetic fixture suite)")
    if not os.path.exists(path):
        return pytest.mark.skip(
            reason=f"{ENV_FLAG} is set but the pinned release is absent at {path}")
    return pytest.mark.release
