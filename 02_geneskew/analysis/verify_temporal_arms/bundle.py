"""RE-DERIVE one ordered-pair bundle from its own shipped bytes and the bound release.

Everything here runs on a bundle that was REOPENED FROM DISK. Nothing is checked against
the producer's in-memory object, and nothing is taken from the producer's own admission
report: a checker that verifies the caller's copy of the thing it is verifying is a
formality with a hash beside it.

WHAT IS RECOMPUTED, from the bundle's own evidence, with this package's own rules:

    base_delta   == delta_p(to) - delta_p(from)              (the DiD)
    arm_value    == SIGN[desired_change] * base_delta
    rank         <- the frozen rank rule, over this arm's OWN shipped values
    bundle_id    == the content hash of the bundle's own content

The ENDPOINTS themselves answer to ``direct_source``: they are admitted Direct all-arm
bundles, and the difference is recomputed against THOSE numbers — against the measurement,
not against the release's restatement of it.
"""
from __future__ import annotations

from typing import Any, Optional

from . import arm_evidence as evidence
from . import direct_source, rules, schema
from .canonical import content_hash
from .failures import Failures, allowlist

BUNDLE_ID_LEN = 16
_ENDS = ("from", "to")



def verify_bundle(doc: dict[str, Any], *, bound, from_condition: str, to_condition: str,
                  artifact_dir: str = "",
                  host_denylist=()) -> tuple[Failures, dict[str, int]]:
    """Every claim in ONE bundle, re-derived. Returns the failures and what was recomputed."""
    f = Failures()
    counts = {"base_deltas": 0, "arm_values": 0}
    where = f"{from_condition}__to__{to_condition}"

    # ---- the firewalls run FIRST, over the whole artifact, before anything is trusted ----
    banned = schema.banned_keys(doc)
    inference = [b for b in banned if _tokens_of(b) & schema.INFERENCE_TOKENS]
    objective = [b for b in banned if _tokens_of(b) & schema.OBJECTIVE_TOKENS]
    join_time = [b for b in banned if _tokens_of(b) & schema.JOIN_TIME_TOKENS
                 or schema.BANNED_SUBSTRING_RE.search(b.rsplit(".", 1)[-1])]
    f.check("no_p_q_fdr_or_significance_field", not inference, where, str(inference))
    f.check("no_combined_balanced_or_weighted_objective", not objective, where,
            str(objective))
    f.check("no_pair_pareto_concordance_joint_role_pole_or_batch_field", not join_time,
            where, str(join_time))
    machine = schema.machine_path_hits(doc, host_denylist=host_denylist)
    f.check("no_machine_path_hostname_or_private_address", not machine, where,
            str(machine))

    # ---- the exact key allowlists. An unknown key is an unauthorised claim. ----
    if not allowlist(f, doc, schema.BUNDLE_KEYS, "bundle_keys_are_the_exact_allowlist",
                      where):
        return f, counts                      # structure is gone; arithmetic is meaningless

    allowlist(f, doc["program_admission"], schema.PROGRAM_ADMISSION_KEYS,
               "program_admission_keys_are_the_exact_allowlist", where)
    allowlist(f, doc["estimand"], schema.ESTIMAND_KEYS,
               "estimand_keys_are_the_exact_allowlist", where)
    allowlist(f, (doc["estimand"] or {}).get("rank_rule"), schema.RANK_RULE_KEYS,
               "rank_rule_keys_are_the_exact_allowlist", where)
    allowlist(f, doc["method"], schema.METHOD_KEYS,
               "method_keys_are_the_exact_allowlist", where)
    allowlist(f, doc["context"], schema.CONTEXT_KEYS,
               "context_keys_are_the_exact_allowlist", where)
    allowlist(f, doc["perturbation"], schema.PERTURBATION_KEYS,
               "perturbation_keys_are_the_exact_allowlist", where)
    allowlist(f, doc["external_admission_requirement"],
              schema.EXTERNAL_ADMISSION_REQUIREMENT_KEYS,
              "external_admission_requirement_keys_are_the_exact_allowlist", where)
    allowlist(f, doc["preflight_ref"], schema.PREFLIGHT_REF_KEYS,
              "preflight_ref_keys_are_the_exact_allowlist", where)
    allowlist(f, doc["env_lock"], schema.ENV_LOCK_KEYS,
              "env_lock_keys_are_the_exact_allowlist", where)
    allowlist(f, doc["endpoint_source"], schema.ENDPOINT_SOURCE_KEYS,
              "endpoint_source_keys_are_the_exact_allowlist", where)
    for arm in doc["arms"]:
        allowlist(f, arm, schema.ARM_KEYS, "arm_keys_are_the_exact_allowlist",
                   str(arm.get("arm_key")))
        for rec in arm.get("records") or []:
            allowlist(f, rec, schema.ARM_RECORD_KEYS,
                       "arm_record_keys_are_the_exact_allowlist", str(arm.get("arm_key")))
    for base in doc["base_records"]:
        allowlist(f, base, schema.BASE_RECORD_KEYS,
                   "base_record_keys_are_the_exact_allowlist", str(base.get("base_key")))
    if f.gates & {"arm_keys_are_the_exact_allowlist",
                  "arm_record_keys_are_the_exact_allowlist",
                  "base_record_keys_are_the_exact_allowlist",
                  "estimand_keys_are_the_exact_allowlist",
                  "method_keys_are_the_exact_allowlist",
                  "perturbation_keys_are_the_exact_allowlist",
                  "external_admission_requirement_keys_are_the_exact_allowlist",
                  "preflight_ref_keys_are_the_exact_allowlist",
                  "env_lock_keys_are_the_exact_allowlist",
                  "endpoint_source_keys_are_the_exact_allowlist",
                  "context_keys_are_the_exact_allowlist",
                  "program_admission_keys_are_the_exact_allowlist"}:
        return f, counts

    _identity(f, doc, where, from_condition, to_condition, bound)
    _estimand(f, doc, where)
    evidence.perturbation(f, doc, where)
    counts = _arithmetic(f, doc, where, bound)
    evidence.rankings(f, doc, where, artifact_dir)

    payload = {k: v for k, v in doc.items() if k != "bundle_id"}
    derived = content_hash(payload)[:BUNDLE_ID_LEN]
    f.check("bundle_id_covers_its_own_content", doc["bundle_id"] == derived, where,
            f"shipped {doc['bundle_id']!r}, its own content hashes to {derived!r}")
    return f, counts


