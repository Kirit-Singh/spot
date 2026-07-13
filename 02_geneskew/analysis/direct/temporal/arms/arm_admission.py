"""ADMISSION for the reusable temporal arm bundle: what may ship, and what is re-derived.

GENERATOR != EVALUATOR. Everything here runs on the SHIPPED BYTES, and re-derives the
claims from them alone. It never takes the producer's word, and it never takes the
producer's in-memory object: a checker that verifies the caller's copy of the thing it is
verifying is a formality with a hash beside it.

THREE FAIL-CLOSED GATES
-----------------------
1. THE EXACT KEY ALLOWLIST, per record kind. An unknown key is a REJECT, not a warning.
   A generator that grows a field has to come here and authorise it.

2. THE INHERITED p/q/COMBINED FIREWALL (``admission.forbidden_keys``), recursive and
   case-insensitive over the whole artifact. This lane has no calibrated null, so a number
   that LOOKS like significance would be READ as significance.

3. THE ARM FIREWALL — this artifact's own prohibition. A reusable arm may not carry a
   ROLE, a POLE, a PARETO tier, a CONCORDANCE class, a PAIR/SELECTION id or a BATCH field.
   Each is a JOIN-TIME or COMPARISON-SCOPED property, and a cached arm that carried one
   would be a pair-shaped artifact wearing a reusable arm's key — which is exactly the
   defect the reusable-arm topology exists to remove.

RE-DERIVATION
-------------
The shipped bytes must prove themselves:

  * every arm key re-derives from ``(program, desired_change, from, to)``;
  * every arm value re-derives as ``SIGN[desired_change] * base_delta`` of the base record
    it points at — so ``decrease`` is EXACTLY the negation of ``increase``;
  * every rank re-derives from the shipped values by the frozen rank rule;
  * the arm inventory is exactly ``n_programs x 2``, with no program missing and none
    invented;
  * the bundle id re-derives from the bundle's own content.
"""
from __future__ import annotations

import re
from typing import Any

from ...arm_keys import DESIRED_CHANGES, SIGN
from ...hashing import content_hash
from .. import admission as comparison_admission
from . import arm_bundle as ab
from . import arm_estimand as est
from . import arm_programs

# --------------------------------------------------------------------------- #
# Gate 3: the arm firewall. A reusable arm carries NONE of these.
# --------------------------------------------------------------------------- #
ARM_FORBIDDEN_PATTERN = (
    r"pareto|concordance|away_from|toward_b|batch"
    r"|pair_id|pair_key|selection_id|question_id"
    r"|(^|_)(pole|poles|role|roles)(_|$)")
ARM_FORBIDDEN_RE = re.compile(ARM_FORBIDDEN_PATTERN, re.IGNORECASE)

# NEGATIVE DECLARATIONS: exempt ONLY while they still say "forbidden". The artifact has to
# be able to write down its own prohibition, or the rule would be unstatable — but it does
# not get to keep the exemption after flipping the prohibition off.
ARM_NEGATIVE_DECLARATIONS = {"bundle_carries_role_or_pole": False}

# THE ONE EXACT-NAME EXEMPTION from the INHERITED firewall (gate 2).
#
# ``registry_scorer_view_sha256`` matches ``/score/`` — because "scorer" contains "score".
# It is nonetheless legitimate: it is the Stage-1 v3 contract's OWN field name for the
# content hash of the program REGISTRY SCORER VIEW, and it is carried under the contract's
# spelling so a reader can trace the program axis back to the release it was derived from.
# It is the hash of a registry. It is not a score, not an objective and not a ranking
# quantity — nothing ranks, gates or sorts on it.
#
# The exemption is the EXACT SPELLING, not the shape. There is no pattern-shaped hole here
# for a ``combined_scorer`` or a ``scorer_value`` to walk through.
# The scorer-view hashes match ``/score/`` only because "scorer" contains "score". They are
# the Stage-1 v3 scorer VIEW content hashes (registry + raw + canonical), carried under the
# contract's own spelling; nothing ranks, gates or sorts on them. Exempt by EXACT spelling.
INHERITED_FIREWALL_EXCEPTIONS = frozenset({
    "registry_scorer_view_sha256", "scorer_view_raw_sha256",
    "scorer_view_canonical_sha256"})


