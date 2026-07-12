"""The exact contributing-guide contract. FAIL CLOSED.

Every effect estimate Stage-2 projects is keyed by

    estimate_type x estimate_id x target x condition x donor_pair? x guide_id

with ONE row per contributing guide. A mask may only ever be built from the
guides that actually contributed to that specific estimate: an unused library
guide can never enter a mask, and an ambiguous estimate is never scored.

Resolution ladder (frozen, ``config.GUIDE_RESOLUTION_LADDER``):

1. ``manifest`` — an explicit, source-hash-bound contributing-guide manifest
   (``manifest.py``), proven per row and covering exactly the GLOBAL pooled-main
   released scope universe (``domain.py``).
2. ``unresolved`` — no mask, no score, no support.

There is NO third rung. The released by-guide object carries no per-row sgRNA
identity. The public release README does define the slots by alphanumeric guide-ID
rank — that is a PUBLISHED rule, not a guess — but a slot NAME still is not evidence
of which guide contributed to a given estimate, so no slot->guide mapping is used
here. Without a manifest row every estimate is unresolved: the designed outcome, not
a degradation.

SUPPORT IS OUT OF DOMAIN IN THIS PASS. Only pooled-main estimates carry contributor
evidence, so a guide-slot or donor-pair estimate resolves to an explicit UNAVAILABLE
state — never to a borrowed pooled contributor set, and never to a slot guessed from
a name.

WHY THERE IS NO SLOT-CONTRADICTION GATE. An earlier rule refused a TARGET outright
when the released guide slots disagreed with the pooled ``n_guides``. Measured against
the release, that rule would have refused 6,707 of 33,374 targets — and it refused the
POOLED estimate too, on the strength of support metadata the pooled fit never depended
on. The support objects' ``n_guides`` is COPIED pooled metadata (59,414/59,414 guide
rows; 29,279/29,279 donor rows), not each estimate's own contributor count, so a
"contradiction" between them was largely an artefact of reading a copy as an
independent witness. The pooled estimate is resolved from the pooled manifest and the
pooled ``n_guides`` alone; a support object can no longer take it down.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from . import domain
from . import manifest as mf

MAIN = "main"
GUIDE = "guide"
DONOR_PAIR = "donor_pair"

RESOLVED = "resolved"
UNRESOLVED = "unresolved"

# Unresolved reasons (exhaustive; each is emitted, never collapsed to "missing").
UNRESOLVED_TARGET_IDENTITY = "unresolved_target_identity"
NO_CONTRIBUTOR_MANIFEST = "no_contributor_manifest_guide_identity_unavailable"
TARGET_ABSENT_FROM_LIBRARY = "target_absent_from_guide_library"
DUPLICATE_GUIDE_IN_LIBRARY = "duplicate_guide_id_in_library"
N_GUIDES_MISSING = "estimate_n_guides_missing"
# Support has no contributor evidence in the pooled-main domain, and says so.
SUPPORT_OUT_OF_DOMAIN = domain.SUPPORT_UNAVAILABLE
ABSENT_FROM_MANIFEST = "absent_from_guide_manifest"
MANIFEST_GUIDE_NOT_IN_LIBRARY = "manifest_guide_not_in_library"
MANIFEST_DUPLICATE_GUIDE = "manifest_duplicate_guide_id"
MANIFEST_COUNT_DISAGREES = "manifest_guide_count_disagrees_with_source"
MANIFEST_CELLS_DISAGREE = "manifest_n_cells_disagrees_with_source"
MANIFEST_GUIDE_EXCLUDED = "manifest_guide_not_included_in_estimate"
MANIFEST_EVIDENCE_AMBIGUOUS = "manifest_guide_identity_ambiguous"
MANIFEST_ROW_UNPROVEN = "manifest_row_lacks_identity_proof"


@dataclass(frozen=True)
class Estimate:
    """One effect estimate that Stage-2 may project.

    Carries the WHOLE released target identity, not just the gene: the manifest join is
    on the full scope, so a record that agrees about the gene but not about the
    namespace it was named in, its symbol, or the release key cannot stand in as
    evidence for a scope it does not describe.
    """
    estimate_type: str            # main | guide | donor_pair
    estimate_id: str              # "main" | "guide_1" | "CE0006864_CE0008162"
    released_estimate_id: str     # EXACT obs.index; never parsed
    target_id: str                # EXACT obs.target_contrast
    target_ensembl: Optional[str] # nullable; explicit sources only (the RUN's id)
    condition: str
    n_guides: Optional[float]     # the ESTIMATE's OWN contributing-guide count
    donor_pair: Optional[str] = None
    n_cells: Optional[float] = None       # the estimate's own cell count, if any
    # The identity as the RELEASE published it. ``released_target_ensembl`` is null for
    # every gene_symbol scope even when a run-level map later enriched target_ensembl:
    # the contributor evidence describes the release, not the run.
    target_id_namespace: Optional[str] = None
    target_symbol: Optional[str] = None
    released_target_ensembl: Optional[str] = None


@dataclass(frozen=True)
class Contributors:
    """Resolved (or explicitly unresolved) contributing guides for one estimate."""
    status: str                                   # resolved | unresolved
    guide_ids: tuple[str, ...] = ()
    source: Optional[str] = None                  # "manifest" (the only source)
    reason: Optional[str] = None

    @property
    def resolved(self) -> bool:
        return self.status == RESOLVED


@dataclass(frozen=True)
class LibraryTarget:
    # sorted only so emission is deterministic; the ORDER carries no identity and
    # is never used to map a released slot to a guide
    guide_ids: tuple[str, ...]
    rows: dict[str, dict[str, Any]] = field(default_factory=dict)
    duplicate_guide_ids: tuple[str, ...] = ()


def build_library(rows_by_target: dict[str, list[dict[str, Any]]],
                  guide_id_column: str = "sgRNA") -> dict[str, LibraryTarget]:
    """Index the sgRNA library by target, for MASK LOOKUP ONLY.

    This index answers "what does guide X mask?" once a manifest has named X. It
    never answers "which guide is behind slot N" — neither library row order nor
    sgRNA-name order is consulted for identity. Duplicate sgRNA IDs for a target
    are recorded, not silently de-duplicated: a duplicate makes every estimate for
    that target unresolved.
    """
    library: dict[str, LibraryTarget] = {}
    for target, rows in rows_by_target.items():
        seen: dict[str, dict] = {}
        dupes: list[str] = []
        for row in rows:
            gid = row.get(guide_id_column)
            if gid is None or str(gid).strip() in ("", "nan", "None"):
                continue
            gid = str(gid)
            if gid in seen:
                dupes.append(gid)
                continue
            seen[gid] = row
        library[str(target)] = LibraryTarget(
            guide_ids=tuple(sorted(seen)),          # deterministic emission only
            rows=seen,
            duplicate_guide_ids=tuple(sorted(set(dupes))),
        )
    return library


def _as_int(v: Optional[float]) -> Optional[int]:
    try:
        return None if v is None else int(v)
    except (TypeError, ValueError):
        return None


def _manifest_key(est: Estimate) -> tuple:
    """The FULL released scope identity — the same 9-tuple ``manifest.scope_of`` makes.

    A reduced join (release key + target + condition) would let a manifest row that
    agrees about the gene but renames its symbol, or moves it to another namespace,
    still resolve as evidence for this estimate. The scope is the whole identity or it
    is not an identity.
    """
    # Normalised exactly as ``manifest.scope_of`` normalises: everything a string,
    # except the two fields that are null BY CONTRACT (released Ensembl for a
    # gene_symbol scope, donor_pair for a pooled scope).
    return (str(est.estimate_type), str(est.estimate_id),
            str(est.released_estimate_id), str(est.target_id),
            str(est.target_id_namespace), str(est.target_symbol),
            None if mf.is_nullish(est.released_target_ensembl)
            else str(est.released_target_ensembl),
            str(est.condition),
            None if mf.is_nullish(est.donor_pair) else str(est.donor_pair))


def build_manifest_index(rows: Iterable[dict[str, Any]]) -> dict[tuple, list[dict]]:
    """Index the contributor manifest by the FULL released scope identity.

    Keyed exactly as ``manifest.scope_of`` keys it, so the runtime join and the
    structural scope-universe check are asking the same question. Structural integrity
    (null keys, duplicates, scope-universe match, source pinning) is enforced in
    ``manifest.py`` first.
    """
    index: dict[tuple, list[dict]] = {}
    for row in rows:
        index.setdefault(mf.scope_of(row), []).append(row)
    return index


def _proven(row: dict[str, Any]) -> bool:
    """A slot->guide row is usable only if it says how it was proven."""
    method = row.get("identity_method")
    sha = row.get("source_sha256")
    return bool(method) and not mf.is_nullish(method) \
        and bool(sha) and not mf.is_nullish(sha)


def _from_manifest(est: Estimate, index: dict[tuple, list[dict]],
                   lib: Optional[LibraryTarget]) -> Contributors:
    rows = index.get(_manifest_key(est))
    if not rows:
        return Contributors(status=UNRESOLVED, reason=ABSENT_FROM_MANIFEST)

    # An ambiguous identity stays UNAVAILABLE. It is never rounded to a guess.
    if any(str(r.get("evidence_state", mf.DETERMINED)).lower() == mf.AMBIGUOUS
           for r in rows):
        return Contributors(status=UNRESOLVED, reason=MANIFEST_EVIDENCE_AMBIGUOUS)
    if not all(_proven(r) for r in rows):
        return Contributors(status=UNRESOLVED, reason=MANIFEST_ROW_UNPROVEN)

    included = [r for r in rows
                if r.get("included", True) not in (False, "false", "False", 0)]
    if not included:
        return Contributors(status=UNRESOLVED, reason=MANIFEST_GUIDE_EXCLUDED)

    gids = [str(r["guide_id"]) for r in included]
    if any(mf.is_nullish(g) for g in gids):
        return Contributors(status=UNRESOLVED, reason=MANIFEST_ROW_UNPROVEN)
    if len(set(gids)) != len(gids):
        return Contributors(status=UNRESOLVED, reason=MANIFEST_DUPLICATE_GUIDE)
    if lib is None or not lib.guide_ids:
        return Contributors(status=UNRESOLVED, reason=TARGET_ABSENT_FROM_LIBRARY)
    if lib.duplicate_guide_ids:
        return Contributors(status=UNRESOLVED, reason=DUPLICATE_GUIDE_IN_LIBRARY)
    if any(g not in lib.rows for g in gids):
        return Contributors(status=UNRESOLVED, reason=MANIFEST_GUIDE_NOT_IN_LIBRARY)

    # Cross-check the manifest against the POOLED estimate's own obs fields. This is
    # the pooled n_guides from the DE release itself — not a support object's copy of
    # it, which is what the retired slot-contradiction rule was really reading.
    declared = _as_int(est.n_guides)
    if declared is None:
        return Contributors(status=UNRESOLVED, reason=N_GUIDES_MISSING)
    if declared != len(gids):
        return Contributors(status=UNRESOLVED, reason=MANIFEST_COUNT_DISAGREES)
    if est.n_cells is not None:
        cells = [r.get("n_cells") for r in included
                 if not mf.is_nullish(r.get("n_cells"))]
        if cells and abs(sum(float(c) for c in cells) - float(est.n_cells)) > 0.5 \
                and all(abs(float(c) - float(est.n_cells)) > 0.5 for c in cells):
            return Contributors(status=UNRESOLVED, reason=MANIFEST_CELLS_DISAGREE)

    return Contributors(status=RESOLVED, guide_ids=tuple(sorted(gids)),
                        source="manifest")


def resolve(est: Estimate, library: dict[str, LibraryTarget],
            manifest_index: Optional[dict[tuple, list[dict]]] = None) -> Contributors:
    """Resolve the contributing guides of one estimate, or refuse explicitly.

    There is no inference path: without a manifest row proving the identity of the
    guides behind THIS estimate, the estimate is unresolved.

    Nothing about a SUPPORT object can refuse a pooled estimate. The pooled fit is
    resolved from the pooled manifest row and the pooled ``n_guides``; the by-guide and
    donor objects are not consulted, so their copied metadata can no longer take a
    valid main estimate down.
    """
    # Support is outside the evidence domain of this pass. It gets an explicit
    # unavailable state — never a pooled contributor set borrowed sideways.
    if est.estimate_type != MAIN:
        return Contributors(status=UNRESOLVED, reason=SUPPORT_OUT_OF_DOMAIN)

    # A target with no resolved Ensembl id cannot be joined to the sgRNA library
    # (which is keyed by Ensembl gene id). It is NOT masked as if its symbol were
    # an accession: it stays in the disposition table, explicitly unresolved.
    if est.target_ensembl is None:
        return Contributors(status=UNRESOLVED, reason=UNRESOLVED_TARGET_IDENTITY)

    # No manifest -> no guide identity. The lane does not read the slot name.
    if manifest_index is None:
        return Contributors(status=UNRESOLVED, reason=NO_CONTRIBUTOR_MANIFEST)

    return _from_manifest(est, manifest_index, library.get(est.target_ensembl))


def contributor_rows(est: Estimate, contrib: Contributors) -> list[dict[str, Any]]:
    """Emit the contributing-guide contract rows for one estimate.

    Unresolved estimates emit exactly one row with a null guide_id and the
    explicit reason, so every estimate is accounted for.
    """
    base = {
        "estimate_type": est.estimate_type,
        "estimate_id": est.estimate_id,
        "released_estimate_id": est.released_estimate_id,
        "target_id": est.target_id,
        "target_ensembl": est.target_ensembl,
        "condition": est.condition,
        "donor_pair": est.donor_pair,
        "contributor_status": contrib.status,
        "contributor_source": contrib.source,
        "contributor_unresolved_reason": contrib.reason,
        "n_guides_declared": _as_int(est.n_guides),
        "n_cells_declared": est.n_cells,
    }
    if not contrib.resolved:
        return [dict(base, guide_id=None)]
    return [dict(base, guide_id=gid) for gid in contrib.guide_ids]
