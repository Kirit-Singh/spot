"""Bin-lock mutation tests (stage1-continuous-v3.0.1 bins amendment).

Pure (no h5ad): the frozen per-gene bins (stage01_bins_v3.csv) + the control-eligible pool
(stage01_control_eligible_pool.json) + the frozen keyed algorithm must reconstruct the committed
controls (stage01_controls_v3.csv) byte-for-byte; and flipping ANY one gene's bin must break that
reconstruction (i.e., fail verification).
"""
import json, csv, hashlib, os
from collections import defaultdict

D = os.path.join(os.path.dirname(__file__), "..", "app", "data")
ACT = ["CD69", "CD38", "MKI67", "TNFRSF9", "IL2RA"]
REG = json.load(open(os.path.join(D, "stage01_program_registry.json")))
ELIG = json.load(open(os.path.join(D, "stage01_control_eligible_pool.json")))["genes"]


def load_bins():
    binof, order = {}, []
    for r in csv.DictReader(open(os.path.join(D, "stage01_bins_v3.csv"))):
        binof[r["gene"]] = int(r["bin"]); order.append(r["gene"])
    return binof, order


def load_controls():
    d = defaultdict(list)
    for r in csv.DictReader(open(os.path.join(D, "stage01_controls_v3.csv"))):
        d[r["program_id"]].append((int(r["bin"]), r["control_symbol"]))
    return dict(d)


def measured_of(pid, present):
    for p in REG["programs"]:
        if p["program_id"] == pid:
            return [g for g in (p.get("panel_symbols") or []) if g in present]
    return [g for g in ACT if g in present] if pid == "activation_predictor" else []


def reconstruct(binof, order):
    gidx = {g: i for i, g in enumerate(order)}
    present = set(order)
    elig_by_bin = defaultdict(list)
    for g in ELIG:                       # ELIG is in var_names order
        elig_by_bin[binof[g]].append(g)
    out = defaultdict(list)
    for pid in load_controls():
        occ = sorted(set(binof[g] for g in measured_of(pid, present)))
        for b in occ:
            keyed = sorted(elig_by_bin[b],
                           key=lambda g: (hashlib.sha256(("12345|%s|%d|%s" % (pid, b, g)).encode()).hexdigest(), gidx[g]))[:50]
            out[pid] += [(b, g) for g in keyed]
    return dict(out)


def test_bins_artifact_reconstructs_committed_controls():
    binof, order = load_bins()
    assert reconstruct(binof, order) == load_controls()


def test_flipping_a_control_gene_bin_fails_verification():
    binof, order = load_bins(); committed = load_controls()
    victim = committed["treg_like"][0][1]          # a committed control gene
    binof[victim] = (binof[victim] + 7) % 25       # move it out of its bin
    assert reconstruct(binof, order) != committed


def test_flipping_a_marker_gene_bin_fails_verification():
    binof, order = load_bins(); committed = load_controls()
    present = set(order)
    marker = next(g for p in REG["programs"] if p["program_id"] == "treg_like"
                  for g in p["panel_symbols"] if g in present)
    binof[marker] = (binof[marker] + 7) % 25
    assert reconstruct(binof, order) != committed


def test_bins_artifact_shape():
    binof, order = load_bins()
    assert len(order) == len(set(order)) == 18130
    assert all(0 <= b <= 24 for b in binof.values())
