"""THE SYMBOL -> ENSEMBL CROSSWALK. Built from the release's own effect universe.

WHY THIS EXISTS
---------------
The pinned public gene sets (Reactome, GO-BP) are keyed by gene SYMBOL. The Stage-2 effect
universe is keyed by ENSEMBL gene id. ``genesets.load`` refuses a symbol-keyed bundle
rather than joining at a loss — a symbol set tested against an Ensembl universe overlaps in
almost nothing, and the "no enrichment" it returns is a failed join wearing the clothes of
a null result. So the sets must be RE-KEYED before they can be used, and the re-keying
needs an authority.

THE AUTHORITY IS THE RELEASE ITSELF
-----------------------------------
``GWCD4i.DE_stats.h5ad`` ships ``var/gene_ids`` (Ensembl) alongside ``var/gene_name``
(symbol), for exactly the genes the effect universe is made of. That IS the crosswalk: it
comes from the same object the effect vectors come from, it is pinned by the same sha256,
and it needs no external database, no download and no version to drift.

Nothing here hand-maps a gene, and nothing here reaches for an unpinned reference. A
symbol this crosswalk cannot resolve is DROPPED and COUNTED — never guessed.

AMBIGUITY IS FAIL-CLOSED
------------------------
A symbol that names more than one Ensembl id is UNRESOLVED, not resolved-by-preference.
There is no "pick the first", no "pick the lowest id", no "pick the one with more
evidence": any such rule is a coin-flip wearing a method's clothes, and it would silently
put a gene in a pathway it does not belong to. Ambiguous symbols are recorded by name.

(For the pinned GWCD4i release this branch is EMPTY: the effect universe is a clean 1:1
bijection — 10,282 unique Ensembl ids, 10,282 unique symbols, zero collisions in either
direction. The rule exists because the NEXT release may not be so tidy, and a rule that
only appears when it is needed is a rule nobody wrote.)

THE SECONDARY ALIAS RESOLVER (optional, subordinate, recorded)
--------------------------------------------------------------
A gene set may name a gene by an ALIAS the DE object does not use — the gene IS measured,
under a different symbol. Those are real genes being thrown away for a naming reason.

The sgRNA library table (``sgrna_library_metadata.suppl_table.csv``) is a SECOND pinned
artifact of the SAME release, carrying ``target_gene_name`` -> ``target_gene_id``. It is
used ONLY as a subordinate resolver, and only when all of these hold:

  * the PRIMARY crosswalk cannot resolve the symbol (it never overrides the primary);
  * the library maps it unambiguously (a symbol naming two ids is refused here too);
  * the id it maps to is ALREADY IN the effect universe (so it can never introduce a gene
    the run did not measure).

Every recovery is recorded by name. For the pinned release this recovers 26 genes
(7 Reactome, 19 GO-BP) that would otherwise have been dropped as unmappable. It cannot
add a gene, only re-attach a measured one to the name a pathway happens to call it.
"""
from __future__ import annotations

import csv
import os
from typing import Any, Optional

from .hashing import content_hash, file_sha256
from .io_data import _decode

CROSSWALK_ID = "spot.stage02.symbol_to_ensembl.de_stats.v2"

# --------------------------------------------------------------------------- #
# TWO NAMESPACES, TWO UNIVERSES. This is the B1 fix, and it is a SCIENTIFIC one.
#
# The DE object carries two different gene populations, and they are NOT the same set:
#
#   READOUT  (var: gene_ids / gene_name)              10,282 genes — what was MEASURED.
#            The columns of the effect matrix. This is the space a signature VECTOR
#            lives in, and the space a cosine similarity is taken over.
#
#   TARGET   (obs: target_contrast / target_contrast_gene_name)
#            11,526 genes — what was PERTURBED. The rows. This is the space the arms
#            RANK, and therefore the space a ranked-arm enrichment tests membership in.
#
# Only 9,497 targets are also readout genes. **2,029 perturbed targets are not in the
# readout universe at all.** Building gene-set membership against the readout universe —
# which is what v1 did — silently made those 2,029 targets ineligible to be a member of
# ANY pathway: they could be ranked at the very top of an arm and still never register as
# a hit. That is a systematic false-negative, and it is invisible in the output, because
# a gene that is not a member simply is not a member.
#
# So there are two crosswalks, each with its OWN authority, and each scoped to its own
# universe. They are NOT unioned: three symbols (IL9R, PAXX, VAMP7) legitimately resolve
# to a DIFFERENT Ensembl id in the two namespaces — a real annotation difference between
# the var and obs axes of the same object — and collapsing them would force a false choice
# between two correct answers.
# --------------------------------------------------------------------------- #
NAMESPACE_READOUT = "de_readout"
NAMESPACE_TARGET = "perturbation_target"
NAMESPACES = (NAMESPACE_READOUT, NAMESPACE_TARGET)

