"""RE-KEY the pinned public gene sets from SYMBOL to ENSEMBL. Generator, not verifier.

The Reactome + GO-BP cache is symbol-keyed; the Stage-2 effect universe is Ensembl-keyed;
``genesets.load`` refuses the mismatch rather than joining at a loss. This is the step that
makes the pathway lane runnable, and it is the ONLY thing standing between the
Direct+temporal lanes (GO) and a complete Stage-2 run with pathways.

WHAT IT DOES
------------
For each set: map its members through the pinned crosswalk (``crosswalk.py`` — the
release's OWN ``var/gene_name`` -> ``var/gene_ids``), drop what cannot be mapped, and
RECORD the loss per set and in total, with a reason on every dropped symbol.

THE LOSS IS LARGE, AND IT IS NOT A MAPPING FAILURE
--------------------------------------------------
Roughly 40% of Reactome member-slots and 57% of GO-BP member-slots do not survive. That
number will alarm anybody who reads it without the decomposition, so here it is:

  * the effect universe is 10,282 genes — the genes this experiment actually TESTED. The
    gene sets span the genome (~12k Reactome symbols, ~31k GO-BP symbols, the latter
    including miRNAs and non-coding entries that were never in the assay);
  * a symbol that is not in the effect universe was NOT MEASURED in this run. Dropping it
    is not a mapping defect: it is the coverage the experiment has. Imputing it would be
    inventing a measurement;
  * the genuinely fixable part — genes that ARE measured but under a different symbol —
    was measured against a second pinned release artifact and is TINY: 7 in Reactome,
    19 in GO-BP. All 26 are recovered by the subordinate alias resolver.

So the honest statement is COVERAGE, not loss, and every set carries its own: how many
symbols it named, how many were measurable, and which were not. A pathway record can
therefore never look better-covered than it is — which is the whole reason the numbers are
carried through instead of being collapsed into a single "mapped" list.

Sets that map to FEWER THAN ``genesets.MIN_SET_SIZE`` genes are still EMITTED, with their
counts and their drop lists. Silently deleting them would hide which pathways this
experiment could never have said anything about.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
from typing import Any, Optional

from . import crosswalk, genesets
from .hashing import content_hash, file_sha256

BUILDER_ID = "spot.stage02.geneset_rekey.symbol_to_ensembl.v1"
SCHEMA_VERSION = genesets.SCHEMA_VERSION
CACHE_SCHEMA = "spot.stage02_geneset_cache_ensembl.v1"

# The two GMT layouts the cache actually ships. They differ, and a builder that assumed one
# would silently read the set NAME as its ID for the other.
GMT_LAYOUTS = {
    "reactome": {"id_col": 1, "name_col": 0},     # name <TAB> R-HSA-id <TAB> genes
    "go_bp": {"id_col": 0, "name_col": 1},        # GO:id <TAB> name    <TAB> genes
}


class GeneSetBuildError(ValueError):
    """The gene sets cannot be re-keyed. Refuse; never repair."""


def read_gmt(path: str, source: str) -> list[dict[str, Any]]:
    """One GMT, as (set_id, name, symbols). Layout is per-source and explicit."""
    if source not in GMT_LAYOUTS:
        raise GeneSetBuildError(
            f"no GMT layout is declared for source {source!r}; the two shipped files put "
            "the id in different columns, and guessing which is which would silently "
            f"read a set's NAME as its ID. Known: {sorted(GMT_LAYOUTS)}")
    layout = GMT_LAYOUTS[source]
    sets = []
    with open(path) as fh:
        for i, line in enumerate(fh, start=1):
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 3:
                continue
            set_id = parts[layout["id_col"]].strip()
            name = parts[layout["name_col"]].strip()
            if not set_id:
                raise GeneSetBuildError(f"{os.path.basename(path)}:{i} has no set id")
            symbols = [g.strip() for g in parts[2:] if g.strip()]
            sets.append({"set_id": set_id, "name": name, "symbols": symbols})
    if not sets:
        raise GeneSetBuildError(f"{os.path.basename(path)} contains no gene sets")
    return sets


def _loss_block(out: list[dict[str, Any]], key: str) -> dict[str, Any]:
    """The mapping loss for ONE namespace. Per set and in total."""
    n_src = sum(o["n_source_symbols"] for o in out)
    n_map = sum(o[f"n_{key}"] for o in out)
    losses = sorted(((1 - o[f"n_{key}"] / o["n_source_symbols"], o["set_id"])
                     for o in out if o["n_source_symbols"]), reverse=True)
    testable = [o for o in out if o[f"n_{key}"] >= genesets.MIN_SET_SIZE]
    worst_t = max(((1 - o[f"n_{key}"] / o["n_source_symbols"]), o["set_id"])
                  for o in testable) if testable else (None, None)
    return {
        "n_sets": len(out),
        "n_sets_with_zero_mapped_genes": sum(1 for o in out if not o[f"n_{key}"]),
        "n_sets_at_or_above_min_size": len(testable),
        "min_set_size": genesets.MIN_SET_SIZE,
        "n_source_member_slots": n_src,
        "n_mapped_member_slots": n_map,
        "n_dropped_member_slots": n_src - n_map,
        "total_loss_fraction": (round((n_src - n_map) / n_src, 6) if n_src else None),
        "worst_set_loss_fraction": (round(losses[0][0], 6) if losses else None),
        "worst_set_id": (losses[0][1] if losses else None),
        "worst_testable_set_loss_fraction": (round(worst_t[0], 6)
                                             if worst_t[0] is not None else None),
        "worst_testable_set_id": worst_t[1],
        "drop_reason_note": crosswalk.DROP_NOT_IN_UNIVERSE,
    }


def rekey(sets: list[dict[str, Any]], xws: dict[str, Any]) -> dict[str, Any]:
    """Map every set's members into BOTH namespaces. Drops counted per namespace.

    ``genes_target``  — members that were PERTURBED. This is what ranked-arm ENRICHMENT
                        tests membership against, because the arms rank targets. It is
                        also what CONVERGENCE selects members from, because a signature
                        only exists for a gene that was knocked down.
    ``genes_readout`` — members that were MEASURED. The signature VECTOR SPACE. Carried
                        because a reader must be able to see how much of the pathway the
                        assay could even observe.

    The two are different sets, they are computed from different crosswalks, and neither
    substitutes for the other (B1).
    """
    ro, tg = xws[crosswalk.NAMESPACE_READOUT], xws[crosswalk.NAMESPACE_TARGET]
    out = []
    for s in sets:
        m_ro = crosswalk.map_symbols(ro, s["symbols"])
        m_tg = crosswalk.map_symbols(tg, s["symbols"])
        n_src = m_tg["n_source_symbols"]
        out.append({
            "set_id": s["set_id"],
            "name": s["name"],
            # THE MEMBERSHIP the arms are ranked in
            "genes_target": m_tg["ensembl"],
            "n_genes_target": m_tg["n_mapped"],
            "n_dropped_target": m_tg["n_dropped"],
            "target_source_coverage": (round(m_tg["n_mapped"] / n_src, 6)
                                       if n_src else None),
            # the signature vector space's view of the same pathway
            "genes_readout": m_ro["ensembl"],
            "n_genes_readout": m_ro["n_mapped"],
            "n_dropped_readout": m_ro["n_dropped"],
            "readout_source_coverage": (round(m_ro["n_mapped"] / n_src, 6)
                                        if n_src else None),
            "n_source_symbols": n_src,
        })
    return {
        "sets": out,
        "mapping_loss": {
            crosswalk.NAMESPACE_TARGET: _loss_block(out, "genes_target"),
            crosswalk.NAMESPACE_READOUT: _loss_block(out, "genes_readout"),
        },
    }


def build(*, source: str, gmt: str, release: dict[str, Any], de_main: str,
          out_dir: str, sgrna: Optional[str] = None,
          effect_universe_sha256: Optional[str] = None,
          target_universe_sha256: Optional[str] = None) -> dict[str, Any]:
    """Re-key one source's GMT into BOTH namespaces; write a content-addressed bundle."""
    os.makedirs(out_dir, exist_ok=True)
    xws = crosswalk.build_both(de_main, sgrna)
    sets = read_gmt(gmt, source)
    result = rekey(sets, xws)

    # The LICENCE is carried through unchanged from the symbol cache's corrected
    # provenance — Reactome CC0-1.0, GO-BP CC-BY-4.0 dated. A re-keying does not change
    # who licensed the sets, and this must not silently regress the m3 fix.
    doc = {
        "schema_version": SCHEMA_VERSION,
        "release": {
            "source": source,
            "release_id": release["release_id"],
            "license": release["license"],
            "license_reference": release["license_reference"],
        },
        # THE POINT OF THE WHOLE EXERCISE
        "gene_id_namespace": genesets.ENSEMBL_GENE_ID,
        # BOTH universes, bound explicitly. A bundle that named only one could be joined
        # against the other without anything noticing — which is exactly what B1 was.
        "effect_universe_sha256": effect_universe_sha256,
        "target_universe_sha256": target_universe_sha256,
        "sets": result["sets"],
    }
    path = os.path.join(out_dir, f"{source}_ensembl.genesets.json")
    with open(path, "w") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)
        fh.write("\n")

    return {
        "source": source,
        "path": path,
        "sha256": file_sha256(path),
        # content-addressed on the SCIENCE (set ids + BOTH memberships), not on formatting
        "canonical_sha256": content_hash(
            [[s["set_id"], s["genes_target"], s["genes_readout"]]
             for s in sorted(result["sets"], key=lambda s: s["set_id"])]),
        "n_sets": len(result["sets"]),
        "gmt_sha256": file_sha256(gmt),
        "release": doc["release"],
        "mapping_loss": result["mapping_loss"],
        "crosswalk": {ns: crosswalk.provenance_block(xw) for ns, xw in xws.items()},
    }


