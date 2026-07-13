"""Rebuild every derived claim from the emitted evidence tables alone.

This is the whole point of the exercise: given only what is in the release directory
(the parquet input bundle + the method JSON + the source catalog), recompute the CNS-MPO
components and totals, the exposure margins, the NEBPI PK derivation and Part-II class,
and the production eligibility — and then compare, cell for cell, with what the generator
claimed in `scorecards.json` and its parquet lanes.

Nothing here imports `analysis/`.
"""

from __future__ import annotations

import json
import os
from decimal import Decimal
from typing import Any, Optional

import pyarrow.parquet as pq

from . import canon
from .delivery import rebuild_delivery

CNS_MPO_PROPERTIES = ("clogp", "clogd_74", "mw", "tpsa", "hbd", "pka_most_basic")
NEB_MATRICES = ("brain_tissue_non_enhancing", "microdialysate_brain_isf")
MARGIN_METRICS = ("MEC", "target_concentration")

# Only an equality is a magnitude to divide by. `>` / `<` / `~` are the source saying the assay
# ran out of range or could not resolve the value. Restated here, not imported: a verifier that
# imported the generator's rule would be checking the generator against itself.
POINT_ESTIMATE_RELATIONS = ("=",)
CONTEXT_FIELDS = ("route", "formulation", "dose", "schedule")
CENSORED_STATUSES = ("not_detected", "below_lloq")

# The whole observation row: the unit of identity for the permutation-invariant reducer.
# Every one of these is a column of nebpi_observations.parquet, so a distinct row can
# never be mistaken here for a duplicate of another.
OBSERVATION_IDENTITY_FIELDS = (
    "observation_id", "candidate_id", "context_id", "criterion_id", "state",
    "assessment_adequate", "adequacy_rationale", "measurement_id", "potency_id",
    "evidence_type", "source_record_id", "source_url", "access_date", "release_version",
    "raw_response_sha256", "extraction_transform",
)


def load_tables(out_dir: str) -> dict[str, list[dict[str, Any]]]:
    tables: dict[str, list[dict[str, Any]]] = {}
    for name in os.listdir(out_dir):
        if name.endswith(".parquet"):
            tables[name[: -len(".parquet")]] = pq.read_table(
                os.path.join(out_dir, name)
            ).to_pylist()
    return tables


def load_method(method_dir: str) -> dict[str, Any]:
    out = {}
    for key, fname in (("cns_mpo", "cns_mpo_wager2010_v1.json"),
                       ("nebpi", "nebpi_grossman2026_v1.json"),
                       ("calculator_policy", "calculator_policy_v1.json"),
                       ("delivery_rules", "delivery_rules_v1.json"),
                       ("safety_taxonomy", "safety_taxonomy_v1.json")):
        with open(os.path.join(method_dir, fname), encoding="utf-8") as fh:
            out[key] = json.load(fh)
    return out


# ------------------------------------------------------------------------- CNS-MPO

