"""The contributor manifest's VALIDATORS: sources, rows, and the replay gate.

Three independent refusals, each stated once:

  * ``validate_sources`` — a self-declared hash establishes nothing. Every source
    must appear in an independently trusted registry with the SAME sha256 and
    revision, AND hash to that pin on disk.
  * ``validate_rows``    — null keys, duplicate scope+guide, an inadmissible target
    identity, an unprovable determined row, or ANY divergence from the released
    scope universe fails closed.
  * ``validate_replay``  — the release gate: the evidence must have been confirmed by
    the raw SOURCE, not merely by a table that agrees with the manifest.

Structural validity is not evidence: these checks cannot certify that a well-formed
manifest is scientifically correct. A manifest emitted by an unaudited or quarantined
process must not be used.
"""
from __future__ import annotations

import os
from typing import Any, Optional

from . import domain, identity
from .hashing import file_sha256
from .manifest_schema import (ADMISSIBLE_IDENTITY_METHODS, ALLOWED_IDENTITY_METHODS,
                              AMBIGUOUS, DETERMINED, EVIDENCE_STATES,
                              ManifestError, MUTABLE_REVISIONS, NON_NULL_ROW_KEYS,
                              PROOF_ROW_KEYS, QUARANTINED_SOURCES,
                              REQUIRED_ROW_KEYS, SHA256_RE, VERIFIED_RAW_BYTES,
                              is_nullish, require, scope_of, scope_sort_key)


# --------------------------------------------------------------------------- #
# Source pinning.
# --------------------------------------------------------------------------- #
def validate_sources(sources: Any,
                     source_registry: Optional[dict[str, dict]] = None,
                     base_dir: str = "") -> list[dict[str, str]]:
    """Every source must be pinned AND independently verified.

    A self-declared hash establishes nothing: the manifest is not a witness to its
    own provenance. Each declared source must (a) appear in an independently
    trusted source registry with the SAME sha256 and revision, and (b) exist on
    disk with raw bytes that hash to that pin.
    """
    require(isinstance(sources, list) and bool(sources),
            "contributor manifest: 'sources' must be a non-empty list")
    require(source_registry is not None,
            "contributor manifest: no trusted source registry was supplied; a "
            "self-declared source hash cannot establish provenance")

    out = []
    for src in sources:
        require(isinstance(src, dict),
                "contributor manifest: malformed source entry")
        name = str(src.get("name") or "")
        sha = str(src.get("sha256", "")).strip().lower()
        rev = str(src.get("revision", "")).strip()
        require(bool(name), "contributor manifest: a source has no name")
        require(name not in QUARANTINED_SOURCES,
                f"contributor manifest: source {name!r} is QUARANTINED and may "
                "not be consumed")
        require(bool(SHA256_RE.match(sha)),
                f"contributor manifest: source {name!r} has no valid sha256 "
                f"(got {src.get('sha256')!r})")
        require(rev.lower() not in MUTABLE_REVISIONS,
                f"contributor manifest: source {name!r} is pinned to the mutable "
                f"revision {rev!r}; an unpinned source is not a pin")

        pin = source_registry.get(name)
        require(pin is not None,
                f"contributor manifest: source {name!r} is not in the trusted "
                "source registry; an unlisted source cannot establish identity")
        require(str(pin.get("sha256", "")).lower() == sha,
                f"contributor manifest: source {name!r} declares sha256 {sha!r} "
                f"but the trusted registry pins {pin.get('sha256')!r}")
        require(str(pin.get("revision", "")) == rev,
                f"contributor manifest: source {name!r} declares revision {rev!r} "
                f"but the trusted registry pins {pin.get('revision')!r}")

        # ...and the bytes on disk must actually hash to the pin.
        path = os.path.join(base_dir, str(pin.get("path", "")))
        require(bool(pin.get("path")) and os.path.exists(path),
                f"contributor manifest: source {name!r} is not present at its "
                "trusted registry path; an absent source cannot be verified")
        actual = file_sha256(path)
        require(actual == sha,
                f"contributor manifest: source {name!r} raw bytes hash to "
                f"{actual!r}, not to the pinned {sha!r}")

        out.append({"name": name, "sha256": sha, "revision": rev,
                    "verified": VERIFIED_RAW_BYTES})
    return sorted(out, key=lambda s: s["name"])