def build_cache(*, cache_dir: str, de_main: str, out_dir: str,
                sgrna: Optional[str] = None,
                effect_universe_sha256: Optional[str] = None,
                target_universe_sha256: Optional[str] = None) -> dict[str, Any]:
    """Re-key EVERY lane of the symbol cache and emit the Ensembl cache + provenance."""
    with open(os.path.join(cache_dir, "provenance.json")) as fh:
        symbol_prov = json.load(fh)

    lanes = {}
    for source, lane in (("reactome", symbol_prov["lanes"]["reactome"]),
                         ("go_bp", symbol_prov["lanes"]["gobp"])):
        gmt = os.path.join(cache_dir, lane["files"]["canonical_gmt"]["name"])
        lanes[source] = build(
            source=source, gmt=gmt,
            release={"release_id": lane["release_id"],
                     "license": lane["license"],
                     "license_reference": lane["license_reference"]},
            de_main=de_main, out_dir=out_dir, sgrna=sgrna,
            effect_universe_sha256=effect_universe_sha256,
            target_universe_sha256=target_universe_sha256)

    prov = {
        "schema_version": CACHE_SCHEMA,
        "builder_id": BUILDER_ID,
        "created_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "identifier_namespace": genesets.ENSEMBL_GENE_ID,
        "rekeyed_from": {
            "cache": "geneset-cache (symbol-keyed)",
            "provenance_sha256": file_sha256(
                os.path.join(cache_dir, "provenance.json")),
            "identifier_namespace": "gene symbol",
        },
        "effect_universe_sha256": effect_universe_sha256,
        "target_universe_sha256": target_universe_sha256,
        "lanes": {k: {kk: vv for kk, vv in v.items() if kk != "crosswalk"}
                  for k, v in lanes.items()},
        "crosswalk": next(iter(lanes.values()))["crosswalk"],
    }
    path = os.path.join(out_dir, "provenance.json")
    with open(path, "w") as fh:
        json.dump(prov, fh, indent=2, sort_keys=True)
        fh.write("\n")
    prov["provenance_path"] = path
    return prov