def rebuild_cns_mpo(tables: dict[str, list[dict]], method: dict) -> dict[str, dict[str, Any]]:
    """Recompute components + total for every candidate from property_evidence rows.

    More than one accepted row for one property is legal — a value corroborated by two
    agreeing sources — but ONLY if they agree on what determines the score: the calculator
    and the exact value in base units. The audit accepted two rows that agreed on those and
    then bound the score to whichever came first, so one id carried two provenance chains.
    Accepted rows that DISAGREE mean the generator chose one, and the component is refused
    here rather than reproduced.
    """
    specs = {p["property_id"]: p for p in method["cns_mpo"]["properties"]}
    decimals = method["cns_mpo"]["total"]["publication_rounding"]["decimals"]

    by_cand: dict[str, list[dict]] = {}
    for r in tables.get("property_evidence", []):
        by_cand.setdefault(r["candidate_id"], []).append(r)

    out: dict[str, dict[str, Any]] = {}
    for cid in {r["candidate_id"] for r in tables.get("drug_forms", [])}:
        rows = [r for r in by_cand.get(cid, []) if r["accepted"]]
        components: dict[str, Optional[float]] = {p: None for p in CNS_MPO_PROPERTIES}

        accepted_by_prop: dict[str, list[dict]] = {}
        for r in rows:
            accepted_by_prop.setdefault(r["property_id"], []).append(r)

        for prop, prop_rows in accepted_by_prop.items():
            scored = {(r["calculator_id"],
                       str(canon.to_base(r["value_source_string"], r["units"])))
                      for r in prop_rows}
            if len(scored) != 1:
                continue  # ambiguous: no component, and the total cannot be complete
            _calculator, base_decimal = scored.pop()
            components[prop] = canon.desirability(specs[prop], float(base_decimal))

        complete = all(components[p] is not None for p in CNS_MPO_PROPERTIES)
        total_raw: Optional[float] = None
        total_published: Optional[float] = None
        if complete:
            total_raw = float(sum(v for v in components.values() if v is not None))
            total_published = canon.round_half_up(total_raw, decimals)
        out[cid] = {
            "status": "complete" if complete else "incomplete",
            "components": components,
            "total_raw": total_raw,
            "total_published": total_published,
            "n_accepted": len(rows),
        }
    return out


# ------------------------------------------------------------------------- exposure

def _context_agreement(m: dict, ctx: dict) -> list[str]:
    bad = []
    for f in CONTEXT_FIELDS:
        if str(m.get(f, "")).strip().lower() != str(ctx.get(f, "")).strip().lower():
            bad.append(f)
    if m.get("active_moiety_id") != ctx.get("active_moiety_id"):
        bad.append("active_moiety_id")
    return bad


def _shared_gates(m: dict, potency: Optional[dict], ctx: Optional[dict],
                  links: list[dict]) -> Optional[str]:
    """Every gate a usable exposure-vs-potency comparison must pass. -> reason code or None.

    A quantified margin and a censored upper bound both run this. The generator's censored
    path used to skip it, so an IC50 from another disease could underwrite `impermeable`.
    """
    if ctx is None:
        return "dangling_context"
    if m.get("context_id") != ctx.get("context_id") or _context_agreement(m, ctx):
        return "context_disagreement"
    if potency is None:
        return "no_potency_record"
    if m["active_moiety_id"] != potency["active_moiety_id"]:
        return "active_moiety_mismatch"
    if m["candidate_id"] != potency["candidate_id"]:
        return "candidate_mismatch"
    if potency["metric"] not in MARGIN_METRICS:
        return "potency_metric_not_a_target_concentration"
    # A censored/approximate potency is a bound, not a magnitude. `relation` defaults to "="
    # for a v1 row, which is exactly how a v1 bare magnitude was already read.
    if (potency.get("relation") or "=") not in POINT_ESTIMATE_RELATIONS:
        return "potency_relation_not_a_point_estimate"
    if "unspecified" in (m["binding_state"], potency["binding_state"]):
        return "binding_state_unspecified"
    if m["binding_state"] != potency["binding_state"]:
        return "free_total_mismatch"
    unknown = {"", "unknown", "unspecified", "not_specified"}
    if any(str(m.get(f, "")).strip().lower() in unknown for f in ("route", "dose", "schedule")):
        return "dosing_context_unknown"
    if potency["biological_context"] != ctx["tumor_context"]:
        if not any(row["potency_id"] == potency["potency_id"]
                   and row["tumor_context"] == ctx["tumor_context"] for row in links):
            return "potency_context_not_relevant"
    return None