# --------------------------------------------------------------------------- #
# Structural validation against the released estimate universe.
# --------------------------------------------------------------------------- #
def validate_rows(rows: list[dict[str, Any]],
                  released_scopes: Optional[set[tuple]] = None,
                  source_shas: Optional[dict[str, str]] = None,
                  source_class: Optional[str] = None) -> None:
    """Fail closed on null keys, duplicates, and any scope-universe divergence."""
    require(isinstance(rows, list) and bool(rows),
            "contributor manifest: 'rows' must be a non-empty list")

    seen: set[tuple] = set()
    n_guides_by_scope: dict[tuple, Any] = {}

    for i, row in enumerate(rows):
        missing = [k for k in REQUIRED_ROW_KEYS if k not in row]
        require(not missing,
                f"contributor manifest row {i}: missing keys {missing}")

        # A null anywhere in the identity is a null identity. The quarantined
        # table's None_None rows are exactly this shape.
        for key in NON_NULL_ROW_KEYS:
            require(not is_nullish(row[key]),
                    f"contributor manifest row {i}: null key component "
                    f"{key}={row[key]!r}")

        # THE EVIDENCE DOMAIN. This artifact is all-condition POOLED-MAIN, and every
        # row must say so. A by-guide or donor-pair row here is not extra evidence: it
        # is a claim this pass has no method to check, and admitting it would let a
        # support estimate acquire a mask and a tier it never earned.
        breach = domain.domain_violation(row)
        require(breach is None,
                f"contributor manifest row {i}: {breach}. The pooled-main evidence "
                f"domain ({domain.DOMAIN_ID}) admits only pooled-main scopes; "
                "by-guide and donor-pair support needs its own provenance method and "
                "its own contract, and has neither in this pass")

        # THE released target identity, by the one shared rule. This is what
        # refuses an ENSG-looking release key promoted into target_ensembl.
        violation = identity.identity_violation(row)
        require(violation is None,
                f"contributor manifest row {i}: inadmissible target identity "
                f"({violation}); target_id={row['target_id']!r} "
                f"namespace={row['target_id_namespace']!r} "
                f"target_ensembl={row.get('target_ensembl')!r}. The "
                "released_estimate_id is provenance only and never supplies a "
                "target field.")

        included = row.get("included", True) not in (False, "false", "False", 0)
        state = str(row.get("evidence_state", DETERMINED)).strip().lower()
        require(state in EVIDENCE_STATES,
                f"contributor manifest row {i}: evidence_state must be one of "
                f"{list(EVIDENCE_STATES)}, got {row.get('evidence_state')!r}")

        if state == AMBIGUOUS:
            # An ambiguous row asserts that the identity is UNKNOWN, and resolution
            # therefore skips it. So it may not ALSO cite evidence: an unchecked
            # citation is exactly where a fabrication would hide. It is NOT held to
            # the determined-row proof rules — a row that proves nothing owes no
            # proof, and the release's own ambiguous scopes omit those fields.
            require(is_nullish(row["guide_id"]),
                    f"contributor manifest row {i}: an ambiguous row names "
                    f"guide_id {row['guide_id']!r}; an unknown identity is not a "
                    "guide")
            require(is_nullish(row.get("source_record_id")),
                    f"contributor manifest row {i}: an ambiguous row cites "
                    f"source_record_id {row.get('source_record_id')!r}; a row that "
                    "claims no identity cannot hold evidence for one")

        if included and state == DETERMINED:
            require(not is_nullish(row["guide_id"]),
                    f"contributor manifest row {i}: a determined, included row "
                    f"has no guide_id ({row['guide_id']!r})")
            for key in PROOF_ROW_KEYS:
                require(key in row and not is_nullish(row[key]),
                        f"contributor manifest row {i}: a determined row must "
                        f"bind {key!r}")
            method = str(row["identity_method"])
            require(method in ALLOWED_IDENTITY_METHODS,
                    f"contributor manifest row {i}: identity_method "
                    f"{method!r} is not one of "
                    f"{list(ALLOWED_IDENTITY_METHODS)}; an arbitrary method "
                    "string is not a proof")
            if source_class is not None:
                admissible = ADMISSIBLE_IDENTITY_METHODS[source_class]
                require(method in admissible,
                        f"contributor manifest row {i}: identity_method "
                        f"{method!r} is NOT admissible for source_class "
                        f"{source_class!r} (admissible: {list(admissible)}). The "
                        "released evidence for this source is a per-guide identity "
                        "column; there is no author-supplied contributor table.")
            if source_shas is not None:
                sid = str(row["source_id"])
                require(sid in source_shas,
                        f"contributor manifest row {i}: source_id {sid!r} is not "
                        "one of the manifest's verified sources")
                require(str(row["source_sha256"]).lower() == source_shas[sid],
                        f"contributor manifest row {i}: source_sha256 does not "
                        f"match the verified hash of source {sid!r}")

        scope = scope_of(row)
        gid = None if is_nullish(row["guide_id"]) else str(row["guide_id"])
        require((scope, gid) not in seen,
                f"contributor manifest row {i}: duplicate scope+guide "
                f"{scope} / {gid!r}")
        seen.add((scope, gid))

        if "n_guides" in row and not is_nullish(row["n_guides"]):
            prev = n_guides_by_scope.setdefault(scope, row["n_guides"])
            require(int(float(prev)) == int(float(row["n_guides"])),
                    f"contributor manifest row {i}: scope {scope} declares "
                    f"conflicting n_guides {prev!r} and {row['n_guides']!r}")

    if released_scopes is None:
        return

    manifest_scopes = {scope_of(r) for r in rows}
    extra = sorted(manifest_scopes - released_scopes, key=scope_sort_key)
    missing_scopes = sorted(released_scopes - manifest_scopes, key=scope_sort_key)
    if extra:
        raise ManifestError(
            f"contributor manifest covers {len(extra)} scope(s) that the release "
            f"does not contain (first: {extra[0]})")
    if missing_scopes:
        raise ManifestError(
            f"contributor manifest is missing {len(missing_scopes)} released "
            f"scope(s) (first: {missing_scopes[0]})")