def _tokens_of(dotted: str) -> set[str]:
    return {t.lower() for t in schema.tokens(dotted.rsplit(".", 1)[-1])}


def _identity(f: Failures, doc: dict[str, Any], where: str, from_condition: str,
              to_condition: str, bound) -> None:
    """WHICH bundle this is, WHICH release it binds, and WHICH programs it may carry."""
    f.check("bundle_schema_version_is_the_contract",
            doc["schema_version"] == schema.SCHEMA_BUNDLE, where, doc["schema_version"])
    f.check("bundle_kind_is_temporal", doc["bundle_kind"] == schema.BUNDLE_KIND, where,
            doc["bundle_kind"])

    # The DIRECTORY is the claim a reader resolves a bundle by. A bundle whose conditions
    # were swapped under it would be served, by path, as the comparison it is the opposite
    # of — with a plausible sign on every number.
    f.check("bundle_directory_names_the_ordered_pair_it_carries",
            (doc["from_condition"], doc["to_condition"]) == (from_condition, to_condition),
            where, f"the directory says ({from_condition} -> {to_condition}), the bundle "
                   f"says ({doc['from_condition']} -> {doc['to_condition']})")
    f.check("bundle_is_scoped_to_conditions_the_release_shipped",
            doc["from_condition"] in bound.conditions
            and doc["to_condition"] in bound.conditions, where,
            f"released conditions are {list(bound.conditions)}")
    f.check("bundle_key_rederives_from_its_ordered_pair",
            doc["bundle_key"] == rules.bundle_key(doc["from_condition"],
                                                  doc["to_condition"]), where,
            doc["bundle_key"])

    admission = doc["program_admission"]
    programs = list(admission["programs"])
    f.check("bundle_program_axis_is_the_bound_releases_admitted_set",
            sorted(programs) == sorted(bound.admitted_programs), where,
            f"bundle {sorted(programs)}, release {sorted(bound.admitted_programs)}")
    f.check("program_count_agrees_with_the_program_axis",
            doc["n_programs"] == len(programs) == admission["n_programs"], where,
            f"n_programs={doc['n_programs']} programs={len(programs)}")
    f.check("bundle_binds_the_scorer_view_of_the_bound_release",
            admission["registry_scorer_view_sha256"] == bound.scorer_view_sha256, where,
            f"bundle binds {admission['registry_scorer_view_sha256']}, the bound release's "
            f"scorer view canonically hashes to {bound.scorer_view_sha256}")

    es = doc["endpoint_source"]
    f.check("the_temporal_endpoints_are_two_admitted_direct_all_arm_bundles",
            es.get("endpoint_source") == direct_source.ENDPOINT_SOURCE_REQUIRED, where,
            f"endpoint_source is {es.get('endpoint_source')!r}. A temporal arm is a "
            "difference of two within-condition numbers; if nobody measured them, every "
            "gate downstream is checking the arithmetic of an invention")

    lock = doc["env_lock"]
    f.check("the_release_was_built_under_a_real_verified_environment_lock",
            lock.get("env_lock_is_synthetic") is False
            and lock.get("env_lock_verified_from_bytes") is True, where,
            f"env_lock is_synthetic={lock.get('env_lock_is_synthetic')!r} "
            f"verified_from_bytes={lock.get('env_lock_verified_from_bytes')!r}; a synthetic "
            "or unverified lock pins no environment at all")

    req = doc["external_admission_requirement"]
    f.check("the_bundle_requires_an_EXTERNAL_admission_from_this_lane",
            req.get("required_verifier_id") == schema.INDEPENDENT_VERIFIER_CONTRACT
            and req.get("required_report_schema_version") == schema.SCHEMA_ENVELOPE, where,
            "a bundle that did not require an external admission could be consumed on the "
            "strength of its own preflight")

    method = doc["method"]
    f.check("method_binds_the_effect_source_it_differenced",
            bool(method.get("effect_source_sha256"))
            and bool(method.get("effect_universe_sha256")), where,
            "an arm value is a projection OF an effect vector; a method that does not bind "
            "the effect source it differenced is naming a number it cannot point at")
    f.check("method_binds_the_within_condition_method",
            bool(method.get("direct_method_version"))
            and bool(method.get("direct_config_sha256")), where,
            "an endpoint IS a within-condition projection, so the within-condition method "
            "is part of what produced this arm")


