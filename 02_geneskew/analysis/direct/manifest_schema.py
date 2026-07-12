"""The FROZEN vocabulary of the contributing-guide manifest.

One exact schema version; one enum of identity methods; one enum of evidence states;
one definition of a released SCOPE and of the canonical row order. Everything that
validates a manifest (``manifest_validate``) or loads one (``manifest``) speaks this
vocabulary and nothing else, so there is exactly one place where the shape of the
contract is stated.

A manifest is not a family of shapes: a value that is not in these enums is refused,
never coerced.
"""
from __future__ import annotations

import re
from typing import Any

# ONE exact schema version. A manifest is not a family of shapes.
#
# v3 supersedes v2 because the SEMANTICS changed, not the spelling:
#   * the evidence domain is stated and enforced — every row is an all-condition
#     pooled-main scope (``domain.py``), and the manifest matches the GLOBAL
#     pooled-main released universe, not a selected-condition main+guide+donor one;
#   * citations name source-record ids minted under the compiled record-id rule
#     (``record_id.py``): ``srcrec:sha256:`` + the full digest of a payload that
#     BINDS the complete offset/row proof. v2 ids were truncated hashes of a payload
#     that omitted that proof, so a record's offsets could be swapped without
#     changing its id, and every citation would still resolve;
#   * the release gate is a COMPLETENESS-bearing replay report, not an
#     existence-only one.
# A v1/v2 manifest is refused, never migrated in place.
SCHEMA_VERSION = "spot.stage02_contributor_manifest.v3"
SCHEMA_PREFIX = "spot.stage02_contributor_manifest."
SUPERSEDED_SCHEMA_VERSIONS = ("spot.stage02_contributor_manifest.v1",
                              "spot.stage02_contributor_manifest.v2")

# The manifest must declare WHICH source-record schema its citations resolve in, and
# that declaration is machine-checked against the table's own schema_version. The
# superseded pair declared 'spot.stage02_source_records.target_id_proposal.v1' while
# its table said 'spot.stage02_source_records.v1' — a drift nobody was checking.
SOURCE_RECORD_TABLE_SCHEMA = "spot.stage02_source_records.v2"

# The FULL generic target identity, on EVERY row. A row may not name a target by
# accession alone: an Ensembl id cannot express the twelve gene-symbol scopes, and
# a symbol cannot express the 33,971 accession scopes. Both namespaces are
# first-class, and target_ensembl is nullable BY CONTRACT (null for every symbol
# scope) rather than by accident.
# ``evidence_state`` is REQUIRED, not defaulted: a row that forgets to say whether
# its identity was determined is not implicitly determined.
REQUIRED_ROW_KEYS = ("estimate_type", "estimate_id", "released_estimate_id",
                     "target_id", "target_id_namespace", "target_symbol",
                     "target_ensembl", "condition", "donor_pair", "guide_id",
                     "evidence_state")
# Present-and-non-null. ``target_ensembl`` is deliberately ABSENT: it must be
# present as a key, but null is its correct value for a gene_symbol scope.
NON_NULL_ROW_KEYS = ("estimate_type", "estimate_id", "released_estimate_id",
                     "target_id", "target_id_namespace", "target_symbol",
                     "condition")
# Every determined row must bind: how identity was established, WHICH source
# established it, and WHERE in that source (the row locator). "It has a method string
# and a SHA" is not a proof.
PROOF_ROW_KEYS = ("identity_method", "source_id", "source_record_id",
                  "source_sha256", "evidence_state")

# An ENUM, not an arbitrary string. A method we cannot audit cannot prove.
ALLOWED_IDENTITY_METHODS = (
    "released_per_guide_identity_column",
    "cell_level_assigned_guide_barcode_join",
    # Retained ONLY for a genuinely different future input class that actually
    # ships a ready-made contributor table. It is NOT admissible for the current
    # Marson source class: no such table exists in that release.
    "author_supplied_contributor_table",
)

# The source class a manifest reconstructs from. Every manifest must declare one,
# and the identity method must be admissible FOR THAT CLASS.
SOURCE_CLASS_MARSON = "marson_gwcd4i_public_release"
SOURCE_CLASSES = (SOURCE_CLASS_MARSON,)

# For the Marson GWCD4i public release the literal, released evidence is a per-guide
# identity column: GWCD4i.pseudobulk_merged.h5ad carries obs.guide_id alongside
# perturbed_gene_id / culture_condition / keep_for_DE. That column IS the pooled
# contributor set. There is no author-supplied ready-made contributor table, so
# that method is refused for this source class rather than silently accepted.
ADMISSIBLE_IDENTITY_METHODS = {
    SOURCE_CLASS_MARSON: ("released_per_guide_identity_column",),
}

# The manifest is POOLED-CONTRIBUTOR only, keyed to released estimates. The
# quarantined mixed tables are not a permitted provenance.
QUARANTINED_SOURCES = ("contributing_guides.canonical.csv.gz",
                       "contributing_guides.mixed.csv.gz")

DETERMINED = "determined"
AMBIGUOUS = "ambiguous"
EVIDENCE_STATES = (DETERMINED, AMBIGUOUS)

# The source-native replay + COMPLETENESS report. Contributor evidence is admitted
# ONLY if the raw source itself confirmed it; see replay.py.
#
# v1 was EXISTENCE-ONLY: it proved each cited locator pointed at a kept raw row that
# said what the record said. That cannot see a contributor who was silently DROPPED —
# every named guide is real, every hash is right, every locator replays, and the mask
# is still built from an incomplete guide set, which changes the score. v2 additionally
# proves COMPLETENESS against the raw source, so an existence-only report may never be
# labelled the release gate.
REPLAY_SCHEMA = "spot.stage02_source_replay.v2"
SUPERSEDED_REPLAY_SCHEMAS = ("spot.stage02_source_replay.v1",)
REPLAY_REPLAYED = "replayed"