def rebuild_margin(m: dict, potency: Optional[dict], ctx: Optional[dict],
                   links: list[dict]) -> dict[str, Any]:
    """Recompute one exposure margin, applying the declared gates from scratch."""
    def nc(code: str) -> dict[str, Any]:
        return {"status": "not_computable", "reason_code": code,
                "margin_canonical_decimal": None}

    gate = _shared_gates(m, potency, ctx, links)
    if gate:
        return nc(gate)
    assert potency is not None  # _shared_gates rejects a missing potency

    if not m.get("concentration_source_string"):
        return nc("no_quantified_concentration")
    if canon.dimension(m["concentration_units"]) != canon.dimension(potency["units"]):
        return nc("unit_family_mismatch")

    num = canon.to_base(m["concentration_source_string"], m["concentration_units"])
    den = canon.to_base(potency["value_source_string"], potency["units"])
    if den == 0:
        return nc("margin_undefined")
    return {"status": "computed", "reason_code": None,
            "margin_canonical_decimal": canon.ratio_decimal(num, den)}


def rebuild_censored_bound(m: dict, potency: Optional[dict], ctx: Optional[dict],
                           links: list[dict]) -> dict[str, Any]:
    """Can this non-detect exclude the MEC? Independent restatement of censored_pk_policy.

    `not_detected` is a statement about the assay, not the drug. It bounds nothing unless
    the source declares how low the assay could see, and that bound is STRICTLY below the
    MEC. Method: nebpi_grossman2026_v1.json::censored_pk_policy.
    """
    def nc(code: str) -> dict[str, Any]:
        return {"status": "not_computable", "reason_code": code, "bound_below_mec": None,
                "bound_over_mec_canonical_decimal": None}

    if m.get("detection_status") not in CENSORED_STATUSES:
        return nc("not_a_censored_measurement")

    gate = _shared_gates(m, potency, ctx, links)
    if gate:
        return nc(gate)
    assert potency is not None  # _shared_gates rejects a missing potency

    kind = m.get("quantitation_limit_kind")
    bound_str = m.get("quantitation_limit_source_string")
    bound_units = m.get("quantitation_limit_units")
    if not bound_str or not bound_units or not kind:
        return nc("no_source_bound_quantitation_limit")
    # A below_lloq value may lie above the LOD, so only an LLOQ bounds it from above.
    if m["detection_status"] == "below_lloq" and kind != "lloq":
        return nc("invalid_quantitation_limit_kind")
    if kind not in ("lod", "lloq"):
        return nc("invalid_quantitation_limit_kind")
    if canon.dimension(bound_units) != canon.dimension(potency["units"]):
        return nc("unit_family_mismatch")

    bound = canon.to_base(bound_str, bound_units)
    mec = canon.to_base(potency["value_source_string"], potency["units"])
    if bound <= 0:
        return nc("invalid_quantitation_limit")
    if mec == 0:
        return nc("margin_undefined")

    ratio = canon.ratio_decimal(bound, mec)
    if not bound < mec:  # STRICT: a bound equal to the MEC excludes nothing.
        return {"status": "not_computable", "reason_code": "censored_bound_not_below_mec",
                "bound_below_mec": False, "bound_over_mec_canonical_decimal": ratio}
    return {"status": "computed", "reason_code": None, "bound_below_mec": True,
            "bound_over_mec_canonical_decimal": ratio}


def rebuild_margins(tables: dict[str, list[dict]]) -> dict[str, dict[str, Any]]:
    ctxs = {c["context_id"]: c for c in tables.get("contexts", [])}
    pots = {p["potency_id"]: p for p in tables.get("potency_evidence", [])}
    links = tables.get("potency_context_links", [])

    out = {}
    for m in tables.get("exposure_evidence", []):
        # The margin denominator is the candidate's single admissible MEC row.
        usable = [p for p in pots.values()
                  if p["candidate_id"] == m["candidate_id"] and p["metric"] in MARGIN_METRICS]
        potency = usable[0] if len(usable) == 1 else None
        code = None
        if len(usable) > 1:
            code = "ambiguous_potency_records"
        elif not usable:
            mine = [p for p in pots.values() if p["candidate_id"] == m["candidate_id"]]
            code = "potency_metric_not_a_target_concentration" if mine else "no_potency_record"
        if code:
            out[m["measurement_id"]] = {"status": "not_computable", "reason_code": code,
                                        "margin_canonical_decimal": None}
            continue
        out[m["measurement_id"]] = rebuild_margin(m, potency, ctxs.get(m["context_id"]), links)
    return out


