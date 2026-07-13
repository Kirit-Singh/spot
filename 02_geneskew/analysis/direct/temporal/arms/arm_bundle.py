"""ONE physical temporal bundle per FROZEN ORDERED condition pair. Pure assembly.

WHAT A BUNDLE IS
----------------
All-program and PAIR-AGNOSTIC. For one ordered ``(from_condition -> to_condition)`` it
carries EVERY admitted program's arms:

    n_programs x 2 desired changes = the bundle's logical arms
    (the frozen release: 10 base-portable programs x 2 = 20 arms per bundle,
     over 6 ordered condition pairs = 120 logical temporal arms)

It binds no A/B selection, no pole, no role and no program pair. A pair-specific question
is a JOIN over two of these arms, performed later and by somebody else.

THE BASE IS STORED ONCE, AND THE ARMS REFERENCE IT
--------------------------------------------------
The two arms of a program are EXACT SIGN TRANSFORMS of ONE base delta, so the bundle
stores that base ONCE per ``(program, target)`` — with the whole provenance chain hanging
off it: the exact contributor mask, the upstream on-target QC, the guide/donor
denominators, the marker/control decomposition and the evaluability reasons. Each of the
20 arms then carries only what is genuinely ITS OWN: its key, its sign-transformed value
and its independently-assigned rank, pointing at the base record it came from.

This is structural, not stylistic. Had each arm carried its own copy of the magnitude and
its own copy of the QC, the two arms of one program would be two chances to disagree about
an estimate they share — and a reader could not tell which copy had been checked. They now
CANNOT disagree: there is one number, and one of them is its negation.

WHAT IS DELIBERATELY ABSENT
---------------------------
No role. No pole. No pair id, no A/B id. No combined, balanced or weighted score. No
Pareto tier, no concordance class. No p, q or FDR — this estimator has no calibrated null
and says so. And no batch field: the batch confound is a property of the ORDERED CONDITION
PAIR and of the frozen policy, not of a reusable arm, and the bundle ships the raw base
delta from which it (and the reliability badge) remain exactly re-derivable. The legacy
per-comparison artifact continues to carry both, byte-identically.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from ... import code_digest
from ...arm_keys import DESIRED_CHANGES
from ...hashing import canonical_json, content_hash, sha256_hex
from .. import config, estimand
from . import arm_estimand as est
from . import arm_preflight, arm_programs, arm_report

SCHEMA_BUNDLE = "spot.stage02_temporal_arm_bundle.v1"
BUNDLE_KIND = "temporal"
# The aggregate run-manifest reads ``bundle["lane"]`` and refuses anything not in its LANES.
# The temporal lane's name is exactly this token — matched, never adapted.
BUNDLE_LANE = "temporal"
# Stage-3 (W16) keys its cross-time loader on this exact mode string.
ANALYSIS_MODE = "temporal_cross_condition"
BUNDLE_ID_LEN = 16

# THE PHYSICAL CONTRACT FILENAMES. Emitted NATIVELY under these names — never renamed or
# copied post-hoc — because the aggregate run-manifest and W11's verifier read the shipped
# bytes at exactly these paths, and W16's loader keys on them.
BUNDLE_FILENAME = "arm_bundle.json"
PROVENANCE_FILENAME = "temporal_provenance.json"
PREFLIGHT_FILENAME = "temporal_preflight.json"
VERIFICATION_FILENAME = "temporal_verification.json"

# EACH arm binds the BYTES its rank/counts are derived from — a bundle-relative ranking
# file with a raw AND a canonical hash, so an independent verifier can open it and recompute
# the ranking rather than trust the arm's own summary. This is the aggregate's ARM_BINDING.
RANKING_SCHEMA = "spot.stage02_temporal_arm_ranking.v1"
RANKINGS_DIR = "rankings"


def ranking_relpath(program_id: str, change: str) -> str:
    """The BUNDLE-RELATIVE path of one arm's ranking file. Never absolute, never escapes."""
    return f"{RANKINGS_DIR}/{program_id}__{change}.json"