def main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(
        description="Re-key the pinned gene-set cache from symbol to Ensembl")
    ap.add_argument("--cache-dir", required=True,
                    help="the symbol-keyed geneset cache (with its provenance.json)")
    ap.add_argument("--de-main", required=True,
                    help="GWCD4i.DE_stats.h5ad — the crosswalk AND the effect universe")
    ap.add_argument("--sgrna", default=None,
                    help="the pinned sgRNA library table, for the subordinate alias "
                         "resolver (in-universe symbols only; never overrides the primary)")
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args(argv)

    from . import identity, io_data
    from . import universe as uni

    gene_universe = uni.primary_universe(io_data.load_main_gene_ids(args.de_main))
    raw = io_data.load_main_identity_universe(args.de_main)
    by_cond = {c: {t: identity.resolve(r["released_estimate_id"], r["target_id"],
                                       r["target_symbol"], {})
                   for t, r in tg.items()} for c, tg in raw.items()}
    target_uni = uni.target_universe(by_cond)
    prov = build_cache(cache_dir=args.cache_dir, de_main=args.de_main,
                       out_dir=args.out_dir, sgrna=args.sgrna,
                       effect_universe_sha256=gene_universe["sha256"],
                       target_universe_sha256=target_uni["sha256"])
    print(json.dumps({
        "identifier_namespace": prov["identifier_namespace"],
        "effect_universe_sha256": prov["effect_universe_sha256"],
        "target_universe_sha256": prov["target_universe_sha256"],
        "crosswalk": {ns: {k: x[k] for k in
                           ("namespace", "primary_source", "n_rows", "n_primary_rows",
                            "n_alias_rows", "n_ambiguous_symbols", "n_universe_genes")}
                      for ns, x in prov["crosswalk"].items()},
        "lanes": {k: {"n_sets": v["n_sets"], "canonical_sha256": v["canonical_sha256"],
                      "license": v["release"]["license"],
                      "mapping_loss": v["mapping_loss"]}
                  for k, v in prov["lanes"].items()},
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