# ---------------------------------------------------------------------------- NEBPI

def rebuild_nebpi(tables: dict[str, list[dict]], method: dict) -> dict[tuple[str, str], dict]:
    """Re-derive the PK level, criterion states and the Part-II class from the rows alone."""
    meas = {m["measurement_id"]: m for m in tables.get("exposure_evidence", [])}
    pots = {p["potency_id"]: p for p in tables.get("potency_evidence", [])}
    links = tables.get("potency_context_links", [])
    # The gate comes from OUR reduction of the assignment rows, not from the generator's
    # `delivery_evidence`. Reading the generator's answer back would make the check a
    # tautology — which is how a delivery assignment citing a nonexistent source came to
    # set `nebpi_primary_gate=true` with both verifiers passing.
    delivery = rebuild_delivery(tables, method)
    criteria = [c["criterion_id"] for c in method["nebpi"]["part_i_criteria"]]

    obs_by: dict[tuple[str, str], list[dict]] = {}
    for o in tables.get("nebpi_observations", []):
        obs_by.setdefault((o["candidate_id"], o["context_id"]), []).append(o)

    out: dict[tuple[str, str], dict] = {}
    for key, ctx in (((c["candidate_id"], c["context_id"]), c) for c in tables.get("contexts", [])):
        obs = obs_by.get(key, [])
        pk_level, pk_blocked = _derive_pk(obs, ctx, meas, pots, links)
        pd_state = _reduce(obs, "pd_in_neb")[0]
        rad_state = _reduce(obs, "radiographic_response_in_neb")[0]

        # criterion_states comes from the SAME reducer as the branch logic — there is no
        # separate last-row-wins path to disagree with.
        criterion_states = {c: _reduce(obs, c)[0] for c in criteria}
        criterion_states["pk_in_neb"] = pk_level

        unknown = {"", "unknown", "unspecified", "not_specified"}
        ctx_ok = not any(str(ctx.get(f, "")).strip().lower() in unknown
                         for f in ("route", "formulation", "dose", "schedule", "tumor_context"))

        pk_derived = pk_level in ("pk_therapeutic_in_neb", "pk_low_in_neb",
                                  "pk_little_to_none_in_neb")
        pk_usable = pk_derived and ctx_ok

        sufficient = (
            (pk_usable and pk_level == "pk_therapeutic_in_neb")
            or (ctx_ok and pd_state == "observed_present")
            or (ctx_ok and rad_state == "observed_present")
        )
        pd_absent = pd_state == "observed_absent"
        rad_absent = rad_state == "observed_absent"
        insufficient = pk_usable and pk_level == "pk_low_in_neb" and pd_absent and rad_absent
        impermeable = pk_usable and pk_level == "pk_little_to_none_in_neb" and pd_absent and rad_absent

        if sufficient:
            cls, status = "sufficiently_permeable", "classified"
        elif insufficient:
            cls, status = "insufficiently_permeable", "classified"
        elif impermeable:
            cls, status = "impermeable", "classified"
        else:
            cls, status = None, "not_classifiable"

        d = delivery.get(key, {})
        out[key] = {
            "nebpi_status": status, "nebpi_class": cls,
            "derived_pk_level": pk_level, "pk_blocked_code": pk_blocked,
            "pd_state": pd_state, "radiographic_state": rad_state,
            "criterion_states": dict(sorted(criterion_states.items())),
            "nebpi_primary_gate": d.get("nebpi_primary_gate"),
        }
    return out


