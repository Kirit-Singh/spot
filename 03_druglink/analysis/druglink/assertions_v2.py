"""The v2 SOURCE-ASSERTION layer: what a drug assertion IS, and where it can be reopened.

Split out of :mod:`druglink.edges_v2` (which owns the arm x target x assertion EDGE) at the
500-line gate — the same seam ``universe_rows`` / ``universe_edges`` already draw between
target identity and source assertion.

A source record travels with the result even when it can never rank a gene. A dropped
assertion is indistinguishable from a drug nobody found, and the store's whole point is that
those are different things.

THREE THINGS EVERY SOURCE RECORD MUST CARRY (the Stage-4 read contract)
----------------------------------------------------------------------
1. **An address.** ``source_locator`` names the exact row the assertion came from —
   ``chembl:CHEMBL_37:drug_mechanism/7600``. A source record that cannot be reopened at its
   origin is an assertion with no address, and "ChEMBL says so" is not provenance.
2. **A release.** ``source_release`` / ``source_sha256`` / ``source_license`` name the exact
   bytes it was drawn from. They are read from the ADMITTED STORE's own manifest and are never
   hardcoded here: a release constant in a source file is a claim about data the file has
   never seen.
3. **Stated absence.** Every nullable magnitude carries a companion ``*_status`` that SAYS why
   it is absent (``not_stated_by_source`` / ``not_applicable_inferred_origin`` /
   ``unranked_by_source``). Absence is a value, never a missing key — a null that a consumer
   coerces becomes a 0, and a 0 sorts. That is the defect this project keeps finding.
"""
from __future__ import annotations

from typing import Any, Mapping

from . import identity
from . import universe_rows as ur

ASSERTIONS_V2_POLICY_VERSION = "stage3-assertions-v2-addressable-sources"

# The scheme every ChEMBL mechanism row is addressed under. A locator is not a URL: it is a
# stable, resolvable coordinate — release + table + row id — that a reader can reopen.
SOURCE_SCHEME_CHEMBL = "chembl"
SOURCE_TABLE_DRUG_MECHANISM = "drug_mechanism"

# --------------------------------------------------------------------------- #
# The MISSINGNESS vocabulary. Absence is STATED, never inferred from a null.
#
# Null must never become 0, and must never sort last by accident. A consumer that reads a
# null rank as 0 has invented a first-place finish for a target nobody ranked.
# --------------------------------------------------------------------------- #
STATED = "stated"
NOT_STATED = "not_stated_by_source"
NOT_APPLICABLE_INFERRED = "not_applicable_inferred_origin"
RANKED = "ranked"
UNRANKED = "unranked_by_source"
NO_DRUG_EVIDENCE = "no_general_drug_evidence"
MISSINGNESS_STATES = (STATED, NOT_STATED, NOT_APPLICABLE_INFERRED, RANKED, UNRANKED,
                      NO_DRUG_EVIDENCE)

# Every column here is a nullable value whose absence must be SPOKEN by its companion.
STATUS_FOR_VALUE = {
    "max_phase_source": "max_phase_status",
    "inchikey": "inchikey_status",
    "arm_rank": "arm_rank_status",
    "arm_value_source_string": "arm_value_status",
}

GATE_NO_SOURCE_LOCATOR = "a_source_record_has_no_addressable_locator"
GATE_NO_SOURCE_RELEASE = "a_source_record_names_no_release"
GATE_ABSENCE_NOT_STATED = "absence_is_not_stated_explicitly"

SOURCE_RECORD_COLUMNS: tuple[str, ...] = (
    "source_record_id", "mec_id", "molecule_chembl_id", "target_chembl_id",
    "pref_name", "molecule_type", "inchikey", "inchikey_status",
    "candidate_id", "active_moiety_id", "identity_status",
    "target_id", "target_id_namespace", "target_disposition",
    "assertion_lane", "general_gene_rankable",
    "action_type_source", "mechanism_of_action", "mechanism_refs",
    "selectivity_comment", "direct_interaction", "molecular_mechanism",
    "disease_efficacy",
    "max_phase_source", "max_phase_canonical", "max_phase_status",
    "max_phase_is_context_only",
    "variant_id", "variant_specific", "variant_disposition", "ambiguity_disposition",
    "direction_decided_in_cache", "edge_policy_version",
    # THE ADDRESS, and the exact bytes it points into. Read from the admitted store's own
    # manifest; never a constant in this file.
    "source_locator", "source_scheme", "source_release", "source_sha256", "source_license",
    "source_required_attribution",
    "chembl_release", "chembl_source_sha256", "chembl_license",
    "chembl_required_attribution", "uniprot_release", "uniprot_source_sha256",
    "uniprot_license",
    "universe_store_id", "typed_universe_sha256",
)
SOURCE_RECORD_KEY: tuple[str, ...] = ("source_record_id",)


