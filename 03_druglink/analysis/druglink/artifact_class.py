"""Two artifact classes, and a strict fixture firewall. Nothing else.

The retired build carried a three-way ``production`` / ``research_only`` / ``fixture``
namespace and a lattice of promotion flags — ``production_candidate``,
``production_promotion_eligible``, ``may_write_production_pointer``,
``production_pointer_written``, ``research_pk_annotation_eligible`` — plus a
0-of-33 Stage-1 gate assumption baked into the code. All of it is **retired**.

Stage 3 does not decide what is "production". It computes a drug annotation from
whatever Stage 2 produced, and reports **scientific workflow states**
(see :mod:`druglink.workflow`). There are exactly two artifact classes:

  analysis   a real computation over real inputs. ONE generic class — there is no
             production/research distinction, because Stage 3 never made that call.
  fixture    synthetic test data. It can never be relabelled as an analysis, can never
             reach Stage 4, and lands in its own output subtree.

The fixture firewall is the only firewall left, and it is strict: an artifact class is
read from the artifact's own ``artifact_class`` field and must agree with the requested
handler, with the acquisition statuses, and with the bundle-id prefix.

RETIRED_KEYS is enforced structurally: a document carrying any retired promotion or
eligibility field is refused, at any depth. That is not a lint — it is the thing that
stops the old vocabulary creeping back in through a downstream writer.
"""
from __future__ import annotations

from typing import Any

ANALYSIS = "analysis"
FIXTURE = "fixture"
ARTIFACT_CLASSES = (ANALYSIS, FIXTURE)

OUTPUT_SCHEMA = {
    ANALYSIS: "spot.stage03_drug_annotation.v1",
    FIXTURE: "spot.fixture.stage03_drug_annotation.v1",
}
OUTPUT_DOC = {
    ANALYSIS: "drug_annotation.json",
    FIXTURE: "fixture_drug_annotation.json",
}
# A fixture never shares an output root with an analysis.
OUTPUT_SUBDIR = {ANALYSIS: "", FIXTURE: "fixtures_only"}
BUNDLE_ID_PREFIX = {ANALYSIS: "s3_", FIXTURE: "fx_"}

# Acquisition statuses each class may consume. A fixture may not consume public bytes;
# an analysis may not consume fixture bytes.
ALLOWED_ACQUISITION = {
    ANALYSIS: ("acquired_public",),
    FIXTURE: ("synthetic_fixture",),
}
REQUIRED_ADAPTER_STATUS = {
    ANALYSIS: ("research_ready", "production_ready"),
    FIXTURE: ("fixture_shaped", "research_ready"),
}

# Only an analysis may be queued for a Stage-4 assessment. A Stage-4 assessment is an
# assessment — it is NOT biological promotion and NOT a recommendation.
STAGE4_QUEUE_PERMITTED = {ANALYSIS: True, FIXTURE: False}

# The retired promotion/eligibility vocabulary. Refused structurally, at any depth.
RETIRED_KEYS = frozenset({
    "production_candidate", "production_promotion_eligible",
    "may_write_production_pointer", "production_pointer_written",
    "research_pk_annotation_eligible", "research_pk_annotation_reason",
    "research_annotation_eligible", "research_direction_evaluable",
    "production_eligible", "stage3_eligible", "stage4_eligible",
    "annotation_only", "production_pointer", "promoted_to_production",
    "current_pointer", "namespace",
})
# Files a promotion pointer would live in. None may ever appear in a bundle.
RETIRED_POINTER_FILES = ("production_pointer.json", "current.json")


class ArtifactClassError(ValueError):
    """An artifact crossed the fixture firewall, or carried a retired field."""


def require(artifact_class: str) -> str:
    if artifact_class not in ARTIFACT_CLASSES:
        raise ArtifactClassError(
            f"unknown artifact_class {artifact_class!r}; expected one of "
            f"{list(ARTIFACT_CLASSES)}. The production/research namespaces are retired.")
    return artifact_class


def bundle_id(artifact_class: str, content_sha256: str) -> str:
    return f"{BUNDLE_ID_PREFIX[require(artifact_class)]}{content_sha256[:16]}"


def check_bundle_id(artifact_class: str, value: str) -> None:
    prefix = BUNDLE_ID_PREFIX[require(artifact_class)]
    if not str(value).startswith(prefix):
        raise ArtifactClassError(
            f"{artifact_class}: bundle id {value!r} must start with {prefix!r}")
    if artifact_class == ANALYSIS and str(value).startswith("fx_"):
        raise ArtifactClassError(
            f"an analysis refuses a fixture identifier: {value!r}")


def check_document(artifact_class: str, doc: dict[str, Any]) -> None:
    require(artifact_class)
    declared = doc.get("artifact_class")
    if declared != artifact_class:
        raise ArtifactClassError(
            f"{artifact_class} handler refuses a document declaring "
            f"artifact_class={declared!r}")
    if doc.get("schema_version") != OUTPUT_SCHEMA[artifact_class]:
        raise ArtifactClassError(
            f"{artifact_class} handler refuses schema_version="
            f"{doc.get('schema_version')!r}")


def retired_keys_in(obj: Any, path: str = "$") -> list[str]:
    """Every retired promotion/eligibility key, at any depth."""
    hits: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in RETIRED_KEYS:
                hits.append(f"{path}.{key}")
            hits += retired_keys_in(value, f"{path}.{key}")
    elif isinstance(obj, (list, tuple)):
        for i, value in enumerate(obj):
            hits += retired_keys_in(value, f"{path}[{i}]")
    return hits


def check_no_retired_keys(doc: dict[str, Any]) -> None:
    """A document may not carry the retired promotion/eligibility vocabulary.

    Structural, not a single boolean: the whole point of a relabel is to add one field.
    """
    hits = retired_keys_in(doc)
    if hits:
        raise ArtifactClassError(
            f"document carries retired promotion/eligibility field(s) at {hits[:5]}. "
            "production_candidate / production_promotion_eligible / "
            "may_write_production_pointer / production_pointer_written / "
            "research_pk_annotation_eligible / namespace are RETIRED. Stage 3 reports "
            "scientific workflow states (see druglink.workflow); it does not decide "
            "promotion.")


def stage4_queue_permitted(artifact_class: str) -> bool:
    return bool(STAGE4_QUEUE_PERMITTED[require(artifact_class)])
