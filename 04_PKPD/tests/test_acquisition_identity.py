"""Deterministic public identity: PubChem, RxNorm, DailyMed, openFDA/Drugs@FDA.

Identity is the FIRST gate. The admission checklist: `identity_converged` ->
consequence_on_fail: refuse_candidate. So every one of these tests is about what the layer
REFUSES:

  * two CIDs / two RxCUIs / two DailyMed products for one name  -> refuse, never a first hit
  * a label version that is not the version that was selected   -> refuse
  * an active-moiety UNII that two sources disagree about       -> refuse
  * a Drugs@FDA application number that is not the label's      -> refuse
  * a salt/prodrug with no sourced mapping to its active moiety -> refuse
  * a request for logD7.4 or pKa from PubChem                   -> refuse (it does not have them)
  * a fetch with no network permission, or to an unlisted host  -> refuse

No network. Every response is a synthetic fixture from tests/fixtures/acquisition/.
"""

from __future__ import annotations

import os

import pytest

from analysis.acquire_http import Client, StaticTransport
from analysis.acquisition import RunRoot
from analysis.dailymed_select import (
    acquire_label,
    acquire_rxcui,
    parse_spl_listing,
    select_spl,
)
from analysis.firewall import Rejection
from analysis.identity import claims_from, resolve_identity
from analysis.openfda_approval import acquire_approval, cross_check_approval
from analysis.pubchem import (
    FORBIDDEN_DESCRIPTORS,
    acquire_pubchem_identity,
    assert_descriptor_is_public,
)

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "acquisition")
NAME = "fixturomide"
SETID = "ffffffff-0000-4000-8000-fixtureacq01"
CLOCK = "2026-07-13T05:00:00Z"

PUBCHEM = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
RXNAV = "https://rxnav.nlm.nih.gov/REST"
DAILYMED = "https://dailymed.nlm.nih.gov/dailymed/services/v2"
OPENFDA = "https://api.fda.gov"


def _bytes(name: str) -> bytes:
    with open(os.path.join(FIX, name), "rb") as fh:
        return fh.read()


def _routes(**over: str) -> dict[str, tuple[int, dict[str, str], bytes]]:
    """The synthetic wire. A URL that is not here cannot be fetched — so a test can never
    silently reach the real network."""
    json_h = {"content-type": "application/json"}
    xml_h = {"content-type": "application/xml"}
    files = {
        "cids": "pubchem_name_cids.json",
        "properties": "pubchem_cid_properties.json",
        "rxcui": "rxnorm_rxcui.json",
        "spls": "dailymed_spls.json",
        "openfda_label": "openfda_label.json",
        "drugsfda": "drugsfda.json",
    }
    files.update(over)
    return {
        f"{PUBCHEM}/compound/name/{NAME}/cids/JSON": (200, json_h, _bytes(files["cids"])),
        f"{PUBCHEM}/compound/cid/999999901/property/HBondAcceptorCount,HBondDonorCount,"
        f"InChI,InChIKey,IUPACName,MolecularFormula,MolecularWeight,TPSA,XLogP/JSON":
            (200, json_h, _bytes(files["properties"])),
        f"{RXNAV}/rxcui.json?name={NAME}&search=0": (200, json_h, _bytes(files["rxcui"])),
        f"{DAILYMED}/spls.json?drug_name={NAME}": (200, json_h, _bytes(files["spls"])),
        f"{DAILYMED}/spls/{SETID}.xml": (200, xml_h, _bytes("dailymed_spl.xml")),
        f"{OPENFDA}/drug/label.json?limit=1&search=openfda.spl_set_id%3A%22{SETID}%22":
            (200, json_h, _bytes(files["openfda_label"])),
        f"{OPENFDA}/drug/drugsfda.json?limit=1&search=openfda.application_number%3A%22NDA999901%22":
            (200, json_h, _bytes(files["drugsfda"])),
    }