class AssertionV2Error(ValueError):
    """A named, fail-closed refusal. The assertion is not emitted."""

    def __init__(self, gate: str, message: str) -> None:
        super().__init__(f"[{gate}] {message}")
        self.gate = gate


# --------------------------------------------------------------------------- #
# Identity.
# --------------------------------------------------------------------------- #
def moiety_id(assertion: Mapping[str, Any]) -> str:
    """A stable ACTIVE-MOIETY identity: structure first (InChIKey), registry id second.

    This IS the ``candidate_id``. It is computed ONCE, here, and every table that references a
    candidate carries the same bytes — a candidate id regenerated per table is not an identity,
    and Stage 4 joins on it.
    """
    return identity.moiety_id_of(
        {"inchikey": assertion.get("inchikey"),
         "chembl_id": assertion.get("molecule_chembl_id")},
        fallback_seed={"mec_id": assertion.get("source_row_id")})


def identity_status(assertion: Mapping[str, Any]) -> str:
    if assertion.get("inchikey"):
        return "resolved"
    if assertion.get("molecule_chembl_id"):
        return "chembl_molecule_id_only"
    return "unresolved"


def rankable(assertion: Mapping[str, Any]) -> bool:
    """Only the general-gene lane may rank a gene. A variant or ambiguous copy never does."""
    return (assertion.get("lane") in ur.RANKABLE_LANES
            and assertion.get("general_gene_rankable") is True)


def stated(value: Any, *, absent: str = NOT_STATED) -> str:
    """The companion status for a nullable value. Absence is a VALUE, not a missing key."""
    return STATED if value not in (None, "") else absent


# --------------------------------------------------------------------------- #
# The address, and the release it points into.
# --------------------------------------------------------------------------- #
def source_locator(assertion: Mapping[str, Any], binding: Mapping[str, Any]) -> str:
    """``chembl:<release>:drug_mechanism/<mec_id>`` — the exact row this assertion came from.

    REFUSES rather than emitting a locator that resolves to nothing: an assertion nobody can
    reopen at its origin cannot be checked against the source, and ChEMBL's REQUIRED
    attribution exists precisely to keep those coordinates.
    """
    release = binding.get("chembl_release")
    mec = assertion.get("source_row_id")
    if not release:
        raise AssertionV2Error(
            GATE_NO_SOURCE_RELEASE,
            f"the admitted store names no ChEMBL release for mec {mec!r}. A source record "
            "that cannot name the release it was drawn from is an assertion about some "
            "unspecified version of the database — 'ChEMBL says so' is not provenance")
    if mec in (None, ""):
        raise AssertionV2Error(
            GATE_NO_SOURCE_LOCATOR,
            "a source assertion carries no source_row_id, so it has no address in "
            f"{release}. A source record that cannot be reopened at its origin is an "
            "assertion with no address")
    return f"{SOURCE_SCHEME_CHEMBL}:{release}:{SOURCE_TABLE_DRUG_MECHANISM}/{mec}"


def release_binding(store: ur.AdmittedStore) -> dict[str, Any]:
    """The releases, licences and source hashes, read from the STORE'S OWN manifest."""
    releases = store.releases
    chembl = releases.get("chembl") or {}
    uniprot = releases.get("uniprot") or {}
    return {
        "chembl_release": chembl.get("source_release"),
        "chembl_source_sha256": chembl.get("source_sha256"),
        "chembl_license": chembl.get("license"),
        "chembl_required_attribution": chembl.get("attribution"),
        "uniprot_release": uniprot.get("source_release"),
        "uniprot_source_sha256": uniprot.get("source_sha256"),
        "uniprot_license": uniprot.get("license"),
    }


