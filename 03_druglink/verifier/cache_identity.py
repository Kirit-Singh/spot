"""v2 INDEPENDENT cache-identity verifier. Imports nothing from ``druglink``.

Encodes the exact predicates of the independent Stage-3 drug-cache source audit,
content-addressed at

    STAGE3_DRUG_CACHE_INDEPENDENT_SOURCE_AUDIT.fa64054e.md
    sha256 fa64054e0698448b143c7e4e564dd2e7003a6e21161ee18b54f826a744a65e67

Verdict: **NO-GO** for acquisition/publication as specified. BLOCKER 1 (identity),
BLOCKER 2 (mechanism collapse) and BLOCKER 3 (mixed universe) are what this module gates.

BLOCKER 1 — "human SINGLE PROTEIN" is not an adequate identity rule
------------------------------------------------------------------
The audit reproduced the defect against this very checkout:

    synthetic target: target_type=SINGLE PROTEIN, organism=Mus musculus,
    two components mapping to ENSG_A and ENSG_B
    direct_gene_lane_eligible True
    dispositions []

A **non-human, two-gene** target admitted into the direct gene lane, with no disposition
recorded. The label was doing all the work and the label is not enough.

The six frozen predicates, in ChEMBL 37's own column names — not paraphrased, because the
extractor and the verifier have to speak the same language as the source:

    td.target_type      = 'SINGLE PROTEIN'
    td.tax_id           = 9606
    td.species_group_flag = 0
    cs.component_type   = 'PROTEIN'
    cs.tax_id           = 9606
    tc.homologue        = 0

``target_components.homologue`` is **0 = exact, 1 = homologue, 2 = species-group
representative** — so the predicate is ``= 0``, and BOTH 1 and 2 are refused. A
species-group representative is not this protein any more than a homologue is.

And then cardinality, which the summary of this audit dropped and which matters: the target
must have **exactly one ELIGIBLE component AND exactly one TOTAL component**. One eligible
out of three is still a multi-component target — filtering down to the one you like and
calling it a single protein is precisely the silent failure. Anything else emits a **named
non-rankable disposition**; it is never merely dropped.
"""
from __future__ import annotations

from typing import Any, Optional

from .report import Report

AUDIT_SHA256 = "fa64054e0698448b143c7e4e564dd2e7003a6e21161ee18b54f826a744a65e67"
IDENTITY_RULE_ID = "spot.stage03.cache_identity.human_single_protein.v2"

HUMAN_TAX_ID = 9606
SINGLE_PROTEIN = "SINGLE PROTEIN"
COMPONENT_PROTEIN = "PROTEIN"

# target_components.homologue: 0 exact | 1 homologue | 2 species-group representative
HOMOLOGUE_EXACT = 0

# Audited universe (BLOCKER 3). 11,526 = 11,522 ENSG + 4 symbol-only.
N_TARGETS = 11_526
N_ENSEMBL = 11_522
N_UNSUPPORTED_SYMBOL = 4
SYMBOL_ONLY_TARGETS = ("MTRNR2L1", "MTRNR2L4", "MTRNR2L8", "OCLM")
UNSUPPORTED_NAMESPACE = "unsupported_namespace"
DE_STATS_SHA256 = \
    "c355f535ff32cf7ba1edc49cf9c6039fe84f2c9ebe4d005515cba75790cfbb62"

# The audit re-derived these: the direction-only top-N unions CONTAIN MTRNR2L4 and
# MTRNR2L8, so a union field named `*_ensg_*` is simply false. Symbols reach the queue.
SYMBOLS_IN_TOP_N_UNION = ("MTRNR2L4", "MTRNR2L8")

# Licences are per-source and DO NOT MERGE (MAJOR 4). The cache DATA is not MIT.
SOURCE_LICENSES = {"uniprot": "CC BY 4.0", "chembl": "CC BY-SA 3.0"}
CHEMBL_REQUIRED_FILES = ("LICENSE", "REQUIRED.ATTRIBUTION")