def inherited_forbidden_keys(obj: Any) -> list[str]:
    """The inherited p/q/combined firewall, minus the one exact-named exemption above."""
    return [hit for hit in comparison_admission.forbidden_keys(obj)
            if hit.rsplit(".", 1)[-1] not in INHERITED_FIREWALL_EXCEPTIONS]


# --------------------------------------------------------------------------- #
# THE PORTABILITY FIREWALL: no machine-local address may enter a shipped artifact.
#
# A content-addressed bundle must be BYTE-IDENTICAL on any host. An absolute path, a
# hostname or a private IP is none of the bundle's business and is not reproducible off the
# machine that wrote it: it breaks portability AND leaks where the run happened. W11's
# path-injection reseal — insert ``/home/.../arm_bundle.json`` and recompute the bundle_id
# so it re-derives — is caught HERE and not by the hash, because this scan runs regardless
# of whether the content hash is internally consistent.
# --------------------------------------------------------------------------- #
_ABSOLUTE_PATH_RE = re.compile(r"^(?:/|~|file://|[A-Za-z]:[\\/])")
_EMBEDDED_ROOT_RE = re.compile(
    r"/(?:home|tmp|Users|root|var|mnt|private|opt|etc|proc)/")
_HOSTNAME_RE = re.compile(r"\b(?:tcedirector|tcefold|localhost)\b", re.IGNORECASE)
_PRIVATE_IP_RE = re.compile(
    r"\b(?:10|127)\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"
    r"|\b192\.168\.\d{1,3}\.\d{1,3}\b"
    r"|\b172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}\b")


def is_machine_local(s: str) -> bool:
    """An absolute/embedded filesystem path, a known hostname, or a private IP address."""
    return bool(_ABSOLUTE_PATH_RE.match(s) or _EMBEDDED_ROOT_RE.search(s)
                or _HOSTNAME_RE.search(s) or _PRIVATE_IP_RE.search(s))


def machine_local_strings(obj: Any, path: str = "") -> list[str]:
    """Every machine-local string in a document, at ANY depth, as a dotted path.

    Scans keys and values alike: a leaked path is a value today, but a firewall that only
    looked at values would miss one that arrived as a key.
    """
    hits: list[str] = []
    if isinstance(obj, str):
        if is_machine_local(obj):
            hits.append(path or repr(obj))
    elif isinstance(obj, dict):
        for key, value in obj.items():
            here = f"{path}.{key}" if path else str(key)
            if is_machine_local(str(key)):
                hits.append(here)
            hits.extend(machine_local_strings(value, here))
    elif isinstance(obj, (list, tuple)):
        for i, value in enumerate(obj):
            hits.extend(machine_local_strings(value, f"{path}[{i}]"))
    return hits


BUNDLE_KEYS = frozenset({
    "schema_version", "bundle_kind", "lane", "analysis_mode", "context", "bundle_key",
    "bundle_id", "from_condition", "to_condition",
    "n_programs", "n_desired_changes", "n_arms", "n_targets", "n_base_records",
    "arm_keys", "base_records", "arms", "program_admission", "stage1_binding", "estimand",
    "perturbation", "method", "code_identity", "preflight_ref",
    "external_admission_requirement", "bundle_is_pair_agnostic", "bundle_carries_role_or_pole",
})

# The two roles the run binding must keep DISTINCT. ``code_identity`` = WHICH BUILD (the
# shared code-digest tuple); the method digest = WHAT THE CODE DID. Structural presence only
# — the producer records its tree state and NEVER self-admits clean; the independent
# verifier re-derives the tuple and decides the final clean-tree status against a pin.
CODE_IDENTITY_FIELDS = ("commit", "clean_tree", "manifest_sha256", "canonical_digest")

