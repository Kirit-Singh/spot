"""PubChem PUG REST — active-moiety structure, identity, and the descriptors PubChem HAS.

What it may supply: CID, InChIKey, InChI, molecular formula, and PubChem's own computed
descriptors (MW, TPSA, HBD, HBA, XLogP).

What it may NOT supply, ever:

  * **logD7.4** — PubChem does not compute it. XLogP3 is a logP, and substituting one for the
    other would be inventing the number, not sourcing it.
  * **most-basic pKa** — PUG REST does not carry it.

Those two are half of the CNS-MPO vector, so under a public-only rule CNS-MPO stays INCOMPLETE.
The audit is explicit that this must not block the measured-exposure, transporter, label-safety
or NEBPI lanes (§4.3). `assert_descriptor_is_public` is the refusal that keeps the fabrication
from happening by convenience.

Name -> CID resolution refuses ambiguity: two CIDs for one name means Stage 4 does not know
which molecule is meant, and taking the first is how a salt becomes a parent by accident.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

from .acquire_http import Client
from .acquisition import AcquisitionRecord, RunRoot, record_from_response
from .firewall import Rejection

SOURCE_KEY = "pubchem"
# PubChem PUG REST carries no global database release. Recorded as an absence, never as a date.
NO_RELEASE = "not_reported_by_source"

# Sorted, so the canonical query for a given property set is stable.
PROPERTIES: tuple[str, ...] = (
    "HBondAcceptorCount",
    "HBondDonorCount",
    "InChI",
    "InChIKey",
    "IUPACName",
    "MolecularFormula",
    "MolecularWeight",
    "TPSA",
    "XLogP",
)

# Lower-cased needles. A descriptor whose name contains one of these is not in PubChem, and a
# value for it would have to have been invented somewhere.
FORBIDDEN_DESCRIPTORS: tuple[str, ...] = ("logd", "pka", "clogd", "most_basic_pka")

FORBIDDEN_REASON = {
    "logd": "PubChem does not compute logD7.4. XLogP3 is a logP at no stated pH and is not a "
            "substitute for it.",
    "pka": "PubChem PUG REST does not supply a most-basic pKa.",
}


@dataclass(frozen=True)
class PubChemIdentity:
    """Structure identity + the descriptors PubChem actually reported. Values stay as the EXACT
    source strings: a magnitude that is re-rounded on the way in can never be checked again."""

    cid: str
    inchikey: str | None
    inchi: str | None
    formula: str | None
    iupac_name: str | None
    descriptors: dict[str, str] = field(default_factory=dict)
    # Named here so the gap is visible in the artifact rather than inferred from a blank.
    not_available: tuple[str, ...] = ("logD7.4", "most_basic_pKa")


def assert_descriptor_is_public(name: str) -> None:
    """Refuse a descriptor no public source in the ledger supplies."""
    needle = name.strip().lower().replace(" ", "").replace("-", "")
    for forbidden in FORBIDDEN_DESCRIPTORS:
        if forbidden in needle:
            reason = FORBIDDEN_REASON.get("logd" if "logd" in forbidden else "pka", "")
            raise Rejection(
                "descriptor_not_public",
                f"{name!r} cannot be acquired from a public source. {reason} CNS-MPO therefore "
                "stays INCOMPLETE — which does not block the measured exposure, transporter, "
                "label-safety or NEBPI lanes, and is not a licence to fabricate the value.")


def name_to_cids_path(name: str) -> str:
    """The name->CIDs PUG path, with ONLY the free-text name segment percent-encoded.

    PubChem embeds the compound name in the URL path. A raw space (`SALMETEROL XINAFOATE`) makes
    urllib raise InvalidURL before the request is sent — and in a bulk warm-up that is an uncaught
    crash, not a counted miss. `quote(name, safe="")` escapes the space (-> %20), the reserved
    characters (`,` `/` `?` -> %2C %2F %3F) and any non-ASCII (UTF-8 percent bytes), while the path
    SEPARATORS and the `/cids/JSON` structure are built here and never touched. A simple ASCII name
    is returned byte-for-byte unchanged, so no cache entry that already worked can move.
    """
    return f"compound/name/{quote(name, safe='')}/cids/JSON"


def cid_to_property_path(cid: str) -> str:
    """The CID->properties PUG path. The CID is numeric and the property commas are PubChem's list
    SEPARATOR — encoding them would ask for one property literally named 'A,B,C'. So this path is
    built from trusted structure and carries no free text to escape."""
    return f"compound/cid/{cid}/property/{','.join(PROPERTIES)}/JSON"


def parse_cids(raw: bytes) -> list[str]:
    payload = _json(raw, "compound/name/.../cids")
    cids = (payload.get("IdentifierList") or {}).get("CID") or []
    return [str(c) for c in cids]


def parse_properties(raw: bytes, cid: str) -> PubChemIdentity:
    payload = _json(raw, "compound/cid/.../property")
    rows = (payload.get("PropertyTable") or {}).get("Properties") or []
    row = next((r for r in rows if str(r.get("CID")) == str(cid)), None)
    if row is None:
        raise Rejection(
            "pubchem_property_missing",
            f"the property response carries no row for CID {cid!r}. Stage 4 does not read a "
            "property table that is about a different compound.")

    descriptors = {
        key: str(row[key]) for key in PROPERTIES
        if key in row and key not in ("InChI", "InChIKey", "MolecularFormula", "IUPACName")
        and row[key] is not None
    }
    return PubChemIdentity(
        cid=str(cid),
        inchikey=_opt(row.get("InChIKey")),
        inchi=_opt(row.get("InChI")),
        formula=_opt(row.get("MolecularFormula")),
        iupac_name=_opt(row.get("IUPACName")),
        descriptors=descriptors,
    )


def acquire_pubchem_identity(client: Client, run_root: RunRoot,
                             name: str) -> tuple[PubChemIdentity, list[AcquisitionRecord]]:
    """name -> (identity, the two responses it rests on). Ambiguity is a refusal."""
    cid_resp = client.get(SOURCE_KEY, name_to_cids_path(name))
    cids = parse_cids(cid_resp.body)
    if not cids:
        raise Rejection(
            "pubchem_identity_not_found",
            f"PubChem resolved no CID for {name!r}. An unresolvable molecule is not assessed; "
            "it is reported as unresolved.")
    if len(cids) > 1:
        raise Rejection(
            "pubchem_identity_ambiguous",
            f"PubChem resolved {name!r} to {len(cids)} CIDs ({', '.join(cids[:8])}). Stage 4 "
            "does not take the first: a name that maps to several compounds is an identity "
            "Stage 4 has not established, and every downstream join would inherit the guess.")

    cid = cids[0]
    prop_resp = client.get(SOURCE_KEY, cid_to_property_path(cid))
    identity = parse_properties(prop_resp.body, cid)

    records = [
        record_from_response(
            cid_resp, run_root=run_root, stable_record_id=cid, release=NO_RELEASE, suffix="json",
            # `compound/name/{name}/cids` is a NAME-TO-LIST query, not a GET by CID. It returns a
            # LIST, so it is a collect-all in canonical order — nothing chosen, nothing dropped.
            # Calling it an identity GET would claim an identity the request never asserted.
            selection_disposition="sorted_unique", selection_pin=cid,
            records_returned=len(cids),

            extraction_transform="pubchem.parse_cids:v1", adapter_file=__file__,
            note=f"name -> CID resolution for {name!r}; exactly one CID, or this record would "
                 "not exist"),
        record_from_response(
            prop_resp, run_root=run_root, stable_record_id=cid, release=NO_RELEASE, suffix="json",
            # A TRUE identity GET: the property table is fetched BY CID. No result set, so no total
            # and NO completeness boolean — both stay null rather than being invented.
            selection_disposition="identity_get", selection_pin=cid, records_returned=1,

            extraction_transform="pubchem.parse_properties:v1", adapter_file=__file__,
            note="PubChem-computed descriptors only. No logD7.4 and no most-basic pKa: PubChem "
                 "does not supply them and Stage 4 does not invent them."),
    ]
    return identity, records


def _json(raw: bytes, what: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise Rejection("pubchem_response_unparseable",
                        f"the PubChem {what} response is not JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise Rejection("pubchem_response_unparseable",
                        f"the PubChem {what} response is not an object")
    return payload


def _opt(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