PRIMARY_SOURCE = {
    NAMESPACE_READOUT: "GWCD4i.DE_stats.h5ad:var(gene_name->gene_ids)",
    NAMESPACE_TARGET:
        "GWCD4i.DE_stats.h5ad:obs(target_contrast_gene_name->target_contrast)",
}
UNIVERSE_ROLE = {
    NAMESPACE_READOUT: "signature_vector_space_and_effect_matrix_columns",
    NAMESPACE_TARGET: "ranked_and_perturbed_population_gene_set_membership",
}
ALIAS_SOURCE = "sgrna_library_metadata.suppl_table.csv:(target_gene_name->target_gene_id)"

# THE RULES, as ids. Stated once, above; an artifact carries the id, not the paragraph.
AMBIGUITY_RULE_ID = "spot.stage02.crosswalk.ambiguity_rule.unresolved_never_guessed.v1"
ALIAS_RULE_ID = "spot.stage02.crosswalk.alias_rule.subordinate_in_universe_only.v1"

# Drop reasons. A dropped symbol always says WHY.
DROP_NOT_IN_UNIVERSE = "symbol_not_in_the_effect_universe"
DROP_AMBIGUOUS = "symbol_names_more_than_one_ensembl_id"
DROP_REASONS = (DROP_NOT_IN_UNIVERSE, DROP_AMBIGUOUS)


class CrosswalkError(ValueError):
    """The crosswalk cannot be built or trusted. Refuse; never repair."""


def _var_columns(h5ad_path: str) -> tuple[list[str], list[str]]:
    """``var/gene_ids`` and ``var/gene_name``. var ONLY — no dense layer is touched."""
    import h5py

    with h5py.File(h5ad_path, "r") as fh:
        var = fh["var"]
        for col in ("gene_ids", "gene_name"):
            if col not in var:
                raise CrosswalkError(
                    f"{os.path.basename(h5ad_path)} has no var/{col}; without both "
                    "gene_ids and gene_name the release carries no crosswalk and one "
                    "must not be invented")
        return _decode(var["gene_ids"][:]), _decode(var["gene_name"][:])


def _obs_columns(h5ad_path: str) -> tuple[list[str], list[str]]:
    """``obs/target_contrast`` and ``obs/target_contrast_gene_name``. obs ONLY.

    The PERTURBATION-TARGET namespace: what the release actually knocked down, and the
    population the arms rank. It is a different gene set from the readout axis, and the
    release names it separately — so this is its own crosswalk, not a view of the other.
    """
    import h5py

    from .io_data import read_categorical

    with h5py.File(h5ad_path, "r") as fh:
        obs = fh["obs"]
        for col in ("target_contrast", "target_contrast_gene_name"):
            if col not in obs:
                raise CrosswalkError(
                    f"{os.path.basename(h5ad_path)} has no obs/{col}; the perturbation-"
                    "target namespace cannot be built and must not be inferred from the "
                    "readout axis — they are different gene populations")
        ids = read_categorical(obs["target_contrast"])
        names = read_categorical(obs["target_contrast_gene_name"])
    return [str(x) for x in ids], [str(x) for x in names]


def _alias_rows(csv_path: str) -> dict[str, set]:
    """symbol -> {ensembl}, from the pinned sgRNA library table."""
    out: dict[str, set] = {}
    with open(csv_path) as fh:
        for row in csv.DictReader(fh):
            sym = (row.get("target_gene_name") or "").strip()
            ens = (row.get("target_gene_id") or "").strip()
            if sym and ens.startswith("ENSG"):
                out.setdefault(sym, set()).add(ens)
    return out


