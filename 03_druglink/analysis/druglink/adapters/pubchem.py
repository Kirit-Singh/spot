"""PubChem PUG-REST adapters.

``pubchem_property`` asserts identifiers only: a property lookup cannot tell a
salt from a parent, so it makes no relationship and no moiety claim.

``pubchem_parent_cid`` (``/compound/cid/{cid}/cids/JSON?cids_type=parent``) asserts
the desalted parent compound of the queried CID. That supports a salt -> parent
relation ONLY; it is not an active-metabolite statement, so a prodrug is never
resolved to its active species here.
"""
from __future__ import annotations

from typing import Any

from . import base
from .base import require

SOURCE = "pubchem"
VERSION = "pubchem-adapter-v2"


def parse_property(raw: Any, entry: dict[str, Any], src_id: str) -> list[dict[str, Any]]:
    require(isinstance(raw, dict) and isinstance(raw.get("PropertyTable"), dict),
            "PubChem property response must carry a 'PropertyTable'")
    props = raw["PropertyTable"].get("Properties")
    require(isinstance(props, list), "PropertyTable must carry 'Properties'")
    out: list[dict[str, Any]] = []
    for p in props:
        cid = p.get("CID")
        if cid is None:
            continue
        out.append(base.form_claim(
            source=SOURCE, source_record_id=src_id,
            identifiers=base.ids(pubchem_cid=cid, inchikey=p.get("InChIKey")),
            form_class=None, relations=[], preferred_name=p.get("Title")))
    return out


def parse_parent_cid(raw: Any, entry: dict[str, Any], src_id: str) -> list[dict[str, Any]]:
    require(isinstance(raw, dict) and isinstance(raw.get("IdentifierList"), dict),
            "PubChem parent-CID response must carry an 'IdentifierList'")
    cids = raw["IdentifierList"].get("CID")
    require(isinstance(cids, list) and cids, "IdentifierList must carry 'CID'")
    query_cid = entry["query"].get("cid")
    require(query_cid is not None, "pubchem_parent_cid entry must record query.cid")
    query_cid, parent = str(query_cid), str(cids[0])

    if parent == query_cid:
        return [base.form_claim(
            source=SOURCE, source_record_id=src_id,
            identifiers=base.ids(pubchem_cid=query_cid), form_class="parent",
            relations=[base.relation("is_parent_of_self",
                                     base.ids(pubchem_cid=query_cid))])]
    return [base.form_claim(
        source=SOURCE, source_record_id=src_id,
        identifiers=base.ids(pubchem_cid=query_cid), form_class="salt",
        relations=[base.relation("is_salt_of", base.ids(pubchem_cid=parent))])]


ADAPTERS = {
    "pubchem_property": base.Adapter(
        "pubchem_property", VERSION, SOURCE, base.FIXTURE_SHAPED,
        ("/rest/pug/compound/cid/{cids}/property/InChIKey,Title/JSON",),
        parse_property),
    "pubchem_parent_cid": base.Adapter(
        "pubchem_parent_cid", VERSION, SOURCE, base.FIXTURE_SHAPED,
        ("/rest/pug/compound/cid/{cid}/cids/JSON?cids_type=parent",),
        parse_parent_cid),
}
