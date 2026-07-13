"""B1 documentation-hygiene guard: the public Stage-1 docs must describe the CURRENT continuous v3
generic selector, never the retired 0-of-33 production gate, the v1/balanced selection contract, or a
stale v2 hash. A retired term is allowed ONLY on a line that explicitly marks it historical/absent.

Scoped to the two docs W13 owns (01_programs/README.md + schemas/README.md); other stages guard their own.
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
DOCS = [os.path.join(REPO, "01_programs", "README.md"),
        os.path.join(REPO, "schemas", "README.md")]

# terms that must NEVER appear as a CURRENT claim in these docs
RETIRED_TERMS = [
    "0 of 33", "0-of-33", "0/33",
    "balanced_a_to_b", "balanced_skew", "balanced objective",
    "stage1-continuous-v2", "contrast_id",
    "production_selectable", "namespace=production",
    "traffic light", "traffic_light",
    "20f91fdd", "1ac9f6b2",              # stale v2/old registry hashes
]
# a retired term is admissible only when the SAME line marks it historical/absent
QUALIFIERS = ("historical", "retired", "gone", "no longer", "not current", "never",
              "no 0-of-33", "no combined", "no composite", "no production", "no traffic",
              "demo default", "labelled demo", "only as", "**no**")


def test_stage1_docs_have_no_retired_current_claims():
    offenders = []
    for doc in DOCS:
        with open(doc, encoding="utf-8") as fh:
            for i, line in enumerate(fh, 1):
                low = line.lower()
                for term in RETIRED_TERMS:
                    if term.lower() in low and not any(q.lower() in low for q in QUALIFIERS):
                        offenders.append(f"{os.path.relpath(doc, REPO)}:{i}: unqualified retired term {term!r}")
    assert not offenders, "retired-as-current claim(s) in Stage-1 docs:\n" + "\n".join(offenders)


def test_stage1_docs_assert_current_v3_selector():
    """Positive control: each doc must actually name the current v3 selection contract."""
    for doc in DOCS:
        text = open(doc, encoding="utf-8").read()
        assert "spot.stage01_selection.v3" in text or "v3 selection contract" in text, \
            f"{os.path.relpath(doc, REPO)} does not describe the current v3 selection contract"