# BLOCKER 2 — assertion-level fields that must survive, keyed on mec_id.
REQUIRED_ASSERTION_FIELDS = (
    "source_row_id",            # = mec_id, the ChEMBL assertion primary key
    "mechanism_of_action", "molecular_mechanism", "direct_interaction",
    "disease_efficacy", "variant_id", "selectivity_comment",
)

# MAJOR 3 — not sourced by the pinned artifacts; must be explicitly not_in_source.
NOT_IN_SOURCE_FIELDS = ("pubchem_cid", "unii")
NOT_IN_SOURCE = "not_in_source"

# Source fields the cache MUST carry. A cache that cannot answer these is refused.
REQUIRED_TARGET_FIELDS = ("target_type", "tax_id", "species_group_flag",
                          "target_components")
REQUIRED_COMPONENT_FIELDS = ("accession", "component_type", "tax_id", "homologue")

# Named dispositions. A refusal is a RECORD, never a silent drop.
DISP_NOT_SINGLE_PROTEIN = "target_type_not_single_protein"
DISP_NON_HUMAN_TARGET = "target_tax_id_not_human"
DISP_SPECIES_GROUP = "species_group_flag_set"
DISP_NON_PROTEIN_COMPONENT = "component_type_not_protein"
DISP_NON_HUMAN_COMPONENT = "component_tax_id_not_human"
DISP_HOMOLOGUE = "component_homologue_not_exact"
DISP_COMPONENT_CARDINALITY = "component_cardinality_not_exactly_one"
DISP_CACHE_TOO_COARSE = "cache_too_coarse_to_decide_identity"
NON_RANKABLE_DISPOSITIONS = (
    DISP_NOT_SINGLE_PROTEIN, DISP_NON_HUMAN_TARGET, DISP_SPECIES_GROUP,
    DISP_NON_PROTEIN_COMPONENT, DISP_NON_HUMAN_COMPONENT, DISP_HOMOLOGUE,
    DISP_COMPONENT_CARDINALITY, DISP_CACHE_TOO_COARSE,
)


def _int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def component_eligible(comp: dict[str, Any]) -> tuple[bool, Optional[str]]:
    """The three COMPONENT-level predicates. Returns (eligible, named disposition)."""
    missing = [f for f in REQUIRED_COMPONENT_FIELDS if f not in comp]
    if missing:
        return False, DISP_CACHE_TOO_COARSE
    if comp["component_type"] != COMPONENT_PROTEIN:
        return False, DISP_NON_PROTEIN_COMPONENT
    if _int(comp["tax_id"]) != HUMAN_TAX_ID:
        return False, DISP_NON_HUMAN_COMPONENT
    if _int(comp["homologue"]) != HOMOLOGUE_EXACT:
        # 1 = homologue, 2 = species-group representative. Neither is THIS protein.
        return False, DISP_HOMOLOGUE
    return True, None


def gene_lane_admissible(target: dict[str, Any]) -> tuple[bool, str]:
    """The six frozen predicates + the cardinality proof. All of it, or a named disposition.

    Cardinality is the part a summary loses: exactly one ELIGIBLE **and** exactly one TOTAL
    component. A target with three components of which one is human-protein-exact is a
    multi-component target, and quietly keeping the component you liked is the bug.
    """
    missing = [f for f in REQUIRED_TARGET_FIELDS if f not in target]
    if missing:
        return False, f"{DISP_CACHE_TOO_COARSE}: target cannot answer {missing}"

    if target["target_type"] != SINGLE_PROTEIN:
        return False, f"{DISP_NOT_SINGLE_PROTEIN}: {target['target_type']!r}"
    if _int(target["tax_id"]) != HUMAN_TAX_ID:
        return False, f"{DISP_NON_HUMAN_TARGET}: tax_id={target['tax_id']!r}"
    if _int(target["species_group_flag"]) != 0:
        return False, (f"{DISP_SPECIES_GROUP}: a protein ACROSS organisms, not one "
                       "protein")

    components = target.get("target_components") or []
    n_total = len(components)
    eligible, reasons = [], []
    for comp in components:
        ok, disp = component_eligible(comp)
        (eligible if ok else reasons).append(comp if ok else disp)

    if n_total != 1:
        return False, (
            f"{DISP_COMPONENT_CARDINALITY}: {n_total} total component(s), "
            f"{len(eligible)} eligible — exactly ONE of each is required; a target with "
            "several components is not a single protein, and keeping only the eligible one "
            "would be choosing the answer")
    if len(eligible) != 1:
        return False, f"{reasons[0]}"

    return True, "human_single_protein_exactly_one_eligible_and_one_total_component"