def ranking_object(arm: dict[str, Any]) -> dict[str, Any]:
    """The ranking an arm actually assigned — the bytes its rank and counts stand on.

    Deliberately reconstructible from the arm alone, so the producer, the emitter and every
    verifier build the SAME bytes: there is exactly one ranking, and its hash is bound into
    the arm rather than restated.
    """
    return {"schema_version": RANKING_SCHEMA, "arm_key": arm["arm_key"],
            "ranked": arm["records"]}


def ranking_binding(arm: dict[str, Any]) -> dict[str, Any]:
    """``{path, raw_sha256, canonical_sha256}`` for one arm's ranking file.

    The bytes are canonical, so ``raw`` (the sha of what lands on disk) and ``canonical``
    (the sha of the parsed content) coincide by construction — both are emitted because the
    aggregate binds and re-checks each independently.
    """
    obj = ranking_object(arm)
    return {"path": ranking_relpath(arm["program_id"], arm["desired_change"]),
            "raw_sha256": sha256_hex(canonical_json(obj)),
            "canonical_sha256": content_hash(obj)}

# The per-endpoint denominators a reader needs in order to know what the support
# denominators WERE. Enumerated, never projected.
DENOMINATORS = ("n_guide_slots_released", "n_guides_mapped", "n_guides_evaluated",
                "n_splits_total", "n_splits_evaluable", "donor_split_denominator",
                "effective_donor_n", "n_cells_target")

# The upstream QC provenance, carried through verbatim. ``qc_ontarget_significant`` is the
# UPSTREAM gate's own field and it is preserved under its own name. The paper-QC adjusted
# p-value is NOT imported: it is a calibrated inference claim this lane does not make, and
# the key firewall would refuse it on sight.
QC_FIELDS = ("qc_ontarget_significant", "qc_ontarget_effect_size", "qc_target_baseMean",
             "qc_low_target_expression")

# The exact contributor mask that produced the projection. Without it a delta is a number
# whose inputs nobody can reconstruct.
MASK_FIELDS = ("mask_resolved", "estimate_mask_sha256", "mask_gene_count",
               "mask_unresolved_reason")

# The marker/control decomposition: the two means the delta is the difference of, and how
# many genes survived the mask on each side.
DECOMPOSITION = ("panel_mean", "control_mean", "n_panel_surviving", "n_control_surviving")


class BundleError(ValueError):
    """The bundle cannot be built as asked. Refuse; never emit a plausible one."""


@dataclass(frozen=True)
class TargetEndpoint:
    """ONE target at ONE condition — the complete program-axis / scorer-view input.

    ``program_delta`` maps EVERY admitted program id to that program's masked projection
    for this target, exactly as ``projection.program_delta`` returns it (delta, panel_mean,
    control_mean, n_panel_surviving, n_control_surviving, status). A program missing from
    this map is a refusal, not a null: the caller claimed a complete program axis.
    """
    target_id: str
    program_delta: dict[str, dict]
    target_symbol: Optional[str] = None
    target_ensembl: Optional[str] = None
    target_id_namespace: Optional[str] = None
    released_estimate_id: Optional[str] = None
    base_qc_passed: bool = True
    base_qc_state: str = "base_qc_passed"
    base_qc_reasons: str = ""
    qc_ontarget_significant: Optional[bool] = None
    qc_ontarget_effect_size: Optional[float] = None
    qc_target_baseMean: Optional[float] = None
    qc_low_target_expression: Optional[bool] = None
    mask_resolved: bool = True
    estimate_mask_sha256: Optional[str] = None
    mask_gene_count: Optional[int] = None
    mask_unresolved_reason: Optional[str] = None
    n_guide_slots_released: Optional[int] = None
    n_guides_mapped: Optional[int] = None
    n_guides_evaluated: Optional[int] = None
    n_splits_total: Optional[int] = None
    n_splits_evaluable: Optional[int] = None
    donor_split_denominator: Optional[int] = None
    effective_donor_n: Optional[int] = None
    n_cells_target: Optional[int] = None
    extra: dict[str, Any] = field(default_factory=dict)


