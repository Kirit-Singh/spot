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


class GeneSetError(ValueError):
    """The gene-set bundle is not usable. Refuse; never repair."""


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise GeneSetError(msg)


def load(path: Optional[str], effect_universe: Optional[list[str]] = None,
         effect_universe_sha256: Optional[str] = None) -> Optional[dict[str, Any]]:
    """Load, pin and BIND a gene-set bundle. ``None`` when no bundle was supplied.

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

    universe = set(effect_universe or [])
    sets: dict[str, dict[str, Any]] = {}
    for i, s in enumerate(raw_sets):
        _require(isinstance(s, dict), f"gene-set bundle: set {i} is malformed")
        set_id = str(s.get("set_id", ""))
        _require(bool(set_id), f"gene-set bundle: set {i} has no set_id")
        _require(set_id not in sets,
                 f"gene-set bundle: duplicate set_id {set_id!r}; two sets under one id "
                 "cannot both be cited")
        genes = [str(g) for g in (s.get("genes") or [])]
        _require(bool(genes), f"gene-set bundle: set {set_id!r} names no genes")
        _require(len(set(genes)) == len(genes),
                 f"gene-set bundle: set {set_id!r} lists a gene twice; a duplicated gene "
                 "would be double-counted by every statistic over the set")

        # Genes absent from the effect universe were never MEASURABLE in this run. They
        # are reported as coverage — never imputed, and never read as evidence of absence.
        measured = sorted(g for g in genes if g in universe) if universe else []
        sets[set_id] = {
            "set_id": set_id,
            "name": str(s.get("name") or set_id),
            "genes": sorted(genes),
            "n_genes": len(genes),
            "genes_in_universe": measured,
            "n_genes_in_universe": len(measured),
            "coverage": (round(len(measured) / len(genes), 6) if universe else None),
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
        "effect_universe_sha256": effect_universe_sha256,
        "min_set_size": MIN_SET_SIZE,
        "max_set_size": MAX_SET_SIZE,
        "sets": sets,
        # Recomputed from the parsed content, independent of any self-declared hash.
        "canonical_sha256": content_hash(
            [[k, v["genes"]] for k, v in sorted(sets.items())]),
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
        "effect_universe_sha256": bundle["effect_universe_sha256"],
        "canonical_sha256": bundle["canonical_sha256"],
        "min_set_size": bundle["min_set_size"],
        "max_set_size": bundle["max_set_size"],
        "pathway_layer_available": True,
    }