def disposition_for(target: dict[str, Any]) -> Optional[dict[str, Any]]:
    """A refused target emits a NAMED non-rankable disposition. It is never just dropped."""
    ok, reason = gene_lane_admissible(target)
    if ok:
        return None
    state = reason.split(":")[0]
    return {
        "subject_kind": "chembl_target",
        "subject_id": target.get("target_chembl_id"),
        "state": state,
        "reason": reason,
        "rankable": False,
        "identity_rule_id": IDENTITY_RULE_ID,
    }


# --------------------------------------------------------------------------- #
# Checks.
# --------------------------------------------------------------------------- #
def check_gene_lane_identity(rep: Report, *, targets: list[dict[str, Any]],
                             admitted_entity_ids: set[str],
                             dispositions: list[dict[str, Any]]) -> None:
    """Every direct-gene-lane target passes all six predicates + the cardinality proof."""
    wrongly_admitted = []
    for t in targets:
        ok, reason = gene_lane_admissible(t)
        tid = t.get("target_chembl_id")
        if tid in admitted_entity_ids and not ok:
            wrongly_admitted.append(f"{tid}: {reason}")

    rep.check(
        "every direct-gene-lane target satisfies ALL SIX frozen predicates "
        "(SINGLE PROTEIN, td.tax_id=9606, species_group_flag=0, component_type=PROTEIN, "
        "cs.tax_id=9606, tc.homologue=0) AND has exactly one eligible and one total "
        "component",
        not wrongly_admitted, "; ".join(wrongly_admitted[:3]))

    # A refused target must leave a RECORD. The audit's reproduction had `dispositions []`.
    disposed = {d.get("subject_id") for d in dispositions}
    silently_dropped = [
        t.get("target_chembl_id") for t in targets
        if not gene_lane_admissible(t)[0]
        and t.get("target_chembl_id") not in admitted_entity_ids
        and t.get("target_chembl_id") not in disposed]
    rep.check(
        "every refused target emits a NAMED non-rankable disposition (it is never silently "
        "dropped — an unrecorded absence is indistinguishable from a target nobody saw)",
        not silently_dropped, f"{len(silently_dropped)} dropped with no disposition")


def check_cache_is_not_coarser_than_the_contract(rep: Report,
                                                 targets: list[dict[str, Any]]) -> None:
    """A cache that cannot ANSWER the identity questions is refused, not downgraded."""
    coarse = []
    for t in targets:
        missing = [f for f in REQUIRED_TARGET_FIELDS if f not in t]
        for comp in (t.get("target_components") or []):
            missing += [f"component.{f}" for f in REQUIRED_COMPONENT_FIELDS
                        if f not in comp]
        if missing:
            coarse.append(f"{t.get('target_chembl_id')}: {sorted(set(missing))}")

    rep.check(
        "the cache carries every ChEMBL source field the identity gate reads "
        "(td.tax_id, td.species_group_flag, cs.component_type, cs.tax_id, tc.homologue) — "
        "a REST-shaped adapter must not discard them before the gate runs",
        not coarse, "; ".join(coarse[:3]))


