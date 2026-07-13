"""The identity gate: four public sources must agree, or the candidate is refused.

`identity_converged` -> consequence_on_fail: **refuse_candidate**. Not "flag"; not "prefer the
better source". If PubChem, DailyMed and openFDA do not describe the same active moiety, then at
least one of them is about a different molecule, and every quantitative join downstream — MW,
potency, exposure, a labelled warning — would inherit the wrong one.

Two refusals in particular:

  * **Conflict.** Two sources give different values for the same identifier. Nothing decides
    between them, so nothing may.
  * **Unresolved salt / prodrug / metabolite mapping.** A salt is not its free base, and a
    prodrug is not its active moiety. Administering one and reasoning about the other is the
    mix-up the evidence contract exists to prevent, so an administered form that is not the
    active moiety must carry an explicit, SOURCED mapping to it.

A shared InChIKey skeleton (first block) is not sameness: a salt and its parent share it and
differ in the protonation layer. That is a conflict with a specific explanation, not a match.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .firewall import Rejection

# The identifiers that must converge. `drugbank_id` is deliberately absent: no valid public
# licence has been established for DrugBank, so it is never populated on this path.
IDENTITY_FIELDS = (
    "inchikey", "unii", "pubchem_cid", "rxcui", "dailymed_setid",
)

# NOT single-valued, and not a conflict when there is more than one. TEMODAR's label declares
# NDA021029 (capsule) AND NDA022277 (injection): one label, two approvals, two routes. Forcing
# that into a scalar is what made the old code pick one by position. Every value is carried, in
# canonical order, and `openfda_approval.cross_check_approval` checks the SETS agree.
MULTI_VALUED_FIELDS = ("fda_application_number",)


@dataclass(frozen=True)
class IdentityClaim:
    """One source, saying one thing, on the authority of one response."""

    field: str
    value: str
    source_key: str
    record_id: str


@dataclass(frozen=True)
class ResolvedIdentity:
    inchikey: Optional[str] = None
    unii: Optional[str] = None
    pubchem_cid: Optional[str] = None
    rxcui: Optional[str] = None
    dailymed_setid: Optional[str] = None
    fda_application_numbers: tuple[str, ...] = ()
    active_moiety_name: Optional[str] = None
    administered_form: str = "active_moiety"
    maps_to_active_moiety_id: Optional[str] = None
    mapping_source_record_id: Optional[str] = None
    claims: list[IdentityClaim] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)

    def sources_for(self, name: str) -> list[str]:
        return sorted({c.source_key for c in self.claims if c.field == name})


def claims_from(*, pubchem: Any = None, rxcui: Optional[str] = None, label: Any = None,
                approval: Any = None) -> list[IdentityClaim]:
    """Collect what each acquired response actually said. Nothing is inferred here."""
    claims: list[IdentityClaim] = []

    if pubchem is not None:
        if pubchem.inchikey:
            claims.append(IdentityClaim("inchikey", pubchem.inchikey, "pubchem",
                                        f"pubchem:cid:{pubchem.cid}"))
        claims.append(IdentityClaim("pubchem_cid", pubchem.cid, "pubchem",
                                    f"pubchem:cid:{pubchem.cid}"))

    if rxcui:
        claims.append(IdentityClaim("rxcui", rxcui, "rxnorm", f"rxnorm:rxcui:{rxcui}"))

    if label is not None:
        setid = label.listing.setid
        claims.append(IdentityClaim("dailymed_setid", setid, "dailymed", f"dailymed:{setid}"))
        uniis = list(label.label.active_moiety_unii)
        if len(uniis) > 1:
            raise Rejection(
                "unresolved_salt_prodrug_or_metabolite_mapping",
                f"the selected label ({setid}) declares {len(uniis)} active moieties "
                f"({', '.join(uniis)}). A multi-ingredient product has no single active moiety, "
                "and Stage 4 does not pick one to hang a PK claim on.")
        if uniis:
            claims.append(IdentityClaim("unii", uniis[0], "dailymed", f"dailymed:{setid}"))

    if approval is not None:
        ref = f"openfda:setid:{approval.setid}"
        # Drugs@FDA and the openFDA label record each get their OWN claim. Preferring one over
        # the other would hide a disagreement about which molecule the label is even about.
        if approval.unii:
            claims.append(IdentityClaim("unii", approval.unii, "drugs_at_fda", ref))
        if approval.label_unii:
            claims.append(IdentityClaim("unii", approval.label_unii, "openfda_label", ref))
        for application_number in approval.application_numbers:   # ALL of them, in order
            claims.append(IdentityClaim("fda_application_number", application_number,
                                        "openfda", ref))
        claims.append(IdentityClaim("dailymed_setid", approval.setid, "openfda", ref))
    return claims


def resolve_identity(claims: list[IdentityClaim], *, administered_form: str = "active_moiety",
                     maps_to_active_moiety_id: Optional[str] = None,
                     mapping_source_record_id: Optional[str] = None,
                     active_moiety_name: Optional[str] = None) -> ResolvedIdentity:
    """Converge, or refuse. There is no third outcome."""
    by_field: dict[str, dict[str, list[IdentityClaim]]] = {}
    for claim in claims:
        by_field.setdefault(claim.field, {}).setdefault(claim.value, []).append(claim)

    for name, values in sorted(by_field.items()):
        if name in MULTI_VALUED_FIELDS:
            continue          # more than one is a fact about the product, not a disagreement
        if len(values) > 1:
            raise Rejection("identity_conflict", _conflict_detail(name, values),
                            {"field": name, "values": sorted(values)})

    if administered_form != "active_moiety":
        if not maps_to_active_moiety_id or not mapping_source_record_id:
            raise Rejection(
                "unresolved_salt_prodrug_or_metabolite_mapping",
                f"the administered form is {administered_form!r}, which is not the active moiety. "
                "Stage 4 admits it only with an explicit mapping to the active moiety AND the "
                "source record that establishes the mapping. A salt is not its free base and a "
                "prodrug is not its active moiety; assuming otherwise corrupts MW, exposure and "
                "every join downstream.")

    resolved: dict[str, Any] = {
        name: next(iter(values)) for name, values in by_field.items() if name in IDENTITY_FIELDS
    }
    applications = tuple(sorted(by_field.get("fda_application_number", {})))
    return ResolvedIdentity(
        **resolved,
        fda_application_numbers=applications,
        active_moiety_name=active_moiety_name,
        administered_form=administered_form,
        maps_to_active_moiety_id=maps_to_active_moiety_id,
        mapping_source_record_id=mapping_source_record_id,
        claims=list(claims),
        conflicts=[],
    )


def _conflict_detail(name: str, values: dict[str, list[IdentityClaim]]) -> str:
    parts = []
    for value, claims in sorted(values.items()):
        sources = ", ".join(sorted({c.source_key for c in claims}))
        parts.append(f"{value!r} (from {sources})")
    detail = (
        f"public sources disagree about {name}: {' vs '.join(parts)}. At least one of them is "
        "about a different molecule, and Stage 4 has no basis to choose — so the candidate is "
        "refused rather than characterised on a guess.")
    if name == "inchikey" and _same_skeleton(list(values)):
        detail += (
            " These InChIKeys share their first block: that is a salt/free-base (or "
            "protonation/isotope) relationship, NOT the same molecule for exposure purposes. It "
            "needs a sourced salt->moiety mapping, not a match.")
    return detail


def _same_skeleton(inchikeys: list[str]) -> bool:
    skeletons = {k.split("-")[0] for k in inchikeys if "-" in k}
    return len(skeletons) == 1 and len(inchikeys) > 1
