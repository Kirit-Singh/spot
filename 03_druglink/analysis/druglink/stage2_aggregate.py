"""Disk-backed admission of the Stage-2 aggregate release. THE production gate.

This module retires one line — ``arm_query``'s source-code Boolean, which was Stage-3's
production gate and was never a gate at all (audit B2). A constant in a Python file means
a REAL Stage-2 aggregate, independently admitted on disk, is still refused because nobody
edited the file — and that flipping it to ``True`` would admit ANYTHING, since it names no
manifest, no report, no verifier and no bytes. It is a developer's memory of a report they
once read. It is not the report.

Admission moves onto the bytes. :func:`admit_aggregate` opens the aggregate manifest, a
SEPARATE independent verification report, and every bundle the manifest inventories, and
refuses unless the whole chain closes:

    report(ADMIT, independent) --binds--> manifest (raw AND canonical)
    manifest --self-hash--> itself
    manifest --raw bytes--> each of the 15 bundles on disk
    manifest --pins--> the Stage-1 release it was computed against

THE MANIFEST MUST PROVE ITS OWN IDENTITY (B6, again). ``manifest_sha256`` is recomputed
here from the manifest's own semantic content (excluding that field and the non-semantic
timestamps). A manifest that cannot recompute its own identity is not a root of trust — it
is a document asserting a number.

The hashes answer different questions: the **self-hash** asks "is this manifest internally
what it says it is?"; the **raw/canonical** pair asks "is this the manifest the verifier
actually read?" — raw catches a re-serialisation, canonical catches a re-format, and the
report must bind BOTH or it is an opinion about some other artifact.

Bundles are verified by their RAW bytes. Their declared canonical hashes are required (an
unaddressable bundle is not admissible) and carried, but never recomputed: Stage 2 owns
that rule, its arm values are floats on the wire, and Stage-3's ``canonical_json`` refuses
floats — so recomputing under a rule the pin was not computed under would fail for the
WRONG reason, and a wrong-reason failure teaches the next reader to add an exception.

TOPOLOGY IS DERIVED, NEVER DECLARED. The release is EXACTLY 15 physical bundles — 3 Direct
(one per condition), 6 temporal (one per ORDERED pair; Rest→Stim48hr is not Stim48hr→Rest),
6 pathway (condition x gene-set source) — carrying 300 logical arm slots (10 programs x 2
desired changes x 15 contexts). Every number is derived from the conditions and sources,
never read from a declared count: a producer that can declare its own completeness can
declare a PARTIAL release complete, and a missing bundle then looks exactly like one that
was computed and found empty.

It assigns **no pair roles** (``away_from_A``/``toward_B``) — a role is what a *selection*
gives an arm at join time, and baking one in fuses two questions — and emits **no combined
score**. It loads reusable arms, and nothing else.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Optional

from . import artifact_class as ac
from .hashing import CanonicalizationError, content_hash, file_sha256, without

# The topology. Everything below is DERIVED from these — never from a declared count.
CONDITIONS = ("Rest", "Stim8hr", "Stim48hr")
PATHWAY_SOURCES = ("Reactome", "GO-BP")
DESIRED_CHANGES = ("increase", "decrease")
N_PROGRAMS = 10

LANE_DIRECT = "direct"
LANE_TEMPORAL = "temporal"
LANE_PATHWAY = "pathway"
LANES = (LANE_DIRECT, LANE_TEMPORAL, LANE_PATHWAY)
MEASURED_LANES = frozenset({LANE_DIRECT, LANE_TEMPORAL})
CONTEXT_FIELDS = ("condition", "from_condition", "to_condition", "pathway_source")

# The manifest's identity, and what is NOT part of it (a timestamp is not semantic content:
# two writes of the same release differ only in when they happened).
SELF_HASH_FIELD = "manifest_sha256"
NON_SEMANTIC_FIELDS = ("generated_at", "created_at", "started_at", "finished_at",
                       "completed_at", "elapsed_seconds")
ADMIT = "admit"

# Named gates. Every refusal names one, so it can be grepped, tested and cited — never
# inferred from a message someone later rewords.
GATE_ARTIFACT_NOT_ON_DISK: str = "aggregate_artifact_is_not_on_disk"
GATE_MANIFEST_UNREADABLE: str = "aggregate_manifest_is_not_canonicalisable"
GATE_MANIFEST_SELF_HASH: str = "manifest_does_not_recompute_its_own_identity"
GATE_SELF_ADMISSION: str = "the_report_and_the_manifest_are_the_same_artifact"
GATE_VERIFIER_NOT_INDEPENDENT: str = "verification_report_is_not_independent"
GATE_VERDICT_NOT_ADMIT: str = "verification_report_does_not_say_admit"
GATE_REPORT_BINDS_NOTHING: str = "verification_report_binds_no_manifest_bytes"
GATE_REPORT_BINDS_ANOTHER_MANIFEST: str = "verification_report_admits_a_different_manifest"
GATE_STAGE1_RELEASE_UNBOUND: str = "stage1_release_on_disk_is_not_the_pinned_release"
GATE_PATH_TRAVERSAL: str = "bundle_path_escapes_the_bundles_root"
GATE_UNKNOWN_LANE: str = "inventory_names_a_lane_or_context_the_release_does_not_have"
GATE_DUPLICATE_BUNDLE: str = "inventory_carries_a_duplicate_bundle_key"
GATE_MISSING_BUNDLE: str = "inventory_is_missing_a_bundle_the_release_must_have"
GATE_INCOMPLETE_TOPOLOGY: str = "the_release_does_not_resolve_its_full_arm_topology"
GATE_BUNDLE_BYTES_MOVED: str = "bundle_on_disk_is_not_the_bundle_the_manifest_inventoried"
GATE_ARM_IDENTITY_UNRESOLVED: str = "an_arm_record_resolves_to_no_target_identity"
GATE_FIXTURE_FIREWALL: str = "a_fixture_aggregate_cannot_enter_the_analysis_path"


class Stage2AggregateError(ValueError):
    """The Stage-2 aggregate on disk is not admissible."""


class AggregateAdmissionRefused(Stage2AggregateError):
    """The admission chain (report → manifest → bytes) does not close."""


class AggregateTopologyRefused(Stage2AggregateError):
    """The release is not the complete 15-bundle / 300-arm topology."""


def _refuse(gate: str, message: str, *, topology: bool = False) -> None:
    """Fail closed, by name. Never a silent pass, never a fixture fallback."""
    exc = AggregateTopologyRefused if topology else AggregateAdmissionRefused
    raise exc(f"[{gate}] {message}")


# --- What a loaded arm retains. No role, no pole, no score. ------------------ #
@dataclass(frozen=True)
class AdmittedBundle:
    bundle_key: str
    lane: str
    path: str                              # relative to bundles_root; never absolute
    raw_sha256: str                        # verified against the bytes on disk
    canonical_sha256: str                  # declared by Stage 2, carried, not recomputed
    condition: Optional[str] = None
    from_condition: Optional[str] = None
    to_condition: Optional[str] = None
    pathway_source: Optional[str] = None


@dataclass(frozen=True)
class LoadedArm:
    arm_key: str
    lane: str
    program_id: str
    desired_change: str
    # Context (condition | ORDERED from/to | condition x source) lives on the bundle it
    # came from: one source of truth, never copied out of it.
    bundle: AdmittedBundle
    ranking: dict[str, Any]                # {path, raw_sha256, canonical_sha256}
    provenance: dict[str, Any]             # every hash this arm stands on
    records: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class AdmittedAggregate:
    artifact_class: str
    manifest_raw_sha256: str
    manifest_canonical_sha256: str
    manifest_self_hash: str
    verifier_id: str
    verdict: str
    stage1_release_sha256: str
    bundles: tuple[AdmittedBundle, ...]
    arms: tuple[LoadedArm, ...]
    program_ids: tuple[str, ...]
    counts: dict[str, Any] = field(default_factory=dict)


# --- 1. Identity. The manifest proves who it is, or it is no root of trust. --- #
def _load_json(path: str, what: str) -> tuple[dict[str, Any], str]:
    """Return (parsed, raw_sha256). Raw is the sha256 of the BYTES ON DISK."""
    if not os.path.isfile(path):
        _refuse(GATE_ARTIFACT_NOT_ON_DISK,
                f"the {what} is not on disk at {path!r}. There is no fixture fallback: a run "
                "without its admitted Stage-2 aggregate does not quietly become one with a "
                "synthetic aggregate.")
    with open(path, "r", encoding="utf-8") as fh:
        doc = json.load(fh)
    return doc, file_sha256(path)


def _canonical(doc: dict[str, Any]) -> str:
    try:
        return content_hash(doc)
    except CanonicalizationError as exc:
        _refuse(GATE_MANIFEST_UNREADABLE, f"the manifest is not canonicalisable: {exc}")
        raise  # pragma: no cover - _refuse always raises


def manifest_self_hash(manifest: dict[str, Any]) -> str:
    """The manifest's identity, over its own semantic content (no self-hash, no clocks)."""
    return _canonical(without(manifest, (SELF_HASH_FIELD, *NON_SEMANTIC_FIELDS)))


