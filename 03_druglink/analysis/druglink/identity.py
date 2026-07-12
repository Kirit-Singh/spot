"""The drug identity / form graph (audit finding 3).

Two separate mechanisms, deliberately:

  * IDENTIFIERS merge. Records sharing an identifier token (``chembl_id=CHEMBL25``,
    ``pubchem_cid=2244``, ``unii=...``) describe one entity, so a ChEMBL molecule
    and its PubChem/RxNorm cross-references collapse into one FORM. Every
    identifier assertion is still emitted as its own row with its source.

  * MOIETY ASSIGNMENT does not merge. It is derived ONLY from explicit, sourced
    relation edges (is_salt_of, is_precise_ingredient_of, is_prodrug_of,
    is_active_metabolite_of, has_ingredient, is_parent_of_self). A salt never
    inherits its parent's structure, an assay on a parent never becomes an assay
    on the salt, and a product with two ingredients resolves to NO single moiety
    (``multi_ingredient``) rather than to ``ingredients[0]``.

Fail-closed: contradictory redirects or cycles -> ``ambiguous``; no resolvable
terminal -> ``AM:UNRESOLVED:*`` with identity_status ``unresolved``. Neither may
enter a direction-compatible lane in any namespace, and ``AM:UNRESOLVED`` can
never carry identity_status ``resolved``.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from .hashing import short_id

IDENTITY_POLICY_VERSION = "stage3-identity-v2"

ID_TYPES = ("inchikey", "chembl_id", "pubchem_cid", "rxcui", "unii")
FORM_ID_PRIORITY = (("chembl_id", "CHEMBL"), ("pubchem_cid", "CID"),
                    ("rxcui", "RXCUI"), ("inchikey", "INCHIKEY"), ("unii", "UNII"))
MOIETY_ID_PRIORITY = (("inchikey", "INCHIKEY"), ("chembl_id", "CHEMBL"),
                      ("pubchem_cid", "CID"), ("rxcui", "RXCUI"), ("unii", "UNII"))

REDIRECT_RELATIONS = ("is_salt_of", "is_precise_ingredient_of", "is_prodrug_of")
TERMINAL_RELATIONS = ("is_parent_of_self", "is_active_metabolite_of")
INGREDIENT_RELATION = "has_ingredient"

DEV_APPROVED = "approved"
DEV_WITHDRAWN = "withdrawn"
_INVESTIGATIONAL = ("phase_4", "phase_3", "phase_2", "phase_1", "preclinical")


class _DSU:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def tokens(identifiers: dict[str, Any]) -> list[str]:
    return [f"{t}={identifiers[t]}" for t in ID_TYPES
            if identifiers.get(t) not in (None, "")]


def _pick_id(identifiers: dict[str, Any], priority) -> Optional[tuple[str, str]]:
    for field, prefix in priority:
        v = identifiers.get(field)
        if v not in (None, ""):
            return prefix, str(v)
    return None


def form_id_of(identifiers: dict[str, Any]) -> Optional[str]:
    hit = _pick_id(identifiers, FORM_ID_PRIORITY)
    return f"{hit[0]}:{hit[1]}" if hit else None


def moiety_id_of(identifiers: dict[str, Any], fallback_seed: Any) -> str:
    hit = _pick_id(identifiers, MOIETY_ID_PRIORITY)
    if hit:
        return f"AM:{hit[0]}:{hit[1]}"
    return f"AM:UNRESOLVED:{short_id(fallback_seed)}"


def development_aggregate(states: Iterable[Optional[str]]) -> str:
    s = {x for x in states if x}
    if DEV_APPROVED in s and DEV_WITHDRAWN in s:
        return "approved_withdrawn_conflict"     # a conflict, never a "best" pick
    if DEV_APPROVED in s:
        return DEV_APPROVED
    if DEV_WITHDRAWN in s:
        return DEV_WITHDRAWN
    if s & set(_INVESTIGATIONAL):
        return "investigational"
    return "unknown"


def build_graph(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Return {forms, identifiers, relations, moieties, dispositions}."""
    claims = [r for r in records if r.get("record_kind") == "form_claim"]
    dsu = _DSU()

    def unite(identifiers: dict[str, Any]) -> None:
        toks = tokens(identifiers)
        for t in toks[1:]:
            dsu.union(toks[0], t)

    for c in claims:
        unite(c["identifiers"])
        for rel in c["relations"]:
            unite(rel["to_identifiers"])       # referenced entities exist too

    # ---- components -> forms ------------------------------------------------
    comps: dict[str, dict[str, Any]] = {}

    def component(identifiers: dict[str, Any]) -> Optional[dict[str, Any]]:
        toks = tokens(identifiers)
        if not toks:
            return None
        key = dsu.find(toks[0])
        c = comps.setdefault(key, {
            "component": key, "identifiers": {}, "form_classes": set(),
            "route": None, "route_source": None, "formulation": None,
            "formulation_source": None, "preferred_names": [],
            "development_states": [], "conflicts": [], "source_record_ids": set(),
            "identifier_rows": [], "relations": [],
        })
        for t in ID_TYPES:
            v = identifiers.get(t)
            if v in (None, ""):
                continue
            cur = c["identifiers"].get(t)
            if cur is None:
                c["identifiers"][t] = str(v)
            elif cur != str(v):
                c["conflicts"].append(f"{t}_conflict:{cur}|{v}")
        return c

    for c in claims:
        comp = component(c["identifiers"])
        if comp is None:
            continue
        comp["source_record_ids"].add(c["source_record_id"])
        if c.get("form_class"):
            comp["form_classes"].add(c["form_class"])
        if c.get("preferred_name"):
            comp["preferred_names"].append(c["preferred_name"])
        if c.get("development_state"):
            comp["development_states"].append(c["development_state"])
        for field in ("route", "formulation"):
            v = c.get(field)
            if v is None:
                continue
            if comp[field] is None:
                comp[field] = v
                comp[f"{field}_source"] = c["source_record_id"]
            elif comp[field] != v:
                comp["conflicts"].append(f"{field}_conflict:{comp[field]}|{v}")
        for t in ID_TYPES:
            if c["identifiers"].get(t) not in (None, ""):
                comp["identifier_rows"].append({
                    "id_type": t, "id_value": str(c["identifiers"][t]),
                    "source": c["source"], "source_record_id": c["source_record_id"]})
        for rel in c["relations"]:
            target = component(rel["to_identifiers"])
            if target is None:
                comp["conflicts"].append(f"relation_{rel['relation']}_without_identifier")
                continue
            comp["relations"].append({"relation": rel["relation"],
                                      "to_component": target["component"],
                                      "source": c["source"],
                                      "source_record_id": c["source_record_id"]})

    # ---- form rows ----------------------------------------------------------
    form_of_component: dict[str, str] = {}
    for key, c in comps.items():
        fid = form_id_of(c["identifiers"])
        form_of_component[key] = fid or f"UNIDENTIFIED:{short_id(key)}"

    forms: dict[str, dict[str, Any]] = {}
    identifier_rows: list[dict[str, Any]] = []
    relation_rows: list[dict[str, Any]] = []
    for key, c in sorted(comps.items()):
        fid = form_of_component[key]
        classes = sorted(c["form_classes"])
        if len(classes) > 1:
            c["conflicts"].append("form_class_conflict:" + "|".join(classes))
        ingredients = sorted({form_of_component[r["to_component"]]
                              for r in c["relations"]
                              if r["relation"] == INGREDIENT_RELATION})
        forms[fid] = {
            "form_id": fid,
            "preferred_name": (sorted(c["preferred_names"])[0]
                               if c["preferred_names"] else None),
            "form_class": (classes[0] if len(classes) == 1
                           else "unclassified" if not classes else "unclassified"),
            "identifiers": dict(c["identifiers"]),
            "ingredient_form_ids": ingredients,
            "n_ingredients": len(ingredients),
            "route": c["route"],
            "route_status": "sourced" if c["route"] else "not_sourced",
            "formulation": c["formulation"],
            "formulation_status": "sourced" if c["formulation"] else "not_sourced",
            "development_states": sorted(set(c["development_states"])),
            "identity_conflicts": sorted(set(c["conflicts"])),
            "source_record_ids": sorted(c["source_record_ids"]),
            "_relations": c["relations"],
            "_component": key,
        }
        for row in c["identifier_rows"]:
            identifier_rows.append({"form_id": fid, **row})
        for r in c["relations"]:
            relation_rows.append({
                "from_form_id": fid, "relation": r["relation"],
                "to_form_id": form_of_component[r["to_component"]],
                "source": r["source"], "source_record_id": r["source_record_id"]})

    # ---- moiety assignment: relation edges only ----------------------------
    def resolve(fid: str, seen: tuple[str, ...] = ()) -> tuple[Optional[str], str, list[str]]:
        """(terminal_form_id, status, reasons)"""
        if fid in seen:
            return None, "ambiguous", [f"relation_cycle:{'->'.join(seen + (fid,))}"]
        form = forms[fid]
        rels = form["_relations"]
        redirects = sorted({form_of_component[r["to_component"]] for r in rels
                            if r["relation"] in REDIRECT_RELATIONS})
        terminal = any(r["relation"] in TERMINAL_RELATIONS for r in rels)
        ingredients = form["ingredient_form_ids"]

        if len(redirects) > 1:
            return None, "ambiguous", [
                "conflicting_moiety_redirects:" + "|".join(redirects)]
        if redirects:
            if redirects[0] == fid:
                return fid, "resolved", []
            return resolve(redirects[0], seen + (fid,))
        if len(ingredients) > 1:
            return None, "multi_ingredient", [
                f"multi_ingredient_product:{len(ingredients)}_ingredients"]
        if len(ingredients) == 1:
            return resolve(ingredients[0], seen + (fid,))
        if terminal:
            return fid, "resolved", []
        return None, "unresolved", ["no_sourced_relation_to_an_active_moiety"]

    moieties: dict[str, dict[str, Any]] = {}
    dispositions: list[dict[str, Any]] = []
    for fid in sorted(forms):
        form = forms[fid]
        terminal, status, reasons = resolve(fid)
        conflicts = sorted(set(form["identity_conflicts"] + reasons))
        if conflicts and status == "resolved":
            status = "ambiguous"

        if status == "resolved" and terminal:
            t = forms[terminal]
            mid = moiety_id_of(t["identifiers"], fallback_seed=terminal)
        else:
            mid = f"AM:UNRESOLVED:{short_id(fid)}"

        form["moiety_assignment_status"] = (
            "resolved_single_moiety" if status == "resolved" else
            "multi_ingredient" if status == "multi_ingredient" else
            "ambiguous" if status == "ambiguous" else "unresolved")
        form["active_moiety_id"] = mid
        form["identity_conflicts"] = conflicts

        m = moieties.setdefault(mid, {
            "active_moiety_id": mid, "preferred_name": None,
            "moiety_inchikey": None, "moiety_chembl_id": None,
            "moiety_pubchem_cid": None, "moiety_rxcui": None, "moiety_unii": None,
            "identity_status": "resolved", "identity_conflicts": [],
            "form_ids": [], "development_states": [], "source_record_ids": set(),
        })
        m["form_ids"].append(fid)
        m["development_states"].extend(form["development_states"])
        m["source_record_ids"].update(form["source_record_ids"])
        m["identity_conflicts"].extend(conflicts)

        if status == "resolved" and terminal:
            t = forms[terminal]
            m["moiety_inchikey"] = t["identifiers"].get("inchikey")
            m["moiety_chembl_id"] = t["identifiers"].get("chembl_id")
            m["moiety_pubchem_cid"] = t["identifiers"].get("pubchem_cid")
            m["moiety_rxcui"] = t["identifiers"].get("rxcui")
            m["moiety_unii"] = t["identifiers"].get("unii")
            m["preferred_name"] = m["preferred_name"] or t["preferred_name"]
        else:
            m["identity_status"] = status
            dispositions.append({
                "subject_kind": "drug_form", "subject_id": fid,
                "state": form["moiety_assignment_status"],
                "reason": (reasons or conflicts or ["unresolved"])[0],
                "detail": "; ".join(conflicts) or None,
                "source_record_id": form["source_record_ids"][0]
                if form["source_record_ids"] else None,
            })

    out_moieties: dict[str, dict[str, Any]] = {}
    for mid, m in moieties.items():
        conflicts = sorted(set(m["identity_conflicts"]))
        status = m["identity_status"]
        if mid.startswith("AM:UNRESOLVED:") and status == "resolved":
            status = "unresolved"          # invariant: UNRESOLVED is never resolved
        if conflicts and status == "resolved":
            status = "ambiguous"
        out_moieties[mid] = {
            "active_moiety_id": mid,
            "preferred_name": m["preferred_name"],
            "moiety_inchikey": m["moiety_inchikey"],
            "moiety_chembl_id": m["moiety_chembl_id"],
            "moiety_pubchem_cid": m["moiety_pubchem_cid"],
            "moiety_rxcui": m["moiety_rxcui"],
            "moiety_unii": m["moiety_unii"],
            "identity_status": status,
            "identity_conflicts": conflicts,
            "form_ids": sorted(set(m["form_ids"])),
            "development_states": sorted(set(m["development_states"])),
            "development_state_aggregate": development_aggregate(m["development_states"]),
            "source_record_ids": sorted(m["source_record_ids"]),
        }

    emitted_forms = []
    for fid in sorted(forms):
        f = dict(forms[fid])
        f.pop("_relations")
        f.pop("_component")
        f.pop("identifiers")
        emitted_forms.append(f)

    return {
        "forms": emitted_forms,
        "form_index": {f["form_id"]: f for f in emitted_forms},
        "identifiers": sorted(identifier_rows,
                              key=lambda r: (r["form_id"], r["id_type"],
                                             r["id_value"], r["source_record_id"])),
        "relations": sorted(relation_rows,
                            key=lambda r: (r["from_form_id"], r["relation"],
                                           r["to_form_id"], r["source_record_id"])),
        "moieties": out_moieties,
        "dispositions": dispositions,
        "token_index": {tok: form_of_component[dsu.find(tok)]
                        for tok in dsu.parent},
    }


def form_for_identifiers(graph: dict[str, Any],
                         identifiers: dict[str, Any]) -> Optional[str]:
    for tok in tokens(identifiers):
        fid = graph["token_index"].get(tok)
        if fid:
            return fid
    return None
