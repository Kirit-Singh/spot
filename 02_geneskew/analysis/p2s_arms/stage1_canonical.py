"""THE Stage-1 canonical score hash — REPRODUCED, and gated.

For one commit this hash was in the config as ``declared, not reproduced``: 25 formulations
of the recipe were tried and none matched, so binding it would have been binding a number
this lane could not check. The missing piece was the FIELD ORDER — a specific program order,
not the alphabetical one the earlier attempts assumed — and a trailing newline.

    primary field order: th1_like, th2_like, th17_like, tfh_like, treg_like, cd4_ctl_like,
                         th9_like, diff_naive, diff_activated, diff_memory, diff_checkpoint,
                         then cd4_ctl_like_score_actadj
    order rows by:       stable np.argsort(barcode)
    each row:            barcode \\t donor \\t condition \\t  f"{round(x,5):.5f}" per field
    body:                rows joined by "\\n", with a TRAILING "\\n"
    hash:                sha256(body)

Verified byte-for-byte against the 396k parquet:
    43c4296d5166740c334441a69df23bb440a073382bbe79628a3bb89e43d51316

This module RE-DERIVES the hash from the parquet at run time. It is NOT read from the file
and trusted, and it is NOT advisory: a score table that does not reproduce it is REFUSED. The
raw sha256 already gates the bytes; this gates the SCIENCE those bytes encode, in the exact
canonical form Stage-1 froze.
"""
from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from . import config
from . import disposition as D

# The field order is Stage-1's, restated here as this lane's OWN literal. A field order
# borrowed from the thing it checks is a field order nobody checked.
CANONICAL_FIELD_ORDER = (
    "th1_like_score", "th2_like_score", "th17_like_score", "tfh_like_score",
    "treg_like_score", "cd4_ctl_like_score", "th9_like_score", "diff_naive_score",
    "diff_activated_score", "diff_memory_score", "diff_checkpoint_score",
    "cd4_ctl_like_score_actadj",
)
ID_COLUMNS = ("barcode", "donor", "condition")
ROUND_DECIMALS = 5

# The expected canonical hash. Defaults to the pin; a test sets it to a fixture table's own
# computed value, exactly as prepare_inputs.PINS is set to the fixture bytes. The GATE
# MECHANISM is what is under test.
EXPECTED = config.STAGE1_SCORES_CANONICAL_SHA256


def canonical_scores_sha256(df: pd.DataFrame) -> str:
    """Re-derive Stage-1's canonical score hash from the parquet. The recipe, reimplemented."""
    missing = [c for c in ID_COLUMNS + CANONICAL_FIELD_ORDER if c not in df.columns]
    if missing:
        raise D.RefusalError(
            D.REFUSE_PROGRAM_SET_MISMATCH,
            f"the score table is missing column(s) {missing}; it cannot be the authoritative "
            "canonical table")

    order = np.argsort(df["barcode"].to_numpy(), kind="stable")
    d = df.iloc[order]

    ids = [d[c].astype(str).to_numpy() for c in ID_COLUMNS]
    vals = [d[f].to_numpy() for f in CANONICAL_FIELD_ORDER]

    rows = []
    for i in range(len(d)):
        row = [ids[0][i], ids[1][i], ids[2][i]]
        row += [f"{round(float(v[i]), ROUND_DECIMALS):.{ROUND_DECIMALS}f}" for v in vals]
        rows.append("\t".join(row))
    body = "\n".join(rows) + "\n"                 # the TRAILING newline is load-bearing
    return hashlib.sha256(body.encode()).hexdigest()


def verify(df: pd.DataFrame) -> dict[str, str]:
    """Gate the score table on its canonical hash. A mismatch is a REFUSAL, not a warning."""
    got = canonical_scores_sha256(df)
    if got != EXPECTED:
        raise D.RefusalError(
            D.REFUSE_INPUT_NOT_PINNED,
            f"the score table's canonical hash is {got[:16]}..., not the pinned "
            f"{EXPECTED[:16]}.... The raw bytes may match while "
            "the SCIENCE they encode does not — a re-rounded or re-ordered score table is a "
            "different table under the same name")
    return {"canonical_scores_sha256": got,
            "canonical_scores_sha256_rederived": True}
