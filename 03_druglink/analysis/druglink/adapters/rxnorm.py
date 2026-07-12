"""RxNorm / RxNav adapters, against the ACTUAL published response shapes.

The previous build invented RxNorm fields. Corrected here:

  * ``getAllRelatedInfo`` returns root ``allRelatedGroup`` (not ``relatedGroup``),
    whose ``conceptGroup[].conceptProperties[]`` carry only rxcui, name, synonym,
    tty, language, suppress, umlscui. There is NO ``unii``, NO ``route`` and NO
    ``doseFormName`` on those concepts, so none is read.
  * UNII comes from a SEPARATE endpoint: ``/rxcui/{rxcui}/property?propName=UNII_CODE``
    -> ``propConceptGroup.propConcept[]``.
  * Dose form comes from a SEPARATE endpoint: ``/rxcui/{rxcui}/related?tty=DF+DFG``
    -> root ``relatedGroup``. That yields a FORMULATION only. RxNorm does not state
    a route there, so route stays null with route_status=not_sourced.

Multi-ingredient products are modelled explicitly: every IN concept becomes a
``has_ingredient`` relation. ``ingredients[0]`` is never chosen.
"""
from __future__ import annotations

from typing import Any

from . import base
from .base import require

SOURCE = "rxnorm"
VERSION = "rxnorm-adapter-v2"

_PRODUCT_TTYS = ("SCD", "SBD", "GPCK", "BPCK", "SCDC", "SBDC")


def _concept_groups(root: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for g in root.get("conceptGroup") or []:
        tty = g.get("tty")
        props = g.get("conceptProperties") or []
        if tty and props:
            groups.setdefault(tty, []).extend(props)
    return groups


def parse_allrelated(raw: Any, entry: dict[str, Any], src_id: str) -> list[dict[str, Any]]:
    require(isinstance(raw, dict) and "allRelatedGroup" in raw,
            "RxNav getAllRelatedInfo response must have an 'allRelatedGroup' root "
            "(a 'relatedGroup' root is a different endpoint)")
    root = raw["allRelatedGroup"]
    require(isinstance(root.get("conceptGroup"), list),
            "allRelatedGroup must carry conceptGroup[]")
    query_rxcui = entry["query"].get("rxcui")
    require(bool(query_rxcui), "rxnorm_allrelated entry must record query.rxcui")
    query_rxcui = str(query_rxcui)

    groups = _concept_groups(root)
    ingredients = groups.get("IN") or []
    out: list[dict[str, Any]] = []

    # Every ingredient is its own parent form.
    for ing in ingredients:
        out.append(base.form_claim(
            source=SOURCE, source_record_id=src_id,
            identifiers=base.ids(rxcui=ing["rxcui"]),
            form_class="parent",
            relations=[base.relation("is_parent_of_self",
                                     base.ids(rxcui=ing["rxcui"]))],
            preferred_name=ing.get("name")))

    # Precise ingredients (often a salt/specific form of the base ingredient).
    for pin in groups.get("PIN") or []:
        rels = [base.relation("is_precise_ingredient_of", base.ids(rxcui=i["rxcui"]))
                for i in ingredients]
        out.append(base.form_claim(
            source=SOURCE, source_record_id=src_id,
            identifiers=base.ids(rxcui=pin["rxcui"]),
            form_class="salt" if len(ingredients) == 1 else "unclassified",
            relations=rels, preferred_name=pin.get("name")))

    # The queried concept itself, when it is a product: link EVERY ingredient.
    queried_tty = None
    for tty in _PRODUCT_TTYS + ("IN", "PIN", "MIN"):
        if any(str(c.get("rxcui")) == query_rxcui for c in groups.get(tty) or []):
            queried_tty = tty
            break
    products = [(tty, c) for tty in _PRODUCT_TTYS for c in groups.get(tty) or []]
    for tty, prod in products:
        rels = [base.relation("has_ingredient", base.ids(rxcui=i["rxcui"]))
                for i in ingredients]
        n_ing = len(ingredients)
        out.append(base.form_claim(
            source=SOURCE, source_record_id=src_id,
            identifiers=base.ids(rxcui=prod["rxcui"]),
            form_class=("multi_ingredient_product" if n_ing > 1
                        else "marketed_product"),
            relations=rels, preferred_name=prod.get("name")))

    # A multi-ingredient concept (MIN) is explicitly multi-ingredient.
    for mini in groups.get("MIN") or []:
        out.append(base.form_claim(
            source=SOURCE, source_record_id=src_id,
            identifiers=base.ids(rxcui=mini["rxcui"]),
            form_class="multi_ingredient_product",
            relations=[base.relation("has_ingredient", base.ids(rxcui=i["rxcui"]))
                       for i in ingredients],
            preferred_name=mini.get("name")))

    if queried_tty is None and not out:
        raise base.UnsupportedSchema(
            f"queried rxcui {query_rxcui} appears in no concept group")
    return out


def parse_property(raw: Any, entry: dict[str, Any], src_id: str) -> list[dict[str, Any]]:
    require(isinstance(raw, dict) and "propConceptGroup" in raw,
            "RxNav property response must have a 'propConceptGroup' root")
    concepts = (raw["propConceptGroup"] or {}).get("propConcept") or []
    rxcui = entry["query"].get("rxcui")
    require(bool(rxcui), "rxnorm_property entry must record query.rxcui")
    out: list[dict[str, Any]] = []
    for c in concepts:
        if c.get("propName") == "UNII_CODE" and c.get("propValue"):
            out.append(base.form_claim(
                source=SOURCE, source_record_id=src_id,
                identifiers=base.ids(rxcui=rxcui, unii=c["propValue"]),
                form_class=None, relations=[]))
    return out


def parse_dose_form(raw: Any, entry: dict[str, Any], src_id: str) -> list[dict[str, Any]]:
    require(isinstance(raw, dict) and "relatedGroup" in raw,
            "RxNav related?tty= response must have a 'relatedGroup' root")
    root = raw["relatedGroup"]
    rxcui = entry["query"].get("rxcui")
    require(bool(rxcui), "rxnorm_dose_form entry must record query.rxcui")
    groups = _concept_groups(root)
    forms = (groups.get("DF") or [])
    if not forms:
        return []
    # Formulation is sourced. RxNorm does not state a route here, so route stays
    # unsourced rather than being inferred from the dose-form name.
    return [base.form_claim(
        source=SOURCE, source_record_id=src_id, identifiers=base.ids(rxcui=rxcui),
        form_class=None, relations=[], formulation=forms[0].get("name"),
        route=None)]


ADAPTERS = {
    "rxnorm_allrelated": base.Adapter(
        "rxnorm_allrelated", VERSION, SOURCE, base.FIXTURE_SHAPED,
        ("/REST/rxcui/{rxcui}/allrelated.json",), parse_allrelated),
    "rxnorm_property": base.Adapter(
        "rxnorm_property", VERSION, SOURCE, base.FIXTURE_SHAPED,
        ("/REST/rxcui/{rxcui}/property.json?propName=UNII_CODE",), parse_property),
    "rxnorm_dose_form": base.Adapter(
        "rxnorm_dose_form", VERSION, SOURCE, base.FIXTURE_SHAPED,
        ("/REST/rxcui/{rxcui}/related.json?tty=DF+DFG",), parse_dose_form),
}