ARM_KEYS_ALLOWED = frozenset({
    "arm_key", "program_id", "desired_change", "from_condition", "to_condition",
    "n_targets", "n_evaluable", "n_ranked", "records", "ranking",
})

ARM_RECORD_KEYS = frozenset({
    "target_id", "base_key", "arm_value", "evaluable", "temporal_status",
    "desired_target_modulation", "rank",
})

_ENDS = ("from", "to")
BASE_RECORD_KEYS = frozenset(
    {"base_key", "program_id", "target_id", "target_symbol", "target_ensembl",
     "target_id_namespace", "perturbation_modality", "from_condition", "to_condition",
     "temporal_status", "evaluable", "base_delta"}
    | {f"{e}_{k}" for e in _ENDS for k in
       ("present", "delta", "projection_status", "evaluable", "state", "reasons",
        "released_estimate_id", "base_qc_passed", "base_qc_state", "base_qc_reasons")}
    | {f"{e}_{k}" for e in _ENDS for k in ab.DECOMPOSITION}
    | {f"{e}_{k}" for e in _ENDS for k in ab.QC_FIELDS}
    | {f"{e}_{k}" for e in _ENDS for k in ab.MASK_FIELDS}
    | {f"{e}_{k}" for e in _ENDS for k in ab.DENOMINATORS})


class BundleRejected(ValueError):
    """The bundle is not admissible. Refuse; never repair, never downgrade to a warning."""


def arm_forbidden_keys(obj: Any, path: str = "") -> list[str]:
    """Every ROLE / POLE / PARETO / CONCORDANCE / PAIR / BATCH key, at ANY depth."""
    hits: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            here = f"{path}.{key}" if path else str(key)
            if ARM_FORBIDDEN_RE.search(str(key)) and not _exempt(str(key), value):
                hits.append(here)
            hits.extend(arm_forbidden_keys(value, here))
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            hits.extend(arm_forbidden_keys(value, f"{path}[{i}]"))
    return hits


def _exempt(key: str, value: Any) -> bool:
    if key in ARM_NEGATIVE_DECLARATIONS:
        # `is` on the literal, so a truthy 1 or "false" cannot pose as the prohibition
        return value is ARM_NEGATIVE_DECLARATIONS[key]
    return False


# A reusable arm is PAIR-AGNOSTIC. It never carries a pole-derived quantity or a POLE/PAIR-
# scoped program projection: those belong to a pair somebody chose. The legitimate Stage-1
# ``per_program_projection_sha256`` (a per-PROGRAM scorer-view hash) is NOT pair-based and is
# not caught — only a projection keyed on a pole or a pair is.
_PAIR_PROJECTION_RE = re.compile(
    r"derived_from_pole|(pole|pair)[a-z_]*projection|projection[a-z_]*(pole|pair)",
    re.IGNORECASE)


def _pair_projection_keys(obj: Any, path: str = "") -> list[str]:
    """Every ``derived_from_pole*`` / ``program_projection*`` key, at ANY depth."""
    hits: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            here = f"{path}.{key}" if path else str(key)
            if _PAIR_PROJECTION_RE.search(str(key)):
                hits.append(here)
            hits.extend(_pair_projection_keys(value, here))
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            hits.extend(_pair_projection_keys(value, f"{path}[{i}]"))
    return hits


def _unknown(got: Any, allowed: frozenset, what: str) -> list[str]:
    return [f"{what}.{k}" for k in sorted(set(got) - set(allowed))]


def _missing(got: Any, allowed: frozenset, what: str) -> list[str]:
    return [f"{what}.{k}" for k in sorted(set(allowed) - set(got))]