def check_typed_universe(rep: Report, universe: dict[str, Any]) -> None:
    """BLOCKER 3. The universe is a TYPED artifact; the four symbols are HASHED ROWS."""
    rep.check(
        f"the universe is typed: {N_TARGETS} targets = {N_ENSEMBL} ENSG + "
        f"{N_UNSUPPORTED_SYMBOL} symbol-only (it is NOT keyed on ENSG, and namespace is "
        "not declared 'ENSG')",
        universe.get("universe_is_homogeneous_ensembl") is False
        and universe.get("namespaces_are_split") is True,
        f"homogeneous={universe.get('universe_is_homogeneous_ensembl')!r}")

    rows = universe.get("hashed_rows") or []
    row_ids = {r.get("target_id") for r in rows}
    missing = [s for s in SYMBOL_ONLY_TARGETS if s not in row_ids]
    rep.check(
        "the four symbol-only targets are HASHED ROWS in the universe artifact "
        "{target_id, target_id_namespace, disposition} — not an out-of-band note",
        rows and not missing, f"missing from hashed rows: {missing}")

    for r in rows:
        pass
    typed = all(("target_id" in r and "target_id_namespace" in r and "disposition" in r)
                for r in rows)
    rep.check("every universe row is typed {target_id, target_id_namespace, disposition}",
              typed or not rows, "untyped rows present")

    rep.check(
        "the store_id hashes the TYPED universe (not only a universe_ensg_set — which "
        "omits four real perturbation targets from the artifact's identity)",
        bool(universe.get("store_id_hashes_typed_universe")),
        f"store_id_hashes_typed_universe={universe.get('store_id_hashes_typed_universe')!r}")


def check_top_n_union_is_not_called_ensg(rep: Report, union: dict[str, Any]) -> None:
    """The direction-only top-N unions CONTAIN MTRNR2L4/L8. `*_ensg_*` is false."""
    ensg_named = sorted(k for k in union if "ensg" in k.lower())
    rep.check(
        "no top-N union field is named *_ensg_* (the audit re-derived that the "
        "direction-only unions CONTAIN MTRNR2L4 and MTRNR2L8, so 'unique ENSG' is simply "
        "false); fields are *_target_id_* and carry namespace counts",
        not ensg_named, f"ensg-named fields: {ensg_named}")

    rep.check(
        "the significance filter is labelled exactly as a PROXY (it requires upstream "
        "significance at both temporal endpoints; it is not the production mask)",
        union.get("significant_filter_is_proxy") is True
        if "significant_filter_is_proxy" in union or union.get("significant") else True,
        "significance presented as the production mask")


def check_max_phase_is_context_only(rep: Report, rows: list[dict[str, Any]], *,
                                    ordering_keys: list[str],
                                    manifest: Optional[dict[str, Any]] = None) -> None:
    """MAJOR 2. Exact, context-only, and the transformation CODE is bound by hash."""
    offenders = [k for k in ordering_keys if "max_phase" in k]
    rep.check("no drug ordering key names max_phase (context only: a clinical phase says "
              "nothing about direction-compatibility with this arm)",
              not offenders, str(offenders))

    bad = [r.get("max_phase_source_record_id") for r in rows
           if r.get("max_phase_may_rank") or r.get("max_phase_may_gate")]
    rep.check("no preserved max_phase declares itself rankable or gating", not bad,
              f"{len(bad)} row(s)")

    collapsed = [r.get("max_phase_source_record_id") for r in rows
                 if r.get("max_phase_state") == "recorded"
                 and r.get("max_phase_source_string") in (None, "")]
    rep.check("a recorded max_phase keeps its exact source string (null / -1 / 0.5 / "
              "integer never collapse)", not collapsed, f"{len(collapsed)} row(s)")

    overclaim = [r.get("max_phase_source_record_id") for r in rows
                 if r.get("development_state_preserves_max_phase")]
    rep.check("development_state does not CLAIM to preserve max_phase", not overclaim,
              f"{len(overclaim)} row(s)")

    if manifest is not None:
        rep.check(
            "the exact max_phase transformation code is BOUND by hash into the "
            "universe/view manifest",
            bool(manifest.get("max_phase_rule_id")
                 and manifest.get("max_phase_code_sha256")),
            f"rule={manifest.get('max_phase_rule_id')!r} "
            f"code={manifest.get('max_phase_code_sha256')!r}")