def _estimand(f: Failures, doc: dict[str, Any], where: str) -> None:
    """The artifact's own claim about WHAT it measured. It may not be relabelled."""
    est = doc["estimand"]
    f.check("estimand_is_population_level_not_per_cell_fate",
            est["estimand_level"] == rules.ESTIMAND_LEVEL
            and est["estimand_is_per_cell_fate"] is False
            and est["estimand_is_lineage_traced"] is False
            and est["estimand_is_a_rate_or_slope"] is False
            and est["estimand_is_author_early_late_cluster_class"] is False, where,
            "this is a shift in a POPULATION-LEVEL program projection between two "
            "separately-fitted condition populations: no cell is followed, and it is not "
            "the authors' early/late cluster call")
    f.check("inference_status_is_not_calibrated",
            est["inference_status"] == rules.INFERENCE_STATUS, where,
            "there is no calibrated null for this projection; a lane that claimed one "
            "would be publishing a significance it never computed")
    f.check("the_two_arms_are_sign_transforms_of_one_base_delta",
            est["arms_are_sign_transforms_of_one_base_delta"] is True
            and est["arms_are_two_experimental_estimates"] is False, where, "")
    f.check("the_declared_sign_map_is_the_frozen_one",
            est["sign_by_desired_change"] == {c: rules.SIGN[c]
                                              for c in rules.DESIRED_CHANGES}, where,
            str(est["sign_by_desired_change"]))
    rank_rule = est["rank_rule"]
    f.check("the_declared_rank_rule_is_the_frozen_one",
            rank_rule["rank_direction"] == rules.RANK_DIRECTION
            and rank_rule["rank_tie_break"] == rules.RANK_TIE_BREAK
            and rank_rule["ranks_are_independent_per_desired_change"] is True
            and rank_rule["rank_inferred_from_the_other_arm"] is False, where,
            "the decrease rank is NOT the increase rank in reverse: under an exact tie the "
            "tie-break runs target_id ASCENDING in both arms")