def base_key(program_id: str, target_id: str) -> str:
    """The id of the ONE base delta both arms of a program are a sign transform of."""
    return f"{program_id}|{target_id}"


def _endpoints_by_target(endpoints: list[TargetEndpoint], condition: str
                         ) -> dict[str, TargetEndpoint]:
    by_target: dict[str, TargetEndpoint] = {}
    for ep in endpoints:
        tid = str(ep.target_id)
        if tid in by_target:
            raise BundleError(
                f"target {tid!r} appears twice at condition {condition!r}; a duplicated "
                "endpoint would silently decide which estimate the arm differenced")
        by_target[tid] = ep
    if not by_target:
        raise BundleError(
            f"condition {condition!r} ships no target endpoints. A bundle cannot difference "
            "a condition that is not there, and inventing an empty one would make every "
            "arm come back 'absent' as though that had been measured")
    return by_target


def _endpoint_side(ep: Optional[TargetEndpoint], program_id: str,
                   end: str) -> dict[str, Any]:
    """One endpoint's contribution to a base record, prefixed ``from_`` / ``to_``.

    ``ep is None`` -> the release ships no estimate for this target at this condition.
    Every field is null and ``{end}_present`` says so. A zero here would be a measurement
    the release never made.
    """
    if ep is None:
        out: dict[str, Any] = {f"{end}_present": False, f"{end}_delta": None,
                               f"{end}_projection_status": None,
                               f"{end}_evaluable": False, f"{end}_state": None,
                               f"{end}_reasons": None,
                               f"{end}_released_estimate_id": None,
                               f"{end}_base_qc_passed": None, f"{end}_base_qc_state": None,
                               f"{end}_base_qc_reasons": None}
        out.update({f"{end}_{k}": None for k in DECOMPOSITION})
        out.update({f"{end}_{k}": None for k in QC_FIELDS})
        out.update({f"{end}_{k}": None for k in MASK_FIELDS})
        out.update({f"{end}_{k}": None for k in DENOMINATORS})
        return out

    delta = ep.program_delta.get(program_id)
    if delta is None:
        raise BundleError(
            f"target {ep.target_id!r} carries no projection for admitted program "
            f"{program_id!r} at the {end} condition. The caller promised a COMPLETE "
            "program axis; a missing program is refused rather than emitted as a null, "
            "which would read as 'measured, and it was nothing'")

    state, evaluable, reasons = est.program_evaluability(
        base_state=str(ep.base_qc_state), base_passed=bool(ep.base_qc_passed),
        projection_status=str(delta["status"]))

    out = {
        f"{end}_present": True,
        f"{end}_delta": est.canonical(delta["delta"]),
        f"{end}_projection_status": delta["status"],
        f"{end}_evaluable": evaluable,
        f"{end}_state": state,
        f"{end}_reasons": ";".join(reasons),
        f"{end}_released_estimate_id": ep.released_estimate_id,
        f"{end}_base_qc_passed": bool(ep.base_qc_passed),
        f"{end}_base_qc_state": ep.base_qc_state,
        f"{end}_base_qc_reasons": ep.base_qc_reasons,
    }
    out.update({f"{end}_{k}": est.canonical(delta[k]) if k.endswith("_mean")
                else delta[k] for k in DECOMPOSITION})
    out.update({f"{end}_{k}": getattr(ep, k) for k in QC_FIELDS})
    out.update({f"{end}_{k}": getattr(ep, k) for k in MASK_FIELDS})
    out.update({f"{end}_{k}": getattr(ep, k) for k in DENOMINATORS})
    return out