def _check_manifest_identity(manifest: dict[str, Any]) -> str:
    """It recomputes its own identity, or nothing it says about anything else stands."""
    declared = manifest.get(SELF_HASH_FIELD)
    recomputed = manifest_self_hash(manifest)
    if declared != recomputed:
        _refuse(GATE_MANIFEST_SELF_HASH,
                f"the manifest declares {SELF_HASH_FIELD}={str(declared)[:16]}… but its own "
                f"content hashes to {recomputed[:16]}…. A manifest that cannot prove its own "
                "identity is not a root of trust; it is a document asserting a number.")
    return recomputed


def _check_report(report: dict[str, Any], *, manifest_raw: str,
                  manifest_canonical: str) -> tuple[str, str]:
    """The SEPARATE independent report. It must ADMIT, and it must admit THESE bytes."""
    verifier_id = str(report.get("verifier_id") or "")
    if "independent" not in verifier_id:
        _refuse(GATE_VERIFIER_NOT_INDEPENDENT,
                f"verifier {verifier_id!r} is not INDEPENDENT: a producer agreeing with "
                "itself is the one thing an independent verifier exists to rule out.")
    verdict = report.get("verdict")
    if verdict != ADMIT:
        _refuse(GATE_VERDICT_NOT_ADMIT,
                f"the independent verifier's verdict is {verdict!r}, not {ADMIT!r}")

    admits = report.get("admits") or {}
    raw = admits.get("manifest_raw_sha256")
    canonical = admits.get("manifest_canonical_sha256")
    if not raw or not canonical:
        _refuse(GATE_REPORT_BINDS_NOTHING,
                "the report must BIND the manifest it admits, by raw AND canonical hash: an "
                "ADMIT that names no bytes is an opinion about some other artifact.")
    if raw != manifest_raw or canonical != manifest_canonical:
        _refuse(GATE_REPORT_BINDS_ANOTHER_MANIFEST,
                f"the report admits raw={str(raw)[:16]}… canon={str(canonical)[:16]}…, but "
                f"the manifest on disk is raw={manifest_raw[:16]}… "
                f"canon={manifest_canonical[:16]}…. Both must match: raw alone misses a "
                "re-serialisation, canonical alone lets the file differ from what was "
                "judged.")
    return verifier_id, str(verdict)


