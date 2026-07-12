"""run_id binds the science, and nothing but the science."""
import json
import os

from direct import runid
from direct import selection as sel_mod
from direct.trust import FixtureRelease

_INPUTS = [{"name": "de.h5ad", "sha256": "a" * 64, "size_bytes": 10},
           {"name": "lib.csv", "sha256": "b" * 64, "size_bytes": 20}]
_SUPPORT_CONTRACT = {"contract_id": "spot.stage02.direct.support_contract."
                                    "unavailable.v1",
                     "state": "support_unavailable",
                     "guide_support_available": False,
                     "donor_support_available": False,
                     "support_may_elevate_evidence_tier": False}
_GUIDE_MANIFEST = {"status": "bound", "manifest_sha256": "d" * 64,
                   "identity_method": "released_per_guide_identity_column"}
_EVIDENCE_DOMAIN = {"domain_id": "spot.stage02.direct.evidence_domain."
                                 "pooled_main_all_condition.v1",
                    "rule_id": "spot.stage02.direct.domain_rule."
                               "pooled_main_exact_scope_match.v1",
                    "n_global_pooled_main_scopes": 33983}
_RELEASE_GATE = {"gate_id": "spot.stage02.direct.release_gate.v2",
                 "lane": "synthetic", "strict_replay_required": False,
                 "state": "not_required_fixture_lane", "strict_replay_ran": False}
_RELEASE = FixtureRelease(
    kind="fixture", method_version="stage1-continuous-v3.0.1", programs={},
    hashes={"registry_canonical_sha256": "r" * 64}, selectable_pairs=frozenset(),
    gate_evidence={"n_production_selectable": 0, "n_pairs_evaluated": 2})


def _selection(**over):
    contract = {
        "schema_version": "spot.stage01_selection_contract.v1",
        "lane": "synthetic",
        "A": {"program_id": "program_a", "direction": "high"},
        "B": {"program_id": "program_b", "direction": "high"},
        "analysis_condition": "StimX",
        "hashes": {"registry_sha256": "r" * 64,
                   "method_version": "stage1-continuous-v3.0.1",
                   "input_manifest_sha256": "m" * 64, "code_sha256": "c" * 64},
    }
    contract.update(over)
    from fixtures_direct import derived_ids
    contract["ids"] = derived_ids(contract)
    return sel_mod.parse_selection(contract, contract_sha256="f" * 64)


def _binding(**over):
    kw = dict(selection=_selection(), lane="synthetic", stage1_release=_RELEASE,
              stage2_inputs=_INPUTS,
              guide_manifest=_GUIDE_MANIFEST, mask_sha256="m" * 64,
              gene_universe_sha256="u" * 64, code_tree="t" * 64,
              env_lock={"name": "base.lock", "sha256": "e" * 64, "status": "locked"},
              support_contract=_SUPPORT_CONTRACT,
              evidence_domain=_EVIDENCE_DOMAIN, release_gate=_RELEASE_GATE)
    kw.update(over)
    return runid.build_run_binding(**kw)


def _rid(**over):
    return runid.run_id_of(_binding(**over))[0]


BASE = _rid()


def test_run_id_is_deterministic():
    assert _rid() == BASE
    assert len(BASE) == runid.RUN_ID_LEN


def test_a_different_stage2_input_changes_run_id():
    other = [dict(_INPUTS[0], sha256="9" * 64), _INPUTS[1]]
    assert _rid(stage2_inputs=other) != BASE


def test_a_different_mask_changes_run_id():
    assert _rid(mask_sha256="0" * 64) != BASE


def test_a_different_gene_universe_changes_run_id():
    assert _rid(gene_universe_sha256="0" * 64) != BASE


def test_a_different_lane_changes_run_id():
    assert _rid(lane="production") != BASE


def test_both_arm_definitions_are_bound_into_run_id(monkeypatch):
    from direct import config
    binding = _binding()
    method = binding["stage2_method"]
    assert method["arms"] == list(config.ARMS)
    assert method["arm_formula"] == dict(config.ARM_FORMULA)
    assert method["arm_rank_column"] == dict(config.ARM_RANK_COLUMN)
    assert method["combined_objective_permitted"] is False

    # changing EITHER arm's formula changes the run
    monkeypatch.setattr(config, "ARM_FORMULA",
                        dict(config.ARM_FORMULA, toward_B="sign_B * delta_B * 2"))
    assert _rid() != BASE


def test_both_pole_definitions_are_bound_into_run_id():
    flipped = _selection(B={"program_id": "program_b", "direction": "low"})
    assert _rid(selection=flipped) != BASE
    other_condition = _selection(analysis_condition="StimY")
    assert _rid(selection=other_condition) != BASE


def test_a_different_guide_manifest_changes_run_id():
    manifest = dict(_GUIDE_MANIFEST, source="manifest", sha256="7" * 64)
    assert _rid(guide_manifest=manifest) != BASE


def test_a_different_code_tree_changes_run_id():
    assert _rid(code_tree="0" * 64) != BASE


def test_a_different_environment_lock_changes_run_id():
    assert _rid(env_lock={"name": "base.lock", "sha256": "0" * 64,
                          "status": "locked"}) != BASE


def test_a_different_selection_changes_run_id():
    other = _selection(analysis_condition="StimZ")
    assert _rid(selection=other) != BASE


