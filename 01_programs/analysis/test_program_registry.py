#!/usr/bin/env python3
"""Contract tests for the Stage-1 program registry (spot.stage01_program_registry.v1).

Runs under pytest OR as a plain script (`python3 test_program_registry.py`). Recomputes
coverage independently against the committed effect-universe crosswalk, so it does not
touch the network or the h5ad.
"""
import os, json, hashlib

HERE = os.path.dirname(os.path.abspath(__file__))
REGISTRY = os.path.join(HERE, "..", "app", "data", "stage01_program_registry.json")
EFFECT = os.path.join(HERE, "effect_universe_gwcd4i.json")
TH9_PANEL = ("IL9", "SPI1")


def _load():
    return json.load(open(REGISTRY)), json.load(open(EFFECT))


def _canon_sha(obj):
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()


def test_schema_version():
    reg, _ = _load()
    assert reg["schema_version"] == "spot.stage01_program_registry.v1"
    assert reg["seed"] == 12345
    assert len(reg["programs"]) == 12


def test_every_program_has_nonempty_control_genes():
    reg, _ = _load()
    for e in reg["programs"]:
        assert e["control_symbols"], f"{e['program_id']} has empty control_symbols"
        assert all(isinstance(g, str) and g for g in e["control_symbols"])
        # control_ensembl is aligned 1:1 with control_symbols
        assert len(e["control_ensembl"]) == len(e["control_symbols"])


def test_registry_sha256_recomputable_and_stable():
    reg, _ = _load()
    core = {k: v for k, v in reg.items() if k not in ("created_at", "registry_sha256")}
    assert _canon_sha(core) == reg["registry_sha256"], "registry_sha256 does not recompute"


def test_coverage_matches_recompute_against_effect_universe():
    reg, eff = _load()
    eff_set = set(eff["symbol_to_ensembl"])
    # the crosswalk itself is intact
    assert eff["provenance"]["n_genes"] == len(eff_set) == 10282
    assert _canon_sha_symbols(eff_set) == eff["symbols_sha256"]
    for e in reg["programs"]:
        pcov = sum(g in eff_set for g in e["panel_symbols"])
        ccov = sum(g in eff_set for g in e["control_symbols"])
        assert e["panel_coverage"]["in_effect_universe"] == pcov, e["program_id"]
        assert e["panel_coverage"]["total"] == len(e["panel_symbols"])
        assert e["control_coverage"]["in_effect_universe"] == ccov, e["program_id"]
        assert e["control_coverage"]["total"] == len(e["control_symbols"])
        # Ensembl IDs are present exactly for genes in the universe, null otherwise (never fabricated)
        for g, ens in zip(e["panel_symbols"], e["panel_ensembl"]):
            assert ens == eff["symbol_to_ensembl"].get(g), f"{e['program_id']} {g}"
        for g, ens in zip(e["control_symbols"], e["control_ensembl"]):
            assert ens == eff["symbol_to_ensembl"].get(g)


def _canon_sha_symbols(symbols):
    return hashlib.sha256("\n".join(sorted(symbols)).encode()).hexdigest()


def test_th9_stage2_reflects_il9_spi1_presence():
    reg, eff = _load()
    eff_set = set(eff["symbol_to_ensembl"])
    th9 = next(e for e in reg["programs"] if e["program_id"] == "th9_like")
    both_absent = all(g not in eff_set for g in TH9_PANEL)
    # ground truth for this released universe: both absent -> not selectable
    assert both_absent is True
    assert th9["stage2_selectable"] is (not both_absent)
    assert th9["stage2_selectable"] is False
    assert th9["stage2_unavailable_reason"] == "no_panel_genes_in_effect_universe"


def test_sensitivity_fields_not_stage2_selectable():
    reg, _ = _load()
    sens = [e for e in reg["programs"] if e["role"] == "sensitivity"]
    assert sens, "expected at least one sensitivity program"
    for e in sens:
        assert e["stage2_selectable"] is False, e["program_id"]
        assert e["stage2_unavailable_reason"] == "role_sensitivity_display_only"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as ex:
            failed += 1
            print(f"FAIL {fn.__name__}: {ex}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
