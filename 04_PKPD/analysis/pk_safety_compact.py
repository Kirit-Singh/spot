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
    clogp, clogd, pka_most_basic              IN NO ACCEPTED SOURCE       -> null, incomplete
    CNS-MPO total                             needs all six inputs        -> null, incomplete
    brain exposure (Kp,uu / CSF)              NOT EXTRACTED FROM THESE    -> null, not_evaluated

`not_extracted_not_available_in_current_sources` is deliberately narrow. Stage 4 has not read the
literature and cannot say a measurement does not exist; it can only say what it extracted from the
responses cached in this run. Those are different claims and only the second one is ours to make.

CNS-MPO IS INCOMPLETE. Only three of its six inputs are accepted here: molecular weight, TPSA and
HBD. PubChem XLogP is not the BioByte ClogP used by the published method, and HBA is not a CNS-MPO
input. ClogP, ClogD7.4 and most-basic pKa therefore remain missing. The three observed component
transforms are emitted, but the CNS-MPO total remains null. A mathematical range over the three
unknown T0 values is explicitly non-rankable and is not a CNS-MPO score.

Absence of a boxed warning is `boxed_warning_present: false` ONLY when the label was actually read.
A label that could not be fetched leaves it `null` — "we looked and there was none" and "we never
looked" are different claims, and only the first is evidence.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Optional

from .cnsmpo import desirability

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

# The six published inputs and the three this compact public-data lane can accept. PubChem XLogP is
# deliberately not mapped to ClogP; HBA is deliberately absent because it is not an MPO component.
CNS_MPO_REQUIRED_INPUTS: tuple[str, ...] = (
    "clogp", "clogd_74", "mw", "tpsa", "hbd", "pka_most_basic",
)
CNS_MPO_ACCEPTED_PUBCHEM: dict[str, str] = {
    "mw": "molecular_weight",
    "tpsa": "tpsa",
    "hbd": "hbd",
}
CNS_MPO_MISSING_INPUTS: tuple[str, ...] = ("clogp", "clogd_74", "pka_most_basic")
_METHOD_PATH = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "method", "cns_mpo_wager2010_v1.json",
))


