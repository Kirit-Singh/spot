"""S1-M3 re-audit: served-artifact stale-label scan with a DOCUMENTED carve-out.

No ACTIVE/rendered served artifact may carry a retired program display label (``Checkpoint-high`` /
``Checkpoint+``); the checkpoint program's active label is bare ``Checkpoint``. The single DELIBERATE,
documented exception is the frozen v2 legacy registry ``stage01_program_registry.json``: it is a
hash-frozen historical PRE-RENAME record (bound by ``stage01_current.json`` ``v2_registry.raw_sha256``,
status ``HISTORICAL_NOT_CURRENT``), is never UI-rendered, and editing it would break that frozen hash — so
it deliberately retains ``Checkpoint-high``. See the tiered-hash convention doc
(docs/superpowers/plans/2026-07-11-stage1-continuous-v3-lock.md). (docs/ references are out of scope: they
record the rename intentionally.)
"""
import glob
import hashlib
import json
import os

APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
DATA = os.path.join(APP, "data")
STALE_LABELS = ["Checkpoint-high", "Checkpoint+"]

# Documented, deliberate carve-out: filename -> reason. This artifact MAY carry the historical label.
ALLOWED_HISTORICAL = {
    "stage01_program_registry.json":
        "hash-frozen v2 legacy registry (bound by current.json v2_registry.raw_sha256; HISTORICAL_NOT_CURRENT); "
        "a pre-rename historical record, never rendered — editing it would break the frozen hash",
}


def _served_files():
    """Every served UI/data artifact: the app HTML pages + all served JSON/CSV under app/data/."""
    return (glob.glob(os.path.join(APP, "*.html"))
            + glob.glob(os.path.join(DATA, "*.json"))
            + glob.glob(os.path.join(DATA, "*.csv")))


def _hits():
    out = {}
    for p in _served_files():
        txt = open(p, encoding="utf-8", errors="replace").read()
        found = [s for s in STALE_LABELS if s in txt]
        if found:
            out[os.path.basename(p)] = found
    return out


def test_stale_label_only_in_the_documented_v2_carveout():
    hits = _hits()
    # 1) NO served artifact outside the documented carve-out may carry a retired label
    unexpected = {k: v for k, v in hits.items() if k not in ALLOWED_HISTORICAL}
    assert not unexpected, f"retired program label in non-carve-out served artifact(s): {unexpected}"
    # 2) the carve-out is the ONLY served artifact carrying it
    assert set(hits) <= set(ALLOWED_HISTORICAL)


def test_v2_carveout_is_a_real_frozen_historical_binding():
    """The carve-out is legitimate, not a silent gap: the v2 registry deliberately retains the historical
    label and is bound as HISTORICAL_NOT_CURRENT by its exact raw hash — scrubbing it breaks that binding."""
    v2 = os.path.join(DATA, "stage01_program_registry.json")
    assert any(s in open(v2).read() for s in STALE_LABELS), \
        "carve-out entry is stale: the v2 registry no longer holds the historical label"
    cur = json.load(open(os.path.join(DATA, "stage01_current.json")))
    assert cur["v2_registry"]["status"] == "HISTORICAL_NOT_CURRENT"
    assert cur["v2_registry"]["raw_sha256"] == hashlib.sha256(open(v2, "rb").read()).hexdigest()
