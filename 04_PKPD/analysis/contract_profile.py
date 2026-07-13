"""The v2 profile: what "acquisition-complete" actually requires, checked row by row.

A schema that DECLARES a field and never requires it has not added a rule — it has added a
place to put a null. The audit's complaint about Stage 4 was precisely that it could parse
cached bytes and validate a preassembled bundle but could not show how any of it was obtained;
a v2 bundle that validated against the models while leaving every acquisition field empty would
reproduce that complaint one schema version later.

So this is the gate, and it is separate from the models on purpose. The MODELS keep the v2
fields optional, which is what lets a v1 document stay valid and keeps its digest frozen. The
PROFILE is what says "if you are claiming v2, you must actually carry the contract". Those are
two different questions and collapsing them would force one of the two answers to be wrong.

v1 passes trivially and is marked NOT acquisition-complete. That is not a failure — v1 is a
legitimate contract, it is simply not a claim that anything was acquired.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contract_version import ContractVersion
from .organ_system import UNSPECIFIED
from .safety_records import EvidenceState
from .firewall import Rejection

# The identity fields a curated activity record must carry before a potency built on it can be
# independently reconstructed. An organism alone is not a binding: without the activity and the
# document, a reader cannot pull the same row and see the same number.
REQUIRED_ASSAY_FIELDS = ("activity_id", "assay_id", "document_id", "target_organism")


@dataclass(frozen=True)
class ProfileViolation:
    """A typed refusal. `code` is stable and testable; `detail` is for the human."""

    code: str
    row_id: str
    detail: str
    contract: ContractVersion = ContractVersion.V2


def assert_contract_satisfied(inputs: Any) -> None:
    """The GATE. A bundle that declares a contract must actually carry it.

    Called by the pipeline before anything is computed, so a v2 bundle cannot reach a release
    while missing the very fields that make it acquisition-complete. Refusing here rather than
    at emit time means the run stops before it can produce a document that reads like a result.
    """
    violations = contract_violations(inputs)
    if not violations:
        return
    raise Rejection(
        "evidence_contract_violation",
        f"the bundle declares the {inputs.contract_version.value} evidence contract but does "
        f"not satisfy it ({len(violations)} violation(s)). A declared contract that is not "
        "carried is an assertion, not evidence.",
        {"violations": [{"code": v.code, "row_id": v.row_id, "detail": v.detail}
                        for v in violations[:10]],
         "n_violations": len(violations)},
    )


def is_acquisition_complete(inputs: Any) -> bool:
    """A v1 bundle is never acquisition-complete, however well-formed it is."""
    return (inputs.contract_version == ContractVersion.V2
            and not contract_violations(inputs))


def contract_violations(inputs: Any) -> list[ProfileViolation]:
    version = getattr(inputs, "contract_version", ContractVersion.V1)
    if version == ContractVersion.V1:
        return _v1_violations(inputs)
    return _v2_violations(inputs)


def _v1_violations(inputs: Any) -> list[ProfileViolation]:
    """v1 has one rule: it is v1.

    Carrying an acquisition manifest or an fu lane while declaring v1 is trying to have it both
    ways — the v1 digest, which does not cover those rows, together with the v2 claim, which
    rests on them. The rows would be consumed and hashed by nothing.
    """
    out: list[ProfileViolation] = []
    for lane in ("acquisitions", "fraction_unbound"):
        rows = getattr(inputs, lane, []) or []
        if rows:
            out.append(ProfileViolation(
                "v1_bundle_carries_v2_rows", lane,
                f"the bundle declares the v1 contract but carries {len(rows)} {lane!r} row(s). "
                "The v1 digest does not cover them, so they would be consumed and bound by "
                "nothing. Declare the v2 contract, or drop the rows.",
                ContractVersion.V1))
    return out


def _v2_violations(inputs: Any) -> list[ProfileViolation]:
    out: list[ProfileViolation] = []
    out += _acquisition_violations(inputs)
    out += _potency_violations(inputs)
    out += _fraction_unbound_violations(inputs)
    out += _exposure_violations(inputs)
    out += _safety_violations(inputs)
    return out


# The controlled organ-system vocabulary. It applies ONLY when acquisition says the source's
# value was a controlled term (`value_kind='controlled_value'`); a `source_term` is the source's
# own words and is carried verbatim, because normalising it here would BE the classifier that
# `organ_system.py` refuses to be.
CONTROLLED_ORGAN_SYSTEMS = frozenset({
    "immune_infectious", "hematologic", "cardiovascular", "hepatic", "renal", "neurologic",
    "pulmonary", "gastrointestinal", "endocrine_metabolic", "reproductive", "dermatologic",
    "ocular", "musculoskeletal", "other", "unspecified",
})


def _safety_violations(inputs: Any) -> list[ProfileViolation]:
    out: list[ProfileViolation] = []
    for r in inputs.safety_records:
        e = r.organ_system_evidence
        if e is None:
            continue
        if (e.value_kind == "controlled_value"
                and e.organ_system not in CONTROLLED_ORGAN_SYSTEMS):
            out.append(ProfileViolation(
                "organ_system_outside_controlled_vocabulary", r.evidence_id,
                f"organ_system={e.organ_system!r} is declared a controlled value but is not in "
                "the vocabulary. A controlled term that nothing controls is free text."))
        if e.organ_system != UNSPECIFIED and not (e.source_record_id and e.locator):
            out.append(ProfileViolation(
                "organ_system_without_source_binding", r.evidence_id,
                "an organ system other than 'unspecified' must name the record it was read from "
                "and the exact place in it, or it is an inference"))
        # W8's refusal, preserved as a contract rule: a label finding must pin the exact label
        # VERSION it came from. Labels are revised; a finding from "the label" is a finding from
        # a document that no longer exists.
        if r.evidence_state == EvidenceState.LABEL_SUPPORTED and r.label_identity is not None:
            li = r.label_identity
            if not li.label_version:
                out.append(ProfileViolation(
                    "label_finding_without_version", r.evidence_id,
                    "a label-supported finding must carry the label VERSION it was read from. "
                    "Labels are revised; a finding attributed to 'the label' cites a document "
                    "that may no longer say it."))
            if not (li.setid or li.application_number):
                out.append(ProfileViolation(
                    "label_finding_without_identity", r.evidence_id,
                    "a label-supported finding must carry the exact set ID or application "
                    "number it was read from"))
    return out


def _acquisition_violations(inputs: Any) -> list[ProfileViolation]:
    """Every source whose BYTES are consumed must say how those bytes were obtained.

    The record is W8's `AcquisitionRecord` (`analysis/acquisition.py`), consumed as-is. It keys
    on `source_key` -- W8's join to the source registry -- and its `origin` says whether Stage 4
    fetched the bytes, carried them verbatim from Stage 3, or made them up (a labelled fixture,
    which can never become a public record).
    """
    out: list[ProfileViolation] = []
    acquired = {a.source_key for a in inputs.acquisitions}

    for sid, rec in sorted(inputs.sources.items()):
        if not rec.raw_sha256:
            continue  # a source with no bytes has nothing to have acquired
        if sid not in acquired:
            out.append(ProfileViolation(
                "source_not_acquired", sid,
                f"source {sid!r} supplies bytes to the evidence but has no acquisition record. "
                "Under v2 a byte with no canonical query, access time, terms URL and adapter "
                "build is a byte nobody can get again."))

    seen: set[str] = set()
    seen_source: set[str] = set()
    for a in inputs.acquisitions:
        if a.acquisition_record_id in seen:
            out.append(ProfileViolation(
                "duplicate_acquisition_id", a.acquisition_record_id,
                "a row id is supplied once, so nothing downstream can pick"))
        seen.add(a.acquisition_record_id)

        if a.source_key in seen_source:
            out.append(ProfileViolation(
                "duplicate_acquisition_for_source", a.acquisition_record_id,
                f"source {a.source_key!r} is acquired twice. One source record is one response; "
                "two acquisitions would let a reader choose which bytes the evidence rests on."))
        seen_source.add(a.source_key)

        if a.source_key not in inputs.sources:
            out.append(ProfileViolation(
                "acquisition_of_unknown_source", a.acquisition_record_id,
                f"acquisition names source {a.source_key!r}, which is not registered"))

        # Bytes that are CONSUMED must match the bytes the acquisition says it got.
        rec = inputs.sources.get(a.source_key)
        if rec is not None and a.raw_sha256 and rec.raw_sha256 != a.raw_sha256:
            out.append(ProfileViolation(
                "acquisition_hash_mismatch", a.acquisition_record_id,
                f"the acquisition of {a.source_key!r} hashes to {a.raw_sha256[:12]}... but the "
                f"source registry pins {(rec.raw_sha256 or '')[:12]}.... These are not the same "
                "bytes, and the evidence rests on one of them."))

        # A negative search is a claim about a search that was actually run.
        if a.evidence_state == "not_found_after_reproducible_search":
            manifested = {s.search_id for s in inputs.search_manifests}
            if not manifested:
                out.append(ProfileViolation(
                    "negative_search_manifest_missing", a.acquisition_record_id,
                    "acquisition claims not_found_after_reproducible_search but the bundle "
                    "carries no search manifest. 'We looked and found nothing' is a claim about "
                    "a search; without the search it is 'nobody looked'."))
    return out


def _potency_violations(inputs: Any) -> list[ProfileViolation]:
    out: list[ProfileViolation] = []
    for p in inputs.potencies:
        b = p.assay_binding
        if b is None:
            out.append(ProfileViolation(
                "potency_without_assay_binding", p.potency_id,
                "under v2 a potency must name the activity, assay, target and document it was "
                "measured in. Free text is a citation; these ids are evidence."))
            continue
        missing = [f for f in REQUIRED_ASSAY_FIELDS if not getattr(b, f, None)]
        if missing:
            out.append(ProfileViolation(
                "potency_assay_binding_incomplete", p.potency_id,
                f"assay binding is missing {sorted(missing)}. Without them an independent "
                "reader cannot pull the same record and see the same number."))
    return out


def _fraction_unbound_violations(inputs: Any) -> list[ProfileViolation]:
    """Uniqueness, ownership, provenance. An fu is the multiplier on an unbound concentration:
    a wrong one misstates every number derived from it, and silently."""
    out: list[ProfileViolation] = []
    seen: set[str] = set()
    by_moiety_matrix: dict[tuple[str, str, str], str] = {}

    for f in inputs.fraction_unbound:
        if f.fraction_unbound_id in seen:
            out.append(ProfileViolation(
                "duplicate_fraction_unbound_id", f.fraction_unbound_id,
                "two fu rows share one id, so a reader downstream gets to choose which unbound "
                "concentration the evidence rests on"))
        seen.add(f.fraction_unbound_id)

        # One moiety, in one matrix, in one species, has one fraction unbound.
        key = (f.active_moiety_id, f.matrix, f.species)
        if key in by_moiety_matrix:
            out.append(ProfileViolation(
                "ambiguous_fraction_unbound_for_moiety_matrix", f.fraction_unbound_id,
                f"{f.active_moiety_id!r} already has an fu for matrix {f.matrix!r} in "
                f"{f.species!r} ({by_moiety_matrix[key]!r}). Two would make the unbound "
                "concentration depend on row order."))
        by_moiety_matrix[key] = f.fraction_unbound_id

        rec = inputs.sources.get(f.provenance.source_record_id)
        if rec is None or rec.raw_sha256 != f.provenance.raw_response_sha256:
            out.append(ProfileViolation(
                "fraction_unbound_source_unbound", f.fraction_unbound_id,
                f"fu cites source {f.provenance.source_record_id!r}, which is unknown or whose "
                "bytes do not hash to what the row declares"))
    return out


def _exposure_violations(inputs: Any) -> list[ProfileViolation]:
    out: list[ProfileViolation] = []
    fu_by_id = {f.fraction_unbound_id: f for f in inputs.fraction_unbound}
    by_id = {m.measurement_id: m for m in inputs.exposures}

    for m in inputs.exposures:
        if m.pk_detail is None:
            out.append(ProfileViolation(
                "exposure_without_pk_detail", m.measurement_id,
                "under v2 an exposure must say WHICH number it is (Cmax? Ctrough?), over how "
                "many subjects, with what spread. A bare concentration carries none of it."))
        if m.sampling is None:
            out.append(ProfileViolation(
                "exposure_without_sampling_detail", m.measurement_id,
                "under v2 an exposure must say how, where and when it was sampled — and, for "
                "tissue, whether residual blood was corrected for."))

        out += _unbound_violations(m, fu_by_id)
        out += _ratio_violations(m, by_id, fu_by_id)
        out += _pairing_violations(m, by_id)
    return out


def _unbound_violations(m: Any, fu_by_id: dict) -> list[ProfileViolation]:
    d = m.unbound_derivation
    if d is None:
        return []
    fu = fu_by_id.get(d.fraction_unbound_id)
    if fu is None:
        return [ProfileViolation(
            "unbound_derivation_unbound_fu", m.measurement_id,
            f"the derivation names fu {d.fraction_unbound_id!r}, which is not in the bundle. A "
            "free concentration derived from an fu nobody can inspect is an assertion.")]
    if fu.active_moiety_id != m.active_moiety_id:
        return [ProfileViolation(
            "fraction_unbound_moiety_mismatch", m.measurement_id,
            f"the free concentration was derived using fu {fu.fraction_unbound_id!r}, which was "
            f"measured for moiety {fu.active_moiety_id!r} — not {m.active_moiety_id!r}. A salt, "
            "a prodrug or another molecule has another fraction unbound, and using it misstates "
            "every number derived from it.")]
    return []


def _ratio_violations(m: Any, by_id: dict, fu_by_id: dict) -> list[ProfileViolation]:
    out: list[ProfileViolation] = []
    for r in (m.kp, m.kp_uu_brain):
        if r is None or r.basis != "derived":
            continue
        for mid in r.input_measurement_ids:
            if mid not in by_id:
                out.append(ProfileViolation(
                    "ratio_input_measurement_unbound", m.measurement_id,
                    f"a derived {r.ratio_kind} names input measurement {mid!r}, which is not in "
                    "the bundle. A ratio derived from rows nobody can see cannot be re-checked."))
        for fid in r.fraction_unbound_ids:
            if fid not in fu_by_id:
                out.append(ProfileViolation(
                    "ratio_input_fu_unbound", m.measurement_id,
                    f"a derived {r.ratio_kind} names fu {fid!r}, which is not in the bundle"))
    return out


def _pairing_violations(m: Any, by_id: dict) -> list[ProfileViolation]:
    pid = m.paired_plasma_measurement_id
    if pid is None:
        return []
    paired = by_id.get(pid)
    if paired is None:
        return [ProfileViolation(
            "paired_plasma_unbound", m.measurement_id,
            f"paired_plasma_measurement_id {pid!r} names no measurement in the bundle")]
    if paired.matrix != "plasma":
        return [ProfileViolation(
            "paired_plasma_is_not_plasma", m.measurement_id,
            f"paired_plasma_measurement_id {pid!r} is a {paired.matrix!r} measurement. A brain "
            "concentration paired with another brain concentration is not a brain:plasma "
            "pairing, and any ratio taken from it is not a Kp.")]
    return []