def _sha256_file(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _provenance(req: dict[str, Any]) -> dict[str, Any]:
    """What a reader needs to re-fetch these exact bytes and check we read them right.

    The public SOURCE URL stays — it is the whole point, and it is not a machine path. What is gone
    is anything that names THIS filesystem: a served document that discloses where a machine keeps
    its files has told the reader nothing useful about the science and something true about the box.
    `cache_relpath` is relative to the prefetch root and is kept; the root itself is in the sidecar.
    """
    return {
        "source_url": req.get("url"),
        "canonical_query": req.get("canonical_query"),
        "accessed_at_utc": req.get("accessed_at_utc"),
        "raw_sha256": req.get("raw_sha256"),
        "raw_bytes": req.get("raw_bytes"),
        "http_status": req.get("http_status"),
        "license_or_terms_url": req.get("license_or_terms_url"),
        "release_or_last_updated": req.get("release_or_last_updated"),
        "cache_relpath": req.get("cache_relpath"),      # relative to the prefetch root, by design
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


def _load_cns_mpo_method() -> dict[str, Any]:
    with open(_METHOD_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _cns_mpo_availability(pk: dict[str, Any], evidence: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Emit observed components and bounds without inventing a partial CNS-MPO total."""
    method = _load_cns_mpo_method()
    components: dict[str, Optional[float]] = {key: None for key in CNS_MPO_REQUIRED_INPUTS}
    values: dict[str, Optional[float]] = {key: None for key in CNS_MPO_REQUIRED_INPUTS}
    component_provenance: dict[str, Any] = {}
    for property_id, compact_field in CNS_MPO_ACCEPTED_PUBCHEM.items():
        cell = pk.get(compact_field)
        if not isinstance(cell, dict) or cell.get("state") != "observed":
            continue
        value = float(cell["value"])
        values[property_id] = value
        components[property_id] = desirability(property_id, value, method)
        component_provenance[property_id] = cell.get("provenance")

    accepted = [p for p, value in components.items() if value is not None]
    missing = [p for p, value in components.items() if value is None]
    observed_sum = sum(float(components[p]) for p in accepted)
    chembl = (evidence or {}).get("chembl_molecule") or {}
    chembl_properties = chembl.get("molecule_properties") or {}
    return {
        "state": "incomplete",
        "method_id": method["method_id"],
        "method_version": method["method_version"],
        "total_raw": None,
        "total_published": None,
        "components": components,
        "property_values": values,
        "component_provenance": component_provenance,
        "component_coverage": {
            "n_accepted": len(accepted),
            "n_required": len(CNS_MPO_REQUIRED_INPUTS),
            "accepted_inputs": accepted,
        },
        "missing_inputs": [
            {
                "property_id": prop,
                "state": "not_available_under_frozen_calculator_policy",
                "chembl_source_observation": chembl_properties.get(prop),
            }
            for prop in missing
        ],
        "possible_total_range": {
            "min": observed_sum,
            "max": observed_sum + len(missing),
            "derivation": "each missing transformed component T0 is bounded in [0,1]",
            "not_a_cns_mpo_score": True,
            "non_rankable": True,
        },
        "non_rankable": True,
        "proxy_only_not_mpo_inputs": {
            key: pk[key] for key in ("xlogp", "hba") if isinstance(pk.get(key), dict)
        },
        "reason": (
            "Only molecular weight, TPSA and HBD are accepted. PubChem XLogP is not the "
            "published BioByte ClogP input, and HBA is not a CNS-MPO component. ClogP, "
            "ClogD7.4 and most-basic pKa remain missing, so no CNS-MPO total is computed."
        ),
    }


def _brain_penetrance(pk: dict[str, Any], evidence: Optional[dict[str, Any]] = None) -> dict[str, Any]:
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
    direct = (evidence or {}).get("direct_human_cns_evidence") or {
        "status": "not_evaluated",
        "measurements": [],
    }
    observed = direct.get("status") == "observed" and bool(direct.get("measurements"))
    if observed:
        basis = "direct_human_brain_pet_target_engagement_primary_source"
        reason = (
            "A primary human PET study reports central target engagement for this candidate. "
            "That establishes human brain entry for the studied dose/context, but it is not a "
            "CSF concentration, unbound brain concentration, Kp,uu, brain:plasma ratio, tumor "
            "exposure measurement, efficacy result or safety result."
        )
    else:
        basis = "not_extracted_not_available_in_current_sources"
        reason = (
            "no structured human CSF concentration, unbound brain concentration, Kp,uu or "
            "brain:plasma ratio was extracted from the sources cached in this run. This is a "
            "statement about what was extracted here, NOT a claim that no such measurement "
            "exists. Physicochemical properties are properties of the molecule, not observations "
            "of the brain: they may SUGGEST penetrance and can never confirm it, and no assessment "
            "is derived from them."
        )
    return {
        "assessment": (
            "direct human brain target engagement observed" if observed else "unknown"
        ),
        "assessment_state": (
            "human_brain_target_engagement_observed" if observed else "not_evaluated"
        ),
        # WHAT WE DID, not a claim about the world. "No source reports this" would be an assertion
        # about the whole literature, which Stage 4 has not read and cannot make. What is true is
        # narrower and checkable: no such structured value was EXTRACTED from the sources cached in
        # this run. A measured Kp,uu may well exist in a paper nobody here fetched.
        "basis": basis,
        "reason": reason,
        "measured_exposure": {
            field: {"value": None, "state": "not_evaluated",
                    "reason": "not_extracted_from_the_sources_cached_in_this_run"}
            for field in MEASURED_EXPOSURE_FIELDS},
        "direct_human_cns_evidence": direct,
        "nonhuman_cns_evidence": (evidence or {}).get("nonhuman_cns_evidence") or [],
        "physicochemical_proxies": proxies,
        "proxies_are_suggestive_never_confirmatory": True,
        "assessment_is_not_derived_from_proxies": True,
    }


def candidate_row(root: str, candidate: dict[str, Any],
                  evidence: Optional[dict[str, Any]] = None) -> dict[str, Any]:
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
        # NOT a CNS-MPO score. Only three of six published inputs are accepted. Observed component
        # transforms and the mathematically possible total range are emitted for audit, explicitly
        # non-rankable; the total itself remains null.
        "cns_mpo": _cns_mpo_availability(pk, evidence),
        # NEBPI-ALIGNED. Measured human exposure OUTRANKS physicochemical proxies, always. The
        # proxies are shown because they are real sourced numbers — but an assessment is NEVER
        # derived from them, and with no measured exposure the assessment is UNKNOWN, not favorable.
        "brain_penetrance": _brain_penetrance(pk, evidence),
        "safety": _safety(label, label_prov),
    }


def build(prefetch_root: str, stage3_source: Optional[dict[str, Any]] = None,
          only: Optional[set[str]] = None,
          evidence_supplement: Optional[dict[str, Any]] = None,
          evidence_supplement_source: Optional[dict[str, Any]] = None) -> dict[str, Any]:
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
        evidence = ((evidence_supplement or {}).get("candidates") or {}).get(cid)
        rows.append(candidate_row(prefetch_root, candidate, evidence))

    doc: dict[str, Any] = {
        "schema_id": COMPACT_SCHEMA,
        # ARTIFACT ROLE + NAME + HASH. Never a path on this machine — the exact paths live in the
        # internal sidecar, which is not served.
        "evidence_source": {
            "artifact_role": "stage4_prefetch_receipt",
            "artifact_name": "prefetch_receipt.json",
            "content_sha256": receipt.get("content_sha256"),
            "bound_to": receipt.get("bound_to"),
            "artifact_class": "prefetch_only",
        },
        "evidence_supplement_source": evidence_supplement_source or {
            "state": "not_bound",
            "reason": "no typed CNS evidence supplement was supplied",
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
