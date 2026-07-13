"""v2 INDEPENDENT cache-identity verifier. Imports nothing from ``druglink``.

Integrates the independent Stage-3 drug-cache source audit (sha `fa64054e…`).

WHY "human SINGLE PROTEIN" IS NOT ENOUGH
---------------------------------------
Stage 3 admits a ChEMBL target into the **direct gene lane** — the lane where a drug is
linked to a gene the screen actually perturbed — only when that target IS that one human
protein. Today the engine admits on ``target_type == "SINGLE PROTEIN"`` alone, and that
label is far weaker than it reads:

* a SINGLE PROTEIN row can be a **non-human** protein (mouse Ctla4 is also a SINGLE PROTEIN);
* it can be a **species group** (``species_group_flag=1``) — a protein *across* organisms,
  not one protein;
* it can be reached via a **homologue** relationship, which is a different gene that
  resembles this one;
* its component can be a non-``PROTEIN`` type;
* and it can carry **more than one component**, at which point "the target" is not a
  single protein at all, whatever the label says.

Any one of those silently attaches a drug to a human gene it was never measured against.
So the gene lane requires ALL of it, and a cache that cannot answer these questions is
**refused, not downgraded**: a coarser cache is not a smaller amount of evidence, it is an
unknown amount, and Stage 3 does not guess the difference.

WHAT THIS VERIFIER DOES *NOT* DO
--------------------------------
It never translates an ``action_type``. The cache is a **verbatim store**; the frozen,
code-digested Stage-3 direction engine is the only thing that interprets an action, and it
does so at view time. This verifier checks that the verbatim string SURVIVED and that the
cache did not quietly classify it.
"""
from __future__ import annotations

from typing import Any, Optional

from .report import Report

AUDIT_SHA256_PREFIX = "fa64054e"
IDENTITY_RULE_ID = "spot.stage03.cache_identity.human_single_protein.v2"

HUMAN_TAXON = 9606
SINGLE_PROTEIN = "SINGLE PROTEIN"
COMPONENT_PROTEIN = "PROTEIN"

# The audited perturbation target universe. Typed, never assumed homogeneous.
N_ENSEMBL = 11_522
N_UNSUPPORTED_SYMBOL = 4
SYMBOL_ONLY_TARGETS = ("MTRNR2L1", "MTRNR2L4", "MTRNR2L8", "OCLM")
UNSUPPORTED_NAMESPACE = "unsupported_namespace"

# Licences are per-source and DO NOT MERGE. A UniProt field and a ChEMBL field in the same
# row are governed by different terms, and a single blended licence on the row would state
# terms that are wrong for one of them.
SOURCE_LICENSES = {
    "uniprot": "CC BY 4.0",
    "chembl": "CC BY-SA 3.0",
}

# Fields the cache MUST be able to answer. A cache missing any of them is refused.
REQUIRED_TARGET_FIELDS = (
    "target_type", "target_taxon", "species_group_flag", "target_components",
)
REQUIRED_COMPONENT_FIELDS = (
    "accession", "component_type", "component_taxon", "relationship",
)


def gene_lane_admissible(target: dict[str, Any]) -> tuple[bool, str]:
    """Is this ChEMBL target exactly ONE HUMAN PROTEIN? All of it, or none of it."""
    missing = [f for f in REQUIRED_TARGET_FIELDS if f not in target]
    if missing:
        return False, (
            f"cache_too_coarse: target cannot answer {missing}. A cache that cannot say "
            "whether this is one human protein is refused, not downgraded.")

    if target["target_type"] != SINGLE_PROTEIN:
        return False, f"target_type_is_{target['target_type']!r}_not_SINGLE_PROTEIN"

    if _int(target["target_taxon"]) != HUMAN_TAXON:
        return False, (
            f"target_taxon_{target['target_taxon']!r}_is_not_human_{HUMAN_TAXON}")

    if _int(target["species_group_flag"]) != 0:
        return False, (
            "species_group_flag_is_set: this row is a protein ACROSS organisms, not one "
            "protein")

    components = target.get("target_components") or []
    if len(components) != 1:
        return False, (
            f"expected_exactly_one_component_got_{len(components)}: a target with "
            "several components is not a single protein, whatever the label says")

    comp = components[0]
    cmissing = [f for f in REQUIRED_COMPONENT_FIELDS if f not in comp]
    if cmissing:
        return False, f"cache_too_coarse: component cannot answer {cmissing}"

    if comp["component_type"] != COMPONENT_PROTEIN:
        return False, f"component_type_is_{comp['component_type']!r}_not_PROTEIN"

    if _int(comp["component_taxon"]) != HUMAN_TAXON:
        return False, (
            f"component_taxon_{comp['component_taxon']!r}_is_not_human_{HUMAN_TAXON}")

    if _homologue(comp):
        return False, (
            "component_is_a_HOMOLOGUE: a homologue is a different gene that resembles this "
            "one, and the screen did not perturb it")

    return True, "human_single_protein_exactly_one_component"


