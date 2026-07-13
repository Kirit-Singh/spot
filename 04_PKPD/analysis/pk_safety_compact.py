"""Compact PK/safety rows for the UI, built ONLY from public bytes already cached on disk.

Every value here was read out of a response that is on this machine, and every value carries the URL
it came from, the UTC time it was fetched, and the SHA-256 of the exact bytes it was read out of. If
a property is not in the cached bytes, the field is `null` and a sibling `*_state` says
`not_evaluated` with the reason. Nothing is imputed, defaulted, or carried over from a similar drug.

WHAT IS AND IS NOT AVAILABLE, and why the distinction is the whole point:

    molecular_weight, xlogp, tpsa, hbd, hba   PubChem property table      -> REAL, sourced
    pharmacokinetics (narrative)              openFDA label section       -> REAL, sourced
    boxed_warning / warnings / contraindications / adverse_reactions
                                              openFDA label sections      -> REAL, sourced
    clogd, pka_most_basic                     IN NO CACHED SOURCE         -> null, not_evaluated
    CNS-MPO composite                         needs clogd + pka           -> not_evaluated
    brain exposure (Kp,uu / CSF)              IN NO CACHED SOURCE         -> null, not_evaluated

CNS-MPO IS NOT REPORTED. Two of its six inputs (cLogD7.4 and the most-basic pKa) are in none of the
cached public sources. A composite computed from four of six is not a CNS-MPO score with two fields
missing — it is a different score wearing CNS-MPO's name, and it would read as a brain-penetrance
result. The sub-properties that ARE sourced are published individually; the composite says
`not_evaluated` and names exactly which inputs are absent.

Absence of a boxed warning is `boxed_warning_present: false` ONLY when the label was actually read.
A label that could not be fetched leaves it `null` — "we looked and there was none" and "we never
looked" are different claims, and only the first is evidence.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Optional

COMPACT_SCHEMA = "spot.stage04_pk_safety_compact.v1"

# The PubChem property table -> the fields we publish. Names are PubChem's own.
PUBCHEM_PROPERTIES: dict[str, tuple[str, Optional[str]]] = {
    "MolecularWeight": ("molecular_weight", "g/mol"),
    "XLogP": ("xlogp", None),
    "TPSA": ("tpsa", "Å²"),
    "HBondDonorCount": ("hbd", None),
    "HBondAcceptorCount": ("hba", None),
    "IUPACName": ("iupac_name", None),
    "InChIKey": ("inchikey", None),
    "MolecularFormula": ("molecular_formula", None),
}

# openFDA label sections -> the safety fields we publish. Every one is the label's own wording.
LABEL_SECTIONS: dict[str, str] = {
    "boxed_warning": "boxed_warning",
    "warnings_and_cautions": "warnings_and_cautions",
    "warnings": "warnings",
    "contraindications": "contraindications",
    "adverse_reactions": "adverse_reactions",
    "drug_interactions": "drug_interactions",
    "pharmacokinetics": "pharmacokinetics",
    "clinical_pharmacology": "clinical_pharmacology",
    "use_in_specific_populations": "use_in_specific_populations",
    "nonclinical_toxicology": "nonclinical_toxicology",
}

# Inputs CNS-MPO needs that NO cached public source carries. Named, not silently omitted.
CNS_MPO_MISSING_INPUTS: tuple[str, ...] = ("clogd_7_4", "pka_most_basic")


def _sha256_file(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _provenance(req: dict[str, Any]) -> dict[str, Any]:
    """What a reader needs to fetch these exact bytes again and check we read them right."""
    return {
        "source_url": req.get("url"),
        "canonical_query": req.get("canonical_query"),
        "accessed_at_utc": req.get("accessed_at_utc"),
        "raw_sha256": req.get("raw_sha256"),
        "raw_bytes": req.get("raw_bytes"),
        "http_status": req.get("http_status"),
        "license_or_terms_url": req.get("license_or_terms_url"),
        "release_or_last_updated": req.get("release_or_last_updated"),
        "cache_relpath": req.get("cache_relpath"),
    }


def _load(root: str, req: dict[str, Any]) -> Optional[Any]:
    """Read a cached response and VERIFY its bytes against the hash the receipt recorded.

    A cached file that no longer hashes to what the receipt says is not the response that was
    fetched — it is a file in the place where that response used to be.
    """
    rel = req.get("cache_relpath")
    if not rel:
        return None
    path = os.path.join(root, str(rel))
    if not os.path.isfile(path):
        return None
    if _sha256_file(path) != str(req.get("raw_sha256")):
        raise ValueError(
            f"cached response {rel} does not hash to the receipt's raw_sha256; these are not the "
            "bytes that were fetched")
    if str(req.get("raw_media_type") or "").endswith("json"):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _requests_by_source(candidate: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for req in candidate.get("requests") or []:
        out.setdefault(str(req.get("source_key")), []).append(req)
    return out


def _pk_properties(root: str, reqs: list[dict[str, Any]]) -> dict[str, Any]:
    """PubChem's property table. Real numbers, each bound to the response it came out of."""
    out: dict[str, Any] = {}
    for req in reqs:
        if "/property/" not in str(req.get("canonical_query") or ""):
            continue
        doc = _load(root, req)
        rows = (((doc or {}).get("PropertyTable") or {}).get("Properties") or [])
        if not rows:
            continue
        row, prov = rows[0], _provenance(req)
        out["pubchem_cid"] = row.get("CID")
        for pubchem_name, (field, units) in PUBCHEM_PROPERTIES.items():
            if pubchem_name not in row:
                continue
            value = row[pubchem_name]
            if field in ("molecular_weight",) and isinstance(value, str):
                value = float(value)          # PubChem ships MW as a string
            out[field] = {"value": value, "units": units, "state": "observed",
                          "provenance": prov}
        break
    return out