def _client(**over: str) -> Client:
    return Client(transport=StaticTransport(_routes(**over), clock=CLOCK), allow_network=True)


@pytest.fixture()
def run_root(tmp_path):
    return RunRoot(str(tmp_path / "run"))


# ------------------------------------------------------------------- the network firewall


def test_no_network_is_the_default_an_adapter_cannot_reach_out_by_accident(run_root):
    client = Client()  # no transport, no permission
    with pytest.raises(Rejection) as exc:
        client.get("pubchem", "compound/name/x/cids/JSON")
    assert exc.value.code == "network_not_permitted"


def test_a_host_outside_the_ledger_is_never_contacted(run_root):
    client = _client()
    with pytest.raises(Rejection) as exc:
        client.get_url("drugbank", "https://go.drugbank.com/drugs/DB00853")
    assert exc.value.code in ("forbidden_source", "unknown_source")


def test_a_reuse_only_source_cannot_be_fetched_even_with_network_permission():
    client = _client()
    with pytest.raises(Rejection) as exc:
        client.get("chembl", "molecule/CHEMBL1.json")
    assert exc.value.code == "stage3_source_reuse_required"


# ------------------------------------------------------------------------------ PubChem


def test_pubchem_supplies_structure_and_the_descriptors_it_actually_computes(run_root):
    identity, records = acquire_pubchem_identity(_client(), run_root, NAME)

    assert identity.cid == "999999901"
    assert identity.inchikey == "FIXTUREKEYAAAA-BBBBBBBBBB-N"
    # exact source strings, never floats — a magnitude is not re-rounded on the way in
    assert identity.descriptors["MolecularWeight"] == "194.15"
    assert identity.descriptors["TPSA"] == "106"
    assert [r.source_key for r in records] == ["pubchem", "pubchem"]
    assert all(r.origin == "fetched_public" and r.http_status == 200 for r in records)
    assert all(r.accessed_at_utc == CLOCK for r in records)


def test_pubchem_records_bind_the_bytes_they_were_parsed_from(run_root):
    from analysis.acquisition import verify_cached_bytes

    _, records = acquire_pubchem_identity(_client(), run_root, NAME)
    for rec in records:
        verify_cached_bytes(rec, run_root)          # the cache holds exactly what was hashed
        assert rec.cache_relpath.startswith("raw/pubchem/")
        assert rec.license_or_terms_url == "https://www.ncbi.nlm.nih.gov/home/about/policies/"
        # PUG REST emits no global release. The record says so; it does not invent one.
        assert rec.release_or_last_updated == "not_reported_by_source"


@pytest.mark.parametrize("descriptor", ["logD7.4", "logd", "most_basic_pKa", "pKa"])
def test_pubchem_may_never_supply_logd_or_pka(descriptor):
    """The audit, §4.3: public sources cover only part of the CNS-MPO vector. XLogP is a logP,
    not a logD. Fabricating the missing two would be the whole point of the firewall."""
    with pytest.raises(Rejection) as exc:
        assert_descriptor_is_public(descriptor)
    assert exc.value.code == "descriptor_not_public"


def test_the_forbidden_descriptor_list_is_not_empty_and_names_both_missing_properties():
    joined = " ".join(FORBIDDEN_DESCRIPTORS)
    assert "logd" in joined and "pka" in joined


def test_two_cids_for_one_name_is_a_refusal_not_a_first_hit(run_root):
    client = _client(cids="pubchem_name_cids_ambiguous.json")
    with pytest.raises(Rejection) as exc:
        acquire_pubchem_identity(client, run_root, NAME)
    assert exc.value.code == "pubchem_identity_ambiguous"


# -------------------------------------------------------------------- RxNorm / DailyMed