def _check_stage1_release(manifest: dict[str, Any], stage1_release_path: str) -> str:
    """The release the aggregate was computed against, bound to the bytes it names."""
    pinned = (manifest.get("stage1_release") or {}).get("raw_sha256")
    if not pinned:
        _refuse(GATE_STAGE1_RELEASE_UNBOUND,
                "the manifest pins no stage1_release.raw_sha256: an aggregate that cannot "
                "name the release it stands on cannot be replayed against it.")
    if not os.path.isfile(stage1_release_path):
        _refuse(GATE_ARTIFACT_NOT_ON_DISK,
                f"the pinned Stage-1 release is not on disk at {stage1_release_path!r}")
    on_disk = file_sha256(stage1_release_path)
    if on_disk != pinned:
        _refuse(GATE_STAGE1_RELEASE_UNBOUND,
                f"the Stage-1 release on disk hashes to {on_disk[:16]}… but the manifest "
                f"pins {str(pinned)[:16]}…: a DIFFERENT release than the aggregate used.")
    return on_disk


# --- 2. Topology. 15 bundles and 300 arm slots, both derived. ---------------- #
def ordered_condition_pairs() -> tuple[tuple[str, str], ...]:
    """Every ORDERED pair. Rest→Stim48hr is not Stim48hr→Rest: the DiD changes sign."""
    return tuple((a, b) for a in CONDITIONS for b in CONDITIONS if a != b)