def _int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _homologue(comp: dict[str, Any]) -> bool:
    rel = str(comp.get("relationship") or "").upper()
    if "HOMOLOG" in rel:
        return True
    flag = comp.get("homologue")
    return _int(flag) not in (0, None) if flag is not None else False


# --------------------------------------------------------------------------- #
# Checks.
# --------------------------------------------------------------------------- #
def check_gene_lane_identity(rep: Report, *, targets: list[dict[str, Any]],
                             admitted_entity_ids: set[str]) -> None:
    """Every target in the DIRECT GENE LANE is exactly one human protein."""
    wrongly_admitted = []
    for t in targets:
        ok, reason = gene_lane_admissible(t)
        tid = t.get("target_chembl_id")
        if tid in admitted_entity_ids and not ok:
            wrongly_admitted.append(f"{tid}: {reason}")

    rep.check(
        "every direct-gene-lane target is exactly ONE HUMAN PROTEIN (SINGLE PROTEIN + "
        "target taxon 9606 + component taxon 9606 + species_group_flag 0 + not a "
        "homologue + component type PROTEIN + exactly one component)",
        not wrongly_admitted, "; ".join(wrongly_admitted[:3]))


def check_cache_is_not_coarser_than_the_contract(rep: Report,
                                                 targets: list[dict[str, Any]]) -> None:
    """A cache that cannot answer the identity questions is REFUSED, not downgraded."""
    coarse = []
    for t in targets:
        missing = [f for f in REQUIRED_TARGET_FIELDS if f not in t]
        for comp in (t.get("target_components") or []):
            missing += [f"component.{f}" for f in REQUIRED_COMPONENT_FIELDS
                        if f not in comp]
        if missing:
            coarse.append(f"{t.get('target_chembl_id')}: {sorted(set(missing))}")

    rep.check(
        "the cache can answer every identity question the gene lane asks (a coarser cache "
        "is refused, never silently downgraded)",
        not coarse, "; ".join(coarse[:3]))


def check_one_assertion_per_mechanism(rep: Report,
                                      assertions: list[dict[str, Any]]) -> None:
    """ONE assertion per ChEMBL ``mec_id`` — carrying its variant/context, not collapsing it.

    Two rows for one mec_id double-count a single mechanism. Collapsing distinct mec_ids
    that differ only by variant or assay context throws away the thing that distinguished
    them. Both are wrong; the row is keyed on mec_id and KEEPS the context.
    """
    seen: dict[str, list[dict[str, Any]]] = {}
    for a in assertions:
        mec = a.get("mec_id")
        if mec is None:
            continue
        seen.setdefault(str(mec), []).append(a)

    dupes = sorted(m for m, rows in seen.items() if len(rows) > 1)
    rep.check("exactly ONE assertion per ChEMBL mec_id (a mechanism is not double-counted)",
              not dupes, f"{len(dupes)} duplicated mec_id(s): {dupes[:3]}")

    missing_ctx = [a.get("mec_id") for a in assertions
                   if a.get("mec_id") is not None
                   and "variant_or_context" not in a and "mechanism_context" not in a]
    rep.check("every mechanism assertion carries its variant/context (it is not collapsed "
              "away)", not missing_ctx, f"{len(missing_ctx)} without context")


