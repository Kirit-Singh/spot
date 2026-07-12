"""Target identity, taken from the release rather than guessed from a key.

The released ``obs.index`` is a UNIQUE RELEASE-ESTIMATE KEY (target + condition).
Its ENSG-looking prefix is NOT the target identity. Verified against the complete
public release (33,983 rows): exactly 12 dispositions carry a NON-Ensembl
``obs.target_contrast`` — 4 symbols x 3 conditions —

    target_id   conditions                 released_estimate_id       flags
    MTRNR2L1    Rest, Stim8hr, Stim48hr    ENSG00000256618_<cond>     ontarget_significant=false
    MTRNR2L4    Rest, Stim8hr, Stim48hr    ENSG00000232196_<cond>     low_target_gex=true
    MTRNR2L8    Rest, Stim8hr, Stim48hr    ENSG00000255823_<cond>     n_guides=2
    OCLM        Rest, Stim8hr, Stim48hr    OCLM_<cond>

Nine of those keys carry an ENSG-looking prefix that belongs to a DIFFERENT gene
than the symbol being targeted; OCLM's key is symbol-prefixed. Parsing any prefix
and promoting it to the target's Ensembl id would silently attach the wrong gene
to a mask and to any downstream drug identity. Non-significant / low-expression
flags are NOT a reason to drop these rows: all 33,983 dispositions are emitted. So:

  * ``released_estimate_id`` is the exact frozen ``obs.index``, preserved verbatim
    and never parsed;
  * ``target_id`` is the exact ``obs.target_contrast``, whatever namespace it is in;
  * ``target_id_namespace`` says which namespace that value is in;
  * ``target_ensembl`` is a SEPARATE, NULLABLE field, populated only from an
    explicit source field (the target_id already being an Ensembl accession) or an
    explicit author-supplied mapping. It never comes from the estimate key.

A target with no resolved Ensembl id cannot be masked (the sgRNA library joins on
Ensembl gene id) and cannot carry a drug identity, so it stays in the all-result
disposition table as ``unresolved_target_identity`` — never masked or ranked as if
the symbol were an accession.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Optional

# The controlled namespace vocabulary. BINARY, and decided ONLY by the literal
# value of obs.target_contrast against the contract's exact Ensembl rule.
ENSEMBL_GENE_ID = "ensembl_gene_id"
GENE_SYMBOL = "gene_symbol"
NAMESPACES = (ENSEMBL_GENE_ID, GENE_SYMBOL)

# THE exact Ensembl identifier rule used by the whole contract.
ENSG_RE = re.compile(r"^ENSG[0-9]+$")


def is_ensembl_gene_id(value: Any) -> bool:
    """The one Ensembl rule, used by identity, masks, schema and verifier alike."""
    return bool(ENSG_RE.match("" if value is None else str(value)))

IDENTITY_MAP_SCHEMA = "spot.stage02_target_identity_map.v1"

# --------------------------------------------------------------------------- #
# THE generic target-identity contract.
#
# Stated once, here, and enforced by every artifact that carries a released target
# identity: screen rows, contributor-manifest rows and source records. The
# standalone verifier REIMPLEMENTS it from this specification rather than importing
# it, so a bug here cannot be reproduced by the checker meant to catch it.
#
#   * released_estimate_id is provenance ONLY. It is preserved verbatim and is
#     never parsed, split or pattern-matched to satisfy ANY target field.
#   * ensembl_gene_id  => target_id IS an Ensembl accession, and target_ensembl is
#                         that same accession, exactly.
#   * gene_symbol      => target_id is NOT an accession, and target_ensembl is NULL.
#
# The second rule is what refuses the release's own trap: nine of the twelve
# symbol scopes carry an ENSG-looking release key belonging to a DIFFERENT gene.
# Promoting that prefix into target_ensembl is refused as a gene_symbol row with a
# non-null target_ensembl — the key itself is never inspected, not even to phrase
# the refusal.
#
# target_symbol is REQUIRED and non-empty: verified against the complete public
# release, all 33,983 rows carry a non-empty obs.target_contrast_gene_name (six of
# them are themselves ENSG-looking, which is permitted — a symbol is an exact
# string, not a pattern).
# --------------------------------------------------------------------------- #
IDENTITY_FIELDS = ("released_estimate_id", "target_id", "target_id_namespace",
                   "target_symbol", "target_ensembl")

# Exact refusal reasons. Each names the ONE invariant that broke; none is collapsed
# into a generic "invalid identity".
MISSING_RELEASED_ESTIMATE_ID = "released_estimate_id_missing"
MISSING_TARGET_ID = "target_id_missing"
MISSING_TARGET_SYMBOL = "target_symbol_missing"
BAD_NAMESPACE = "target_id_namespace_not_in_enum"
ENSEMBL_NS_TARGET_ID_NOT_ENSEMBL = (
    "namespace_ensembl_gene_id_but_target_id_is_not_an_ensembl_gene_id")
ENSEMBL_NS_ENSEMBL_NOT_TARGET_ID = (
    "namespace_ensembl_gene_id_but_target_ensembl_does_not_equal_target_id")
SYMBOL_NS_TARGET_ID_IS_ENSEMBL = (
    "namespace_gene_symbol_but_target_id_is_an_ensembl_gene_id")
SYMBOL_NS_ENSEMBL_NOT_NULL = (
    "namespace_gene_symbol_but_target_ensembl_is_not_null")


def identity_violation(row: dict[str, Any]) -> Optional[str]:
    """The exact reason a row's target identity is inadmissible, or None.

    Value rules only: FIELD PRESENCE is the caller's contract (``REQUIRED_ROW_KEYS``
    / ``REQUIRED_RECORD_COLUMNS``), because a row that omits ``target_ensembl``
    entirely is a different failure from one that fills it in wrongly.
    """
    if _nullish(row.get("released_estimate_id")):
        return MISSING_RELEASED_ESTIMATE_ID
    if _nullish(row.get("target_id")):
        return MISSING_TARGET_ID
    if _nullish(row.get("target_symbol")):
        return MISSING_TARGET_SYMBOL

    namespace = row.get("target_id_namespace")
    if not isinstance(namespace, str) or namespace not in NAMESPACES:
        return BAD_NAMESPACE

    target_id = str(row["target_id"])
    ensembl = row.get("target_ensembl")
    if namespace == ENSEMBL_GENE_ID:
        if not is_ensembl_gene_id(target_id):
            return ENSEMBL_NS_TARGET_ID_NOT_ENSEMBL
        # EQUALITY, not merely "looks like an accession": a well-formed ENSG that
        # is not this target's accession is a different gene.
        if _nullish(ensembl) or str(ensembl) != target_id:
            return ENSEMBL_NS_ENSEMBL_NOT_TARGET_ID
    else:
        if is_ensembl_gene_id(target_id):
            return SYMBOL_NS_TARGET_ID_IS_ENSEMBL
        if not _nullish(ensembl):
            return SYMBOL_NS_ENSEMBL_NOT_NULL
    return None


class IdentityError(ValueError):
    """The target-identity map is unusable."""


def _nullish(v: Any) -> bool:
    return v is None or str(v).strip().lower() in ("", "none", "nan", "null")


@dataclass(frozen=True)
class TargetIdentity:
    released_estimate_id: str          # exact obs.index; never parsed
    target_id: str                     # exact obs.target_contrast
    target_id_namespace: str
    target_symbol: Optional[str]
    target_ensembl: Optional[str]      # nullable; explicit sources only
    ensembl_source: str                # how the Ensembl id (if any) was obtained

    @property
    def ensembl_resolved(self) -> bool:
        return self.target_ensembl is not None

    @property
    def released_target_ensembl(self) -> Optional[str]:
        """The Ensembl id the RELEASE itself carries — null for every symbol scope.

        ``target_ensembl`` may additionally be enriched for the RUN by an explicit
        identity map. That enrichment is a run-level claim, not something the
        release said, so the contributor-evidence contract binds THIS field: the
        manifest and the source records describe the released identity, and a
        gene_symbol scope's released Ensembl id is null whether or not a map later
        supplies one.
        """
        return self.target_id if self.target_id_namespace == ENSEMBL_GENE_ID else None


def load_identity_map(path: Optional[str]) -> dict[str, str]:
    """An EXPLICIT author-supplied target_id -> Ensembl gene id mapping.

    This is the only way a non-Ensembl ``target_id`` may acquire an Ensembl id.
    Every mapped value must be a real Ensembl accession.
    """
    if not path:
        return {}
    with open(path) as fh:
        doc = json.load(fh)
    if str(doc.get("schema_version", "")) != IDENTITY_MAP_SCHEMA:
        raise IdentityError(
            f"target-identity map: schema_version must be {IDENTITY_MAP_SCHEMA!r}")
    mapping = doc.get("map") or {}
    out: dict[str, str] = {}
    for k, v in mapping.items():
        if not ENSG_RE.match(str(v)):
            raise IdentityError(
                f"target-identity map: {k!r} -> {v!r} is not an Ensembl gene id")
        out[str(k)] = str(v)
    return out


def resolve(released_estimate_id: Any, target_contrast: Any,
            target_gene_name: Any = None,
            identity_map: Optional[dict[str, str]] = None) -> TargetIdentity:
    """Build the target identity from the release's OWN fields.

    ``released_estimate_id`` is carried through verbatim and is NEVER split,
    stripped or pattern-matched to produce an identity.
    """
    rel = "" if released_estimate_id is None else str(released_estimate_id)
    target_id = "" if target_contrast is None else str(target_contrast)
    symbol = None if _nullish(target_gene_name) else str(target_gene_name)

    ensembl: Optional[str] = None
    source = "none"

    if is_ensembl_gene_id(target_id):
        # the NAMED source field obs.target_contrast literally IS an Ensembl id
        namespace = ENSEMBL_GENE_ID
        ensembl = target_id
        source = "obs.target_contrast_is_an_ensembl_gene_id"
    else:
        # not an Ensembl id -> gene symbol. The released_estimate_id is NEVER
        # consulted: its ENSG-looking prefix is a release key, not an identity.
        namespace = GENE_SYMBOL

    if ensembl is None and identity_map:
        mapped = identity_map.get(target_id)
        if mapped and ENSG_RE.match(mapped):
            ensembl = mapped
            source = "explicit_target_identity_map"

    return TargetIdentity(
        released_estimate_id=rel,
        target_id=target_id,
        target_id_namespace=namespace,
        target_symbol=symbol,
        target_ensembl=ensembl,
        ensembl_source=source,
    )