def base_record(*, program_id: str, target_id: str, from_ep: Optional[TargetEndpoint],
                to_ep: Optional[TargetEndpoint], from_condition: str,
                to_condition: str) -> dict[str, Any]:
    """The ONE base delta for a (program, target) over the ordered pair, with its evidence.

    The base is POLE-FREE and SIGN-FREE: it is what the program projection DID between the
    two condition populations, not what anybody wanted it to do.
    """
    present = from_ep or to_ep
    if present is None:
        raise BundleError(f"base record for {program_id}|{target_id} has no endpoint at "
                          "either condition; it would be a record of nothing")

    rec: dict[str, Any] = {
        "base_key": base_key(program_id, target_id),
        "program_id": program_id,
        # STABLE, NORMALISED target identity — carried HERE (base_records), never on the arm
        # records that join to it. Stage-3 reads identity from the base record it joins to.
        "target_id": target_id,
        "target_symbol": present.target_symbol,
        "target_ensembl": present.target_ensembl,
        "target_id_namespace": present.target_id_namespace,
        # the perturbation is a CRISPRi knockdown — the fact Stage-3 needs to read the
        # modulation orientation. A screen-wide constant, but carried on the record the
        # consumer joins to; the verifier holds it to exactly this value everywhere.
        "perturbation_modality": est.PERTURBATION_MODALITY,
        "from_condition": from_condition,
        "to_condition": to_condition,
    }
    rec.update(_endpoint_side(from_ep, program_id, "from"))
    rec.update(_endpoint_side(to_ep, program_id, "to"))

    status = estimand.temporal_status(
        from_present=from_ep is not None, to_present=to_ep is not None,
        from_evaluable=bool(rec["from_evaluable"]),
        to_evaluable=bool(rec["to_evaluable"]))

    # A value that EXISTS but is not evaluable is NOT differenced. The within-condition
    # lane declined to score that program there, and a difference built on a declined score
    # would smuggle it back in under a new name.
    base = (est.base_temporal_delta(rec["from_delta"], rec["to_delta"])
            if status == estimand.ESTIMATED else None)

    rec.update({
        "temporal_status": status,
        "evaluable": status == estimand.ESTIMATED and base is not None,
        # THE RAW BASE DELTA. Unsigned by any desire; both arms are transforms of it. That
        # it is pole-free is declared ONCE, on the bundle — restating it on all 60 base
        # records would be one claim written down 60 times.
        "base_delta": est.canonical(base),
    })
    return rec


def code_identity() -> dict[str, Any]:
    """WHICH BUILD produced these bytes — the shared Stage-2 code-digest tuple.

    ``(commit, clean_tree, manifest_sha256, canonical_digest)`` over the Stage-2 tree, via
    the ONE shared convention (``code_digest.run_binding``). The producer RECORDS its tree
    state; it never SELF-ADMITS clean — ``require_clean`` is deliberately not set, so a dirty
    checkout is recorded as ``clean_tree=false`` rather than refused. The independent
    verifier re-derives this tuple and decides the FINAL clean-tree status against an
    externally pinned build; a run is not the witness for its own checkout.
    """
    return code_digest.run_binding()