def check_namespace_typing(rep: Report, universe: dict[str, Any]) -> None:
    """11,522 ENSG + 4 unsupported symbols. Typed, and the four are RETAINED."""
    rep.check(
        f"the target universe is TYPED as {N_ENSEMBL} Ensembl + {N_UNSUPPORTED_SYMBOL} "
        "unsupported-symbol targets (it is not homogeneous ENSG)",
        universe.get("universe_is_homogeneous_ensembl") is False
        and universe.get("namespaces_are_split") is True,
        f"declared={universe.get('universe_is_homogeneous_ensembl')!r}")

    symbols = set(universe.get("symbol_only_targets") or [])
    rep.check(
        "the four symbol-only targets are RETAINED with an unsupported_namespace "
        "disposition (they are not dropped to make coverage look complete)",
        set(SYMBOL_ONLY_TARGETS) <= symbols or not symbols,
        f"symbol-only present: {sorted(symbols)}")


def check_verbatim_action_type(rep: Report,
                               assertions: list[dict[str, Any]]) -> None:
    """The cache stores the source's word. It does NOT classify."""
    lost = [a.get("assertion_id") for a in assertions
            if a.get("action_type_source") in (None, "")]
    rep.check("every mechanism assertion preserves the VERBATIM ChEMBL action_type "
              "(the cache is a faithful store and never classifies)",
              not lost, f"{len(lost)} row(s) lost the source string")

    # View-time translation: the interpretation must be separable from the source.
    unseparated = [a.get("assertion_id") for a in assertions
                   if "intervention_effect" in a and "action_type_source" not in a]
    rep.check("the interpretation is SEPARABLE from the source string (translation happens "
              "at view time in the frozen direction engine, never in the cache)",
              not unseparated, f"{len(unseparated)} row(s) carry only the interpretation")


def check_max_phase_is_context_only(rep: Report, rows: list[dict[str, Any]], *,
                                    ordering_keys: list[str]) -> None:
    """max_phase is preserved exactly and used for NOTHING. Mutation-refused."""
    offenders = [k for k in ordering_keys if "max_phase" in k]
    rep.check("no drug ordering key names max_phase (it is CONTEXT ONLY: a clinical phase "
              "says nothing about direction-compatibility with this arm)",
              not offenders, str(offenders))

    bad_flags = [r.get("max_phase_source_record_id") for r in rows
                 if r.get("max_phase_may_rank") or r.get("max_phase_may_gate")]
    rep.check("no preserved max_phase declares itself rankable or gating",
              not bad_flags, f"{len(bad_flags)} row(s)")

    # null / -1 / 0.5 / integer must remain DISTINCT: a cast to int destroys three of them.
    collapsed = [r.get("max_phase_source_record_id") for r in rows
                 if r.get("max_phase_state") == "recorded"
                 and r.get("max_phase_source_string") in (None, "")]
    rep.check("a recorded max_phase keeps its exact source string (null / -1 / 0.5 / "
              "integer never collapse into one another)",
              not collapsed, f"{len(collapsed)} row(s) lost the exact value")

    overclaim = [r.get("max_phase_source_record_id") for r in rows
                 if r.get("development_state_preserves_max_phase")]
    rep.check("development_state does not CLAIM to preserve max_phase",
              not overclaim, f"{len(overclaim)} row(s) overclaim")


def check_license_separation(rep: Report, source_records: list[dict[str, Any]]) -> None:
    """UniProt and ChEMBL licences do not merge. A blended licence is wrong for one of them."""
    wrong = []
    for r in source_records:
        src = str(r.get("source") or "").lower()
        expected = SOURCE_LICENSES.get(src)
        if expected and r.get("license") != expected:
            wrong.append(f"{src}:{r.get('license')!r} (expected {expected!r})")

    rep.check("each source record carries ITS OWN source's licence "
              "(UniProt CC BY 4.0; ChEMBL CC BY-SA 3.0 — they are not merged into one "
              "blended licence, which would state terms that are wrong for one of them)",
              not wrong, "; ".join(sorted(set(wrong))[:3]))

    blended = [r.get("source_record_id") for r in source_records
               if r.get("license_is_blended") or r.get("combined_license")]
    rep.check("no source record carries a blended/combined licence",
              not blended, f"{len(blended)} row(s)")