def _endpoint(f: Failures, base: dict[str, Any], end: str, where: str,
              from_direct: bool = False) -> None:
    """ONE endpoint of ONE base record: the projection identity, its status, its state."""
    if not base[f"{end}_present"]:
        f.check("an_absent_endpoint_carries_no_measurement",
                base[f"{end}_delta"] is None and base[f"{end}_evaluable"] is False, where,
                f"the release ships no estimate at the {end} condition; a zero there would "
                "be a measurement nobody made")
        return

    panel, control = base[f"{end}_panel_mean"], base[f"{end}_control_mean"]
    status = base[f"{end}_projection_status"]

    # WITH A DIRECT ENDPOINT SOURCE the panel/control decomposition lives in the DIRECT
    # bundle, not here: this endpoint's delta IS that bundle's admitted base delta, and it
    # is proved against it in ``direct_source.recompute`` — against the measurement, not
    # against a restatement of it. Re-deriving it from a decomposition the release does not
    # carry would be checking arithmetic nobody performed.
    if from_direct:
        f.check("a_direct_sourced_endpoint_carries_no_second_copy_of_the_decomposition",
                panel is None and control is None, where,
                f"{base['base_key']} {end}: the endpoint is an admitted Direct base delta; "
                "a second copy of the decomposition here would be a second chance to "
                "disagree with the bundle it came from")
        return

    if status == rules.OK:
        f.check("endpoint_delta_is_the_masked_panel_minus_control_projection",
                base[f"{end}_delta"] == rules.projection_delta(panel, control), where,
                f"{base['base_key']} {end}: shipped delta {base[f'{end}_delta']!r}, "
                f"panel_mean - control_mean = {rules.projection_delta(panel, control)!r}")
    else:
        f.check("endpoint_delta_is_the_masked_panel_minus_control_projection",
                base[f"{end}_delta"] is None, where,
                f"{base['base_key']} {end}: status {status!r} but a delta was shipped")

    rederived = rules.projection_status(base[f"{end}_n_panel_surviving"],
                                        base[f"{end}_n_control_surviving"],
                                        mask_resolved=bool(base[f"{end}_mask_resolved"]))
    f.check("projection_status_rederives_from_the_surviving_counts",
            status == rederived, where,
            f"{base['base_key']} {end}: shipped {status!r}, re-derived {rederived!r} from "
            f"panel={base[f'{end}_n_panel_surviving']!r} "
            f"control={base[f'{end}_n_control_surviving']!r}")

    state, evaluable, reasons = rules.arm_state(
        base_state=str(base[f"{end}_base_qc_state"]),
        base_passed=bool(base[f"{end}_base_qc_passed"]),
        projection_status=str(status))
    f.check("endpoint_evaluability_rederives_from_base_qc_and_projection",
            (base[f"{end}_state"], base[f"{end}_evaluable"], base[f"{end}_reasons"])
            == (state, evaluable, ";".join(reasons)), where,
            f"{base['base_key']} {end}: shipped ({base[f'{end}_state']!r}, "
            f"{base[f'{end}_evaluable']!r}), re-derived ({state!r}, {evaluable!r})")