def _derive_pk(obs: list[dict], ctx: dict, meas: dict, pots: dict,
               links: list[dict]) -> tuple[str, Optional[str]]:
    state, o = _reduce(obs, "pk_in_neb")
    if state == "conflicting":
        return "pk_conflicting", "conflicting_pk_observations"
    if o is None:
        return "pk_not_evaluated", None
    m = meas.get(o.get("measurement_id") or "")
    if m is None:
        return "pk_not_evaluated", "measurement_not_found"
    p = pots.get(o.get("potency_id") or "")
    if p is None:
        return "pk_not_evaluated", "potency_not_found"
    if m["candidate_id"] != o["candidate_id"] or m["context_id"] != o["context_id"]:
        return "pk_not_evaluated", "measurement_context_mismatch"
    if m["active_moiety_id"] != ctx["active_moiety_id"]:
        return "pk_not_evaluated", "measurement_moiety_mismatch"
    if m["matrix"] not in NEB_MATRICES or m["enhancement_context"] != "non_enhancing":
        return "pk_not_evaluated", "measurement_not_in_neb"

    # "Little to no drug in NEB" carries footnote (a) too: it is a claim RELATIVE TO THE
    # MEC, so the non-detect must be bounded and the bound must clear the MEC.
    if m["detection_status"] in CENSORED_STATUSES:
        bound = rebuild_censored_bound(m, p, ctx, links)
        if bound["status"] != "computed":
            return "pk_not_evaluated", bound["reason_code"]
        return "pk_little_to_none_in_neb", None

    margin = rebuild_margin(m, p, ctx, links)
    if margin["status"] != "computed":
        return "pk_not_evaluated", margin["reason_code"]
    value = Decimal(margin["margin_canonical_decimal"])
    return ("pk_therapeutic_in_neb" if value >= 1 else "pk_low_in_neb"), None


def _observation_identity(o: dict) -> str:
    """The whole row is the identity. Anything less than byte-identical is a distinct row."""
    return canon.chash({k: o.get(k) for k in OBSERVATION_IDENTITY_FIELDS})


def _reduce(obs: list[dict], criterion: str) -> tuple[str, Optional[dict]]:
    """Permutation-invariant. Independent restatement of evidence_reduction_policy.

    Byte-identical duplicates collapse (they are the same record and add no evidence);
    two DISTINCT rows for one criterion are `conflicting` and satisfy no branch, in every
    order. There is no first-row-wins here.
    """
    unique: dict[str, dict] = {}
    for o in obs:
        if o["criterion_id"] == criterion:
            unique.setdefault(_observation_identity(o), o)
    keys = sorted(unique)
    if not keys:
        return "not_evaluated", None
    if len(keys) > 1:
        return "conflicting", None
    r = unique[keys[0]]
    if r["state"] == "observed_absent" and not r.get("assessment_adequate"):
        return "absent_claim_inadequate", r
    return r["state"], r


# ----------------------------------------------------------------------- eligibility

def rebuild_eligibility(tables: dict[str, list[dict]], namespace: str) -> dict[str, dict]:
    """Production eligibility, re-derived from the source catalog and the namespace."""
    catalog = tables.get("source_catalog", [])
    any_fixture = any(r["acquisition_status"] != "acquired_public" for r in catalog)
    out = {}
    for f in tables.get("drug_forms", []):
        if namespace != "production" or f["namespace"] != "production":
            code = "research_only_namespace" if "research" in (namespace, f["namespace"]) \
                else "fixture_namespace"
            eligible = False
        elif f["direction_compatibility"] == "incompatible":
            eligible, code = False, "direction_incompatible"
        elif f["direction_compatibility"] == "unknown":
            eligible, code = False, "direction_unknown"
        elif any_fixture:
            eligible, code = False, "non_public_source_in_evidence"
        else:
            eligible, code = True, "eligible"
        out[f["candidate_id"]] = {"production_eligible": eligible, "reason_code": code}
    return out
