"""Nested SPL sections: the warnings a flat parser silently dropped.

Found by a live acquisition of the real innovator TEMODAR label (DailyMed setid
046a9011-3911-4d3f-a15f-fbb56d5aad56, spl_version 40, 2026-07-13). Measured against the
actual bytes, the flat parser reached:

    43685-7 Warnings and Precautions   0 of 7,199 chars   <- ALL SIX warnings dropped
    34084-4 Adverse Reactions        515 of 21,412 chars  <- 97.6% dropped
    34070-3 Contraindications        474 of   797 chars

The section carries no direct <text>: every warning lives in a <component><section>
subsection coded 42229-5 (SPL UNCLASSIFIED), which is not a safety LOINC code, so a parser
that reads only the coded section's own <text> collects nothing — and says nothing. A drug
with six labeled warnings presented as having none. In a system whose firewall says absence
of evidence is never a favourable result, that is the worst possible failure: it fails
SILENTLY, and silence reads as safety.

These tests run against `dailymed_spl_nested_fixture.xml` — synthetic content, real
structure (public-data-only: the real label's bytes are not bundled).
"""

from __future__ import annotations

from analysis.label_adapters import parse_dailymed_spl
from fixtures import fixture_bytes

NESTED = "dailymed_spl_nested_fixture.xml"
LOINC = "2.16.840.1.113883.6.1"


def _parsed():
    return parse_dailymed_spl(fixture_bytes(NESTED))


def _of(kind: str):
    return [f for f in _parsed().findings if f.finding_type == kind]


# ------------------------------------------------------- the regression: nested warnings

def test_every_nested_warning_subsection_is_collected():
    """THE regression. Six warnings live only in 42229-5 subsections; the flat parser got 0."""
    warnings = _of("warning_precaution")
    titles = {f.labeled_subsection_name for f in warnings}
    for n in ("5.1", "5.2", "5.3", "5.4", "5.5", "5.6"):
        assert any(t and t.startswith(n) for t in titles), f"warning {n} was dropped: {titles}"
    # 5.1-5.5 carry one paragraph each (5); 5.6 carries two, of which one is a verbatim repeat
    # of 5.1 and collapses (+1). The section itself has no direct <text>. So: 6.
    assert len(warnings) == 6


def test_nested_adverse_reaction_subsections_are_collected():
    """6.1 Clinical Trials Experience + 6.2 Postmarketing Experience carry the substance."""
    ars = _of("adverse_reaction")
    codes = {f.labeled_subsection_code for f in ars}
    assert "90374-0" in codes, "clinical-trials-experience subsection dropped"
    assert "90375-7" in codes, "postmarketing-experience subsection dropped"
    # the direct preamble is still collected, attributed to the section itself
    assert None in codes or "34084-4" in codes


def test_the_flat_contraindications_section_is_unchanged():
    """Backward compatibility: a section with direct <text> and no nesting behaves as before."""
    cs = _of("contraindication")
    assert len(cs) == 1
    assert cs[0].labeled_subsection_code is None, "a direct-text finding has no subsection"


# --------------------------------------------------------- coded subsection provenance

def test_a_nested_finding_keeps_BOTH_the_section_and_the_subsection_identity():
    """The safety TYPE comes from the ancestor LOINC section; the provenance names the
    subsection the sentence actually came from. Losing either is losing traceability."""
    w = next(f for f in _of("warning_precaution")
             if (f.labeled_subsection_name or "").startswith("5.2"))
    # attributed to the ancestor safety section — the taxonomy is unchanged
    assert w.labeled_section_code == "43685-7"
    assert w.finding_type == "warning_precaution"
    assert w.code_system == LOINC
    # ...and traceable to the exact labeled subsection it was read from
    assert w.labeled_subsection_code == "42229-5"
    assert w.labeled_subsection_name == "5.2 Fixture Hepatotoxicity"
    assert "hepatotoxicity" in w.finding_text.lower()


# ------------------------------------------------- the <excerpt> highlights double-count

def test_the_excerpt_highlights_restatement_is_never_collected():
    """<excerpt> is the SPL Highlights RESTATEMENT of the same warnings. Collecting it would
    double-count every finding — and it is a summary, not the labeled section."""
    for f in _parsed().findings:
        assert "HIGHLIGHTS RESTATEMENT" not in f.finding_text, (
            "the <excerpt> highlights duplicate was collected as evidence")


# ---------------------------------------------------------- absence-of-evidence semantics

def test_a_genuinely_absent_section_stays_zero_and_is_never_invented():
    """This label has no boxed warning and no drug-interactions section. Recursion must not
    manufacture findings for a section that is not in the bytes."""
    assert _of("boxed_warning") == []
    assert _of("labeled_interaction") == []


# ------------------------------------------------------------------- determinism / dupes

def test_parsing_is_deterministic_and_duplicates_are_collapsed_stably():
    """Same bytes -> same findings, same order, every time. 5.6 repeats 5.1's sentence
    verbatim (real labels cross-repeat); the repeat is collapsed deterministically, not
    emitted twice and not dropped at random."""
    a, b = _parsed().findings, _parsed().findings
    assert a == b

    texts = [f.finding_text for f in a if f.finding_type == "warning_precaution"]
    assert len(texts) == len(set(texts)), f"a duplicated warning was emitted twice: {texts}"

    # the repeated sentence is kept ONCE, at its first occurrence (5.1), not at 5.6
    dupe = "FIXTURE: Severe fixture myelosuppression occurred. Monitor fixture blood counts prior to each cycle."
    keeper = [f for f in a if f.finding_text == dupe]
    assert len(keeper) == 1
    assert keeper[0].labeled_subsection_name.startswith("5.1"), (
        "de-duplication must keep the FIRST occurrence in document order, deterministically")