def _identity_of(f: Failures, base: dict[str, Any], where: str,
                 from_direct: bool = False) -> None:
    """THE STABLE TARGET IDENTITY a downstream stage joins on. Normalized, in ONE place.

    Stage 3 needs to know WHICH gene an arm is about, not merely which rank it got. The
    identity is carried ONCE, on the base record, and the arm records carry only
    ``target_id`` + ``base_key`` and join to it — so there is exactly one statement of a
    target's identity per bundle and it cannot drift between the two arms of a program.
    (The arm-record allowlist is what keeps it that way: an arm record that grew its own
    ``target_symbol`` would be a second, unreconcilable identity.)

    A symbol is NOT an identity: symbols are ambiguous and get renamed. The stable id and
    its NAMESPACE are required; the symbol and the Ensembl id are carried as evidence.
    """
    # With a Direct endpoint source the per-endpoint identity provenance lives in the DIRECT
    # bundle, which the release binds by id, sha and W10 admission. The stable target_id is
    # still required here — it is what every join runs on.
    f.check("base_record_carries_a_stable_namespaced_target_identity",
            bool(str(base.get("target_id") or "").strip())
            and (from_direct
                 or bool(str(base.get("target_id_namespace") or "").strip())), where,
            f"{base.get('base_key')!r}: a target_id without a namespace is not a stable "
            "identity, and a downstream join on a bare symbol is a lossy join")
    f.check("every_base_record_declares_the_crispri_knockdown_modality",
            base.get("perturbation_modality") == rules.PERTURBATION_MODALITY, where,
            f"{base.get('base_key')!r}: shipped "
            f"{base.get('perturbation_modality')!r}. Stage 3 reads the modulation "
            "orientation off the record it joins to, so the modality must travel with it")
    for end in _ENDS:
        if base[f"{end}_present"] and not from_direct:
            f.check("a_present_endpoint_binds_the_released_estimate_it_projected",
                    bool(base[f"{end}_released_estimate_id"]), where,
                    f"{base['base_key']} {end}: the endpoint claims an estimate but does "
                    "not say WHICH released estimate it projected")