def _label(root: str, reqs: list[dict[str, Any]]) -> tuple[Optional[dict[str, Any]], Optional[dict]]:
    """The openFDA label result + its provenance, or (None, None) if none was cached."""
    for req in reqs:
        if "drug/label.json" not in str(req.get("canonical_query") or ""):
            continue
        doc = _load(root, req)
        results = (doc or {}).get("results") or []
        if results:
            return results[0], _provenance(req)
    return None, None


def _safety(label: Optional[dict[str, Any]], prov: Optional[dict]) -> dict[str, Any]:
    """The label's OWN wording, section by section. Never summarized, never paraphrased.

    `boxed_warning_present` is False only when a label WAS read and carried none. With no label it
    stays null: "we looked and there was none" and "we never looked" are different claims.
    """
    if label is None:
        return {
            "label_state": "not_evaluated",
            "label_not_evaluated_reason": "no openFDA drug label response is cached for this moiety",
            "boxed_warning_present": None,
            "sections": {field: {"value": None, "state": "not_evaluated"}
                         for field in LABEL_SECTIONS.values()},
        }

    sections: dict[str, Any] = {}
    for section, field in LABEL_SECTIONS.items():
        text = label.get(section)
        if isinstance(text, list):
            text = "\n\n".join(str(t) for t in text)
        sections[field] = (
            {"value": text, "state": "observed", "characters": len(text)}
            if text else
            {"value": None, "state": "not_found_in_label",
             "reason": f"the label carries no {section!r} section"}
        )

    openfda = label.get("openfda") or {}
    return {
        "label_state": "observed",
        "label_id": label.get("id"),
        "label_effective_time": label.get("effective_time"),
        "spl_set_id": (openfda.get("spl_set_id") or [None])[0],
        "application_numbers": openfda.get("application_number") or [],
        "brand_names": openfda.get("brand_name") or [],
        "boxed_warning_present": bool(label.get("boxed_warning")),
        "sections": sections,
        "provenance": prov,
    }


# The measured evidence NEBPI ranks above every proxy. None of it is in any cached public source.
MEASURED_EXPOSURE_FIELDS: tuple[str, ...] = (
    "human_csf_concentration",
    "unbound_brain_concentration",
    "kp_uu_brain",
    "brain_to_plasma_ratio",
)

# The sourced physicochemical numbers. They are SUGGESTIVE and never confirmatory: a molecule can
# satisfy every one of them and not reach the brain, and the literature is full of ones that do.
PROXY_FIELDS: tuple[str, ...] = ("molecular_weight", "xlogp", "tpsa", "hbd", "hba")