def build(de_main: str, sgrna: Optional[str] = None,
          namespace: str = NAMESPACE_READOUT) -> dict[str, Any]:
    """The pinned symbol -> id crosswalk for ONE namespace, scoped to ITS universe.

    ``namespace=de_readout``          var: what was MEASURED (signature vector space).
    ``namespace=perturbation_target`` obs: what was PERTURBED (the ranked population, and
                                      therefore the space gene-set membership must be
                                      tested in for a ranked-arm enrichment). See the
                                      module docstring: getting this wrong made 2,029
                                      perturbed targets permanently ineligible to be a
                                      member of any pathway.
    """
    if namespace not in NAMESPACES:
        raise CrosswalkError(
            f"unknown namespace {namespace!r}; expected one of {list(NAMESPACES)}")

    if namespace == NAMESPACE_READOUT:
        gene_ids, gene_names = _var_columns(de_main)
        what = "var/gene_ids", "var/gene_name"
    else:
        gene_ids, gene_names = _obs_columns(de_main)
        what = "obs/target_contrast", "obs/target_contrast_gene_name"
    if len(gene_ids) != len(gene_names):
        raise CrosswalkError(
            f"{what[0]} ({len(gene_ids)}) and {what[1]} ({len(gene_names)}) are "
            "different lengths; they do not describe the same genes")

    universe = set(gene_ids)

    # ---- PRIMARY: the effect universe's own naming ----
    by_symbol: dict[str, set] = {}
    for ens, sym in zip(gene_ids, gene_names):
        if sym:
            by_symbol.setdefault(str(sym), set()).add(str(ens))

    mapping: dict[str, str] = {}
    ambiguous: dict[str, list[str]] = {}
    for sym, ids in by_symbol.items():
        if len(ids) == 1:
            mapping[sym] = next(iter(ids))
        else:
            # FAIL-CLOSED. A coin-flip here puts a gene in a pathway it is not in.
            ambiguous[sym] = sorted(ids)

    primary_n = len(mapping)

    # ---- SECONDARY: the subordinate, in-universe-only alias resolver ----
    aliases: dict[str, str] = {}
    alias_ambiguous: dict[str, list[str]] = {}
    if sgrna:
        for sym, ids in _alias_rows(sgrna).items():
            if sym in mapping or sym in ambiguous:
                continue                      # the primary decides; this never overrides
            if len(ids) > 1:
                alias_ambiguous[sym] = sorted(ids)
                continue
            ens = next(iter(ids))
            if ens in universe:               # it can re-attach a MEASURED gene, never add
                aliases[sym] = ens
        mapping.update(aliases)

    return {
        "crosswalk_id": CROSSWALK_ID,
        "namespace": namespace,
        "universe_role": UNIVERSE_ROLE[namespace],
        "ambiguity_rule_id": AMBIGUITY_RULE_ID,
        "alias_rule_id": ALIAS_RULE_ID,
        "primary_source": PRIMARY_SOURCE[namespace],
        "primary_source_sha256": file_sha256(de_main),
        "alias_source": (ALIAS_SOURCE if sgrna else None),
        "alias_source_sha256": (file_sha256(sgrna) if sgrna else None),
        "n_universe_genes": len(universe),
        "n_rows": len(mapping),
        "n_primary_rows": primary_n,
        "n_alias_rows": len(aliases),
        "n_ambiguous_symbols": len(ambiguous),
        "ambiguous_symbols": {k: ambiguous[k] for k in sorted(ambiguous)},
        "n_alias_ambiguous_symbols": len(alias_ambiguous),
        "alias_symbols_recovered": {k: aliases[k] for k in sorted(aliases)},
        "mapping": mapping,
        "universe": universe,
        "canonical_sha256": content_hash(
            [[s, mapping[s]] for s in sorted(mapping)]),
    }


def build_both(de_main: str, sgrna: Optional[str] = None) -> dict[str, Any]:
    """BOTH crosswalks. They are kept separate, and deliberately NOT unioned.

    Three symbols (IL9R, PAXX, VAMP7) resolve to a different Ensembl id on the var axis
    than on the obs axis — a real annotation difference inside the same object. A union
    would have to pick one, and picking would put a gene in a pathway under an id the
    computation that reads it does not use. Each namespace keeps its own authority.
    """
    return {ns: build(de_main, sgrna, namespace=ns) for ns in NAMESPACES}


def provenance_block(xw: dict[str, Any]) -> dict[str, Any]:
    """What the crosswalk IS, for the cache's provenance. No mapping table inlined."""
    return {k: v for k, v in xw.items() if k not in ("mapping", "universe")}


def map_symbols(xw: dict[str, Any], symbols: list[str]) -> dict[str, Any]:
    """Re-key one set's members. Unmappable symbols are DROPPED and COUNTED, with a why.

    Two distinct symbols can legitimately resolve to the SAME Ensembl id (a set that names
    a gene by both its primary symbol and an alias). The result is de-duplicated: a gene
    listed twice would be double-counted by every statistic taken over the set.
    """
    mapping, ambiguous = xw["mapping"], xw["ambiguous_symbols"]
    mapped: dict[str, str] = {}
    dropped: list[dict[str, str]] = []
    for sym in symbols:
        ens = mapping.get(sym)
        if ens is not None:
            mapped.setdefault(ens, sym)
            continue
        dropped.append({
            "symbol": sym,
            "reason": (DROP_AMBIGUOUS if sym in ambiguous else DROP_NOT_IN_UNIVERSE),
        })
    return {
        "ensembl": sorted(mapped),
        "n_source_symbols": len(set(symbols)),
        "n_mapped": len(mapped),
        "n_dropped": len(dropped),
        "dropped": dropped,
        "n_collapsed_by_alias": max(0, len(set(symbols)) - len(dropped) - len(mapped)),
    }