def expected_bundle_keys() -> dict[str, str]:
    """The 15 keys the release must have -> their lane. Derived, never declared."""
    keys = {f"{LANE_DIRECT}|{c}": LANE_DIRECT for c in CONDITIONS}
    keys.update({f"{LANE_TEMPORAL}|{a}|{b}": LANE_TEMPORAL
                 for a, b in ordered_condition_pairs()})
    keys.update({f"{LANE_PATHWAY}|{c}|{s}": LANE_PATHWAY
                 for c in CONDITIONS for s in PATHWAY_SOURCES})
    return keys


N_BUNDLES = len(expected_bundle_keys())                          # 15
N_ARM_SLOTS = N_BUNDLES * N_PROGRAMS * len(DESIRED_CHANGES)      # 300


def _entry_key(entry: dict[str, Any]) -> str:
    """The key IMPLIED by the entry's own context: disagreement is a mislabelled bundle."""
    lane = entry.get("lane")
    ctx = {LANE_DIRECT: (entry.get("condition"),),
           LANE_TEMPORAL: (entry.get("from_condition"), entry.get("to_condition")),
           LANE_PATHWAY: (entry.get("condition"), entry.get("pathway_source"))}.get(lane)
    return "|".join([str(lane), *(str(c) for c in ctx)]) if ctx else ""


def _safe_bundle_path(rel_path: Any, bundles_root: str) -> str:
    """Resolve INSIDE bundles_root or refuse. Absolute paths and `..` never resolve."""
    if not isinstance(rel_path, str) or not rel_path:
        _refuse(GATE_PATH_TRAVERSAL, "a bundle inventory entry names no path")
    if os.path.isabs(rel_path):
        _refuse(GATE_PATH_TRAVERSAL,
                f"bundle path {rel_path!r} is ABSOLUTE: it reads a file admission never "
                "bound, from outside the explicit root.")
    if ".." in rel_path.replace("\\", "/").split("/"):
        _refuse(GATE_PATH_TRAVERSAL,
                f"bundle path {rel_path!r} traverses upwards ('..'), out of the admitted "
                "root.")
    root = os.path.realpath(bundles_root)
    full = os.path.realpath(os.path.join(root, rel_path))
    if full != root and os.path.commonpath([root, full]) != root:
        _refuse(GATE_PATH_TRAVERSAL,
                f"bundle path {rel_path!r} resolves OUTSIDE the bundles root: {full!r} not "
                f"under {root!r} (a symlink counts — realpath is what gets opened).")
    return full