# THE rule ids a v2 report must declare. They are the single source of truth: the
# generator (``replay.py``) stamps them and the validators require them EXACTLY, so a
# report produced under some other rule cannot be read as if it were produced under
# this one. Naming a rule is not obeying it, which is why the arithmetic below is
# checked as well as the id.
REPLAY_RULE_ID = "spot.stage02.direct.replay_rule.v2"
COMPLETENESS_RULE_ID = "spot.stage02.direct.completeness_rule.v2"
# WHICH rule decided determined-vs-ambiguous. Not the manifest — the SOURCE. A report
# computed under any other classification rule answered a different question, and its
# partition says nothing about this one.
SOURCE_CLASSIFICATION_RULE_ID = "spot.stage02.direct.source_classification_rule.v1"

# The completeness fields a v2 report MUST carry. Their absence is not "an older
# report": it is a report that never asked the question. The scope counters are
# REQUIRED, not defaulted — every one of them is an operand of the arithmetic that binds
# the report to the released universe, and a missing operand silently becomes a
# sentinel that some comparison then passes.
#
# The four SOURCE-classification counters are required for the same reason, and for a
# sharper one: a report that carries no source-derived partition cannot show that the
# manifest's ``evidence_state`` labels were ever checked against anything. Its
# determined/ambiguous split is then just the manifest's own claim, restated — and a
# scope can be downgraded out of the evidence set with every total still balancing.
REPLAY_COMPLETENESS_KEYS = ("completeness_verdict", "n_scopes_complete",
                            "n_scopes_incomplete", "n_scopes_determined",
                            "n_scopes_ambiguous", "n_scopes_named",
                            "n_records_offset_proven",
                            "n_nontargeting_guides_cited",
                            "replay_rule_id", "completeness_rule_id",
                            "source_classification_rule_id",
                            "n_scopes_source_determinable",
                            "n_scopes_source_non_determinable",
                            "n_scopes_downgraded", "n_scopes_overclaimed")
REPLAY_COMPLETE = "complete"

# A revision that can move is not a pin.
MUTABLE_REVISIONS = frozenset({"", "main", "master", "head", "latest", "dev",
                               "trunk", "none", "null"})
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_NULLISH = frozenset({"", "none", "nan", "null", "na", "<na>"})

VERIFIED_RAW_BYTES = "raw_bytes_match_trusted_pin"


class ManifestError(ValueError):
    """The contributor manifest is not usable. Refuse; never repair."""


def is_nullish(v: Any) -> bool:
    return v is None or str(v).strip().lower() in _NULLISH


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise ManifestError(msg)


def scope_of(row: dict[str, Any]) -> tuple:
    """The full estimate identity a manifest row belongs to.

    Carries the exact release key AND the WHOLE released target identity: a
    manifest may not claim a scope by gene alone, may not substitute one field for
    another, and may not rename a target's symbol. This is also the only check that
    binds an AMBIGUOUS row — which cites no evidence and so resolves against no
    source record — to the identity the release actually published.
    """
    return (str(row["estimate_type"]), str(row["estimate_id"]),
            str(row["released_estimate_id"]), str(row["target_id"]),
            str(row["target_id_namespace"]), str(row["target_symbol"]),
            None if is_nullish(row.get("target_ensembl"))
            else str(row["target_ensembl"]),
            str(row["condition"]),
            None if is_nullish(row.get("donor_pair")) else str(row["donor_pair"]))


def scope_sort_key(scope: tuple) -> tuple:
    """Order scopes for reporting without comparing None to str."""
    return tuple("" if x is None else str(x) for x in scope)


def row_is_included(row: dict[str, Any]) -> bool:
    """``included`` is false in every spelling a JSON producer might use."""
    return row.get("included", True) not in (False, "false", "False", 0)


def scope_partition(rows: list[dict[str, Any]]) -> tuple[set[tuple], set[tuple]]:
    """The DETERMINED / AMBIGUOUS scope split, derived from the rows themselves.

    The replay report STATES this split, and a stated split is a claim. It has to be
    checked against the manifest the report is describing, because relabelling costs a
    forger nothing and buys them everything: move six scopes from determined to
    ambiguous and every total still balances — named, complete+incomplete, the released
    universe size — while six scopes that DO carry evidence are no longer required to
    have been proven complete. The totals cannot see it. Only the split can.

    A scope is determined iff it has a row that actually claims an identity: state
    ``determined``, still ``included``, and naming a guide. It is ambiguous iff it has
    a row that says the identity is unknown. The two sets must be disjoint and must
    together be every scope in the manifest.
    """
    determined: set[tuple] = set()
    ambiguous: set[tuple] = set()
    for row in rows:
        state = str(row.get("evidence_state", DETERMINED)).strip().lower()
        scope = scope_of(row)
        if state == DETERMINED and row_is_included(row) \
                and not is_nullish(row.get("guide_id")):
            determined.add(scope)
        elif state == AMBIGUOUS:
            ambiguous.add(scope)
    return determined, ambiguous


def canonical_row_key(row: dict[str, Any]) -> tuple:
    return scope_sort_key(scope_of(row)
                          + (None if is_nullish(row.get("guide_id"))
                             else str(row["guide_id"]),))


def canonical_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Row ORDER carries no meaning, so it must not carry identity either.

    A manifest listing the same evidence in another order is the same manifest. It
    is canonically ordered here, so the canonical hash, the run_id and every emitted
    artifact are invariant to how the producer happened to serialise its rows.
    """
    return sorted(rows, key=canonical_row_key)