def check_verbatim_action_type(rep: Report,
                               assertions: list[dict[str, Any]]) -> None:
    """The cache stores the source's word; the frozen policy translates at VIEW TIME."""
    lost = [a.get("source_row_id") for a in assertions
            if a.get("action_type_source") in (None, "")]
    rep.check("every assertion preserves the VERBATIM ChEMBL action_type (the cache never "
              "classifies)", not lost, f"{len(lost)} row(s) lost the source string")

    unseparated = [a.get("source_row_id") for a in assertions
                   if "intervention_effect" in a and "action_type_source" not in a]
    rep.check("the interpretation is SEPARABLE from the source string (if the source string "
              "is gone, nobody can re-translate under a corrected vocabulary)",
              not unseparated, f"{len(unseparated)} row(s) carry only the interpretation")


def check_cross_identifiers_are_sourced(rep: Report,
                                        molecules: list[dict[str, Any]]) -> None:
    """MAJOR 3. PubChem CID and UNII are NOT in the pinned SQLite join."""
    invented = []
    for m in molecules:
        for field in NOT_IN_SOURCE_FIELDS:
            value = m.get(field)
            prov = m.get(f"{field}_provenance")
            if value not in (None, "") and prov != NOT_IN_SOURCE:
                if not prov:
                    invented.append(f"{m.get('molecule_chembl_id')}.{field}")
    rep.check(
        "pubchem_cid / unii are either null with explicit not_in_source provenance, or "
        "carry a named, licensed, pinned cross-reference source (they cannot be inferred "
        "from a name or a first external match)",
        not invented, "; ".join(invented[:3]))


def check_license_separation(rep: Report, source_records: list[dict[str, Any]], *,
                             packaging: Optional[dict[str, Any]] = None) -> None:
    """MAJOR 4. Separable data layers; the cache DATA is not MIT."""
    wrong = []
    for r in source_records:
        src = str(r.get("source") or "").lower()
        expected = SOURCE_LICENSES.get(src)
        if expected and r.get("license") != expected:
            wrong.append(f"{src}:{r.get('license')!r} != {expected!r}")
    rep.check("each source record carries ITS OWN source's licence (ChEMBL CC BY-SA 3.0; "
              "UniProt CC BY 4.0 — a blended licence states terms that are wrong for one "
              "of them)",
              not wrong, "; ".join(sorted(set(wrong))[:3]))

    mit = [r.get("source_record_id") for r in source_records
           if str(r.get("license") or "").upper() == "MIT"]
    rep.check("no cache DATA row is represented as MIT (application code may be; the "
              "ChEMBL-derived data may not)", not mit, f"{len(mit)} row(s)")

    if packaging is not None:
        bundled = set(packaging.get("chembl_bundled_files") or [])
        rep.check(
            "the ChEMBL-derived layer bundles LICENSE + REQUIRED.ATTRIBUTION and displays "
            "release/URL/DOI with ChEMBL identifiers preserved",
            set(CHEMBL_REQUIRED_FILES) <= bundled
            and bool(packaging.get("chembl_release"))
            and bool(packaging.get("chembl_doi")),
            f"bundled={sorted(bundled)} release={packaging.get('chembl_release')!r}")
        rep.check(
            "the ChEMBL-derived cache is a SEPARABLE data layer (ShareAlike scope is a "
            "release/compliance question, not something silently absorbed)",
            bool(packaging.get("chembl_layer_is_separable")),
            f"separable={packaging.get('chembl_layer_is_separable')!r}")
