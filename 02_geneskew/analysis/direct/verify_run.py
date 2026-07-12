"""STANDALONE independent verifier for a Stage-2 direct run.

INDEPENDENCE RULE (test-enforced): this module and its rule/evidence/source modules
import NOTHING from the generator — no selection, projection, ranking, disposition,
emission, run-id, trust, arms, masks, guides, donors, universe, contract or hashing
helper. The canonical rules are reimplemented from the written spec in:

    verify_rules      the screen contract (QC, projection, support, identity)
    verify_evidence   contributor evidence: citations RESOLVED, not asserted
    verify_source     source-native replay + contributor COMPLETENESS
    verify_tables     the full table reconstruction

It rebuilds the run from the INPUTS — raw public DE matrices, the sgRNA library,
the hash-pinned contributor manifest AND its source-record table, the Stage-1
artifacts — and then RECONSTRUCTS AND COMPARES:

    screen.parquet                 every column, dtype, null, disposition,
                                   arm state/tier/support, rank, modulation
    masks.parquet                  every estimate-specific masked gene
    contributing_guides.parquet    every resolved contributor row
    guide_support.parquet          every per-(slot, arm) value
    donor_support.parquet          every per-(split, arm) half
    axis.json                      re-derived from the Stage-1 registry
    Stage-1 gates                  re-derived from validation rows + gate spec
    ids / hashes / file inventory / verification.json agreement

Usage:  python -m direct.verify_run --run-dir <dir> --inputs-root <dir>
Exit 0 = every check passed; 1 = at least one failed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

# The verifier is standalone: it loads its own rule modules by path, never as part
# of the generator package.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import verify_rules as R  # noqa: E402  (independent reimplementation)
from verify_binding import (  # noqa: E402
    verify_evidence_domain,
    verify_identity,
    verify_release_gate,
    verify_replay_rules_bound,
    verify_stage1_gates,
    verify_support_contract,
)
from verify_evidence import resolve_contributors, scope_coverage  # noqa: E402
from verify_method import (  # noqa: E402
    expected_config_sha256,
    verify_eligibility_policy,
    verify_method_identity,
)
from verify_source import check_source_replay, decode, obs_column  # noqa: E402

# WHICH modalities are support, restated. In the released by-guide object the support
# modalities are the per-slot ones (``guide_*``); in the by-donors object every modality
# is a donor pair. This is the rule the run's own support accounting uses, and the
# verifier states it independently so the counts it derives are comparable.
GUIDE_MODALITY_PREFIX = "guide_"


EXPECTED_FILES = {
    "axis.json", "input_manifest.json", "gene_universe.json", "provenance.json",
    "verification.json", "screen.parquet", "masks.parquet",
    "contributing_guides.parquet", "guide_support.parquet", "donor_support.parquet",
}


class Report:
    def __init__(self):
        self.checks = []

    def check(self, name, ok, detail=""):
        self.checks.append((name, bool(ok), detail))
        return bool(ok)

    @property
    def failures(self):
        return [(n, d) for n, ok, d in self.checks if not ok]

    def render(self):
        out = [f"  [{'PASS' if ok else 'FAIL'}] {n}"
               + (f" — {d}" if d and not ok else "") for n, ok, d in self.checks]
        out += ["", f"{len(self.checks) - len(self.failures)}/{len(self.checks)} "
                    "checks passed"]
        return "\n".join(out)


# --------------------------------------------------------------------------- #
# Independent readers.
# --------------------------------------------------------------------------- #
def read_pooled(path, condition):
    import h5py
    with h5py.File(path, "r") as f:
        genes = decode(f["var/gene_ids"][:])
        obs = f["obs"]
        cond = obs_column(obs, "culture_condition").astype(object)
        sel = np.sort(np.where(cond == condition)[0])
        meta = {k: obs_column(obs, k)[sel] for k in
                ("target_contrast", "target_contrast_gene_name", "n_cells_target",
                 "n_guides", "ontarget_significant", "low_target_gex")}
        idx_name = obs.attrs.get("_index", "index")
        meta["released_estimate_id"] = np.array(decode(obs[idx_name][:]),
                                                dtype=object)[sel]
        log_fc = f["layers/log_fc"][sel, :].astype(np.float64)
    return genes, meta, log_fc


def derive_global_scopes(path, rep):
    """The GLOBAL all-condition pooled-main scope set, re-derived from the RAW DE obs.

    INDEPENDENT of the run: it reads the released obs metadata directly and rebuilds the
    full 9-field scope tuple (estimate, release key, target, namespace, symbol, released
    Ensembl, condition, null donor pair) by the same identity rule the verifier restates
    in ``verify_rules.target_identity``. Nothing here is read from the run's provenance,
    because the run's provenance is the thing under test.

    This is the ONLY check that can see a WHOLLY DROPPED scope. A missing scope has no
    manifest row, so no per-row check will ever look at it, and every row that IS present
    can be perfectly valid while the universe is quietly one scope smaller.
    """
    import h5py
    with h5py.File(path, "r") as f:
        obs = f["obs"]
        cond = obs_column(obs, "culture_condition").astype(object)
        target = obs_column(obs, "target_contrast")
        symbol = obs_column(obs, "target_contrast_gene_name")
        idx_name = obs.attrs.get("_index", "index")
        released = np.array(decode(obs[idx_name][:]), dtype=object)

    scopes, seen, dupes = set(), {}, []
    for i in range(len(cond)):
        if cond[i] is None:
            continue
        ident = R.target_identity(released[i], target[i], symbol[i])
        key = (str(target[i]), str(cond[i]))
        scope = ("main", "main", ident["released_estimate_id"], ident["target_id"],
                 ident["target_id_namespace"], ident["target_symbol"],
                 ident["released_target_ensembl"], str(cond[i]), None)
        # ANY second row for a (target, condition) is fatal, INCLUDING an identical one.
        # Only conflicting scopes used to be caught; an exact duplicate was absorbed by
        # the set and vanished. But the dense loader reads BOTH rows and scores both, so
        # the scope universe the manifest is matched against would be one smaller than
        # the release the run actually projects — and a manifest can then be "complete"
        # over a universe that is missing a scope. Two estimates that agree about their
        # metadata are still two estimates.
        if key in seen:
            dupes.append((key, "identical" if seen[key] == scope else "conflicting"))
        seen[key] = scope
        scopes.add(scope)
    rep.check("the released pooled-main scope universe is unique per "
              "(target, condition)", not dupes,
              f"{len(dupes)} duplicate scope key(s) (first: "
              f"{dupes[0] if dupes else None}); a collapsed duplicate silently shrinks "
              "the universe the contributor manifest is matched against")
    return scopes


def read_support_identities(path, condition, rep):
    """Which support estimates the release ships. METADATA ONLY — obs, never a layer.

    This reader used to load ``layers/log_fc`` for every guide slot and donor pair and
    then never use it. Leaving the effect vectors unused is not the same as not reading
    them: as long as the support matrices are in the verifier's hands, a future edit is
    one line away from projecting them, and the verifier would then be checking a claim
    the run is forbidden to make. Support carries no contributor evidence in this pass,
    so it has no mask, no projection and no tier — and the checker that enforces that
    should not be holding the numbers it forbids. ``var`` is not read either: the
    support gene axis never enters a score.

    ``n_guides`` is deliberately not read: in this release it is COPIED pooled metadata,
    not the estimate's own contributor count.

    A duplicate target within a modality FAILS the run. Silently keeping the first (the
    old behaviour) undercounts the released support estimates, and that count is bound
    into the support contract and into run_id.
    """
    import h5py
    out = {}
    with h5py.File(path, "r") as f:
        for mod_id in sorted(f["mod"].keys()):
            obs = f[f"mod/{mod_id}"]["obs"]
            cond = obs_column(obs, "culture_condition").astype(object)
            sel = np.sort(np.where(cond == condition)[0])
            tg = obs_column(obs, "target_contrast")[sel]
            idx_name = obs.attrs.get("_index", "index")
            rel = np.array(decode(obs[idx_name][:]), dtype=object)[sel]
            by_t, dupes = {}, []
            for i, t in enumerate(tg):
                if t is None:
                    continue
                key = str(t)
                if key in by_t:
                    dupes.append(key)
                    continue
                by_t[key] = {"released_estimate_id": str(rel[i])}
            rep.check(f"support modality {mod_id}: one released estimate per target",
                      not dupes,
                      f"{len(dupes)} duplicate target(s) (first: "
                      f"{dupes[0] if dupes else None}); a collapsed duplicate "
                      "undercounts the released support estimates")
            out[mod_id] = {"by_target": by_t}
    return out


def derive_observed_support(by_guide, by_donor):
    """COUNT the support estimates the release actually ships. Metadata only.

    The support contract declares how many guide-slot and donor-pair estimates it saw,
    and run_id hashes those numbers — but until now nothing counted them. Three
    mutually consistent copies of a fabricated total (in the contract, in the binding
    and in the evidence-domain block) agreed with each other perfectly and with the
    release not at all, and a run could report that it had accounted for every released
    support estimate while having enumerated none of them.

    Derived from the ALREADY-READ obs identities: no layer is opened, no gene axis is
    touched. Support carries no contributor evidence in this pass, so the verifier still
    never holds the numbers the run is forbidden to use — it only counts the rows.
    """
    guides = {m: v for m, v in by_guide.items()
              if m.startswith(GUIDE_MODALITY_PREFIX)}
    donors = dict(by_donor)
    n_guide = sum(len(v["by_target"]) for v in guides.values())
    n_donor = sum(len(v["by_target"]) for v in donors.values())
    return {
        "guide_modalities": sorted(guides),
        "donor_pairs": sorted(donors),
        "n_guide": n_guide,
        "n_donor": n_donor,
        "n_support": n_guide + n_donor,
    }


def read_library(path):
    df = pd.read_csv(path, low_memory=False)
    lib = {}
    for rec in df.to_dict("records"):
        t = str(rec.get("target_gene_id"))
        if t in ("nan", "None", ""):
            continue
        lib.setdefault(t, {})[str(rec["sgRNA"])] = rec
    return lib


def index_by_sha(root):
    out = {}
    for base, _d, files in os.walk(root):
        for fn in files:
            fp = os.path.join(base, fn)
            try:
                out.setdefault(R.sha256_file(fp), fp)
            except OSError:
                pass
    return out


def verify_manifest_canonical_hash(mdoc, gm, rep):
    """Re-derive, order-independently, the manifest hash that run_id bound."""
    canon = R.canonical_manifest_sha256(mdoc)
    rep.check("the canonical manifest hash re-derives from the manifest's content",
              canon == gm.get("canonical_sha256"),
              f"re-derived {canon!r}, run_id bound {gm.get('canonical_sha256')!r}")


# --------------------------------------------------------------------------- #
# Full reconstruction.
# --------------------------------------------------------------------------- #
def reconstruct(run_dir, inputs_root, rep, strict=False):
    prov = json.load(open(os.path.join(run_dir, "provenance.json")))
    binding = prov["run_binding"]
    cond = prov["analysis_condition"]

    present = {f for f in os.listdir(run_dir) if not f.startswith(".")}
    rep.check("file inventory: no extra or stale files", present == EXPECTED_FILES,
              f"extra={sorted(present - EXPECTED_FILES)} "
              f"missing={sorted(EXPECTED_FILES - present)}")

    by_sha = index_by_sha(inputs_root)
    inputs = {e["name"]: e for e in
              json.load(open(os.path.join(run_dir, "input_manifest.json")))["files"]}
    paths = {}
    for name, entry in inputs.items():
        paths[name] = by_sha.get(entry["sha256"])
        rep.check(f"input {name} present with bytes matching its pin",
                  paths[name] is not None)
    if any(v is None for v in paths.values()):
        return rep

    de = next(n for n in inputs if n.endswith(".h5ad"))
    bg = next(n for n in inputs if "by_guide" in n)
    bd = next(n for n in inputs if "by_donors" in n)
    sg = next(n for n in inputs if n.endswith(".csv"))
    reg_name = next(n for n in inputs if "registry" in n)

    genes, meta, log_fc = read_pooled(paths[de], cond)
    # METADATA ONLY. The support matrices are never opened: no dense read, no mask, no
    # projection — the verifier does not hold the numbers the run is forbidden to use.
    by_guide = read_support_identities(paths[bg], cond, rep)
    by_donor = read_support_identities(paths[bd], cond, rep)
    # ...but they ARE counted, so the run's declared support totals have something
    # independent to be wrong against.
    observed_support = derive_observed_support(by_guide, by_donor)
    library = read_library(paths[sg])
    registry = json.load(open(paths[reg_name]))

    # THE METHOD. Bound into run_id, therefore resealable — and therefore worth nothing
    # unless something says what it was supposed to be. This does.
    verify_method_identity(prov, binding, rep)
    verify_eligibility_policy(binding, rep)
    verify_release_gate(binding, rep)

    # ---- axis re-derived from the Stage-1 REGISTRY, not from axis.json ----
    axis_doc = json.load(open(os.path.join(run_dir, "axis.json")))
    programs = {p["program_id"]: p for p in registry["programs"]}
    pole_sign = {"high": 1, "low": -1}
    derived_axis = {}
    for p in ("A", "B"):
        prog = programs.get(axis_doc[p]["program_id"])
        rep.check(f"axis {p}: program is in the pinned Stage-1 registry",
                  prog is not None)
        if prog is None:
            return rep
        derived_axis[p] = {
            "panel": [str(g) for g in prog["panel_ensembl"]],
            "control": [str(g) for g in prog["control_ensembl"]],
            "sign": pole_sign[axis_doc[p]["direction"]],
        }
        rep.check(f"axis {p}: sign re-derives from the pole direction",
                  derived_axis[p]["sign"] == int(axis_doc[p]["sign"]))

    # ---- Stage-1 gates re-derived from validation rows + gate spec ----
    verify_stage1_gates(binding, by_sha, axis_doc, prov, cond, rep)

    # ---- gene universe: POOLED-MAIN ONLY ----
    # Only main is projected, so the universe is the pooled object's own axis. An
    # intersection with the by-guide/by-donor gene sets would discard pooled genes to
    # match matrices no score is ever taken over — and would change every primary score.
    universe = list(genes)
    uni_doc = json.load(open(os.path.join(run_dir, "gene_universe.json")))
    rep.check("the gene universe is the pooled-main axis, reconstructed exactly",
              uni_doc["gene_ids"] == universe)
    rep.check("the gene universe declares the pooled-main basis",
              uni_doc.get("basis") == "pooled_main_only",
              f"got {uni_doc.get('basis')!r}")
    rep.check("gene_universe_sha256 is the hash of the reconstruction",
              R.content_sha256(universe) == uni_doc["sha256"]
              == prov["gene_universe_sha256"])
    common = set(universe)
    for p in ("A", "B"):
        derived_axis[p]["panel"] = [g for g in derived_axis[p]["panel"] if g in common]
        derived_axis[p]["control"] = [g for g in derived_axis[p]["control"]
                                      if g in common]
        # axis.json must publish exactly the registry panel/control restricted to the
        # common universe -- re-derived from the REGISTRY, never trusted from axis.json
        rep.check(f"axis {p}: panel/control re-derive from the Stage-1 registry",
                  derived_axis[p]["panel"] == list(axis_doc[p]["panel"])
                  and derived_axis[p]["control"] == list(axis_doc[p]["control"]))

    # ---- contributor evidence, RESOLVED ----
    gm = binding["guide_manifest"]
    contrib = {}
    if gm.get("status") == "bound":
        # The BINDING deliberately holds no raw manifest hash (row order and
        # indentation are not science). The exact bytes are recorded in provenance
        # for audit, and the manifest is located by them — then its CANONICAL hash
        # is re-derived and compared against what run_id actually bound.
        audit = prov["guide_contract"]["contributor_manifest"]
        mpath = by_sha.get(audit.get("manifest_sha256"))
        rep.check("contributor manifest present with bytes matching its pin",
                  mpath is not None)
        if mpath is None:
            return rep
        mdoc = json.load(open(mpath))
        verify_manifest_canonical_hash(mdoc, gm, rep)
        shas = {s["name"]: s["sha256"] for s in mdoc["sources"]}
        tname = mdoc.get("source_record_table")
        tpath = by_sha.get(shas.get(str(tname), ""))
        rep.check("source-record table present with bytes matching its pin",
                  tpath is not None)
        if tpath is None:
            return rep
        tdoc = json.load(open(tpath))
        contrib = resolve_contributors(mdoc, tdoc, shas, rep)

        # THE global scope domain, re-derived from the RAW DE obs — not from the run.
        # A wholly dropped scope is invisible to every per-row check and dies only here.
        released_scopes = derive_global_scopes(paths[de], rep)
        coverage = scope_coverage(mdoc, released_scopes, rep)
        check_source_replay(mdoc, tdoc, tpath, shas, by_sha, rep, strict=strict,
                            coverage=coverage)
        verify_support_contract(prov, binding, observed_support, rep)
        verify_evidence_domain(prov, binding, coverage, observed_support, rep)
        verify_replay_rules_bound(gm, rep)

    ctx = dict(cond=cond, genes=genes, meta=meta, log_fc=log_fc, by_guide=by_guide,
               by_donor=by_donor, library=library, axis=derived_axis,
               universe=universe, contrib=contrib, run_dir=run_dir,
               # Re-derived, never read from the run: the config id comes from the
               # verifier's OWN restated policy, and the effect-source id from the bytes
               # of the DE object the verifier itself opened.
               expected_config_sha256=expected_config_sha256(),
               effect_source_sha256=R.sha256_file(paths[de]))
    rebuild_and_compare(ctx, prov, rep)
    verify_identity(prov, binding, axis_doc, run_dir, rep)
    return rep


def rebuild_and_compare(ctx, prov, rep):
    from verify_tables import compare_all  # split for module size
    compare_all(ctx, prov, rep)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Independent Stage-2 direct verifier")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--inputs-root", required=True)
    ap.add_argument("--strict-replay", action="store_true",
                    help="re-derive the source-native replay AND the contributor "
                         "completeness from the RAW source instead of checking the "
                         "pinned replay report. Expensive (the pinned release is "
                         "~44 GB): this is the release gate, not the "
                         "every-invocation default.")
    args = ap.parse_args(argv)

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    rep = Report()
    try:
        reconstruct(args.run_dir, args.inputs_root, rep, strict=args.strict_replay)
    except Exception as exc:                       # a crash IS a verification failure
        rep.check(f"verifier completed ({type(exc).__name__}: {exc})", False)

    print(rep.render())
    if rep.failures:
        print("\nFAILURES:")
        for name, detail in rep.failures:
            print(f"  - {name} {detail}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