def test_rxnorm_gives_one_rxcui_or_the_candidate_is_refused(run_root):
    rxcui, record = acquire_rxcui(_client(), run_root, NAME)
    assert rxcui == "9999901"
    assert record.source_key == "rxnorm" and record.stable_record_id == "9999901"

    with pytest.raises(Rejection) as exc:
        acquire_rxcui(_client(rxcui="rxnorm_rxcui_ambiguous.json"), run_root, NAME)
    assert exc.value.code == "rxnorm_identity_ambiguous"


def test_dailymed_selection_is_deterministic_and_refuses_to_choose_between_two_products():
    one = parse_spl_listing(_bytes("dailymed_spls.json"))
    assert select_spl(one).setid == SETID

    two = parse_spl_listing(_bytes("dailymed_spls_ambiguous.json"))
    with pytest.raises(Rejection) as exc:
        select_spl(two)
    assert exc.value.code == "dailymed_product_selection_ambiguous"
    assert "ffffffff-0000-4000-8000-fixtureacq02" in exc.value.detail  # both are named

    # ...unless the caller pins the product explicitly. That is a decision, not a default.
    assert select_spl(two, setid=SETID).setid == SETID


def test_the_selected_label_is_fetched_parsed_and_its_nested_warnings_survive(run_root):
    """The e410d72 repair, exercised through the acquisition path: WARNINGS AND PRECAUTIONS
    carries no direct text and both warnings live in 42229-5 subsections."""
    selected, records = acquire_label(_client(), run_root, NAME)

    assert selected.listing.setid == SETID
    assert selected.label.label_version == "40"
    assert selected.label.active_moiety_unii == ["FIXTURE001"]

    warnings = [f for f in selected.label.findings if f.finding_type == "warning_precaution"]
    assert len(warnings) == 2
    assert all(f.labeled_subsection_code == "42229-5" for f in warnings)

    spl = [r for r in records if r.raw_media_type and "xml" in r.raw_media_type][0]
    assert spl.release_or_last_updated == "spl_version=40; effective_time=2026-02-20"
    assert spl.license_status == "no_blanket_license_verified"
    assert spl.redistribution == "do_not_store_full_labels_in_git"


def test_a_label_whose_version_is_not_the_selected_version_is_refused(run_root, tmp_path):
    """FAIL-CLOSED (version): the listing said 40; if the document says otherwise, the two are
    not the same label and Stage 4 will not silently prefer one."""
    routes = _routes()
    body = _bytes("dailymed_spl.xml").replace(
        b'<versionNumber value="40"/>', b'<versionNumber value="41"/>')
    routes[f"{DAILYMED}/spls/{SETID}.xml"] = (200, {"content-type": "application/xml"}, body)
    client = Client(transport=StaticTransport(routes, clock=CLOCK), allow_network=True)

    with pytest.raises(Rejection) as exc:
        acquire_label(client, run_root, NAME)
    assert exc.value.code == "dailymed_version_conflict"


# --------------------------------------------------------------- openFDA / Drugs@FDA


def test_openfda_supplies_the_application_number_and_drugsfda_confirms_the_approval(run_root):
    approval, records = acquire_approval(_client(), run_root, SETID)

    assert approval.application_number == "NDA999901"
    assert approval.marketing_status == "Prescription"
    assert approval.unii == "FIXTURE001"
    # openFDA's own last_updated is the release; it is not invented.
    assert all(r.release_or_last_updated == "2026-06-30" for r in records)
    assert all(r.license_status == "generally_cc0_with_marked_source_exceptions"
               for r in records)


def test_a_drugsfda_application_that_is_not_the_labels_is_an_approval_conflict(run_root):
    """FAIL-CLOSED (approval): `label_current_and_approval_crosschecked` -> safety_not_evaluated.
    A label that cannot be tied to an approval is not cross-checked, and pretending otherwise
    is exactly the overclaim the audit flagged."""
    client = _client(drugsfda="drugsfda_conflicting.json")
    with pytest.raises(Rejection) as exc:
        acquire_approval(client, run_root, SETID)
    assert exc.value.code == "approval_conflict"


