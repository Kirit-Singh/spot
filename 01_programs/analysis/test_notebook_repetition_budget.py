"""Static repetition-budget test for the rendered Stage-1 notebook.

The scope boundary should be stated once, not repeated as a caveat banner throughout.
This test reads the rendered HTML only (no science imports, no pipeline execution) and
asserts each scope concept appears exactly once, while the methods / reproduction
anchors remain present so the budget cannot be satisfied by gutting the notebook.
"""
import re
from pathlib import Path

NOTEBOOK = Path(__file__).resolve().parent.parent / "app" / "01_notebook.html"

# Each concept must appear exactly once: not zero (a real boundary is required) and
# not repeated (state it once).
SCOPE_CONCEPTS_ONCE = [
    "exploratory decision-support",
    "does not demonstrate lineage stability",
    "confirmed Treg identity",
]

# Must remain present — methods, provenance and reproduction are never dropped.
REQUIRED_ANCHORS = [
    "stage1_pipeline.py",
    "STAGE1_REMEDIATION_METHOD.md",
    "verify_reproduce.py",
    "canonical_table_sha256",
    "barcode_set_sha256",
    "./reproduce.sh",
    "CZI Virtual Cell",
    "Hugging Face",
]


def _normalized_text() -> str:
    raw = NOTEBOOK.read_text(encoding="utf-8")
    return re.sub(r"\s+", " ", raw)


def test_notebook_exists():
    assert NOTEBOOK.is_file(), f"notebook not found: {NOTEBOOK}"


def test_scope_boundary_stated_exactly_once():
    text = _normalized_text()
    for concept in SCOPE_CONCEPTS_ONCE:
        count = text.count(concept)
        assert count == 1, f"scope concept {concept!r} appears {count}x (want exactly 1)"


def test_methods_and_reproduction_anchors_preserved():
    text = _normalized_text()
    for anchor in REQUIRED_ANCHORS:
        assert anchor in text, f"required methods/reproduction anchor missing: {anchor!r}"
