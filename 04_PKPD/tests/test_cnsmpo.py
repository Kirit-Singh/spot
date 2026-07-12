"""CNS-MPO: published boundaries, published goldens, and refusal to impute.

The expected values in this file are an INDEPENDENT transcription of the published
tables (Wager et al. 2010, ACS Chem Neurosci 1(6):435-449, doi:10.1021/cn100008c,
PMC3368654 — read from the PMC-rendered full text on 2026-07-11). They are written out
here as literals on purpose: a test that reads its expectations from the same method
file it is testing proves nothing.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from analysis.canonical import round_half_up
from analysis.cnsmpo import desirability, hump, monotonic_decreasing, score_cns_mpo
from analysis.evidence_records import PropertyRecord, Provenance
from analysis.method_config import load_method_bundle
from analysis.properties import select_properties

METHOD = load_method_bundle()
CNS_MPO = METHOD.cns_mpo
POLICY = METHOD.calculator_policy

# Wager 2010, Table 1: "The CNS MPO Properties, Functions, Weighting, Value Range and
# Parameter Ranges."  property | transformation (T0) | weight | more desirable (T0=1.0)
# | less desirable (T0=0.0)
PUBLISHED_TABLE_1 = {
    "clogp": ("monotonic_decreasing", 1.0, {"x1": 3.0, "x2": 5.0}),
    "clogd_74": ("monotonic_decreasing", 1.0, {"x1": 2.0, "x2": 4.0}),
    "mw": ("monotonic_decreasing", 1.0, {"x1": 360.0, "x2": 500.0}),
    "tpsa": ("hump", 1.0, {"x1": 20.0, "x2": 40.0, "x3": 90.0, "x4": 120.0}),
    "hbd": ("monotonic_decreasing", 1.0, {"x1": 0.5, "x2": 3.5}),
    "pka_most_basic": ("monotonic_decreasing", 1.0, {"x1": 8.0, "x2": 10.0}),
}

# Wager 2010, Table 2: "CNS MPO Scores and Individual Transformed Scores (T0) for
# Selected Drugs."  These are the AUTHORS' published values. Spot asserts nothing about
# these drugs; they are arithmetic goldens for the scoring engine only.
PUBLISHED_TABLE_2 = [
    # drug,           T0_ClogP T0_ClogD T0_TPSA T0_MW T0_HBD T0_pKa  CNS MPO
    ("alprazolam",      1.00, 0.75, 1.00, 1.00, 1.00, 1.00, 5.8),
    ("zolpidem",        0.99, 0.57, 0.88, 1.00, 1.00, 1.00, 5.4),
    ("paroxetine",      0.38, 1.00, 0.99, 1.00, 0.83, 0.00, 4.2),
    ("risperidone",     1.00, 0.86, 1.00, 0.64, 1.00, 1.00, 5.5),
    ("methylphenidate", 1.00, 1.00, 0.92, 1.00, 0.83, 0.00, 4.8),
]


def test_method_file_matches_published_table_1():
    encoded = {
        p["property_id"]: (p["transform"], p["weight"], p["inflection_points"])
        for p in CNS_MPO["properties"]
    }
    assert encoded == PUBLISHED_TABLE_1
    assert len(encoded) == 6, "exactly six inputs; no seventh property may be added"
    assert (CNS_MPO["total"]["min"], CNS_MPO["total"]["max"]) == (0.0, 6.0)


@pytest.mark.parametrize(
    "prop,value,expected",
    [
        # ClogP: 1.0 at <=3, 0.0 at >=5, linear between.
        ("clogp", 0.0, 1.0), ("clogp", 3.0, 1.0), ("clogp", 4.0, 0.5),
        ("clogp", 5.0, 0.0), ("clogp", 9.9, 0.0),
        # ClogD: 1.0 at <=2, 0.0 at >=4.
        ("clogd_74", -1.0, 1.0), ("clogd_74", 2.0, 1.0), ("clogd_74", 3.0, 0.5),
        ("clogd_74", 4.0, 0.0), ("clogd_74", 6.0, 0.0),
        # MW: 1.0 at <=360, 0.0 at >=500.
        ("mw", 100.0, 1.0), ("mw", 360.0, 1.0), ("mw", 430.0, 0.5),
        ("mw", 500.0, 0.0), ("mw", 145000.0, 0.0),
        # TPSA hump: 0 at <=20, rising to 1 at 40, plateau to 90, falling to 0 at 120.
        ("tpsa", 0.0, 0.0), ("tpsa", 20.0, 0.0), ("tpsa", 30.0, 0.5), ("tpsa", 40.0, 1.0),
        ("tpsa", 65.0, 1.0), ("tpsa", 90.0, 1.0), ("tpsa", 105.0, 0.5),
        ("tpsa", 120.0, 0.0), ("tpsa", 200.0, 0.0),
        # HBD: 1.0 at <=0.5, 0.0 at >=3.5.
        ("hbd", 0.0, 1.0), ("hbd", 0.5, 1.0), ("hbd", 2.0, 0.5),
        ("hbd", 3.5, 0.0), ("hbd", 6.0, 0.0),
        # most-basic pKa: 1.0 at <=8, 0.0 at >=10.
        ("pka_most_basic", 1.0, 1.0), ("pka_most_basic", 8.0, 1.0), ("pka_most_basic", 9.0, 0.5),
        ("pka_most_basic", 10.0, 0.0), ("pka_most_basic", 12.0, 0.0),
    ],
)
def test_published_desirability_boundaries(prop, value, expected):
    assert desirability(prop, value, CNS_MPO) == pytest.approx(expected, abs=1e-12)


def test_transform_shapes_are_monotonic_and_bounded():
    for prop in ("clogp", "clogd_74", "mw", "hbd", "pka_most_basic"):
        ip = next(p for p in CNS_MPO["properties"] if p["property_id"] == prop)["inflection_points"]
        lo, hi = ip["x1"], ip["x2"]
        xs = [lo + (hi - lo) * i / 50 for i in range(-10, 61)]
        ys = [desirability(prop, x, CNS_MPO) for x in xs]
        assert all(0.0 <= y <= 1.0 for y in ys)
        assert all(ys[i] >= ys[i + 1] - 1e-12 for i in range(len(ys) - 1)), f"{prop} not monotonic decreasing"

    ys = [desirability("tpsa", float(x), CNS_MPO) for x in range(0, 200, 2)]
    assert all(0.0 <= y <= 1.0 for y in ys)
    assert max(ys) == 1.0 and ys[0] == 0.0 and ys[-1] == 0.0


def test_transforms_reject_invalid_inflection_points():
    with pytest.raises(ValueError):
        monotonic_decreasing(1.0, 5.0, 3.0)
    with pytest.raises(ValueError):
        hump(1.0, 40.0, 20.0, 90.0, 120.0)


@pytest.mark.parametrize("drug,t_clogp,t_clogd,t_tpsa,t_mw,t_hbd,t_pka,published", PUBLISHED_TABLE_2)
def test_wager_table2_published_golden_totals(drug, t_clogp, t_clogd, t_tpsa, t_mw, t_hbd, t_pka, published):
    """Equal weights, plain summation, 0-6 range, published 1-dp rounding.

    Scope: Table 2 publishes the six TRANSFORMED components and the total, but not the
    raw property values behind them (the SI holding those is paywalled — ACS returned
    403 on 2026-07-11). So this golden validates the aggregation exactly; the raw-value
    -> T0 transforms are validated against the published Table-1 inflection points above.
    """
    components = [t_clogp, t_clogd, t_tpsa, t_mw, t_hbd, t_pka]
    total = sum(components)
    assert 0.0 <= total <= 6.0
    assert round_half_up(total, 1) == pytest.approx(published, abs=1e-9), (
        f"{drug}: published components sum to {total}, published CNS MPO is {published}"
    )


# An UNVERIFIED DERIVED REGRESSION EXAMPLE — not a published golden.
#
# These six values are attributed to Wager et al. 2016 Table 2, but no bytes of that
# article or its table were ever acquired or hashed (ACS returned 403; the DOI is not in
# PMC). They were copied from a prior audit report. Pushing them through the very
# Wager-2010 transforms they would be checking proves only that this implementation is
# self-consistent — that is circular, and it is not primary-source validation.
#
# What the row IS good for: pinning the arithmetic against a future edit. That is why it
# stays. 4.5 is this example's TOTAL on the 0-6 desirability scale — it is NOT a cutoff,
# validated or otherwise.
#   ClogP 3.7 -> 0.65 | ClogD 2.7 -> 0.65 | TPSA 90 -> 1.00
#   MW    375 -> 0.89 | HBD   1   -> 0.83 | pKa  9  -> 0.50   total 4.5
UNVERIFIED_REGRESSION_ROW = {
    "clogp": ("3.7", 0.65), "clogd_74": ("2.7", 0.65), "tpsa": ("90", 1.00),
    "mw": ("375", 0.89), "hbd": ("1", 0.83), "pka_most_basic": ("9", 0.50),
}
UNVERIFIED_REGRESSION_TOTAL = 4.5


def test_unverified_derived_regression_example_still_reproduces():
    """A regression pin on the arithmetic. NOT a published golden, NOT a validated cutoff."""
    records = [
        _prop("C2016", prop, raw, {
            "clogp": "biobyte_clogp", "clogd_74": "acd_labs",
            "mw": "pubchem_molecular_weight", "tpsa": "pubchem_tpsa",
            "hbd": "pubchem_hbond_donor_count", "pka_most_basic": "acd_labs",
        }[prop])
        for prop, (raw, _t0) in UNVERIFIED_REGRESSION_ROW.items()
    ]
    r = score_cns_mpo("C2016", "M1", select_properties(records, POLICY), CNS_MPO)

    assert r.status == "complete"
    for prop, (_raw, expected_t0) in UNVERIFIED_REGRESSION_ROW.items():
        assert round_half_up(r.components[prop], 2) == pytest.approx(expected_t0, abs=1e-9), prop
    assert r.total_published == pytest.approx(UNVERIFIED_REGRESSION_TOTAL, abs=1e-9)


def test_the_2016_row_is_not_claimed_as_a_published_golden():
    """The method file must not sell an unacquired document as primary-source validation."""
    g = CNS_MPO["unverified_derived_regression_example"]
    assert g["status"] == "UNVERIFIED_DERIVED_REGRESSION_EXAMPLE"
    assert g["is_a_published_golden"] is False
    assert g["is_primary_source_validation"] is False
    assert g["is_a_validated_cutoff"] is False
    assert g["counts_toward_source_verified_goldens"] is False
    assert g["attributed_to"]["document_acquired"] is False
    assert "circular" in g["attributed_to"]["why_unverified"]

    # The arithmetic itself is preserved, under an honest name.
    encoded = {k: (v["value"], v["t0"]) for k, v in g["row"].items()
               if k != "expected_total_from_this_implementation"}
    assert encoded == {k: (float(raw), t0)
                       for k, (raw, t0) in UNVERIFIED_REGRESSION_ROW.items()}
    assert g["row"]["expected_total_from_this_implementation"] == UNVERIFIED_REGRESSION_TOTAL
    # The old, overclaiming key is gone for good.
    assert "golden_examples_end_to_end" not in CNS_MPO


def test_the_2016_source_entry_claims_no_validation():
    sources = {s["source_id"]: s for s in METHOD.sources["sources"]}
    s = sources["wager2016_cnsmpo_desirability"]
    assert s["document_acquired"] is False
    assert s["is_evidence"] is False
    assert "raw_sha256" not in s  # a hash of bytes never held would be a fiction


def test_method_file_carries_the_published_goldens_with_their_source():
    golden = CNS_MPO["golden_examples"]
    assert golden["provenance"]["table"].startswith("Table 2.")
    assert golden["provenance"]["source_id"] == "wager2010_cnsmpo_pmc_web"
    encoded = {r["drug"]: r["cns_mpo_published"] for r in golden["rows"]}
    assert encoded == {d: p for d, *_rest, p in PUBLISHED_TABLE_2}


# The unit each property must be expressed in. A magnitude is an exact source string plus
# a declared unit — never a bare float on a universal rounding grid.
UNITS = {
    "clogp": "dimensionless_log10", "clogd_74": "dimensionless_log10",
    "mw": "g_per_mol", "tpsa": "angstrom_squared", "hbd": "count",
    "pka_most_basic": "pka_units",
}


def _prop(cand: str, prop: str, value: str, calc: str, units: str | None = None,
          software_version: str | None = "1", record_id: str | None = None,
          source: str = "src.test", method: str = "test") -> PropertyRecord:
    return PropertyRecord(
        property_record_id=record_id or f"PRP-{cand}-{prop}-{calc}",
        candidate_id=cand, active_moiety_id="M1", property_id=prop,
        value_source_string=value, units=units or UNITS[prop],
        determination="predicted", calculator_id=calc, method=method,
        software_version=software_version,
        provenance=Provenance(source_record_id=source, access_date="2026-07-11",
                              raw_response_sha256="0" * 64, extraction_transform="test"),
    )


def _six(**overrides) -> list[PropertyRecord]:
    base = {
        "clogp": ("biobyte_clogp", "2.5"),
        "clogd_74": ("acd_labs", "1.8"),
        "mw": ("pubchem_molecular_weight", "342.4"),
        "tpsa": ("pubchem_tpsa", "65.0"),
        "hbd": ("pubchem_hbond_donor_count", "1"),
        "pka_most_basic": ("acd_labs", "7.2"),
    }
    base.update(overrides)
    return [_prop("C1", p, v, c) for p, (c, v) in base.items()]


def test_complete_six_inputs_score():
    r = score_cns_mpo("C1", "M1", select_properties(_six(), POLICY), CNS_MPO)
    assert r.status == "complete"
    assert r.components["hbd"] == pytest.approx(2.5 / 3.0)  # (3.5 - 1) / (3.5 - 0.5)
    assert r.total_published == pytest.approx(5.8)
    assert 0.0 <= r.total_raw <= 6.0


def test_one_missing_input_gives_incomplete_and_null_total():
    """No partial totals: five of six is not a score, it is a lower score."""
    records = [p for p in _six() if p.property_id != "pka_most_basic"]
    r = score_cns_mpo("C1", "M1", select_properties(records, POLICY), CNS_MPO)
    assert r.status == "incomplete"
    assert r.total_raw is None and r.total_published is None
    assert [m.property_id for m in r.missing_inputs] == ["pka_most_basic"]
    assert r.missing_inputs[0].reason_code == "absent"
    assert r.components["pka_most_basic"] is None


@pytest.mark.parametrize("prop", ["clogd_74", "pka_most_basic"])
def test_rdkit_cannot_supply_clogd_or_pka(prop):
    """RDKit implements neither: such a value would be fabricated, not merely worse."""
    r = score_cns_mpo("C1", "M1", select_properties(_six(**{prop: ("rdkit", "2.2")}), POLICY), CNS_MPO)
    assert r.status == "incomplete"
    missing = {m.property_id: m for m in r.missing_inputs}
    assert missing[prop].reason_code == "disallowed_calculator"
    assert "does not implement" in missing[prop].detail


def test_rdkit_may_supply_properties_it_genuinely_implements():
    r = score_cns_mpo(
        "C1", "M1",
        select_properties(_six(tpsa=("rdkit_tpsa_ertl", "65.0"), mw=("rdkit_descriptors_molwt", "342.4"),
                               hbd=("rdkit_lipinski_numhdonors", "1")), POLICY),
        CNS_MPO,
    )
    assert r.status == "complete"
    conformance = {p["property_id"]: p["method_conformance"] for p in r.input_provenance}
    assert conformance["tpsa"] == "published_method_equivalent"
    assert conformance["clogp"] == "published_method"


def test_documented_deviation_is_surfaced_not_hidden():
    r = score_cns_mpo("C1", "M1", select_properties(_six(clogp=("rdkit_crippen_mollogp", "2.5")), POLICY), CNS_MPO)
    assert r.status == "complete"
    assert any("documented deviation" in w for w in r.warnings)
    conformance = {p["property_id"]: p["method_conformance"] for p in r.input_provenance}
    assert conformance["clogp"] == "documented_deviation"


def test_conflicting_property_records_are_not_silently_resolved():
    records = _six() + [_prop("C1", "clogd_74", "3.9", "chemaxon_logd")]
    r = score_cns_mpo("C1", "M1", select_properties(records, POLICY), CNS_MPO)
    assert r.status == "incomplete"
    assert r.missing_inputs[0].reason_code == "ambiguous_multiple_sources"


def test_non_finite_value_is_never_scored():
    """A non-finite magnitude cannot even become a record."""
    with pytest.raises(ValidationError, match="non-finite"):
        _prop("C1", "mw", "nan", "pubchem_molecular_weight")


def test_units_are_enforced_not_reinterpreted():
    """MW 0.6 kg/mol is 600 g/mol, not 0.6. The audit found it scoring a perfect 1.0."""
    r = score_cns_mpo(
        "C1", "M1",
        select_properties(_six(mw=("pubchem_molecular_weight", "0.6")) [:0]
                          + [_prop("C1", "mw", "0.6", "pubchem_molecular_weight", units="kg_per_mol")]
                          + [p for p in _six() if p.property_id != "mw"], POLICY),
        CNS_MPO,
    )
    assert r.status == "complete"
    # 0.6 kg/mol -> 600 g/mol -> above the 500 inflection -> component 0.0, not 1.0.
    assert r.components["mw"] == 0.0
    assert r.property_values["mw"] == pytest.approx(600.0)


def test_a_dimensionally_wrong_unit_is_rejected_not_reinterpreted():
    """nM is a concentration; MW is a molar mass. Stage 4 refuses rather than reinterpret."""
    with pytest.raises(ValidationError, match="molar_mass.*expected|expected"):
        _prop("C1", "mw", "342.4", "pubchem_molecular_weight", units="nM")


def test_an_unknown_unit_is_rejected():
    with pytest.raises(ValidationError, match="unsupported unit"):
        _prop("C1", "mw", "342.4", "pubchem_molecular_weight", units="squiggles")


def test_a_negative_molecular_weight_is_a_bad_record_not_a_low_score():
    with pytest.raises(ValidationError, match="MW must be positive"):
        _prop("C1", "mw", "-10", "pubchem_molecular_weight")


def test_hbd_must_be_a_nonnegative_integer():
    with pytest.raises(ValidationError, match="integer"):
        _prop("C1", "hbd", "1.5", "pubchem_hbond_donor_count")


def test_calculator_policy_requires_are_enforced():
    """The audit accepted a BioByte ClogP whose required software_version was null."""
    records = [p for p in _six() if p.property_id != "clogp"]
    records.append(_prop("C1", "clogp", "2.5", "biobyte_clogp", software_version=None))
    r = score_cns_mpo("C1", "M1", select_properties(records, POLICY), CNS_MPO)
    assert r.status == "incomplete"
    missing = {m.property_id: m for m in r.missing_inputs}
    assert missing["clogp"].reason_code == "disallowed_calculator"
    assert "requires" in missing["clogp"].detail


def test_score_is_never_promoted_to_permeability_or_probability():
    """The guard is METHOD DATA (method/stage4_prose_v1.json), hashed into the
    scorecard_set_id — not a literal in the scorer, where it was bound by nothing. This is the
    sentence that stops a design-space score being read as brain exposure, so it is exactly the
    sentence a resealed release would want to rewrite."""
    guard = METHOD.prose["cns_mpo"]["interpretation_guard"].lower()
    assert "not measured brain permeability" in guard
    assert "not a probability" in guard
    assert "not an nebpi class" in guard