def test_the_stage1_release_binding_enters_run_id():
    other = FixtureRelease(
        kind="fixture", method_version="stage1-continuous-v3.0.1", programs={},
        hashes={"registry_canonical_sha256": "9" * 64},
        selectable_pairs=frozenset(), gate_evidence={})
    assert _rid(stage1_release=other) != BASE


def test_a_different_stage1_registry_changes_run_id():
    other = _selection(hashes={"registry_sha256": "9" * 64,
                               "method_version": "stage1-continuous-v3.0.1",
                               "input_manifest_sha256": "m" * 64,
                               "code_sha256": "c" * 64})
    assert _rid(selection=other) != BASE


def test_binding_the_pending_stage1_validation_hash_changes_run_id():
    """Today it is null. Filling it later must produce a different run."""
    binding = _binding()
    assert binding["stage1"]["validation_sha256"] is None
    other = _selection(hashes={"registry_sha256": "r" * 64,
                               "method_version": "stage1-continuous-v3.0.1",
                               "input_manifest_sha256": "m" * 64,
                               "code_sha256": "c" * 64,
                               "validation_sha256": "v" * 64})
    assert _rid(selection=other) != BASE


def test_a_different_eligibility_policy_changes_run_id(monkeypatch):
    from direct import config
    policy = dict(config.ELIGIBILITY_POLICY, n_cells_min=999)
    monkeypatch.setattr(config, "ELIGIBILITY_POLICY", policy)
    assert _rid() != BASE


def test_a_different_stage2_method_version_changes_run_id(monkeypatch):
    from direct import config
    monkeypatch.setattr(config, "METHOD_VERSION", "stage2-direct-v99")
    assert _rid() != BASE


def test_run_binding_carries_no_timestamp_or_display_label():
    blob = json.dumps(_binding(), sort_keys=True).lower()
    for banned in ("generated_at", "created_at", "timestamp", "display_label",
                   "/home/"):
        assert banned not in blob


def test_code_tree_hash_is_deterministic_and_content_addressed(tmp_path):
    d = str(tmp_path)
    with open(os.path.join(d, "a.py"), "w") as fh:
        fh.write("x = 1\n")
    first = runid.code_tree_sha256(d)
    assert first == runid.code_tree_sha256(d)
    with open(os.path.join(d, "a.py"), "w") as fh:
        fh.write("x = 2\n")
    assert runid.code_tree_sha256(d) != first


def test_missing_environment_lock_is_declared_not_faked():
    block = runid.env_lock_block(None)
    assert block["sha256"] is None
    assert block["status"] == "environment_lock_not_supplied"


# --------------------------------------------------------------------------- #
# What a run STOOD ON is part of what the run IS.
#
# Each of these claims can be weakened without touching a single score, and each
# would then be a different scientific result wearing the same name. So each moves
# run_id, and a verifier can therefore refuse a run whose emitted claim is not the
# one its id hashed.
# --------------------------------------------------------------------------- #
def test_the_evidence_domain_is_bound_into_run_id():
    other = dict(_EVIDENCE_DOMAIN, domain_id="spot.stage02.direct.evidence_domain.v0")
    assert _rid(evidence_domain=other) != BASE


def test_the_domain_rule_id_is_bound_into_run_id():
    """A run may not keep its id while its manifest is matched by a different rule."""
    other = dict(_EVIDENCE_DOMAIN, rule_id="spot.stage02.direct.domain_rule.lax.v0")
    assert _rid(evidence_domain=other) != BASE


def test_a_smaller_global_scope_universe_changes_run_id():
    """One scope fewer is a DROPPED scope — invisible to every per-row check."""
    other = dict(_EVIDENCE_DOMAIN, n_global_pooled_main_scopes=33982)
    assert _rid(evidence_domain=other) != BASE


def test_the_release_gate_is_bound_into_run_id():
    """A run that was never gated is not the run that replayed the raw source.

    What proved the gate is part of what the run IS: an unbound gate could be swapped
    afterwards for a friendlier one and the run would still answer to its name.
    """
    gated = dict(_RELEASE_GATE, lane="production", strict_replay_required=True,
                 state="fresh_strict_replay", strict_replay_ran=True)
    assert _rid(release_gate=gated) != BASE


def test_a_run_that_did_not_run_its_strict_replay_is_a_DIFFERENT_run():
    """The gate STATE is hashed, so 'it ran' and 'it did not' cannot share an id."""
    ran = dict(_RELEASE_GATE, lane="production", strict_replay_required=True,
               state="fresh_strict_replay", strict_replay_ran=True)
    did_not = dict(ran, strict_replay_ran=False)
    assert _rid(release_gate=ran) != _rid(release_gate=did_not)


def test_the_replay_and_completeness_rule_ids_are_bound_into_run_id():
    """The v2 report is only interpretable under the rule that produced it."""
    bound = dict(_GUIDE_MANIFEST, source_replay={
        "replay_rule_id": "spot.stage02.direct.replay_rule.v2",
        "completeness_rule_id": "spot.stage02.direct.completeness_rule.v2",
        "completeness_verdict": "complete"})
    weaker = dict(_GUIDE_MANIFEST, source_replay={
        "replay_rule_id": "spot.stage02.direct.replay_rule.v1",
        "completeness_rule_id": "spot.stage02.direct.completeness_rule.v1",
        "completeness_verdict": "complete"})
    assert _rid(guide_manifest=bound) != _rid(guide_manifest=weaker)