def _check_inventory(manifest: dict[str, Any],
                     bundles_root: str) -> list[tuple[AdmittedBundle, str]]:
    """The 15 bundles: known, distinct, complete, and inside the root."""
    inventory = manifest.get("inventory")
    if not isinstance(inventory, list) or not inventory:
        _refuse(GATE_INCOMPLETE_TOPOLOGY,
                f"the manifest ships no bundle inventory; the release is exactly "
                f"{N_BUNDLES} bundles, and a partial release is never admissible.",
                topology=True)

    expected = expected_bundle_keys()
    seen: dict[str, AdmittedBundle] = {}
    out: list[tuple[AdmittedBundle, str]] = []
    for entry in inventory:
        key, lane = entry.get("bundle_key"), entry.get("lane")
        if lane not in LANES or key not in expected or expected[key] != lane:
            _refuse(GATE_UNKNOWN_LANE,
                    f"entry {key!r} (lane={lane!r}) is not one of the {N_BUNDLES} bundles "
                    f"derived from {list(CONDITIONS)} x {list(PATHWAY_SOURCES)}; it belongs "
                    "to another release.")
        if key != _entry_key(entry):
            _refuse(GATE_UNKNOWN_LANE,
                    f"entry declares bundle_key {key!r} but its own context implies "
                    f"{_entry_key(entry)!r}: a mislabelled bundle fills the wrong slot.")
        if key in seen:
            _refuse(GATE_DUPLICATE_BUNDLE,
                    f"bundle_key {key!r} appears twice: a duplicate silently fills a missing "
                    "slot, and the count still looks right.")
        if not (entry.get("raw_sha256") and entry.get("canonical_sha256")):
            _refuse(GATE_BUNDLE_BYTES_MOVED,
                    f"bundle {key!r} is not content-addressed; one nobody can address is "
                    "one nobody admitted.")

        full = _safe_bundle_path(entry.get("path"), bundles_root)
        seen[key] = AdmittedBundle(
            bundle_key=key, lane=lane, path=str(entry["path"]),
            raw_sha256=entry["raw_sha256"], canonical_sha256=entry["canonical_sha256"],
            **{f: entry.get(f) for f in CONTEXT_FIELDS})
        out.append((seen[key], full))

    missing = sorted(set(expected) - set(seen))
    if missing:
        _refuse(GATE_MISSING_BUNDLE,
                f"the inventory is missing {len(missing)} bundle(s): {missing}. The release "
                f"is exactly {N_BUNDLES} (3 Direct, 6 ordered temporal pairs, 6 pathway "
                "condition x source); a missing bundle is indistinguishable from one "
                "computed and found empty.", topology=True)
    return out            # distinct + complete + all known => exactly N_BUNDLES


# --- 3. The arms. Reusable, role-free, nulls retained. ----------------------- #
def _records(doc: dict[str, Any], arm: dict[str, Any], *,
             lane: str, arm_key: str) -> tuple[dict[str, Any], ...]:
    """Resolve every record's identity through base_records. Never on a symbol."""
    bases = {b["base_key"]: b for b in doc.get("base_records", [])}
    rows: list[dict[str, Any]] = []
    for rec in arm.get("records") or ():
        base = bases.get(rec.get("base_key"))
        if lane in MEASURED_LANES and base is None:
            _refuse(GATE_ARM_IDENTITY_UNRESOLVED,
                    f"arm {arm_key!r} points at base_key {rec.get('base_key')!r}, which "
                    "resolves to nothing: an unresolvable record is a drug target nobody "
                    "can name.")
        base = base or {}
        if base and base.get("target_id") != rec.get("target_id"):
            _refuse(GATE_ARM_IDENTITY_UNRESOLVED,
                    f"arm {arm_key!r}: base_key {rec.get('base_key')!r} resolves to "
                    f"{base.get('target_id')!r} but the record says {rec.get('target_id')!r}"
                    " — the join is checked, never trusted.")
        estimate: Any = ({"from": base.get("from_released_estimate_id"),
                          "to": base.get("to_released_estimate_id")}
                         if lane == LANE_TEMPORAL else base.get("released_estimate_id"))
        rows.append({
            "target_id": rec.get("target_id"),
            "target_id_namespace": (base.get("target_id_namespace")
                                    or rec.get("target_id_namespace")),
            "target_symbol": base.get("target_symbol"),
            "target_ensembl": base.get("target_ensembl"),
            "set_id": rec.get("set_id"),                  # pathway lane only
            "released_estimate_id": estimate,
            "arm_value": rec.get("arm_value"),
            "rank": rec.get("rank"),   # null is a STATE (unranked): never 0, never last
            "evaluable": bool(rec.get("evaluable")),
            "desired_target_modulation": rec.get("desired_target_modulation")})
    return tuple(rows)


