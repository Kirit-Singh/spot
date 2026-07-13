"""PINNED public gene sets, bound to the release they came from AND to the universe.

A pathway result is meaningless without three things, and each is a separate refusal:

  * WHICH gene sets. "Reactome" is not a version. Pathway membership changes between
    releases — sets are split, merged, renamed and retired — so an enrichment computed
    against one release is not comparable with one computed against another, and a result
    that names no release cannot be reproduced or contested. The release id AND the raw
    sha256 of the file are pinned, and the file on disk must hash to the pin.

  * WHICH NAMESPACE. A gene set of HGNC symbols tested against an Ensembl-keyed effect
    universe silently overlaps in almost nothing, and "no enrichment" is the answer you
    get. That is not a null result, it is a failed join wearing one. The namespace is
    declared and checked.

  * WHICH UNIVERSE. An enrichment statistic is a statement about a set RELATIVE TO a
    background. Test the same set against a different background and you get a different
    number, so the gene-set bundle is BOUND to the exact effect universe it was computed
    against (``effect_universe_sha256``). A bundle bound to another run's universe is
    refused rather than silently reused.

THE SETS ARE NOT THE UNIVERSE. Genes in a set that are absent from the effect universe
were never measurable in this run: they are reported as coverage, never imputed, and
never counted as evidence of absence.

The real bundle (pinned public Reactome + GO-BP releases) is being acquired separately.
Nothing here knows which source it is: the loader is parameterised by release + namespace
+ universe binding, and the fixture bundle is a bundle like any other.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from .hashing import content_hash, file_sha256

SCHEMA_VERSION = "spot.stage02_gene_sets.v1"

# The namespace the effect universe is keyed by. A set in any other namespace is refused
# rather than joined at a loss.
ENSEMBL_GENE_ID = "ensembl_gene_id"
ALLOWED_NAMESPACES = (ENSEMBL_GENE_ID,)

# Sources we know how to name. An unknown source is not fatal — the bundle still pins its
# release and hash — but it must SAY what it is.
KNOWN_SOURCES = ("reactome", "go_bp", "fixture")

# --------------------------------------------------------------------------- #
# LICENCE, per source (m3). A licence is not a footnote: it decides what may be
# redistributed and how it must be attributed, and recording the wrong one is a
# compliance claim we cannot stand behind.
#
# REACTOME IS CC0 — NOT CC BY 4.0. The Reactome database data and files derived from it
# are released under CC0 1.0 (https://reactome.org/license). It was recorded as
# "CC BY 4.0" and that is simply wrong. The expected licence is ENFORCED below rather
# than merely documented, because a bundle that arrives asserting the wrong licence is
# exactly the artifact that would be cited later.
#
# GO stays CC BY 4.0 — and it must name a DATED release: "GO" is not a version any more
# than "Reactome" is, and a CC BY attribution that cannot name what it is attributing is
# not an attribution.
# --------------------------------------------------------------------------- #
SOURCE_LICENSE = {
    "reactome": "CC0-1.0",
    "go_bp": "CC-BY-4.0",
    "fixture": "not_applicable_synthetic",
}
SOURCE_LICENSE_REFERENCE = {
    "reactome": "https://reactome.org/license",
    "go_bp": "http://geneontology.org/docs/go-citation-policy/",
    "fixture": None,
}
# Sources whose release_id must carry a date (YYYY-MM-DD or YYYY-MM): an undated release
# id cannot identify the thing being attributed.
REQUIRE_DATED_RELEASE = ("go_bp",)
_DATED_RE = re.compile(r"\d{4}-\d{2}(-\d{2})?")

# The licence recorded in error, kept here BY NAME so a bundle carrying it is refused
# with a message that says what happened rather than a generic mismatch.
RETIRED_LICENSE_CLAIMS = {("reactome", "CC-BY-4.0"): (
    "Reactome database data and derived files are CC0 1.0, not CC BY 4.0. The bundle is "
    "asserting a licence Reactome does not use; see https://reactome.org/license")}


def normalize_license(value: Any) -> str:
    """``CC BY 4.0`` / ``cc-by-4.0`` / ``CC_BY_4.0`` all name the same licence."""
    return re.sub(r"[\s_]+", "-", str(value or "").strip()).upper().replace("--", "-")

# A set too small to say anything, or so large it says nothing. Both are reported, and
# both are excluded from convergence claims rather than silently kept.
MIN_SET_SIZE = 3
MAX_SET_SIZE = 500

# --------------------------------------------------------------------------- #
# B4 — COVERAGE GOVERNANCE. A PROSPECTIVE disposition, frozen BEFORE any result was
# looked at. This paragraph is the pre-registration; the constants below are the rule.
#
# THE PROBLEM. Size is not coverage. "Testable" required only 3-500 mapped genes, so a
# 1,200-gene pathway that retained THREE of them — 0.25% of the genes it is named for —
# could be ranked beside a pathway with 90% of its genes present, and nothing in the
# ranking said which was which. The enrichment statistic is perfectly well defined on
# those three genes; it simply is not a statement about that pathway. Disclosing coverage
# in a column and then ranking on it anyway is disclosure without governance.
#
# THE RULE. A set whose TARGET-namespace source coverage is below MIN_SOURCE_COVERAGE is
# DESCRIPTIVE_ONLY: it is still computed, still emitted, still carries its full statistic
# and leading edge — and it is EXCLUDED FROM HEADLINE RANKING. It is not deleted, because
# a pathway missing from the table is indistinguishable from one that was tested and found
# nothing; and it is not silently ranked, because a number computed on 0.25% of a pathway
# is not evidence about that pathway.
#
# THE THRESHOLD. 0.50 — a pathway must retain at least HALF the genes it is named for
# before a ranking is allowed to speak for it. Chosen before results, on the principle
# that a statistic which speaks for a pathway should be computed on most of it. It is a
# GOVERNANCE threshold, not a significance one: nothing here is calibrated, and the
# emitted disposition is a permission, never a p-value.
# --------------------------------------------------------------------------- #
COVERAGE_POLICY_ID = "spot.stage02.pathway.coverage_governance.prospective.v1"
MIN_SOURCE_COVERAGE = 0.50
DISPOSITION_RANKABLE = "rankable"
DISPOSITION_DESCRIPTIVE_ONLY = "descriptive_only_low_source_coverage"
DISPOSITION_UNKNOWN_COVERAGE = "descriptive_only_source_coverage_unknown"
DISPOSITIONS = (DISPOSITION_RANKABLE, DISPOSITION_DESCRIPTIVE_ONLY,
                DISPOSITION_UNKNOWN_COVERAGE)
COVERAGE_NAMESPACE = "perturbation_target"   # the space the statistic is computed in


def coverage_disposition(target_source_coverage: Optional[float]) -> dict[str, Any]:
    """May a ranking speak for this pathway? Decided by coverage, before any result.

    Unknown coverage is DESCRIPTIVE-ONLY, not rankable. A bundle that cannot say how much
    of a pathway it retained has not earned a headline rank by failing to answer.
    """
    if target_source_coverage is None:
        disposition = DISPOSITION_UNKNOWN_COVERAGE
    elif target_source_coverage >= MIN_SOURCE_COVERAGE:
        disposition = DISPOSITION_RANKABLE
    else:
        disposition = DISPOSITION_DESCRIPTIVE_ONLY
    return {
        "coverage_disposition": disposition,
        "headline_rankable": disposition == DISPOSITION_RANKABLE,
        "coverage_policy_id": COVERAGE_POLICY_ID,
        "min_source_coverage": MIN_SOURCE_COVERAGE,
        "coverage_namespace": COVERAGE_NAMESPACE,
    }


class GeneSetError(ValueError):
    """The gene-set bundle is not usable. Refuse; never repair."""


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise GeneSetError(msg)


def load(path: Optional[str], effect_universe: Optional[list[str]] = None,
         effect_universe_sha256: Optional[str] = None,
         target_universe: Optional[list[str]] = None,
         target_universe_sha256: Optional[str] = None) -> Optional[dict[str, Any]]:
    """Load, pin and BIND a gene-set bundle against BOTH universes.

    TWO UNIVERSES, BOUND SEPARATELY (B1)
    ------------------------------------
    ``effect_universe``  the DE READOUT genes — what was MEASURED. The signature vector
                         space; the columns of the effect matrix.
    ``target_universe``  the PERTURBATION TARGETS — what was KNOCKED DOWN. The population
                         the arms RANK, and therefore the space a ranked-arm enrichment
                         must test gene-set membership in.

    They are not the same set. 11,526 targets, 10,282 readout genes, 9,497 in common:
    **2,029 perturbed targets are not readout genes at all.** Testing membership against
    the readout universe — which is what this did — made those 2,029 targets permanently
    ineligible to be a member of ANY pathway. They could top an arm's ranking and still
    never count as a hit, and nothing in the output would say so.

    When only one universe is supplied it is used for both, and the binding records that
    (``single_universe_binding``) rather than pretending two were checked.

    An absent bundle is a STATE, not an error: the pathway layer is simply unavailable,
    and every pathway artifact says so. It is never quietly skipped.
    """
    if not path:
        return None

    with open(path) as fh:
        doc = json.load(fh)
    _require(isinstance(doc, dict),
             "gene-set bundle: top level must be an object")
    _require(str(doc.get("schema_version")) == SCHEMA_VERSION,
             f"gene-set bundle: schema_version must be exactly {SCHEMA_VERSION!r}, got "
             f"{doc.get('schema_version')!r}")

    release = doc.get("release") or {}
    source = str(release.get("source", ""))
    release_id = str(release.get("release_id", ""))
    _require(source in KNOWN_SOURCES,
             f"gene-set bundle: release.source must be one of {list(KNOWN_SOURCES)}, "
             f"got {source!r}; a bundle that will not say what it is cannot be cited")
    _require(bool(release_id),
             "gene-set bundle: release.release_id is required. 'Reactome' is not a "
             "version — pathway membership changes between releases, so an enrichment "
             "computed against an unnamed release cannot be reproduced or contested")

    # ---- THE LICENCE (m3). Declared, correct, and referenced — or refused. ----
    expected = SOURCE_LICENSE[source]
    declared_license = normalize_license(release.get("license"))
    _require(bool(declared_license),
             f"gene-set bundle: release.license is required for source {source!r} "
             f"(expected {expected!r}). A redistributable artifact that will not say "
             "what licence it carries cannot be redistributed")
    retired = RETIRED_LICENSE_CLAIMS.get((source, declared_license))
    _require(retired is None, f"gene-set bundle: {retired}")
    _require(declared_license == normalize_license(expected),
             f"gene-set bundle: source {source!r} is licensed {expected!r}, but the "
             f"bundle declares {declared_license!r}. The licence decides what may be "
             "redistributed and how it must be attributed; recording the wrong one is a "
             "compliance claim nobody can stand behind")
    reference = SOURCE_LICENSE_REFERENCE[source]
    if reference is not None:
        _require(str(release.get("license_reference", "")).strip() == reference,
                 f"gene-set bundle: release.license_reference must cite {reference!r} "
                 f"for source {source!r}; a licence nobody can look up is not a licence")

    # ...and a DATED release where attribution needs one.
    if source in REQUIRE_DATED_RELEASE:
        _require(bool(_DATED_RE.search(release_id)),
                 f"gene-set bundle: source {source!r} must name a DATED release "
                 f"(YYYY-MM-DD or YYYY-MM), got release_id {release_id!r}. 'GO' is not a "
                 "version, and a CC BY attribution that cannot name what it is "
                 "attributing is not an attribution")

    namespace = str(doc.get("gene_id_namespace", ""))
    _require(namespace in ALLOWED_NAMESPACES,
             f"gene-set bundle: gene_id_namespace must be one of "
             f"{list(ALLOWED_NAMESPACES)}, got {namespace!r}. A symbol-keyed set tested "
             "against an Ensembl-keyed universe overlaps in almost nothing, and the "
             "'no enrichment' it returns is a failed join, not a null result")

    # THE UNIVERSE BINDING. An enrichment statistic is a statement about a set RELATIVE
    # TO a background; the same set against a different background is a different number.
    declared = doc.get("effect_universe_sha256")
    if effect_universe_sha256 is not None and declared is not None:
        _require(str(declared) == str(effect_universe_sha256),
                 f"gene-set bundle: it is bound to effect universe {declared!r}, but "
                 f"this run's universe is {effect_universe_sha256!r}. A bundle computed "
                 "against another background is not evidence about this one")

    raw_sets = doc.get("sets")
    _require(isinstance(raw_sets, list) and bool(raw_sets),
             "gene-set bundle: 'sets' must be a non-empty list")

    readout_universe = set(effect_universe or [])
    # One universe supplied -> it serves as both, and the binding SAYS so.
    single_binding = target_universe is None
    targets = set(target_universe if target_universe is not None
                  else (effect_universe or []))

    sets: dict[str, dict[str, Any]] = {}
    for i, s in enumerate(raw_sets):
        _require(isinstance(s, dict), f"gene-set bundle: set {i} is malformed")
        set_id = str(s.get("set_id", ""))
        _require(bool(set_id), f"gene-set bundle: set {i} has no set_id")
        _require(set_id not in sets,
                 f"gene-set bundle: duplicate set_id {set_id!r}; two sets under one id "
                 "cannot both be cited")

        # A two-namespace bundle names its memberships separately. A legacy single-list
        # bundle (Ensembl ids, never re-keyed) is read as naming the same members in both.
        two_ns = ("genes_target" in s) or ("genes_readout" in s)
        if two_ns:
            g_target = [str(g) for g in (s.get("genes_target") or [])]
            g_readout = [str(g) for g in (s.get("genes_readout") or [])]
        else:
            legacy = [str(g) for g in (s.get("genes") or [])]
            g_target = g_readout = legacy

        n_source = s.get("n_source_symbols")

        # A set with NO members is normally malformed. There is exactly one honest way for
        # it to happen: a RE-KEYED set that named genes and had none of them survive,
        # because this experiment did not perturb or measure any of them. That is a real,
        # informative state — "this pathway could never have been tested here" — and the
        # lane emits it rather than deleting it: a pathway missing from the table is
        # indistinguishable from one that was tested and found nothing.
        #
        # It must SAY that is what it is. An empty set that explains nothing is refused.
        empty = not g_target and not g_readout
        explained = bool(n_source) and int(n_source) > 0
        _require(not empty or explained,
                 f"gene-set bundle: set {set_id!r} names no genes. A set may be empty ONLY "
                 "if it was re-keyed and declares how many source symbols it started from "
                 "(n_source_symbols > 0); an empty set that explains nothing is malformed")
        for label, g in (("genes_target", g_target), ("genes_readout", g_readout)):
            _require(len(set(g)) == len(g),
                     f"gene-set bundle: set {set_id!r} lists a gene twice in {label}; a "
                     "duplicated gene would be double-counted by every statistic over it")

        # MEMBERSHIP, per universe. Members outside a universe were never measurable /
        # never perturbed in this run: reported as coverage, never imputed.
        in_target = sorted(g for g in g_target if g in targets) if targets else []
        in_readout = (sorted(g for g in g_readout if g in readout_universe)
                      if readout_universe else [])

        # THE HONEST DENOMINATOR. A re-keyed bundle has already dropped what it could not
        # map, so a raw in-universe fraction reads 1.0 for every set and a pathway record
        # would look perfectly covered while most of the pathway was never observed.
        # `source_coverage` is the fraction of the genes the pathway ORIGINALLY NAMED that
        # this run could act on at all.
        src = int(n_source) if n_source else None
        target_cov = (round(len(in_target) / src, 6) if src else None)
        readout_cov = (round(len(in_readout) / src, 6) if src else None)

        sets[set_id] = {
            "set_id": set_id,
            "name": str(s.get("name") or set_id),
            # THE MEMBERSHIP THE ARMS RANK. Enrichment and convergence both read this.
            "genes_target": sorted(g_target),
            "n_genes_target": len(g_target),
            "genes_in_target_universe": in_target,
            "n_genes_in_target_universe": len(in_target),
            "target_source_coverage": target_cov,
            # the signature vector space's view of the same pathway
            "genes_readout": sorted(g_readout),
            "n_genes_readout": len(g_readout),
            "genes_in_universe": in_readout,
            "n_genes_in_universe": len(in_readout),
            "readout_source_coverage": readout_cov,
            "n_source_symbols": src,
            # what a reader must see before believing anything about this set: the
            # coverage of the space the statistic is actually computed in.
            "source_coverage": target_cov,
            "coverage": (round(len(in_target) / len(g_target), 6)
                         if (targets and g_target) else None),
            **coverage_disposition(target_cov),
        }

    return {
        "schema_version": SCHEMA_VERSION,
        "gene_set_release": {
            "source": source,
            "release_id": release_id,
            "sha256": file_sha256(path),
            "n_sets": len(sets),
            "license": expected,
            "license_reference": reference,
        },
        # m3: the licence travels WITH the bundle, checked against the source's actual
        # terms — Reactome is CC0, not CC BY 4.0.
        "gene_set_license": expected,
        "gene_set_license_reference": reference,
        "gene_id_namespace": namespace,
        # BOTH universes, bound and named (B1). A bundle that named only one could be
        # joined against the other without anything noticing.
        "effect_universe_sha256": effect_universe_sha256,
        "target_universe_sha256": target_universe_sha256,
        "single_universe_binding": single_binding,
        "n_effect_universe_genes": len(readout_universe),
        "n_target_universe_genes": len(targets),
        # B4: the PROSPECTIVE coverage governance, frozen before any result.
        "coverage_policy_id": COVERAGE_POLICY_ID,
        "min_source_coverage": MIN_SOURCE_COVERAGE,
        "coverage_namespace": COVERAGE_NAMESPACE,
        "n_headline_rankable_sets": sum(1 for v in sets.values()
                                        if v["headline_rankable"]),
        "n_descriptive_only_sets": sum(1 for v in sets.values()
                                       if not v["headline_rankable"]),
        "min_set_size": MIN_SET_SIZE,
        "max_set_size": MAX_SET_SIZE,
        "sets": sets,
        # Recomputed from the parsed content, independent of any self-declared hash.
        # BOTH memberships: two bundles that agree on one and differ on the other are
        # different bundles, and would produce different pathway results.
        "canonical_sha256": content_hash(
            [[k, v["genes_target"], v["genes_readout"]]
             for k, v in sorted(sets.items())]),
    }


def testable(bundle: dict[str, Any], set_id: str) -> bool:
    """Is this set big enough to say anything, and small enough to say something?

    A 2-gene set "enriches" on one lucky target; a 5,000-gene set is the universe with a
    label. Both are still EMITTED — with their sizes and an explicit reason — because
    silently dropping them would hide which pathways were never actually tested.
    """
    n = bundle["sets"][set_id]["n_genes_in_universe"]
    return bundle["min_set_size"] <= n <= bundle["max_set_size"]


# Absence is a STATE. With no bundle there is no pathway layer, and every artifact says
# so in enums and flags — never by omitting the block.
ABSENT_BLOCK = {
    "status": "absent",
    "gene_set_release": None,
    "pathway_layer_available": False,
    "enrichment_possible": False,
    "convergence_possible": False,
}


def binding_block(bundle: Optional[dict[str, Any]]) -> dict[str, Any]:
    """What run_id binds about the gene sets: the release, the namespace, the universe."""
    if bundle is None:
        return dict(ABSENT_BLOCK)
    return {
        "status": "bound",
        "schema_version": bundle["schema_version"],
        "gene_set_release": bundle["gene_set_release"],
        # m3: the licence is part of what the run stands on, and it is bound, not noted
        "gene_set_license": bundle["gene_set_license"],
        "gene_set_license_reference": bundle["gene_set_license_reference"],
        "gene_id_namespace": bundle["gene_id_namespace"],
        # BOTH universes (B1). The commit and the matrix CLAIMED both were in the method
        # hash; only the readout id was. Two bundles differing ONLY in which population
        # was PERTURBED produced an identical method hash — and the target universe is the
        # space enrichment tests membership in, so that is a different method, not a
        # different input. The claim is now true.
        "effect_universe_sha256": bundle["effect_universe_sha256"],
        "target_universe_sha256": bundle.get("target_universe_sha256"),
        "single_universe_binding": bundle.get("single_universe_binding"),
        "canonical_sha256": bundle["canonical_sha256"],
        "min_set_size": bundle["min_set_size"],
        "max_set_size": bundle["max_set_size"],
        "pathway_layer_available": True,
    }