def verify_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    """RE-DERIVE every claim in the bundle from the bundle. Returns a checked report.

    Raises ``BundleRejected`` on the first structural refusal; collects every
    re-derivation failure so a reader sees ALL of them rather than one at a time. Records
    every gate — passed or failed — so the independent report can carry its inventory: an
    ADMIT that ran no gates is an ADMIT that checked nothing.
    """
    gates: dict[str, dict[str, Any]] = {}
    failures: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        # A gate is PASS only if EVERY occurrence passes: the first failure pins it failed.
        g = gates.setdefault(name, {"gate": name, "status": "pass", "detail": ""})
        if not ok and g["status"] == "pass":
            g["status"] = "fail"
            g["detail"] = detail
            failures.append(f"[{name}] {detail}")

    # ---- gate 1: the exact key allowlists ----
    problems = (_unknown(bundle, BUNDLE_KEYS, "bundle")
                + _missing(bundle, BUNDLE_KEYS, "bundle"))
    if problems:
        raise BundleRejected(
            f"bundle keys are not the contract: {problems}. An unknown key is an "
            "unauthorised claim; a missing one means this is not the artifact the "
            "contract describes")
    for arm in bundle["arms"]:
        p = _unknown(arm, ARM_KEYS_ALLOWED, "arm") + _missing(arm, ARM_KEYS_ALLOWED, "arm")
        if p:
            raise BundleRejected(f"arm {arm.get('arm_key')!r} keys are not the contract: {p}")
        for rec in arm["records"]:
            p = (_unknown(rec, ARM_RECORD_KEYS, "arm_record")
                 + _missing(rec, ARM_RECORD_KEYS, "arm_record"))
            if p:
                raise BundleRejected(f"arm record keys are not the contract: {p}")
    for base in bundle["base_records"]:
        p = (_unknown(base, BASE_RECORD_KEYS, "base_record")
             + _missing(base, BASE_RECORD_KEYS, "base_record"))
        if p:
            raise BundleRejected(f"base record keys are not the contract: {p}")

    # ---- gate 2: the inherited p / q / combined-objective firewall ----
    pq = inherited_forbidden_keys(bundle)
    check("no_pq_or_combined_objective", not pq, f"forbidden keys: {pq}")

    # ---- gate 3: the arm firewall ----
    arm_hits = arm_forbidden_keys(bundle)
    check("no_role_pole_pareto_concordance_pair_or_batch_field", not arm_hits,
          f"forbidden keys: {arm_hits}")

    # ---- gate 4: the portability firewall (fail-closed on a resealed path injection) ----
    local = machine_local_strings(bundle)
    check("no_machine_local_path_hostname_or_private_address", not local,
          f"machine-local strings at: {local[:6]}")

    # ---- gate 5: the bundle names the temporal lane / mode the consumers key on ----
    check("bundle_declares_the_temporal_lane", bundle.get("lane") == ab.BUNDLE_LANE,
          f"lane is {bundle.get('lane')!r}, not {ab.BUNDLE_LANE!r}")
    check("bundle_declares_the_temporal_cross_condition_mode",
          bundle.get("analysis_mode") == ab.ANALYSIS_MODE,
          f"analysis_mode is {bundle.get('analysis_mode')!r}, not {ab.ANALYSIS_MODE!r}")

    # ---- gate 6: the perturbation modality Stage-3 reads the modulation orientation by ----
    modality = est.PERTURBATION_MODALITY
    check("bundle_declares_the_crispri_knockdown_modality",
          (bundle.get("perturbation") or {}).get("perturbation_modality") == modality,
          f"bundle perturbation modality is not {modality!r}")
    check("bundle_states_no_pharmacologic_reversibility_assumed",
          (bundle.get("perturbation") or {}).get(
              "pharmacologic_reversibility_assumed") is False,
          "the modulation rule must not assume pharmacologic reversibility")
    bad_modality = [b["base_key"] for b in bundle["base_records"]
                    if b.get("perturbation_modality") != modality]
    check("every_base_record_carries_the_same_modality", not bad_modality,
          f"base records with a divergent modality: {bad_modality[:4]}")

    # ---- gate 7: the code_identity + method-digest roles, both present, kept distinct ----
    # STRUCTURAL only. The producer records its tree state; it does not get to declare
    # itself clean, so this checks presence of the tuple, NOT clean_tree == True.
    code = bundle.get("code_identity") or {}
    missing_ci = [f for f in CODE_IDENTITY_FIELDS if f not in code]
    check("bundle_binds_a_structural_code_identity_without_self_admitting_clean",
          isinstance(bundle.get("code_identity"), dict) and not missing_ci,
          f"code_identity is absent or omits {missing_ci}")
    check("method_digest_and_code_identity_are_both_bound_as_distinct_roles",
          bool((bundle.get("method") or {}).get("temporal_method_sha256"))
          and bool(code),
          "a method digest is not a build and a build is not a method; both must be bound")

    # ---- gate 8: the reusable arm stays PAIR-AGNOSTIC — no pole-derived projection ----
    projection_hits = [h for h in _pair_projection_keys(bundle)]
    check("no_pole_derived_or_pair_based_program_projection_field", not projection_hits,
          f"pair/pole-derived projection keys: {projection_hits[:6]}")

    # ---- gate 9: the Stage-1 v3 release binding is COMPLETE (no null identity) ----
    s1 = bundle.get("stage1_binding") or {}
    s1_nulls = arm_programs.stage1_binding_nulls(s1)
    check("stage1_binding_is_complete_and_non_null", not s1_nulls,
          f"stage1_binding null/absent fields: {s1_nulls}")
    pa = bundle.get("program_admission") or {}
    check("stage1_binding_programs_match_the_admitted_program_set",
          list(s1.get("admitted_programs") or []) == list(pa.get("programs") or []),
          "the stage1 binding names a different program set than program_admission")
    check("stage1_binding_scorer_view_matches_program_admission",
          s1.get("scorer_view_canonical_sha256") == pa.get("registry_scorer_view_sha256"),
          "the stage1 scorer-view hash disagrees with program_admission")

    # ---- the inventory: n_programs x 2, complete and not invented ----
    programs = bundle["program_admission"]["programs"]
    expected = {est.arm_key(p, c, bundle["from_condition"], bundle["to_condition"])
                for p in programs for c in DESIRED_CHANGES}
    got = {a["arm_key"] for a in bundle["arms"]}
    check("arm_inventory_is_every_program_x_every_desired_change", got == expected,
          f"missing={sorted(expected - got)} unexpected={sorted(got - expected)}")
    check("n_arms_is_n_programs_x_n_desired_changes",
          bundle["n_arms"] == len(programs) * len(DESIRED_CHANGES),
          f"n_arms={bundle['n_arms']} programs={len(programs)}")
    check("arm_keys_index_matches_the_arms", sorted(got) == list(bundle["arm_keys"]),
          "the arm_keys index disagrees with the arms it indexes")

    by_base = {b["base_key"]: b for b in bundle["base_records"]}

    for arm in bundle["arms"]:
        key = arm["arm_key"]
        # the KEY re-derives from its own parts — a forged key cannot survive this
        rederived = est.arm_key(arm["program_id"], arm["desired_change"],
                                arm["from_condition"], arm["to_condition"])
        check("arm_key_rederives_from_its_own_parts", key == rederived,
              f"shipped {key!r}, re-derived {rederived!r}")
        check("arm_is_scoped_to_the_bundles_ordered_pair",
              arm["from_condition"] == bundle["from_condition"]
              and arm["to_condition"] == bundle["to_condition"],
              f"arm {key!r} names a different ordered pair than its bundle")

        sign = SIGN[arm["desired_change"]]
        for rec in arm["records"]:
            base = by_base.get(rec["base_key"])
            # REFERENTIAL INTEGRITY: the arm record joins to EXACTLY ONE base record, and
            # that base record is about the SAME target. Stage-3 reads identity by this
            # join, so a dangling or mismatched base_key is a broken identity, not a warning.
            check("arm_record_joins_to_exactly_one_base_record", base is not None,
                  f"{key} / {rec['target_id']}: base_key {rec['base_key']!r} resolves to "
                  "no base record")
            if base is None:
                continue
            check("arm_record_and_its_base_record_name_the_same_target",
                  base["target_id"] == rec["target_id"],
                  f"{key}: arm record target {rec['target_id']!r} joins base record for "
                  f"{base['target_id']!r}")
            # the VALUE is a sign transform of the ONE base delta. Not a re-estimate.
            b = base["base_delta"]
            want = None if b is None else (0.0 if b == 0 else sign * b)
            check("arm_value_is_the_sign_transform_of_the_base_delta",
                  rec["arm_value"] == want,
                  f"{key} / {rec['target_id']}: shipped {rec['arm_value']!r}, "
                  f"re-derived {want!r} from base_delta={b!r}")
            check("arm_evaluability_is_the_bases_evaluability",
                  rec["evaluable"] == base["evaluable"],
                  f"{key} / {rec['target_id']}: the two arms of a program share an "
                  "estimate, so they share its evaluability")
            # the MODULATION orientation re-derives from the sign of the shipped value —
            # a suggestive claim cannot be asserted out of step with the number it is about.
            want_mod = est.target_modulation(rec["arm_value"],
                                             evaluable=bool(rec["evaluable"]))
            check("desired_target_modulation_rederives_from_the_arm_value",
                  rec.get("desired_target_modulation") == want_mod,
                  f"{key} / {rec['target_id']}: modulation "
                  f"{rec.get('desired_target_modulation')!r} != re-derived {want_mod!r}")

        # the RANK re-derives from the SHIPPED values, by the frozen rule
        _check_ranks(arm, check)

        # the RANKING BINDING re-derives from this arm's own ranked list. The aggregate
        # opens the bound file and recomputes; here the binding is checked against the arm
        # it claims to summarise, so a hash pointing at some other ranking cannot survive.
        want_bind = ab.ranking_binding(arm)
        check("ranking_binding_matches_the_arm", arm.get("ranking") == want_bind,
              f"{key}: shipped ranking {arm.get('ranking')} != re-derived {want_bind}")

    # ---- the bundle id covers the bundle's own content ----
    payload = {k: v for k, v in bundle.items() if k != "bundle_id"}
    derived = content_hash(payload)[:ab.BUNDLE_ID_LEN]
    check("bundle_id_covers_its_own_content", bundle["bundle_id"] == derived,
          f"shipped {bundle['bundle_id']!r}, content hashes to {derived!r}")

    return {"admitted": not failures, "failures": failures,
            "checks": list(gates.values()),
            "n_arms": bundle["n_arms"], "n_base_records": bundle["n_base_records"],
            "bundle_id": bundle["bundle_id"], "bundle_key": bundle["bundle_key"]}