def _load_bundle_arms(bundle: AdmittedBundle, full_path: str, *,
                      provenance: dict[str, Any]) -> list[LoadedArm]:
    """One inventoried bundle -> its reusable arms, after re-hashing the bytes on disk."""
    doc, raw = _load_json(full_path, f"Stage-2 bundle {bundle.bundle_key!r}")
    if raw != bundle.raw_sha256:
        _refuse(GATE_BUNDLE_BYTES_MOVED,
                f"bundle {bundle.bundle_key!r} on disk hashes to {raw[:16]}… but the manifest "
                f"inventoried {bundle.raw_sha256[:16]}…: the bytes changed after the "
                "independent verifier read them.")

    arms: list[LoadedArm] = []
    for arm in doc.get("arms") or ():
        arm_key = str(arm.get("arm_key") or "")
        ranking = arm.get("ranking") or {}
        if not arm_key or not arm.get("program_id") \
                or arm.get("desired_change") not in DESIRED_CHANGES:
            _refuse(GATE_INCOMPLETE_TOPOLOGY,
                    f"bundle {bundle.bundle_key!r} carries an arm with no key, no program or "
                    f"an unknown desired_change: {arm.get('arm_key')!r} / "
                    f"{arm.get('desired_change')!r}", topology=True)
        if not (ranking.get("raw_sha256") and ranking.get("canonical_sha256")):
            _refuse(GATE_INCOMPLETE_TOPOLOGY,
                    f"arm {arm_key!r} binds no content-addressed ranking, so it cannot be "
                    "replayed.", topology=True)
        arms.append(LoadedArm(
            arm_key=arm_key, lane=bundle.lane, program_id=str(arm["program_id"]),
            desired_change=str(arm["desired_change"]), bundle=bundle,
            ranking=dict(ranking),
            provenance=dict(provenance, bundle_key=bundle.bundle_key,
                            bundle_raw_sha256=bundle.raw_sha256,
                            bundle_canonical_sha256=bundle.canonical_sha256),
            records=_records(doc, arm, lane=bundle.lane, arm_key=arm_key)))
    return arms


def _check_arm_topology(arms: list[LoadedArm],
                        bundles: list[AdmittedBundle]) -> tuple[str, ...]:
    """300 slots: every bundle x every program x both desired changes. Derived."""
    programs = sorted({a.program_id for a in arms})
    if len(programs) != N_PROGRAMS:
        _refuse(GATE_INCOMPLETE_TOPOLOGY,
                f"the release resolves {len(programs)} programs; the aggregate is "
                f"{N_PROGRAMS} x {len(DESIRED_CHANGES)} desired changes across {N_BUNDLES} "
                "contexts. Programs are DERIVED from the loaded arms, never copied from a "
                "declared count.", topology=True)
    slots = {(a.bundle.bundle_key, a.program_id, a.desired_change) for a in arms}
    if len(slots) != len(arms):
        _refuse(GATE_INCOMPLETE_TOPOLOGY,
                "two arms occupy the same (bundle, program, desired_change) slot; a "
                "duplicate arm silently fills a missing one.", topology=True)

    expected = {(b.bundle_key, p, d)
                for b in bundles for p in programs for d in DESIRED_CHANGES}
    missing = sorted(expected - slots)
    if missing:
        _refuse(GATE_INCOMPLETE_TOPOLOGY,
                f"the release resolves {len(slots)} of {len(expected)} arm slots; "
                f"{len(missing)} are missing, e.g. {missing[:3]}. The aggregate is "
                f"{N_ARM_SLOTS} arms (60 Direct + 120 temporal + 120 pathway); a partial "
                "release is never admissible.", topology=True)
    return tuple(programs)   # 15 bundles x 10 programs x 2 changes => exactly N_ARM_SLOTS


