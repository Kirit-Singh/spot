"""Pure-python replication of the spot.stage01_selection.v1 contrast_id derivation.

Mirrors the in-browser canonicalization in 01_programs/app/01_page.html
(canonicalJSON + SubtleCrypto SHA-256) and the reference implementation in
02_geneskew/analysis/direct/{contrast,hashing}.py. The single source of truth is
the shared schema in schemas/README.md.

Run: python 01_programs/analysis/test_selection_contract.py   (or under pytest)
"""
import hashlib
import json

# ── frozen constants for this dataset (schemas/README.md · spot.stage01_selection.v1) ──
DATASET_ID = "marson2025_gwcd4_perturbseq"
EFFECT_UNIVERSE_ID = "marson2025_gwcd4_perturbseq : GWCD4i.DE_stats.h5ad"
DONOR_SCOPE = "all"
STAGE1_METHOD_VERSION = "stage1-continuous-v2"
PROGRAM_REGISTRY_SHA256 = (
    "1ac9f6b2c3a738e0f44119add5c4f72f61225372fedb3fa6dd8d5f6ae19e95fa"
)
SOURCE_H5AD_SHA256 = (
    "2edc6d318415c8b0ee779d707ab86e26ddb6f0274db51ab4a12f21ebfda50e43"
)
SOURCE_HF_REVISION = "e5fcf98b56a9302921d402e97fc5a190bd88f9a6"

ANCHOR_CONTRAST_ID = "26b866f2ad813d71"
ANCHOR_FULL_SHA256 = (
    "26b866f2ad813d717022d22d9ac1966f6bb35cbfda0c585d9023a0b6a8e0b42d"
)


def canonical_content(
    a_program_id="treg_like",
    a_score_field="treg_like_score",
    a_direction="high",
    b_program_id="th1_like",
    b_score_field="th1_like_score",
    b_direction="high",
    analysis_condition="Stim48hr",
    objective="balanced_a_to_b",
    dataset_id=DATASET_ID,
    donor_scope=DONOR_SCOPE,
    effect_universe_id=EFFECT_UNIVERSE_ID,
    program_registry_sha256=PROGRAM_REGISTRY_SHA256,
    source_h5ad_sha256=SOURCE_H5AD_SHA256,
    source_hf_revision=SOURCE_HF_REVISION,
    stage1_method_version=STAGE1_METHOD_VERSION,
):
    """The scientific content ONLY — no timestamps / display labels / UI ordering."""
    return {
        "A": {
            "program_id": a_program_id,
            "score_field": a_score_field,
            "direction": a_direction,
        },
        "B": {
            "program_id": b_program_id,
            "score_field": b_score_field,
            "direction": b_direction,
        },
        "analysis_condition": analysis_condition,
        "dataset_id": dataset_id,
        "donor_scope": donor_scope,
        "effect_universe_id": effect_universe_id,
        "objective": objective,
        "program_registry_sha256": program_registry_sha256,
        "source_h5ad_sha256": source_h5ad_sha256,
        "source_hf_revision": source_hf_revision,
        "stage1_method_version": stage1_method_version,
    }


def canonical_json(obj):
    """Sorted keys + compact separators — the JS canonicalJSON is byte-identical."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def full_sha256(content):
    return hashlib.sha256(canonical_json(content).encode("utf-8")).hexdigest()


def contrast_id(content):
    return full_sha256(content)[:16]


# ── tests ──────────────────────────────────────────────────────────────────────
def test_default_reproduces_anchor():
    cc = canonical_content()
    assert full_sha256(cc) == ANCHOR_FULL_SHA256
    assert contrast_id(cc) == ANCHOR_CONTRAST_ID


def test_scientific_fields_change_the_id():
    base = contrast_id(canonical_content())
    changed = {
        "A direction": canonical_content(a_direction="low"),
        "B direction": canonical_content(b_direction="low"),
        "A program": canonical_content(
            a_program_id="th2_like", a_score_field="th2_like_score"
        ),
        "B program": canonical_content(
            b_program_id="tfh_like", b_score_field="tfh_like_score"
        ),
        "analysis_condition": canonical_content(analysis_condition="Rest"),
        "objective": canonical_content(objective="away_from_a"),
        "dataset_id": canonical_content(dataset_id="other_dataset"),
        "registry hash": canonical_content(program_registry_sha256="0" * 64),
        "h5ad hash": canonical_content(source_h5ad_sha256="0" * 64),
        "hf revision": canonical_content(source_hf_revision="deadbeef"),
        "method version": canonical_content(stage1_method_version="stage1-x"),
    }
    for name, cc in changed.items():
        assert contrast_id(cc) != base, f"{name} should change contrast_id"


def test_display_labels_and_timestamps_do_not_change_the_id():
    """Non-canonical fields (created_at, display labels, ordering) never affect the id."""
    cc = canonical_content()
    base = contrast_id(cc)

    # a full emitted artifact carries created_at + display mirrors around the canonical body;
    # the id hashes ONLY canonical_content, so any of those non-canonical fields are invisible.
    artifact = {
        "schema_version": "spot.stage01_selection.v1",
        "created_at": "2026-07-11T07:01:38.619693+00:00",
        "A_display_label": "Treg-like",  # display label — excluded
        "B_display_label": "Th1-like",  # display label — excluded
        "validation_status": "preflight_passed",
        "canonical_content": cc,
    }
    assert artifact["canonical_content"] == cc
    assert contrast_id(artifact["canonical_content"]) == base

    # changing a display label / timestamp does not touch the id
    artifact["created_at"] = "2099-01-01T00:00:00+00:00"
    artifact["A_display_label"] = "Regulatory T"
    assert contrast_id(artifact["canonical_content"]) == base

    # key insertion order of canonical_content is irrelevant (canonical_json sorts keys)
    reordered = {k: cc[k] for k in reversed(list(cc.keys()))}
    assert contrast_id(reordered) == base


if __name__ == "__main__":
    test_default_reproduces_anchor()
    test_scientific_fields_change_the_id()
    test_display_labels_and_timestamps_do_not_change_the_id()
    print("contrast_id (default):", contrast_id(canonical_content()))
    print("all tests passed")