def build_bundle(*, from_condition: str, to_condition: str,
                 admitted: dict[str, dict[str, Any]],
                 from_endpoints: list[TargetEndpoint],
                 to_endpoints: list[TargetEndpoint],
                 method: dict[str, Any],
                 conditions: Optional[list[str]] = None,
                 scorer_view_sha256: Optional[str] = None,
                 code: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """The complete, deterministic bundle for ONE frozen ordered condition pair.

    Contains every admitted program's ``increase`` and ``decrease`` arm, each ranked over
    its OWN admitted+evaluable population. Deterministic by construction: every collection
    is sorted by a stable key and NO timestamp is carried, so the same inputs re-emit the
    same bytes.

    ``conditions`` is the AUTHORITATIVE condition universe — the Stage-1 v3
    ``release.selector.conditions``, NOT the temporal batch policy, which is no longer the
    condition-universe authority. When supplied, the ordered pair MUST be drawn from it: a
    bundle for a pair the release never named is refused, so a forged or stale condition
    cannot enter the manifest under a valid-looking key.
    """
    from_condition, to_condition = str(from_condition), str(to_condition)
    if from_condition == to_condition:
        raise BundleError(
            f"the ordered pair ({from_condition!r} -> {to_condition!r}) is degenerate: a "
            "condition compared with itself has a base delta of exactly 0 for every target "
            "by construction, which is an arithmetic identity and not a measurement")
    if conditions is not None:
        arm_programs.require_ordered_pair(conditions, from_condition, to_condition)
    if not admitted:
        raise BundleError("no admitted programs; there is no program axis to build arms on")

    from_by_target = _endpoints_by_target(from_endpoints, from_condition)
    to_by_target = _endpoints_by_target(to_endpoints, to_condition)
    # The UNION: a target the release ships at only one endpoint still gets a record, and
    # its status says which endpoint it was absent at. An intersection would silently drop
    # it, and a reader would never learn it had been asked about.
    targets = sorted(set(from_by_target) | set(to_by_target))

    bases: list[dict[str, Any]] = []
    for program_id in sorted(admitted):
        for target_id in targets:
            bases.append(base_record(
                program_id=program_id, target_id=target_id,
                from_ep=from_by_target.get(target_id), to_ep=to_by_target.get(target_id),
                from_condition=from_condition, to_condition=to_condition))
    by_base_key = {b["base_key"]: b for b in bases}

    arms: list[dict[str, Any]] = []
    for program_id in sorted(admitted):
        for change in DESIRED_CHANGES:
            arms.append(_arm(program_id=program_id, change=change,
                             from_condition=from_condition, to_condition=to_condition,
                             targets=targets, by_base_key=by_base_key))

    bundle: dict[str, Any] = {
        "schema_version": SCHEMA_BUNDLE,
        "bundle_kind": BUNDLE_KIND,
        # the aggregate keys on ``lane``; Stage-3 (W16) keys on ``analysis_mode``
        "lane": BUNDLE_LANE,
        "analysis_mode": ANALYSIS_MODE,
        # ``context`` is the ordered pair, read as-is
        "context": {"from_condition": from_condition, "to_condition": to_condition},
        "bundle_key": bundle_key(from_condition, to_condition),
        "from_condition": from_condition,
        "to_condition": to_condition,
        "n_programs": len(admitted),
        "n_desired_changes": len(DESIRED_CHANGES),
        "n_arms": len(arms),
        "n_targets": len(targets),
        "n_base_records": len(bases),
        "arm_keys": sorted(a["arm_key"] for a in arms),
        "base_records": bases,
        "arms": arms,
        "program_admission": arm_programs.admission_block(admitted, scorer_view_sha256),
        "estimand": est.estimand_block(),
        # the perturbation modality + the SUGGESTIVE modulation rule, stated once
        "perturbation": est.perturbation_block(),
        # TWO ROLES, KEPT EXPLICIT. ``method`` is WHAT THE CODE DID (estimator/method/config
        # digests); ``code_identity`` is WHICH BUILD produced the bytes (commit + digest +
        # recorded tree state). A method hash is not a build and a build is not a method;
        # both are bound, neither stands in for the other. Bound into the bundle AND its id,
        # so an arm inventory cannot be lifted onto a build that did not produce it.
        "method": dict(method),
        "code_identity": dict(code if code is not None else code_identity()),
        # A POINTER to the producer's own PREFLIGHT (a self-check, never an admission), and
        # a DECLARATION of the required external contract — NOT a claim that an independent
        # verification already exists. The producer does not assert an admission it has not
        # earned; W11 emits the authoritative external admission separately.
        "preflight_ref": {
            "preflight_file": PREFLIGHT_FILENAME,
            "preflight_schema_version": arm_preflight.SCHEMA_PREFLIGHT,
            "preflight_verifier_id": arm_preflight.PREFLIGHT_VERIFIER_ID,
            "provenance_file": PROVENANCE_FILENAME,
        },
        "external_admission_requirement": {
            "required_verifier_id": arm_report.VERIFIER_ID,
            "required_report_schema_version": arm_report.EXTERNAL_ADMISSION_SCHEMA,
            "scope": "root_release",
        },
        "bundle_is_pair_agnostic": True,
        "bundle_carries_role_or_pole": False,
    }
    bundle["bundle_id"] = content_hash(bundle)[:BUNDLE_ID_LEN]
    return bundle


def _arm(*, program_id: str, change: str, from_condition: str, to_condition: str,
         targets: list[str], by_base_key: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """ONE reusable arm: its key, its sign-transformed values, its OWN rank.

    The rank is computed over THIS arm's own admitted+evaluable population, by the frozen
    rule, and it is NOT read off the other arm in reverse — under an exact tie both arms
    break on ``target_id`` ascending, so the two rank vectors are not mirror images.
    """
    records: list[dict[str, Any]] = []
    for target_id in targets:
        base = by_base_key[base_key(program_id, target_id)]
        value = est.canonical(est.arm_value(base["base_delta"], change))
        records.append({
            # the IMMUTABLE join key back to the normalised identity in base_records —
            # Stage-3 joins on this, never on a symbol. target_id is carried too, so the
            # join is checkable, but the full identity is not duplicated here.
            "target_id": target_id,
            "base_key": base["base_key"],
            "arm_value": value,
            "evaluable": bool(base["evaluable"]),
            "temporal_status": base["temporal_status"],
            # what this arm value SUGGESTS for drug linkage under CRISPRi knockdown —
            # deterministic from the sign, suggestive, re-derivable by the verifier
            "desired_target_modulation": est.target_modulation(
                value, evaluable=bool(base["evaluable"])),
            "rank": None,
        })
    est.rank_population(records)
    records.sort(key=lambda r: r["target_id"])   # emission order is never a headline rank

    arm = {
        "arm_key": est.arm_key(program_id, change, from_condition, to_condition),
        "program_id": program_id,
        "desired_change": change,
        "from_condition": from_condition,
        "to_condition": to_condition,
        "n_targets": len(records),
        "n_evaluable": sum(1 for r in records if r["evaluable"]),
        "n_ranked": sum(1 for r in records if r["rank"] is not None),
        "records": records,
    }
    # bind the BYTES the rank stands on: a bundle-relative ranking file + its two hashes.
    arm["ranking"] = ranking_binding(arm)
    return arm


def bundle_key(from_condition: str, to_condition: str) -> str:
    """``temporal|from|to`` — the ORDERED-pair scope of one physical bundle."""
    return f"{BUNDLE_KIND}|{from_condition}|{to_condition}"


def method_block(*, temporal_method_sha256: Optional[str] = None,
                 direct_method_version: Optional[str] = None,
                 direct_config_sha256: Optional[str] = None,
                 effect_source_sha256: Optional[str] = None,
                 effect_universe_sha256: Optional[str] = None) -> dict[str, Any]:
    """WHAT produced this bundle. Bound into its content hash, so it cannot be re-labelled.

    No timestamp, no host, no path: those are not content, and a bundle whose identity
    moved every time it was rebuilt could not be content-addressed at all.
    """
    return {
        "estimator_id": config.ESTIMATOR_ID,
        "estimator_version": config.ESTIMATOR_VERSION,
        "temporal_method_sha256": temporal_method_sha256,
        "direct_method_version": direct_method_version,
        "direct_config_sha256": direct_config_sha256,
        "effect_source_sha256": effect_source_sha256,
        "effect_universe_sha256": effect_universe_sha256,
        "inference_status": config.INFERENCE_STATUS,
    }