# --------------------------------------------------------------------------- #
# The source record.
# --------------------------------------------------------------------------- #
def source_record(assertion: Mapping[str, Any], store: ur.AdmittedStore) -> dict[str, Any]:
    """One source drug assertion — verbatim, addressable, and licence-bound.

    ``assertion`` is a store edge from :func:`druglink.universe_rows.drug_edges_for_targets`:
    the source row exactly as ChEMBL wrote it, typed by its lane, carrying no Stage-3 verdict.
    """
    binding = release_binding(store)
    row = {c: assertion.get(c) for c in SOURCE_RECORD_COLUMNS}
    row.update({
        "source_record_id": assertion.get("edge_id"),
        "mec_id": assertion.get("source_row_id"),
        "candidate_id": moiety_id(assertion),
        "active_moiety_id": moiety_id(assertion),
        "identity_status": identity_status(assertion),
        "assertion_lane": assertion.get("lane"),
        "inchikey_status": stated(assertion.get("inchikey")),
        "max_phase_status": stated(assertion.get("max_phase_source")),
        # The address, and the bytes it points into.
        "source_locator": source_locator(assertion, binding),
        "source_scheme": SOURCE_SCHEME_CHEMBL,
        "source_release": binding["chembl_release"],
        "source_sha256": binding["chembl_source_sha256"],
        "source_license": binding["chembl_license"],
        "source_required_attribution": binding["chembl_required_attribution"],
        **binding,
        "universe_store_id": store.store_id,
        "typed_universe_sha256": store.typed_universe_sha256,
    })
    check_source_record(row)
    return row


def check_edge_absence(edge: Mapping[str, Any]) -> None:
    """Every nullable magnitude on an EDGE says why it is absent, and no null became a 0.

    Re-asserted on the emitted row rather than only inside the builder: a property nobody
    re-checks on the bytes is a property the next writer can drop.
    """
    if edge.get("source_locator") in (None, ""):
        raise AssertionV2Error(
            GATE_NO_SOURCE_LOCATOR,
            f"edge {edge.get('edge_id')!r} names no source_locator; an edge that cannot be "
            "reopened at the ChEMBL row it came from is an assertion with no address")
    for value_col, status_col in (("arm_rank", "arm_rank_status"),
                                  ("arm_value_source_string", "arm_value_status"),
                                  ("max_phase_source", "max_phase_status")):
        status = edge.get(status_col)
        if status not in MISSINGNESS_STATES:
            raise AssertionV2Error(
                GATE_ABSENCE_NOT_STATED,
                f"edge {edge.get('edge_id')!r} carries {status_col}={status!r} for "
                f"{value_col}={edge.get(value_col)!r}. Absence is a STATED value and never a "
                f"missing key; known states are {list(MISSINGNESS_STATES)}")
        if edge.get(value_col) is None and status in (STATED, RANKED):
            raise AssertionV2Error(
                GATE_ABSENCE_NOT_STATED,
                f"edge {edge.get('edge_id')!r} declares {status_col}={status!r} while "
                f"{value_col} is absent. A null read as a 0 invents a measurement, and a 0 "
                "sorts — which is exactly how an unranked target reaches first place")
    if edge.get("arm_rank") == 0:
        raise AssertionV2Error(
            GATE_ABSENCE_NOT_STATED,
            f"edge {edge.get('edge_id')!r} carries arm_rank=0. Stage-2 ranks start at 1; a 0 "
            "here is a null that someone coerced")


def check_source_record(row: Mapping[str, Any]) -> None:
    """A source record names its address, its release, its licence — and its absences."""
    for field, gate in (("source_locator", GATE_NO_SOURCE_LOCATOR),
                        ("source_release", GATE_NO_SOURCE_RELEASE),
                        ("source_sha256", GATE_NO_SOURCE_RELEASE),
                        ("source_license", GATE_NO_SOURCE_RELEASE)):
        if not row.get(field):
            raise AssertionV2Error(
                gate,
                f"source record {row.get('source_record_id')!r} carries {field}="
                f"{row.get(field)!r}. An empty string satisfies a schema and proves nothing: "
                "a source nobody can reopen, date or licence is a source nobody can check")

    for value_col, status_col in STATUS_FOR_VALUE.items():
        if value_col not in row:
            continue
        status = row.get(status_col)
        if status not in MISSINGNESS_STATES:
            raise AssertionV2Error(
                GATE_ABSENCE_NOT_STATED,
                f"source record {row.get('source_record_id')!r} leaves {status_col}="
                f"{status!r} for {value_col}={row.get(value_col)!r}. Absence is a STATED "
                f"value, never a missing key: known states are {list(MISSINGNESS_STATES)}")
        if row.get(value_col) in (None, "") and status == STATED:
            raise AssertionV2Error(
                GATE_ABSENCE_NOT_STATED,
                f"source record {row.get('source_record_id')!r} says {status_col}={STATED!r} "
                f"while {value_col} is absent. A null read as a 0 is the defect this "
                "vocabulary exists to make impossible")