def _arithmetic(f: Failures, doc: dict[str, Any], where: str, bound) -> dict[str, int]:
    """The base records, then the arms. Every number re-derived from the shipped bytes."""
    counts = {"base_deltas": 0, "arm_values": 0}
    from_direct = ((doc.get("endpoint_source") or {}).get("endpoint_source")
                   == direct_source.ENDPOINT_SOURCE_REQUIRED)

    by_base: dict[str, dict[str, Any]] = {}
    seen_bases: dict[str, int] = {}
    for base in doc["base_records"]:
        seen_bases[base["base_key"]] = seen_bases.get(base["base_key"], 0) + 1
        by_base[base["base_key"]] = base
        # A malformed id must be REFUSED, not raised on: a verifier that throws on hostile
        # input has not refused it — it has crashed, and a crash is not a verdict.
        try:
            rederived = rules.base_key(base["program_id"], base["target_id"])
        except rules.RuleViolation as exc:
            rederived = None
            f.check("base_key_rederives_from_its_program_and_target", False, where,
                    str(exc))
        if rederived is not None:
            f.check("base_key_rederives_from_its_program_and_target",
                    base["base_key"] == rederived, where, base["base_key"])
        _identity_of(f, base, where, from_direct)
        for end in _ENDS:
            _endpoint(f, base, end, where, from_direct)

        status = rules.temporal_status(
            from_present=bool(base["from_present"]), to_present=bool(base["to_present"]),
            from_evaluable=bool(base["from_evaluable"]),
            to_evaluable=bool(base["to_evaluable"]))
        f.check("temporal_status_rederives_from_presence_and_evaluability",
                base["temporal_status"] == status, where,
                f"{base['base_key']}: shipped {base['temporal_status']!r}, re-derived "
                f"{status!r}")

        # A value that EXISTS but is not evaluable is NOT differenced: the within-condition
        # lane declined to score that program there, and differencing a declined score would
        # smuggle it back in under a new name.
        want = (rules.base_temporal_delta(base["from_delta"], base["to_delta"])
                if status == rules.ESTIMATED else None)
        f.check("base_delta_is_the_difference_in_differences",
                base["base_delta"] == want, where,
                f"{base['base_key']}: shipped base_delta {base['base_delta']!r}, "
                f"to_delta - from_delta = {want!r} (status {status!r})")
        f.check("base_evaluable_follows_the_temporal_status",
                base["evaluable"] == (status == rules.ESTIMATED and want is not None),
                where, base["base_key"])
        counts["base_deltas"] += 1

    dup_bases = sorted(k for k, n in seen_bases.items() if n > 1)
    f.check("each_base_key_resolves_to_exactly_one_base_record", not dup_bases, where,
            f"duplicated: {dup_bases}. A duplicate base record silently decides which "
            "estimate an arm differenced, and the join stops being a function")

    # A malformed target id is refused above; it may not then crash the inventory check.
    targets = sorted({str(b["target_id"]) for b in doc["base_records"]
                      if b.get("target_id")})
    expected_bases = {rules.base_key(p, t) for p in bound.admitted_programs
                      for t in targets}
    f.check("a_base_record_exists_for_every_admitted_program_and_target",
            set(by_base) == expected_bases, where,
            f"missing={sorted(expected_bases - set(by_base))} "
            f"unexpected={sorted(set(by_base) - expected_bases)}")

    seen: dict[str, int] = {}
    for arm in doc["arms"]:
        seen[arm["arm_key"]] = seen.get(arm["arm_key"], 0) + 1
        counts["arm_values"] += _arm(f, arm, doc, by_base, where, targets)

    dupes = sorted(k for k, n in seen.items() if n > 1)
    f.check("each_arm_key_appears_exactly_once_in_its_bundle", not dupes, where,
            f"duplicated: {dupes}. A reusable arm has exactly one home, and two would be "
            "two chances to disagree")

    expected = rules.expected_arm_keys(bound.admitted_programs, doc["from_condition"],
                                       doc["to_condition"])
    got = set(seen)
    f.check("arm_inventory_is_every_program_x_every_desired_change", got == expected,
            where, f"missing={sorted(expected - got)} unexpected={sorted(got - expected)}")
    f.check("n_arms_is_n_programs_x_n_desired_changes",
            doc["n_arms"] == len(doc["arms"])
            == len(bound.admitted_programs) * len(rules.DESIRED_CHANGES), where,
            f"n_arms={doc['n_arms']}")
    f.check("the_arm_keys_index_matches_the_arms_it_indexes",
            list(doc["arm_keys"]) == sorted(a["arm_key"] for a in doc["arms"]), where, "")
    f.check("the_declared_counts_match_the_records",
            doc["n_base_records"] == len(doc["base_records"])
            and doc["n_targets"] == len(targets)
            and doc["n_desired_changes"] == len(rules.DESIRED_CHANGES), where,
            f"n_base_records={doc['n_base_records']} n_targets={doc['n_targets']}")
    return counts