def _check_ranks(arm: dict[str, Any], check) -> None:
    """Re-derive this arm's ranks from its OWN shipped values, by the frozen rule.

    Descending on the canonical value; ties on ``target_id`` ascending; dense 1..n over the
    evaluable, non-null population; everything else null. Computed from the bytes, so a
    rank that was assigned by some other rule cannot survive.
    """
    rankable = [r for r in arm["records"]
                if r["evaluable"] and r["arm_value"] is not None]
    order = sorted(rankable, key=lambda r: (-r["arm_value"], r["target_id"]))
    want = {r["target_id"]: i for i, r in enumerate(order, start=1)}
    for rec in arm["records"]:
        expected = want.get(rec["target_id"])
        check("rank_rederives_by_the_frozen_rule", rec["rank"] == expected,
              f"{arm['arm_key']} / {rec['target_id']}: shipped rank {rec['rank']!r}, "
              f"re-derived {expected!r}")
    check("n_ranked_is_the_evaluable_population",
          arm["n_ranked"] == len(rankable) and arm["n_evaluable"] == len(rankable),
          f"{arm['arm_key']}: n_ranked={arm['n_ranked']} n_evaluable={arm['n_evaluable']} "
          f"rankable={len(rankable)}")


def verify_shipped(out_dir: str) -> dict[str, Any]:
    """The STANDALONE verifier W11/W16 re-run: read the shipped bytes off disk, re-derive.

    Independent of the producer's in-memory state — it opens ``arm_bundle.json`` and each
    arm's bound ranking file from disk and checks that what shipped re-derives. A consumer
    that cannot see a bundle verified is a consumer that refuses it, so this is the entry
    point that reconstructs the bundle from nothing but its own bytes.
    """
    import json
    import os

    from ...hashing import content_hash, sha256_hex
    from . import arm_provenance

    path = os.path.join(out_dir, ab.BUNDLE_FILENAME)
    if not os.path.exists(path):
        return {"admitted": False, "failures": [f"[no_bundle] {ab.BUNDLE_FILENAME} absent"],
                "checks": [], "out_dir": out_dir}
    with open(path, "rb") as fh:
        bundle_raw = fh.read()
    bundle = json.loads(bundle_raw)
    arm_raw = sha256_hex(bundle_raw)

    result = verify_bundle(bundle)
    failures = list(result["failures"])

    # the on-disk ranking files must be present and match the bindings the bundle carries
    expected_rankings = set()
    for arm in bundle.get("arms", []):
        binding = arm.get("ranking") or {}
        rel = str(binding.get("path", ""))
        expected_rankings.add(rel)
        rpath = os.path.join(out_dir, rel)
        if os.path.isabs(rel) or ".." in rel.split("/") or not os.path.exists(rpath):
            failures.append(f"[ranking_file_missing_or_not_relative] {rel!r}")
            continue
        with open(rpath, "rb") as fh:
            raw = fh.read()
        if sha256_hex(raw) != binding.get("raw_sha256") \
                or content_hash(json.loads(raw)) != binding.get("canonical_sha256"):
            failures.append(f"[ranking_file_hash_mismatch] {rel!r}")

    # NO STALE / EXTRA ranking files: the rankings dir must hold EXACTLY the bound set. A
    # left-over ranking from a program no longer admitted is an arm nobody bound but a
    # reader could pick up, so it is a refusal, not a shrug.
    rdir = os.path.join(out_dir, ab.RANKINGS_DIR)
    on_disk = {f"{ab.RANKINGS_DIR}/{fn}" for fn in os.listdir(rdir)} \
        if os.path.isdir(rdir) else set()
    stale = sorted(on_disk - expected_rankings)
    if stale:
        failures.append(f"[stale_or_extra_ranking_files] {stale[:6]}")

    # if the provenance shipped, it must RE-DERIVE from the bundle and bind this bundle's
    # bytes — so the self-check covers the provenance the preflight then binds, rather than
    # a document produced after the check that nothing validated.
    prov_path = os.path.join(out_dir, ab.PROVENANCE_FILENAME)
    if os.path.exists(prov_path):
        with open(prov_path, "rb") as fh:
            shipped_prov = json.loads(fh.read())
        want_prov = arm_provenance.build_provenance(
            bundle, bundle_file=ab.BUNDLE_FILENAME, bundle_raw_sha256=arm_raw)
        if shipped_prov != want_prov:
            failures.append("[provenance_does_not_rederive_from_the_bundle]")
        if shipped_prov.get("bundle_raw_sha256") != arm_raw:
            failures.append("[provenance_binds_a_different_bundle]")

    result = dict(result)
    result["failures"] = failures
    result["admitted"] = not failures
    result["out_dir"] = out_dir
    result["arm_bundle_sha256"] = arm_raw
    return result