def _brain_penetrance(pk: dict[str, Any]) -> dict[str, Any]:
    """MEASURED exposure over proxies. With no measurement, the assessment is UNKNOWN.

    The failure this is shaped to prevent: reading MW / XLogP / TPSA off PubChem, seeing they look
    "CNS-like", and calling the drug brain-penetrant. Those are properties of the MOLECULE, not
    observations of the BRAIN. Nothing in the cached public sources reports a human CSF
    concentration, an unbound brain concentration, a Kp,uu or a brain:plasma ratio for any of these
    moieties — so there is no measurement to rank, and the assessment says exactly that.
    """
    proxies = {
        field: {"value": pk[field]["value"], "units": pk[field].get("units"),
                "provenance": pk[field]["provenance"]}
        for field in PROXY_FIELDS if isinstance(pk.get(field), dict)
    }
    return {
        "assessment": "unknown",
        "assessment_state": "not_evaluated",
        "basis": "no_measured_human_cns_exposure",
        "reason": ("no cached public source reports a human CSF concentration, an unbound brain "
                   "concentration, a Kp,uu or a brain:plasma ratio for this moiety. Physicochemical "
                   "properties are properties of the molecule, not observations of the brain: they "
                   "may SUGGEST penetrance and can never confirm it, and no assessment is derived "
                   "from them here."),
        "measured_exposure": {field: {"value": None, "state": "not_evaluated"}
                              for field in MEASURED_EXPOSURE_FIELDS},
        "physicochemical_proxies": proxies,
        "proxies_are_suggestive_never_confirmatory": True,
        "assessment_is_not_derived_from_proxies": True,
    }


def candidate_row(root: str, candidate: dict[str, Any]) -> dict[str, Any]:
    """One drug: real PK properties, real label safety, explicit absence everywhere else."""
    by_source = _requests_by_source(candidate)
    pk = _pk_properties(root, by_source.get("pubchem") or [])
    label, label_prov = _label(root, by_source.get("openfda") or [])

    return {
        "candidate_id": candidate.get("candidate_id"),
        "moiety_name": candidate.get("moiety_name"),
        "acquisition_status": candidate.get("status"),
        "pk_properties": pk or {"state": "not_evaluated",
                                "reason": "no PubChem property response is cached for this moiety"},
        # NOT a CNS-MPO score. Two of its six inputs are in no cached public source, and a composite
        # computed from four of six is a different score wearing CNS-MPO's name.
        "cns_mpo": {
            "value": None,
            "state": "not_evaluated",
            "missing_inputs": list(CNS_MPO_MISSING_INPUTS),
            "reason": ("CNS-MPO requires cLogD7.4 and the most-basic pKa; neither is present in any "
                       "cached public source. The sourced sub-properties are published individually "
                       "above. A partial composite would read as a brain-penetrance result."),
        },
        # NEBPI-ALIGNED. Measured human exposure OUTRANKS physicochemical proxies, always. The
        # proxies are shown because they are real sourced numbers — but an assessment is NEVER
        # derived from them, and with no measured exposure the assessment is UNKNOWN, not favorable.
        "brain_penetrance": _brain_penetrance(pk),
        "safety": _safety(label, label_prov),
    }


def build(prefetch_root: str, stage3_source: Optional[dict[str, Any]] = None,
          only: Optional[set[str]] = None) -> dict[str, Any]:
    """The compact document. `only` restricts to a Stage-3 selection's candidates."""
    receipt_path = os.path.join(prefetch_root, "prefetch_receipt.json")
    with open(receipt_path, encoding="utf-8") as fh:
        receipt = json.load(fh)

    rows, skipped = [], []
    for candidate in receipt.get("candidates") or []:
        cid = str(candidate.get("candidate_id"))
        if only is not None and cid not in only:
            continue
        if candidate.get("status") != "acquired":
            # NOT dropped: a candidate whose evidence could not be fetched is REPORTED, with the
            # source's own reason. A row that vanishes and a row that never existed look identical.
            skipped.append({"candidate_id": cid, "moiety_name": candidate.get("moiety_name"),
                            "acquisition_status": candidate.get("status"),
                            "detail": candidate.get("detail"),
                            "pk_properties": {"state": "not_evaluated",
                                              "reason": "no public evidence was acquired"},
                            "safety": {"label_state": "not_evaluated"}})
            continue
        rows.append(candidate_row(prefetch_root, candidate))

    doc: dict[str, Any] = {
        "schema_id": COMPACT_SCHEMA,
        "evidence_source": {
            "prefetch_receipt": receipt_path,
            "prefetch_receipt_content_sha256": receipt.get("content_sha256"),
            "bound_to": receipt.get("bound_to"),
            "artifact_class": "prefetch_only",
        },
        "stage3_source": stage3_source or {
            "state": "not_bound",
            "reason": ("no Stage-3 Rest/Stim8 drug JSON was supplied; these rows are the "
                       "selection-INDEPENDENT public-evidence store over the acquired moieties"),
        },
        "counts": {"n_rows": len(rows), "n_unacquired_reported": len(skipped)},
        "candidates": sorted(rows, key=lambda r: str(r["candidate_id"])),
        "unacquired": sorted(skipped, key=lambda r: str(r["candidate_id"])),
        "not_a_ranking": True,
        "fields_absent_from_public_sources_are_null_and_stated": True,
    }
    return doc
