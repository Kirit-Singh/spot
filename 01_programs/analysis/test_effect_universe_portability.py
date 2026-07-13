"""Release-hygiene checks for the Stage-2 effect-universe crosswalk.

The raw JSON contains provenance as well as the 10,282-gene scientific mapping. A
portable-path metadata reseal may move the raw artifact hash, but it must not move the
scientific projection protected here.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
EFFECT = HERE / "effect_universe_gwcd4i.json"
BASELINE = HERE / "stage2_bridge" / "PROTECTED_HASHES.json"


def _scientific_projection(effect: dict) -> dict:
    return {
        "n_genes": effect["provenance"]["n_genes"],
        "symbols_sha256": effect["symbols_sha256"],
        "symbol_to_ensembl": effect["symbol_to_ensembl"],
    }


def _sha(obj: dict) -> str:
    payload = json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def test_source_path_is_portable():
    effect = json.loads(EFFECT.read_text())
    source_path = effect["provenance"]["host_path"]
    assert source_path == "${SPOT_MARSON_DATA_ROOT}/GWCD4i.DE_stats.h5ad"
    for machine_fragment in ("/Users/", "/home/", "/mnt/", "tcedirector:", "tcefold:"):
        assert machine_fragment not in source_path


def test_scientific_projection_is_frozen_separately_from_provenance():
    effect = json.loads(EFFECT.read_text())
    baseline = json.loads(BASELINE.read_text())
    assert len(effect["symbol_to_ensembl"]) == effect["provenance"]["n_genes"] == 10282
    assert _sha(_scientific_projection(effect)) == baseline[
        "effect_universe_scientific_sha256"
    ]


def test_scientific_projection_detects_mapping_mutation():
    effect = json.loads(EFFECT.read_text())
    expected = _sha(_scientific_projection(effect))
    effect["symbol_to_ensembl"]["AAAS"] = "ENSG_FORGED"
    assert _sha(_scientific_projection(effect)) != expected
