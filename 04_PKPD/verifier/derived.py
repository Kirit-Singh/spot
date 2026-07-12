"""Reconstruct every DERIVED cell of every evidence table, from the bound inputs alone.

A derived column is a pure function of (bound input rows, method, code) — all three of which
are already in the `scorecard_set_id`. So the right defence is not to hash it into identity
again, it is to RECOMPUTE it and insist the release agrees. A resealed tamper can rewrite the
cell and every hash around it; it cannot make the arithmetic come out.

The full-column sweep of the resealed release found 20 derived cells that no check
reconstructed — a margin's `potency_context_link_id` and `caveats`, a property's
`component_score_t0`, a safety row's `renders_as_safe`, and so on. Each is rebuilt here.

NOTHING is exempt. `property_evidence.rejection_reason` and `exposure_evidence.margin_reason`
used to be — free prose, bound by nothing, reconstructed by nothing, excused because a machine
code sat next to them. A neighbouring code does not license unbound prose: the sentence a human
actually reads could be rewritten to say anything while the code beside it stayed honest. Both
columns are now GONE from the parquet; the typed code is reconstructed here, and the human
sentence lives in scorecards.json where prose belongs.

`evidence_state_display` is pinned verbatim below for the same reason — rewriting
`no_evidence_found` to read like a clean bill of health is the most dangerous edit available on
a release, and "it is only display text" is exactly the excuse that would let it through.

Imports nothing from `analysis/`.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from . import canon
from .reconstruct import MARGIN_METRICS, rebuild_margin

# dimension -> base unit. The published transforms are evaluated on these.
BASE_UNIT = {
    "molar": "nM", "mass_per_volume": "ng/mL", "mass_per_mass": "ng/g",
    "molar_mass": "g/mol", "polar_surface_area": "A^2", "log10": "log10",
    "count": "count", "pka": "pka", "ratio": "ratio",
}

# NOT ONE of the five evidence states renders as "safe" — not even `no_evidence_found`, which
# is a statement about the SEARCH. The method file says so in its hard rules; this is the
# independent restatement of that rule.
RENDERS_AS_SAFE = False

# What each state is allowed to say, pinned verbatim. This is the text a reader sees next to a
# finding, so a tamper here is a scientific claim changing — rewriting `no_evidence_found` to
# read like a clean bill of health is the single most dangerous edit anyone could make to a
# release, and it is exactly the edit an "it's only display text" exemption would have allowed.
EVIDENCE_STATE_DISPLAY = {
    "label_supported": "Stated in the cited section of the cited label version.",
    "literature_supported": "Stated in the cited publication.",
    "signal_only": (
        "Spontaneous-report / disproportionality signal only. Hypothesis-generating. Cannot "
        "establish incidence, causality, safety or a contraindication."
    ),
    "no_evidence_found": (
        "The named sources were searched and returned nothing for this item. This is a statement "
        "about the search, NOT a finding of safety. Absence of evidence is not evidence of absence."
    ),
    "not_evaluated": "Not searched in any source. Nothing is known either way.",
}

CNS_MPO_PROPERTIES = ("clogp", "clogd_74", "mw", "tpsa", "hbd", "pka_most_basic")


def _base_unit(unit: str) -> str:
    return BASE_UNIT[canon.dimension(unit)]


def _harmonized(value: str, unit: str) -> str:
    return format(canon.to_base(value, unit).normalize(), "E")


def _conversion_transform(value: str, unit: str) -> str:
    """`<value> <unit> x <factor> = <base value> <base unit>` — the engine's own wording.

    The magnitude enters as its CANONICAL decimal (`4E+1`, not `40`): a Stage-4 quantity is
    normalised on construction, so `1e-12` and `4e-11` can never share an identity.
    """
    factor = canon._UNITS[unit][1]
    base = Decimal(canon.canonical_decimal(value)) * factor
    return f"{value} {unit} x {factor} = {base} {_base_unit(unit)}"


# ------------------------------------------------------------------ safety_evidence

def check_safety_derived(rows: list[dict], method: dict) -> list[str]:
    bad: list[str] = []
    allowed = set(method["safety_taxonomy"]["evidence_states"]["allowed"])
    for r in rows:
        if r.get("evidence_state") not in allowed:
            bad.append(f"{r.get('evidence_id')}: evidence_state "
                       f"{r.get('evidence_state')!r} is not in the method's vocabulary")
            continue
        if r.get("renders_as_safe") is not RENDERS_AS_SAFE:
            bad.append(
                f"{r.get('evidence_id')}: renders_as_safe={r.get('renders_as_safe')!r}. No "
                "evidence state renders as safe — not even no_evidence_found, which is a "
                "statement about the search, not about the drug.")
        want = EVIDENCE_STATE_DISPLAY[r["evidence_state"]]
        if r.get("evidence_state_display") != want:
            bad.append(
                f"{r.get('evidence_id')}: evidence_state_display was rewritten. This is the "
                f"text a reader sees beside the finding. got={r.get('evidence_state_display')!r}")
    return sorted(bad)


# ---------------------------------------------------------------- potency_evidence

def check_potency_derived(rows: list[dict]) -> list[str]:
    bad: list[str] = []
    for r in rows:
        want = canon.canonical_decimal(r["value_source_string"])
        if r.get("value_canonical_decimal") != want:
            bad.append(f"{r['potency_id']}: value_canonical_decimal="
                       f"{r.get('value_canonical_decimal')!r}, recomputed {want!r}")
    return sorted(bad)


# --------------------------------------------------------------- property_evidence

def _calculator_conformance(policy: dict, property_id: str, row: dict) -> tuple[bool, str, str]:
    """Independent restatement of the calculator policy. -> (allowed, conformance, code)."""
    entry = policy.get("properties", {}).get(property_id)
    if entry is None:
        return False, "", "absent"
    calculator = row["calculator_id"]
    for f in entry.get("forbidden", []):
        if calculator == f["calculator_id"] or calculator.startswith(f["calculator_id"] + "_"):
            return False, "", "disallowed_calculator"
    for a in entry.get("allowed", []):
        if a["calculator_id"] != calculator:
            continue
        for req in a.get("requires", []):
            if not row.get(req):
                return False, "", "disallowed_calculator"
        return True, a["conformance"], ""
    return False, "", "disallowed_calculator"


def check_property_derived(rows: list[dict], method: dict) -> list[str]:
    """Recompute accepted / component / conformance / magnitudes for every property row."""
    policy = method["calculator_policy"]
    specs = {p["property_id"]: p for p in method["cns_mpo"]["properties"]}
    bad: list[str] = []

    by_key: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        by_key.setdefault((r["candidate_id"], r["property_id"]), []).append(r)

    for (_cid, prop), group in by_key.items():
        usable = []
        for r in group:
            ok, conformance, _code = _calculator_conformance(policy, prop, r)
            if ok:
                usable.append((r, conformance))

        # Agreeing rows (same calculator AND same exact base value) are all accepted; rows
        # that disagree are ambiguous and NONE of them is accepted.
        scored = {(r["calculator_id"], str(canon.to_base(r["value_source_string"], r["units"])))
                  for r, _c in usable}
        accept_all = len(scored) == 1

        for r in group:
            rid = r["property_record_id"]
            ok, conformance, code = _calculator_conformance(policy, prop, r)
            want_accepted = bool(ok and accept_all)

            if bool(r.get("accepted")) != want_accepted:
                bad.append(f"{rid}: accepted={r.get('accepted')!r}, recomputed {want_accepted}")
                continue

            # magnitudes are recomputed for EVERY row, accepted or not
            want_dec = canon.canonical_decimal(r["value_source_string"])
            if r.get("value_canonical_decimal") != want_dec:
                bad.append(f"{rid}: value_canonical_decimal={r.get('value_canonical_decimal')!r}, "
                           f"recomputed {want_dec!r}")
            base = canon.to_base(r["value_source_string"], r["units"])
            if r.get("value_in_base_units") is None or \
                    abs(float(r["value_in_base_units"]) - float(base)) > 1e-9:
                bad.append(f"{rid}: value_in_base_units={r.get('value_in_base_units')!r}, "
                           f"recomputed {float(base)}")
            if r.get("base_units") != _base_unit(r["units"]):
                bad.append(f"{rid}: base_units={r.get('base_units')!r}, "
                           f"recomputed {_base_unit(r['units'])!r}")
            want_conv = _conversion_transform(r["value_source_string"], r["units"])
            if r.get("unit_conversion") != want_conv:
                bad.append(f"{rid}: unit_conversion={r.get('unit_conversion')!r}, "
                           f"recomputed {want_conv!r}")

            if want_accepted:
                want_score = canon.desirability(specs[prop], float(base))
                got = r.get("component_score_t0")
                if got is None or abs(float(got) - want_score) > 1e-9:
                    bad.append(f"{rid}: component_score_t0={got!r}, recomputed {want_score}")
                if r.get("method_conformance") != conformance:
                    bad.append(f"{rid}: method_conformance={r.get('method_conformance')!r}, "
                               f"recomputed {conformance!r}")
                if r.get("rejection_reason_code") is not None:
                    bad.append(f"{rid}: an accepted row carries "
                               f"rejection_reason_code={r.get('rejection_reason_code')!r}")
            else:
                if r.get("component_score_t0") is not None:
                    bad.append(f"{rid}: a row that was not accepted carries a component score "
                               f"{r.get('component_score_t0')!r}")
                if r.get("method_conformance") is not None:
                    bad.append(f"{rid}: a row that was not accepted carries a conformance "
                               f"{r.get('method_conformance')!r}")
                want_code = "ambiguous_multiple_sources" if (ok and not accept_all) else code
                if r.get("rejection_reason_code") != want_code:
                    bad.append(f"{rid}: rejection_reason_code="
                               f"{r.get('rejection_reason_code')!r}, recomputed {want_code!r}")
    return sorted(bad)


# --------------------------------------------------------------- exposure_evidence

def _caveats(m: dict, ctx: Optional[dict], link_id: Optional[str],
             potency: Optional[dict]) -> list[str]:
    """The gate caveats, in the order the engine appends them: CSF, enhancing, then link."""
    out: list[str] = []
    if m.get("matrix") == "csf":
        out.append("CSF")
    if m.get("enhancement_context") == "enhancing":
        out.append("ENHANCING")
    if link_id:
        out.append("LINK")
    return out


def _caveat_kinds(caveats: list[str]) -> list[str]:
    """Classify the emitted prose caveats into the kinds the gates can produce.

    The caveat TEXT is the engine's prose; what is checkable independently is that the set of
    caveats present is exactly the set the gates entail — no missing warning, and no invented
    one. A dropped "CSF is not non-enhancing brain" caveat is a scientific claim changing.
    """
    kinds = []
    for c in caveats or []:
        low = str(c).lower()
        if "csf" in low:
            kinds.append("CSF")
        elif "enhancing tissue" in low or "contrast-enhancing" in low:
            kinds.append("ENHANCING")
        elif "relevance link" in low:
            kinds.append("LINK")
        else:
            kinds.append(f"UNKNOWN:{c[:40]}")
    return kinds


def check_exposure_derived(tables: dict[str, list[dict]]) -> list[str]:
    ctxs = {c["context_id"]: c for c in tables.get("contexts", [])}
    pots = {p["potency_id"]: p for p in tables.get("potency_evidence", [])}
    links = tables.get("potency_context_links", [])
    bad: list[str] = []

    for m in tables.get("exposure_evidence", []):
        mid = m["measurement_id"]

        # magnitudes
        for src, dst in (("concentration_source_string", "concentration_canonical_decimal"),
                         ("quantitation_limit_source_string",
                          "quantitation_limit_canonical_decimal")):
            want = canon.canonical_decimal(m[src]) if m.get(src) else None
            if m.get(dst) != want:
                bad.append(f"{mid}: {dst}={m.get(dst)!r}, recomputed {want!r}")

        usable = [p for p in pots.values()
                  if p["candidate_id"] == m["candidate_id"] and p["metric"] in MARGIN_METRICS]
        potency = usable[0] if len(usable) == 1 else None
        ctx = ctxs.get(m["context_id"])
        rebuilt = rebuild_margin(m, potency, ctx, links) if potency else None

        # The potency the margin was taken against is bound whenever ONE admissible MEC
        # exists — including when the comparison then failed, so the reader can see what it
        # was refused against. The relevance link is bound only when a margin was computed.
        want_potency = potency["potency_id"] if potency else None
        want_link = None
        if (rebuilt and rebuilt["status"] == "computed" and potency and ctx
                and potency["biological_context"] != ctx.get("tumor_context")):
            matched = sorted((row["link_id"] for row in links
                              if row["potency_id"] == potency["potency_id"]
                              and row["tumor_context"] == ctx.get("tumor_context")))
            want_link = matched[0] if matched else None

        if m.get("potency_id") != want_potency:
            bad.append(f"{mid}: potency_id={m.get('potency_id')!r}, recomputed {want_potency!r}")
        if m.get("potency_context_link_id") != want_link:
            bad.append(f"{mid}: potency_context_link_id="
                       f"{m.get('potency_context_link_id')!r}, recomputed {want_link!r}")

        # reason code, both ways round
        want_code = rebuilt["reason_code"] if rebuilt else "no_potency_record"
        if len(usable) > 1:
            want_code = "ambiguous_potency_records"
        elif not usable:
            mine = [p for p in pots.values() if p["candidate_id"] == m["candidate_id"]]
            want_code = ("potency_metric_not_a_target_concentration" if mine
                         else "no_potency_record")
        if m.get("margin_reason_code") != want_code:
            bad.append(f"{mid}: margin_reason_code={m.get('margin_reason_code')!r}, "
                       f"recomputed {want_code!r}")

        computed = rebuilt is not None and rebuilt["status"] == "computed"

        # the float beside the exact decimal must be that decimal
        if computed and rebuilt is not None:
            want_float = float(Decimal(rebuilt["margin_canonical_decimal"]))
            got = m.get("margin")
            if got is None or abs(float(got) - want_float) > 1e-9:
                bad.append(f"{mid}: margin={got!r}, recomputed {want_float}")
            want_units = _base_unit(m["concentration_units"])
            if m.get("harmonized_units") != want_units:
                bad.append(f"{mid}: harmonized_units={m.get('harmonized_units')!r}, "
                           f"recomputed {want_units!r}")
            want_exp = _harmonized(m["concentration_source_string"], m["concentration_units"])
            if m.get("exposure_harmonized") != want_exp:
                bad.append(f"{mid}: exposure_harmonized={m.get('exposure_harmonized')!r}, "
                           f"recomputed {want_exp!r}")
            assert potency is not None
            want_pot = _harmonized(potency["value_source_string"], potency["units"])
            if m.get("potency_harmonized") != want_pot:
                bad.append(f"{mid}: potency_harmonized={m.get('potency_harmonized')!r}, "
                           f"recomputed {want_pot!r}")
            assert potency is not None
            want_transform = (
                f"margin = ({_conversion_transform(m['concentration_source_string'], m['concentration_units'])})"
                f" / ({_conversion_transform(potency['value_source_string'], potency['units'])}); "
                f"both {m['binding_state']}; potency metric = {potency['metric']}")
            if m.get("margin_transform") != want_transform:
                bad.append(f"{mid}: margin_transform={m.get('margin_transform')!r}, "
                           f"recomputed {want_transform!r}")
        else:
            for col in ("margin", "harmonized_units", "exposure_harmonized",
                        "potency_harmonized", "margin_transform"):
                if m.get(col) is not None:
                    bad.append(f"{mid}: a margin that was not computed carries "
                               f"{col}={m.get(col)!r}")

        # caveats: exactly the ones the gates entail — none dropped, none invented
        want_caveats = _caveats(m, ctx, m.get("potency_context_link_id"), potency)
        got_caveats = _caveat_kinds(list(m.get("caveats") or []))
        if sorted(want_caveats) != sorted(got_caveats):
            bad.append(f"{mid}: caveats={got_caveats}, recomputed {want_caveats}")

    return sorted(bad)