# --- The gate. -------------------------------------------------------------- #
def admit_aggregate(*, manifest_path: str, report_path: str, bundles_root: str,
                    stage1_release_path: str) -> AdmittedAggregate:
    """Admit the Stage-2 aggregate FROM DISK, or refuse by name.

    The production gate. It replaces a source-code Boolean, which admitted nothing and
    refused everything because it named no manifest, no report, no verifier and no bytes.
    """
    if os.path.realpath(manifest_path) == os.path.realpath(report_path):
        _refuse(GATE_SELF_ADMISSION,
                "the report and the manifest are the SAME file. A producer does not admit "
                "itself: the report is a separate artifact from a separate verifier.")

    manifest, manifest_raw = _load_json(manifest_path, "Stage-2 aggregate manifest")
    report, _ = _load_json(report_path, "independent aggregate verification report")
    manifest_canonical = _canonical(manifest)
    self_hash = _check_manifest_identity(manifest)
    verifier_id, verdict = _check_report(
        report, manifest_raw=manifest_raw, manifest_canonical=manifest_canonical)
    stage1_sha = _check_stage1_release(manifest, stage1_release_path)
    klass = ac.require(str(manifest.get("artifact_class") or ""))

    provenance = {"manifest_raw_sha256": manifest_raw,
                  "manifest_canonical_sha256": manifest_canonical,
                  "manifest_self_hash": self_hash, "independent_verifier_id": verifier_id,
                  "independent_verdict": verdict, "stage1_release_sha256": stage1_sha}

    inventory = _check_inventory(manifest, bundles_root)
    arms: list[LoadedArm] = []
    for bundle, full in inventory:
        arms.extend(_load_bundle_arms(bundle, full, provenance=provenance))
    bundles = [b for b, _ in inventory]
    programs = _check_arm_topology(arms, bundles)

    return AdmittedAggregate(
        artifact_class=klass, manifest_raw_sha256=manifest_raw,
        manifest_canonical_sha256=manifest_canonical, manifest_self_hash=self_hash,
        verifier_id=verifier_id, verdict=verdict, stage1_release_sha256=stage1_sha,
        bundles=tuple(bundles), arms=tuple(arms), program_ids=programs,
        counts={"n_bundles": len(bundles), "n_arm_slots": len(arms),
                "n_programs": len(programs),
                "bundles_per_lane": {ln: sum(b.lane == ln for b in bundles) for ln in LANES},
                "arms_per_lane": {ln: sum(a.lane == ln for a in arms) for ln in LANES},
                "topology_is_derived_not_declared": True,
                "combined_objective_permitted": False, "pair_roles_assigned": False})


def require_analysis(admitted: AdmittedAggregate) -> AdmittedAggregate:
    """The fixture firewall. A sealed test aggregate never becomes a real analysis."""
    if admitted.artifact_class != ac.ANALYSIS:
        _refuse(GATE_FIXTURE_FIREWALL,
                f"the aggregate declares artifact_class={admitted.artifact_class!r}; only an "
                "'analysis' aggregate may enter the analysis path — a synthetic number on "
                "its way to Stage 4 is a fabricated candidate.")
    return admitted