def _arm(f: Failures, arm: dict[str, Any], doc: dict[str, Any],
         by_base: dict[str, dict[str, Any]], where: str, targets: list[str]) -> int:
    """ONE arm: its key, its sign-transformed values, its OWN independently-derived rank."""
    key = arm["arm_key"]
    try:
        change = rules.validated_change(arm["desired_change"])
    except rules.RuleViolation as exc:
        f.check("desired_change_is_a_real_desired_change_not_a_pole_or_a_role", False,
                key, str(exc))
        return 0

    # RETAINED ROWS. Every target the bundle knows about stays in every arm, and an
    # unrankable one carries a NULL rank rather than vanishing. A dropped row is
    # indistinguishable from a target that was never asked about, and a consumer counting
    # what it got back would silently be counting a different denominator.
    got_targets = [r["target_id"] for r in arm["records"]]
    f.check("every_arm_retains_a_row_for_every_target_in_the_bundle",
            sorted(got_targets) == list(targets), key,
            f"missing={sorted(set(targets) - set(got_targets))} "
            f"unexpected={sorted(set(got_targets) - set(targets))}; a row is retained with "
            "a null rank when it is not rankable, never dropped")

    f.check("arm_key_rederives_from_its_own_parts",
            key == rules.arm_key(arm["program_id"], change, arm["from_condition"],
                                 arm["to_condition"]), key,
            "a relabelled key serves the values of one arm under the name of another")
    f.check("arm_is_scoped_to_the_bundles_ordered_pair",
            (arm["from_condition"], arm["to_condition"])
            == (doc["from_condition"], doc["to_condition"]), key,
            "the reverse pair is a DIFFERENT bundle whose every value is negated")

    sign_ok = True
    for rec in arm["records"]:
        base = by_base.get(rec["base_key"])
        if base is None:
            f.check("every_arm_record_points_at_a_real_base_record", False, key,
                    rec["base_key"])
            continue
        # REFERENTIAL INTEGRITY, both ways. The base_key must resolve, AND the record it
        # resolves to must be about the SAME target and the SAME program — a join that
        # resolves to the wrong row is worse than one that fails to resolve, because it
        # returns a number.
        f.check("the_arm_to_base_join_resolves_to_the_same_target_and_program",
                base["target_id"] == rec["target_id"]
                and base["program_id"] == arm["program_id"]
                and rec["base_key"] == rules.base_key(arm["program_id"],
                                                      rec["target_id"]), key,
                f"{rec['target_id']}: joins to base {base['base_key']!r} "
                f"(program {base['program_id']!r}, target {base['target_id']!r})")
        want = rules.arm_value(base["base_delta"], change)
        sign_ok &= f.check("arm_value_is_the_sign_transform_of_the_base_delta",
                           rec["arm_value"] == want, key,
                           f"{rec['target_id']}: shipped {rec['arm_value']!r}, "
                           f"SIGN[{change}] * {base['base_delta']!r} = {want!r}")
        f.check("arm_evaluability_is_the_bases_evaluability",
                rec["evaluable"] == base["evaluable"], key,
                f"{rec['target_id']}: the two arms of a program share the estimate they "
                "are a sign transform of, so they share its evaluability")
        f.check("arm_record_carries_the_bases_temporal_status",
                rec["temporal_status"] == base["temporal_status"], key, rec["target_id"])

        # THE ORIENTATION Stage 3 acts on, re-derived from the value it is about — so it
        # can never be asserted out of step with the number beside it.
        want_mod = rules.target_modulation(rec["arm_value"],
                                           evaluable=bool(rec["evaluable"]))
        f.check("desired_target_modulation_rederives_from_the_arm_value_and_evaluability",
                rec["desired_target_modulation"] == want_mod, key,
                f"{rec['target_id']}: shipped {rec['desired_target_modulation']!r}, "
                f"re-derived {want_mod!r} from arm_value={rec['arm_value']!r} "
                f"evaluable={rec['evaluable']!r}")

    _ranks(f, arm, key)
    return len(arm["records"])


def _ranks(f: Failures, arm: dict[str, Any], key: str) -> None:
    """Re-derive this arm's ranks from its OWN shipped values, by the frozen rule."""
    want = rules.rank_population(arm["records"])
    for rec in arm["records"]:
        expected: Optional[int] = want.get(rec["target_id"])
        f.check("rank_rederives_by_the_frozen_rule", rec["rank"] == expected, key,
                f"{rec['target_id']}: shipped rank {rec['rank']!r}, re-derived {expected!r}")
    f.check("n_ranked_and_n_evaluable_are_the_ranked_population",
            arm["n_ranked"] == len(want)
            and arm["n_evaluable"] == sum(1 for r in arm["records"] if r["evaluable"])
            and arm["n_targets"] == len(arm["records"]), key,
            f"n_ranked={arm['n_ranked']} n_evaluable={arm['n_evaluable']} "
            f"ranked={len(want)}")