def test_cross_check_refuses_a_label_application_number_that_drugsfda_does_not_know():
    with pytest.raises(Rejection) as exc:
        cross_check_approval(label_application_number="NDA999901",
                             drugsfda_application_number="NDA111111")
    assert exc.value.code == "approval_conflict"


# ------------------------------------------------------------------------ the identity gate


def test_identity_converges_across_four_public_sources(run_root):
    client = _client()
    pubchem, _ = acquire_pubchem_identity(client, run_root, NAME)
    rxcui, _ = acquire_rxcui(client, run_root, NAME)
    label, _ = acquire_label(client, run_root, NAME)
    approval, _ = acquire_approval(client, run_root, label.listing.setid)

    identity = resolve_identity(
        claims_from(pubchem=pubchem, rxcui=rxcui, label=label, approval=approval))

    assert identity.inchikey == "FIXTUREKEYAAAA-BBBBBBBBBB-N"
    assert identity.unii == "FIXTURE001"
    assert identity.pubchem_cid == "999999901"
    assert identity.rxcui == "9999901"
    assert identity.dailymed_setid == SETID
    assert identity.fda_application_number == "NDA999901"
    assert identity.conflicts == []
    # DrugBank stays empty on a public-only path, whatever else is known.
    assert not hasattr(identity, "drugbank_id")


def test_two_sources_that_disagree_about_the_active_moiety_refuse_the_candidate(run_root):
    """FAIL-CLOSED (identity): `identity_converged` -> refuse_candidate. The label says the
    active moiety is FIXTURE001; openFDA says FIXTURE999. One of them is about another
    molecule, and Stage 4 does not get to choose which."""
    client = _client(openfda_label="openfda_label_conflicting.json")
    pubchem, _ = acquire_pubchem_identity(client, run_root, NAME)
    label, _ = acquire_label(client, run_root, NAME)
    approval, _ = acquire_approval(client, run_root, label.listing.setid)

    with pytest.raises(Rejection) as exc:
        resolve_identity(claims_from(pubchem=pubchem, label=label, approval=approval))
    assert exc.value.code == "identity_conflict"
    assert "unii" in exc.value.detail
    assert "FIXTURE001" in exc.value.detail and "FIXTURE999" in exc.value.detail


def test_a_salt_or_prodrug_with_no_sourced_mapping_to_its_active_moiety_is_refused(run_root):
    client = _client()
    pubchem, _ = acquire_pubchem_identity(client, run_root, NAME)

    with pytest.raises(Rejection) as exc:
        resolve_identity(claims_from(pubchem=pubchem), administered_form="salt")
    assert exc.value.code == "unresolved_salt_prodrug_or_metabolite_mapping"

    resolved = resolve_identity(
        claims_from(pubchem=pubchem), administered_form="salt",
        maps_to_active_moiety_id="FIXTURE001", mapping_source_record_id="acq_s3_deadbeef")
    assert resolved.administered_form == "salt"
    assert resolved.maps_to_active_moiety_id == "FIXTURE001"


def test_two_inchikeys_that_share_a_skeleton_but_differ_in_protonation_still_conflict():
    """A salt and its free base share the first InChIKey block. They are NOT the same molecule
    for exposure, and a mapping is required — silently accepting the pair is the salt-vs-moiety
    mix-up the contract exists to prevent."""
    from analysis.identity import IdentityClaim

    claims = [
        IdentityClaim(field="inchikey", value="FIXTUREKEYAAAA-BBBBBBBBBB-N",
                      source_key="pubchem", record_id="acq_a"),
        IdentityClaim(field="inchikey", value="FIXTUREKEYAAAA-CCCCCCCCCC-M",
                      source_key="dailymed", record_id="acq_b"),
    ]
    with pytest.raises(Rejection) as exc:
        resolve_identity(claims)
    assert exc.value.code == "identity_conflict"
