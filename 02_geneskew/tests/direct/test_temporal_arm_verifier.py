"""THE INDEPENDENT VERIFIER, and the attacks it has to survive.

Every attack below is RESEALED: the tampered bundle's id is recomputed over its own new
content, the verification file's raw and canonical hashes are recomputed over the tampered
bytes, the PRODUCER'S OWN report is rewritten to say ADMITTED, and the release inventory is
rebuilt around it. Every hash agrees. The producer says it is fine. Only the SCIENCE is
wrong — and that is the only interesting kind of attack, because an attack a hash check
would have caught proves nothing about a scientific verifier.

The honest control (``TestTheHonestReleaseIsAdmitted``) is what keeps the rest meaningful:
a verifier that refused everything would pass every mutation test and be worthless.
"""
from __future__ import annotations

import json
import os
import re
import sys

_ANALYSIS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..",
                                         "analysis"))
if _ANALYSIS not in sys.path:
    sys.path.insert(0, _ANALYSIS)
if os.path.dirname(os.path.abspath(__file__)) not in sys.path:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fixtures_arm_verifier as FX  # noqa: E402
from verify_temporal_arms import canonical, schema, verify  # noqa: E402

PAIR = (FX.CONDITIONS[0], FX.CONDITIONS[2])          # one ordered pair, used by the attacks
REVERSE = (FX.CONDITIONS[2], FX.CONDITIONS[0])


_REPO = os.path.abspath(os.path.join(_ANALYSIS, "..", ".."))


def _verify(release_root, bundle_root, **kw):
    root = os.path.dirname(os.path.dirname(os.path.abspath(str(bundle_root))))
    ctx = _CTX.get(root) or _CTX.get(str(os.path.dirname(os.path.abspath(str(bundle_root)))))
    if ctx:
        direct, w10, lock = ctx
        kw.setdefault("direct_bundles", direct)
        kw.setdefault("w10_reports", w10)
        kw.setdefault("env_lock", lock)
    """The producer here runs from THIS working tree, which is dirty by construction while
    this lane is under development. The FINAL clean-tree decision is not waived — it is
    proved in ``test_temporal_arm_crossworktree``, against the producer's committed,
    clean checkout, where it is not optional."""
    kw.setdefault("producer_checkout", _REPO)
    kw.setdefault("require_clean_checkout", False)
    return verify.verify_release(release_root=release_root, bundle_root=bundle_root, **kw)


def _staged(tmp_path):
    """The complete PRODUCTION shape: admitted Direct bundles + W10 admissions, the
    authoritative solver lock, and the temporal release built from all of them."""
    rr, br, direct, w10, lock = FX.stage_full(tmp_path)
    _CTX[str(tmp_path)] = (direct, w10, lock)
    return rr, br, lock


_CTX: dict = {}


def run(tmp_path, **kw):
    release_root, bundle_root, _ = _staged(tmp_path)
    return _verify(release_root, bundle_root, **kw)


def attack(tmp_path, mutate, pair=PAIR):
    """Stage an honest release, mutate ONE bundle, reseal everything, and verify."""
    release_root, bundle_root, _ = _staged(tmp_path)
    FX.reseal(release_root, bundle_root, pair[0], pair[1], mutate)
    return _verify(release_root, bundle_root)


def gates(report) -> set[str]:
    return {f["gate"] for f in report["failures"]}


# --------------------------------------------------------------------------- #
# RESEALED NULL / MUTATION ATTACKS on the Stage-1 and Stage-2 bindings.
# --------------------------------------------------------------------------- #
class TestTheBindingsCannotBeNulledOrMutated:
    def _reseal_inventory_with(self, release_root, bundle_root, mutate):  # noqa: D102
        ipath = os.path.join(bundle_root, schema.INVENTORY_FILENAME)
        with open(ipath) as fh:
            inv = json.load(fh)
        mutate(inv)
        inv.pop("release_id", None)
        inv["release_id"] = canonical.content_hash(inv)
        with open(ipath, "wb") as fh:
            fh.write(canonical.canonical_json(inv).encode("utf-8"))

    def test_a_nulled_stage1_binding_is_refused_though_the_inventory_reseals(self, tmp_path):
        release_root, bundle_root, lock = _staged(tmp_path)
        self._reseal_inventory_with(
            release_root, bundle_root,
            lambda inv: inv["stage1_binding"].update(
                {"registry_scorer_projection_sha256": None,
                 "release_self_sha256": None}))
        report = _verify(release_root, bundle_root, env_lock=lock)
        assert report["verdict"] == verify.REJECT
        assert "no_stage1_binding_is_null" in gates(report)

    def test_a_mutated_scorer_view_binding_is_refused(self, tmp_path):
        release_root, bundle_root, lock = _staged(tmp_path)
        self._reseal_inventory_with(
            release_root, bundle_root,
            lambda inv: inv["stage1_binding"].update(
                {"registry_scorer_view_sha256": "b" * 64}))
        report = _verify(release_root, bundle_root)
        assert report["verdict"] == verify.REJECT
        assert "the_stage1_scorer_view_binding_is_the_bound_releases" in gates(report)

    def test_a_reordered_selector_sequence_is_refused(self, tmp_path):
        """The order IS the time axis. A resealed reordering is a different claim about
        which way time runs."""
        release_root, bundle_root, lock = _staged(tmp_path)
        self._reseal_inventory_with(
            release_root, bundle_root,
            lambda inv: inv["stage1_binding"].update(
                {"selector_condition_sequence":
                 list(reversed(inv["stage1_binding"]["selector_condition_sequence"]))}))
        report = _verify(release_root, bundle_root)
        assert report["verdict"] == verify.REJECT
        assert "the_selector_condition_SEQUENCE_is_the_releases_own_order" in gates(report)

    def test_a_mutated_per_program_projection_identity_is_refused(self, tmp_path):
        release_root, bundle_root, lock = _staged(tmp_path)
        self._reseal_inventory_with(
            release_root, bundle_root,
            lambda inv: inv["stage1_binding"].update(
                {"registry_scorer_projection_sha256": "c" * 64}))
        report = _verify(release_root, bundle_root)
        assert report["verdict"] == verify.REJECT
        assert "the_scalar_scorer_projection_identity_rederives" in gates(report)

    def test_a_mutated_per_program_projection_MAP_entry_is_refused(self, tmp_path):
        """The map is what says WHICH program moved. One wrong hash in it is one program
        whose axis nobody can vouch for."""
        release_root, bundle_root, lock = _staged(tmp_path)
        self._reseal_inventory_with(
            release_root, bundle_root,
            lambda inv: inv["stage1_binding"]["per_program_projection_sha256"].update(
                {FX.PORTABLE_IDS[4]: "d" * 64}))
        report = _verify(release_root, bundle_root)
        assert report["verdict"] == verify.REJECT
        assert "every_per_program_projection_hash_rederives" in gates(report)

    def test_a_map_that_declares_no_rule_is_refused(self, tmp_path):
        """Two readers computing two different "correct" maps would both be right and would
        still disagree. The artifact must say which rule it used."""
        release_root, bundle_root, lock = _staged(tmp_path)
        self._reseal_inventory_with(
            release_root, bundle_root,
            lambda inv: inv["stage1_binding"].update(
                {"per_program_projection_rule_id": None}))
        report = _verify(release_root, bundle_root, env_lock=lock)
        assert report["verdict"] == verify.REJECT
        assert "no_stage1_binding_is_null" in gates(report)

    def test_a_map_that_declares_the_WRONG_rule_is_refused(self, tmp_path):
        release_root, bundle_root, lock = _staged(tmp_path)
        self._reseal_inventory_with(
            release_root, bundle_root,
            lambda inv: inv["stage1_binding"].update(
                {"per_program_projection_rule_id": "spot.some.other.rule.v1"}))
        report = _verify(release_root, bundle_root, env_lock=lock)
        assert report["verdict"] == verify.REJECT
        assert "the_per_program_map_declares_the_canonical_stage1_record_rule" in \
            gates(report)

    def test_the_declared_rule_is_the_frozen_stage1_record_rule(self, tmp_path):
        _, bundle_root, _ = _staged(tmp_path)
        with open(os.path.join(bundle_root, schema.INVENTORY_FILENAME)) as fh:
            sb = json.load(fh)["stage1_binding"]
        assert sb["per_program_projection_rule_id"] == \
            "spot.stage01_stage2_registry_view.program_record.canonical_sha256.v1"

    def test_a_SELF_CONSISTENT_WRONG_four_field_map_is_refused(self, tmp_path):
        """The map is internally perfect: ten entries, one per admitted program, each a real
        sha256 the producer computed by a real rule. It is just the WRONG rule — the retired
        four-field summary instead of the whole Stage-1 record. Nothing about the map's
        SHAPE gives it away; only re-deriving it from the authoritative view does."""
        release_root, bundle_root, _ = _staged(tmp_path)
        with open(os.path.join(release_root, "scorer_view.json")) as fh:
            view = json.load(fh)

        def four_field(rec):
            return canonical.content_hash({
                "program_id": rec["program_id"],
                "base_portable": rec["base_portable"],
                "panel_ensembl": sorted(rec["panel_ensembl"]),
                "control_ensembl": sorted(rec["control_ensembl"]),
            })

        wrong = {p["program_id"]: four_field(p) for p in view["programs"]
                 if p["base_portable"]}
        assert len(wrong) == 10
        self._reseal_inventory_with(
            release_root, bundle_root,
            lambda inv: inv["stage1_binding"].update(
                {"per_program_projection_sha256": wrong}))
        report = _verify(release_root, bundle_root)
        assert report["verdict"] == verify.REJECT
        assert "every_per_program_projection_hash_rederives" in gates(report)

    def test_a_NON_PORTABLE_program_in_the_map_is_refused(self, tmp_path):
        """The map is keyed on exactly the base-portable programs. An eleventh key vouches
        for a program the base topology excluded."""
        release_root, bundle_root, lock = _staged(tmp_path)
        self._reseal_inventory_with(
            release_root, bundle_root,
            lambda inv: inv["stage1_binding"]["per_program_projection_sha256"].update(
                {FX.NON_PORTABLE_ID: "e" * 64}))
        report = _verify(release_root, bundle_root)
        assert report["verdict"] == verify.REJECT
        assert "the_per_program_projection_map_is_keyed_by_the_admitted_programs" in \
            gates(report)

    def test_a_per_program_projection_map_missing_a_program_is_refused(self, tmp_path):
        release_root, bundle_root, lock = _staged(tmp_path)
        self._reseal_inventory_with(
            release_root, bundle_root,
            lambda inv: inv["stage1_binding"]["per_program_projection_sha256"].pop(
                FX.PORTABLE_IDS[0]))
        report = _verify(release_root, bundle_root)
        assert report["verdict"] == verify.REJECT
        assert "the_per_program_projection_map_is_keyed_by_the_admitted_programs" in \
            gates(report)

    def _reseal_prov(self, release_root, bundle_root, mutate):
        d = FX.pair_dir(bundle_root, *PAIR)
        ppath = os.path.join(d, schema.PROVENANCE_FILENAME)
        with open(ppath) as fh:
            prov = json.load(fh)
        mutate(prov)
        with open(ppath, "wb") as fh:
            fh.write(canonical.canonical_json(prov).encode("utf-8"))
        FX.reseal_inventory(release_root, bundle_root)

    def test_a_missing_stage2_inputs_object_is_refused(self, tmp_path):
        release_root, bundle_root, _ = _staged(tmp_path)
        self._reseal_prov(release_root, bundle_root,
                          lambda p: p["run_binding"].pop("stage2_inputs"))
        report = _verify(release_root, bundle_root)
        assert report["verdict"] == verify.REJECT
        assert "provenance_carries_a_canonical_fixed_key_stage2_inputs_object" in \
            gates(report)

    def test_a_nulled_stage2_input_is_refused(self, tmp_path):
        release_root, bundle_root, _ = _staged(tmp_path)
        self._reseal_prov(
            release_root, bundle_root,
            lambda p: p["run_binding"]["stage2_inputs"].update(
                {"effect_source_sha256": None}))
        report = _verify(release_root, bundle_root)
        assert report["verdict"] == verify.REJECT
        assert "no_stage2_input_is_null" in gates(report)

    def test_a_stage2_input_that_drifts_from_the_bundles_method_is_refused(self, tmp_path):
        release_root, bundle_root, _ = _staged(tmp_path)
        self._reseal_prov(
            release_root, bundle_root,
            lambda p: p["run_binding"]["stage2_inputs"].update(
                {"effect_source_sha256": "9" * 64}))
        report = _verify(release_root, bundle_root)
        assert report["verdict"] == verify.REJECT
        assert "the_stage2_inputs_are_the_method_the_bundle_declares" in gates(report)

    def test_a_role_list_smuggled_back_into_run_binding_is_refused(self, tmp_path):
        """The regression this contract exists to prevent."""
        release_root, bundle_root, _ = _staged(tmp_path)
        self._reseal_prov(
            release_root, bundle_root,
            lambda p: p["run_binding"].update(
                {"stage2_inputs": [{"role": "effect_source_sha256", "value": "x"}]}))
        report = _verify(release_root, bundle_root)
        assert report["verdict"] == verify.REJECT
        assert "provenance_carries_a_canonical_fixed_key_stage2_inputs_object" in \
            gates(report)


# --------------------------------------------------------------------------- #
# THE ENDPOINTS ARE TWO ADMITTED DIRECT BUNDLES — and this is what happens when they
# are not.
# --------------------------------------------------------------------------- #
class TestTheDirectEndpointSource:
    def test_the_release_is_re_differenced_from_the_admitted_direct_bundles(self, tmp_path):
        report = run(tmp_path)
        assert report["verdict"] == verify.ADMIT, report["failures"]
        assert "every_temporal_base_delta_recomputes_from_the_admitted_direct_bundles" in \
            report["gates_run"]

    def test_a_verifier_given_no_direct_bundles_refuses(self, tmp_path):
        """An endpoint nobody re-read is an endpoint nobody verified."""
        release_root, bundle_root, lock = _staged(tmp_path)
        report = verify.verify_release(
            release_root=release_root, bundle_root=bundle_root, producer_checkout=_REPO,
            require_clean_checkout=False, env_lock=lock)
        assert report["verdict"] == verify.REJECT
        assert "the_admitted_direct_bundles_were_supplied_to_the_verifier" in gates(report)

    def test_a_MISSING_condition_direct_bundle_is_refused(self, tmp_path):
        release_root, bundle_root, _ = _staged(tmp_path)
        direct, w10, lock = _CTX[str(tmp_path)]
        short = {c: p for c, p in direct.items() if c != FX.CONDITIONS[1]}
        report = _verify(release_root, bundle_root, direct_bundles=short)
        assert report["verdict"] == verify.REJECT
        assert "every_released_condition_has_an_admitted_direct_bundle" in gates(report)

    def test_a_SWAPPED_condition_direct_bundle_is_refused(self, tmp_path):
        """A swapped endpoint differences the wrong two populations, and every number that
        comes out looks entirely reasonable."""
        release_root, bundle_root, _ = _staged(tmp_path)
        direct, w10, lock = _CTX[str(tmp_path)]
        swapped = dict(direct)
        swapped[FX.CONDITIONS[0]] = direct[FX.CONDITIONS[1]]
        report = _verify(release_root, bundle_root, direct_bundles=swapped)
        assert report["verdict"] == verify.REJECT
        assert "the_direct_bundle_is_the_condition_the_endpoint_asked_for" in gates(report)

    def test_a_STALE_direct_bundle_is_refused(self, tmp_path):
        """A stale bundle admits a run against numbers that were superseded."""
        release_root, bundle_root, _ = _staged(tmp_path)
        direct, _, _ = _CTX[str(tmp_path)]
        path = os.path.join(direct[FX.CONDITIONS[0]], "arm_bundle.json")
        with open(path) as fh:
            doc = json.load(fh)
        doc["n_arm_rows"] = 999                      # the bundle moved on
        with open(path, "w") as fh:
            json.dump(doc, fh)
        report = _verify(release_root, bundle_root)
        assert report["verdict"] == verify.REJECT
        assert "the_direct_bundle_is_the_one_the_temporal_release_bound" in gates(report)

    def test_a_FIXTURE_effect_source_may_not_stand_in_for_a_direct_bundle(self, tmp_path):
        """A fixture that CAN stand in for a measurement is a fixture that eventually will."""
        release_root, bundle_root, _ = _staged(tmp_path)
        direct, _, _ = _CTX[str(tmp_path)]
        import shutil

        fake = os.path.join(str(tmp_path), "fixture_src")
        shutil.copytree(direct[FX.CONDITIONS[0]], fake)
        with open(os.path.join(fake, "arm_bundle.json"), "w") as fh:
            json.dump({"schema_version": "spot.stage02_temporal_arm_effect_source.v1",
                       "condition": FX.CONDITIONS[0]}, fh)
        swapped = dict(direct)
        swapped[FX.CONDITIONS[0]] = fake
        report = _verify(release_root, bundle_root, direct_bundles=swapped)
        assert report["verdict"] == verify.REJECT
        assert "no_fixture_json_may_stand_in_for_a_direct_bundle" in gates(report)

    def test_the_producers_own_PLACEHOLDER_verification_admits_nothing(self, tmp_path):
        """Every Direct bundle ships a ``verification.json`` that says, in its own bytes,
        that it is NOT an admission: admitted=false, verifier_id=null, verdict pending.
        Pointing the verifier at it must fail — a producer that could admit itself by
        shipping a file with the right name in the right place would not be admitted by
        anybody."""
        release_root, bundle_root, _ = _staged(tmp_path)
        direct, w10, _ = _CTX[str(tmp_path)]

        placeholder = os.path.join(direct[FX.CONDITIONS[0]], "verification.json")
        with open(placeholder) as fh:
            doc = json.load(fh)
        assert doc["admitted"] is False and doc["verifier_id"] is None
        assert doc["verdict"] == "pending_independent_verification"

        as_w10 = dict(w10)
        as_w10[FX.CONDITIONS[0]] = placeholder
        report = _verify(release_root, bundle_root, w10_reports=as_w10)
        assert report["verdict"] == verify.REJECT
        assert {"the_w10_report_is_not_the_producers_own_placeholder",
                "the_w10_report_actually_ADMITS_this_direct_bundle"} & gates(report)

    def test_a_SELF_ADMITTED_report_is_refused(self, tmp_path):
        release_root, bundle_root, _ = _staged(tmp_path)
        _, w10, _ = _CTX[str(tmp_path)]
        with open(w10[FX.CONDITIONS[0]]) as fh:
            rep = json.load(fh)
        rep["self_admitted"] = True
        with open(w10[FX.CONDITIONS[0]], "w") as fh:
            json.dump(rep, fh)
        report = _verify(release_root, bundle_root)
        assert report["verdict"] == verify.REJECT
        assert "the_w10_report_actually_ADMITS_this_direct_bundle" in gates(report)

    def test_a_direct_bundle_solved_under_the_WRONG_env_lock_is_refused(self, tmp_path):
        """Two endpoints solved by two different solvers are not a difference of one screen."""
        release_root, bundle_root, _ = _staged(tmp_path)
        direct, _, _ = _CTX[str(tmp_path)]
        path = os.path.join(direct[FX.CONDITIONS[0]], "provenance.json")
        with open(path) as fh:
            prov = json.load(fh)
        prov["run_binding"]["environment_lock"]["sha256"] = "b9284e63" + "0" * 56
        with open(path, "w") as fh:
            json.dump(prov, fh)
        report = _verify(release_root, bundle_root)
        assert report["verdict"] == verify.REJECT
        assert "the_direct_bundle_was_solved_under_the_authoritative_env_lock" in \
            gates(report)

    def test_a_direct_bundle_missing_a_file_is_refused(self, tmp_path):
        release_root, bundle_root, _ = _staged(tmp_path)
        direct, _, _ = _CTX[str(tmp_path)]
        os.remove(os.path.join(direct[FX.CONDITIONS[0]], "arms.parquet"))
        report = _verify(release_root, bundle_root)
        assert report["verdict"] == verify.REJECT
        assert "the_direct_bundle_ships_every_file_it_is_made_of" in gates(report)

    def test_direct_rows_that_do_not_hash_to_what_the_bundle_declares_are_refused(
            self, tmp_path):
        import pandas as pd

        release_root, bundle_root, _ = _staged(tmp_path)
        direct, _, _ = _CTX[str(tmp_path)]
        path = os.path.join(direct[FX.CONDITIONS[0]], "arms.parquet")
        df = pd.read_parquet(path)
        df.loc[0, "base_delta"] = 42.0
        df.to_parquet(path)
        report = _verify(release_root, bundle_root)
        assert report["verdict"] == verify.REJECT
        assert "the_direct_rows_hash_to_what_the_bundle_declares" in gates(report)

    def test_a_direct_bundle_no_INDEPENDENT_lane_admitted_is_refused(self, tmp_path):
        """W5 hashes the W10 report; it never reads it. A report that is merely PRESENT
        admits nothing."""
        release_root, bundle_root, _ = _staged(tmp_path)
        direct, w10, _ = _CTX[str(tmp_path)]
        path = w10[FX.CONDITIONS[0]]
        with open(path) as fh:
            rep = json.load(fh)
        rep["admitted"] = False
        rep["verdict"] = "REJECT"
        with open(path, "w") as fh:
            json.dump(rep, fh)
        report = _verify(release_root, bundle_root)
        assert report["verdict"] == verify.REJECT
        assert "the_w10_report_actually_ADMITS_this_direct_bundle" in gates(report)

    def test_a_w10_report_that_names_NO_verifier_is_refused(self, tmp_path):
        """An admission nobody signed is an admission nobody made."""
        release_root, bundle_root, _ = _staged(tmp_path)
        _, w10, _ = _CTX[str(tmp_path)]
        path = w10[FX.CONDITIONS[0]]
        with open(path) as fh:
            rep = json.load(fh)
        rep["verifier_id"] = None
        with open(path, "w") as fh:
            json.dump(rep, fh)
        report = _verify(release_root, bundle_root)
        assert report["verdict"] == verify.REJECT
        assert "the_w10_report_actually_ADMITS_this_direct_bundle" in gates(report)

    def test_two_direct_arms_that_DISAGREE_about_their_shared_base_delta_are_refused(
            self, tmp_path):
        """They are sign transforms of ONE number. A Direct bundle whose two arms disagree
        about it is internally broken, and the temporal run would inherit the disagreement
        while looking perfectly consistent."""
        import pandas as pd

        release_root, bundle_root, _ = _staged(tmp_path)
        direct, _, _ = _CTX[str(tmp_path)]
        path = os.path.join(direct[FX.CONDITIONS[0]], "arms.parquet")
        df = pd.read_parquet(path)
        i = df.index[df["desired_change"] == "decrease"][0]
        df.loc[i, "base_delta"] = float(df.loc[i, "base_delta"]) + 1.0
        df.to_parquet(path)
        report = _verify(release_root, bundle_root)
        assert report["verdict"] == verify.REJECT
        assert {"the_two_direct_arms_agree_about_the_base_delta_they_share",
                "the_direct_rows_hash_to_what_the_bundle_declares"} & gates(report)

    def test_an_endpoint_source_that_is_NOT_BOUND_is_refused(self, tmp_path):
        """The producer emits ``not_bound`` when it falls back off the Direct bundles. A
        release built that way is a difference of two things nobody measured."""
        report = attack(tmp_path, lambda b: b["endpoint_source"].update(
            {"endpoint_source": "not_bound"}))
        assert report["verdict"] == verify.REJECT
        assert "the_temporal_endpoints_are_two_admitted_direct_all_arm_bundles" in \
            gates(report)


# --------------------------------------------------------------------------- #
# THE ENVIRONMENT LOCK. The code digest says WHAT was run; the lock says WHAT WITH.
# --------------------------------------------------------------------------- #
class TestTheEnvironmentLock:
    def test_the_authoritative_stage2_lock_is_the_default_pin(self):
        """One environment across every lane. A lane pinned to a different lock is running a
        different computation and agrees with the others only by luck."""
        from verify_temporal_arms import code_identity

        assert code_identity.FROZEN_STAGE2_ENV_LOCK_SHA256 == (
            "2983d140941f13d223dad93bae71434663882f23f25f6717c3debe59d2711abe")
        assert FX.env_lock_sha256() == code_identity.FROZEN_STAGE2_ENV_LOCK_SHA256

    def test_the_release_binds_the_real_lock_verified_from_its_bytes(self, tmp_path):
        _, bundle_root, _ = _staged(tmp_path)
        lock = FX.read_bundle(bundle_root, *PAIR)["env_lock"]
        assert lock["env_lock_sha256"] == FX.env_lock_sha256()
        assert lock["env_lock_is_synthetic"] is False
        assert lock["env_lock_verified_from_bytes"] is True

    def test_a_SYNTHETIC_lock_is_refused(self, tmp_path):
        """A synthetic lock pins no environment at all."""
        report = attack(tmp_path, lambda b: b["env_lock"].update(
            {"env_lock_is_synthetic": True, "env_lock_verified_from_bytes": False}))
        assert report["verdict"] == verify.REJECT
        assert "the_release_was_built_under_a_real_verified_environment_lock" in \
            gates(report)

    def test_a_verifier_given_no_lock_at_all_refuses(self, tmp_path):
        """An unverified environment is an unbound input."""
        release_root, bundle_root, _ = _staged(tmp_path)
        report = verify.verify_release(
            release_root=release_root, bundle_root=bundle_root,
            producer_checkout=_REPO, require_clean_checkout=False)
        assert report["verdict"] == verify.REJECT
        assert "the_env_lock_was_supplied_to_the_verifier" in gates(report)

    def test_the_b928_requirements_lock_is_refused_by_name(self, tmp_path):
        """``_requirements/base.lock`` (b9284e63…) is NOT the frozen Stage-2 solver lock. A
        release built against it was built somewhere else than Direct, pathway and the run."""
        release_root, bundle_root, _ = _staged(tmp_path)
        wrong = os.path.join(str(tmp_path), "base.lock")
        with open(os.path.join(_REPO, "_requirements", "base.lock"), "rb") as fh:
            raw = fh.read()
        assert canonical.sha256_hex(raw).startswith("b9284e63")
        with open(wrong, "wb") as fh:
            fh.write(raw)
        report = _verify(release_root, bundle_root, env_lock=wrong)
        assert report["verdict"] == verify.REJECT
        assert "the_supplied_env_lock_is_the_authoritative_stage2_lock" in gates(report)

    def test_a_release_built_in_a_DIFFERENT_environment_is_refused(self, tmp_path):
        report = attack(tmp_path, lambda b: b["env_lock"].update(
            {"env_lock_sha256": "b" * 64}))
        assert report["verdict"] == verify.REJECT
        assert {"one_environment_lock_underlies_every_bundle_in_the_release",
                "the_env_lock_sha256_matches_the_lock_bytes_supplied"} & gates(report)


# --------------------------------------------------------------------------- #
# The honest control. Without it every refusal below is worthless.
# --------------------------------------------------------------------------- #
class TestTheHonestReleaseIsAdmitted:
    def test_an_untampered_release_verifies(self, tmp_path):
        report = run(tmp_path)
        assert report["verdict"] == verify.ADMIT, report["failures"]
        assert report["n_failed"] == 0

    def test_the_topology_is_derived_and_comes_out_at_six_bundles_and_120_arms(self, tmp_path):
        report = run(tmp_path)
        assert report["counts"] == {
            "n_conditions": 3, "n_ordered_pairs": 6, "n_programs": 10,
            "n_desired_changes": 2, "n_arms_per_bundle": 20, "n_bundles": 6,
            "n_logical_arms": 120,
        }

    def test_the_six_ordered_pairs_are_exactly_the_distinct_ones(self, tmp_path):
        report = run(tmp_path)
        pairs = [tuple(p) for p in report["ordered_pairs"]]
        assert len(pairs) == len(set(pairs)) == 6
        assert all(a != b for a, b in pairs)
        assert all((b, a) in pairs for a, b in pairs)

    def test_no_program_or_condition_name_is_hard_coded_anywhere_in_the_verifier(self):
        """A verifier holding a (Treg, Th1) pair would confirm the topology it was told to
        expect instead of the one that shipped."""
        pkg = os.path.join(_ANALYSIS, "verify_temporal_arms")
        banned = re.compile(
            r"\b(treg\w*|th1|th2|th17|th9|rest|stim\w*|naive|tfh)\b", re.IGNORECASE)
        for name in sorted(os.listdir(pkg)):
            if not name.endswith(".py"):
                continue
            hits = banned.findall(open(os.path.join(pkg, name)).read())
            assert hits == [], f"{name} hard-codes {sorted(set(hits))}"

    def test_the_report_is_typed_and_content_addressed(self, tmp_path):
        report = run(tmp_path)
        assert report["schema_version"] == schema.SCHEMA_REPORT
        payload = {k: v for k, v in report.items() if k != "report_id"}
        assert report["report_id"] == canonical.content_hash(payload)[:16]

    def test_the_producers_own_preflight_is_recorded_and_never_counted_as_evidence(
            self, tmp_path):
        """A producer self-check may say it passed. It may not say it was ADMITTED, and it
        may not sign itself with this lane's contract."""
        report = run(tmp_path)
        assert report["producer_self_report_trusted"] is False
        for b in report["bundles"]:
            pre = b["producer_self_report"]["preflight"]
            assert pre["is_admission"] is False

    def test_the_verifier_and_the_producer_agree_on_the_canonical_form(self, tmp_path):
        """Two independent serialisers, one answer. If they ever disagreed, one of them
        would be wrong and neither could tell you which."""
        from direct.hashing import content_hash as producer_hash

        _, bundle_root, _ = _staged(tmp_path)
        bundle = FX.read_bundle(bundle_root, *PAIR)
        assert canonical.content_hash(bundle) == producer_hash(bundle)


# --------------------------------------------------------------------------- #
# The estimand, re-derived from the bytes.
# --------------------------------------------------------------------------- #
class TestTheDifferenceInDifferencesIsRecomputed:
    def test_every_base_delta_is_re_derived_for_every_target_program_and_pair(
            self, tmp_path):
        report = run(tmp_path)
        assert report["n_base_deltas_rederived"] == 6 * 10 * 6      # pairs x programs x targets
        assert report["n_arm_values_rederived"] == 120 * 6

    def test_a_changed_base_delta_is_caught_even_when_everything_reseals(self, tmp_path):
        def mutate(b):
            base = b["base_records"][0]
            base["base_delta"] = (base["base_delta"] or 0.0) + 0.5
            for arm in b["arms"]:
                sign = 1 if arm["desired_change"] == "increase" else -1
                for rec in arm["records"]:
                    if rec["base_key"] == base["base_key"]:
                        rec["arm_value"] = sign * base["base_delta"]
        report = attack(tmp_path, mutate)
        assert report["verdict"] == verify.REJECT
        assert "base_delta_is_the_difference_in_differences" in gates(report)

    def test_a_changed_endpoint_delta_is_caught_against_the_ADMITTED_DIRECT_NUMBER(
            self, tmp_path):
        """The endpoint IS an admitted Direct base delta. Move it — and reseal the DiD and
        every arm value around it so the bundle is internally perfect — and it still has to
        answer to the Direct bundle it came from."""
        def mutate(b):
            base = b["base_records"][0]
            base["from_delta"] = 99.0
            base["base_delta"] = base["to_delta"] - 99.0
            for arm in b["arms"]:
                sign = 1 if arm["desired_change"] == "increase" else -1
                for rec in arm["records"]:
                    if rec["base_key"] == base["base_key"]:
                        rec["arm_value"] = sign * base["base_delta"]
        report = attack(tmp_path, mutate)
        assert report["verdict"] == verify.REJECT
        assert "every_temporal_base_delta_recomputes_from_the_admitted_direct_bundles" in \
            gates(report)

    def test_the_estimand_may_not_be_relabelled_as_a_per_cell_fate_claim(self, tmp_path):
        def mutate(b):
            b["estimand"]["estimand_is_per_cell_fate"] = True
        report = attack(tmp_path, mutate)
        assert report["verdict"] == verify.REJECT
        assert "estimand_is_population_level_not_per_cell_fate" in gates(report)

    def test_the_estimand_may_not_claim_a_calibrated_null(self, tmp_path):
        def mutate(b):
            b["estimand"]["inference_status"] = "calibrated"
        report = attack(tmp_path, mutate)
        assert report["verdict"] == verify.REJECT
        assert "inference_status_is_not_calibrated" in gates(report)


# --------------------------------------------------------------------------- #
# The sign transform.
# --------------------------------------------------------------------------- #
class TestTheSignTransform:
    def test_a_flipped_sign_on_one_arm_is_caught(self, tmp_path):
        def mutate(b):
            arm = next(a for a in b["arms"] if a["desired_change"] == "increase")
            for rec in arm["records"]:
                if rec["arm_value"] is not None:
                    rec["arm_value"] = -rec["arm_value"]
        report = attack(tmp_path, mutate)
        assert report["verdict"] == verify.REJECT
        assert "arm_value_is_the_sign_transform_of_the_base_delta" in gates(report)

    def test_a_relabelled_desired_change_is_caught(self, tmp_path):
        """Relabel an ``increase`` arm as a ``decrease`` — key and all — and its values no
        longer follow from the base delta they point at."""
        def mutate(b):
            arm = next(a for a in b["arms"] if a["desired_change"] == "increase")
            arm["desired_change"] = "decrease"
            arm["arm_key"] = arm["arm_key"].replace("|increase|", "|decrease|")
            b["arm_keys"] = sorted(a["arm_key"] for a in b["arms"])
        report = attack(tmp_path, mutate)
        assert report["verdict"] == verify.REJECT
        assert {"arm_inventory_is_every_program_x_every_desired_change",
                "arm_value_is_the_sign_transform_of_the_base_delta"} & gates(report)

    def test_a_pole_may_not_be_smuggled_in_as_a_desired_change(self, tmp_path):
        def mutate(b):
            arm = b["arms"][0]
            arm["desired_change"] = "high"
            arm["arm_key"] = arm["arm_key"].replace("|increase|", "|high|")
            b["arm_keys"] = sorted(a["arm_key"] for a in b["arms"])
        report = attack(tmp_path, mutate)
        assert report["verdict"] == verify.REJECT
        assert "desired_change_is_a_real_desired_change_not_a_pole_or_a_role" in gates(report)

    def test_the_two_arms_of_a_program_cannot_disagree_about_their_evaluability(
            self, tmp_path):
        def mutate(b):
            arm = b["arms"][0]
            arm["records"][0]["evaluable"] = not arm["records"][0]["evaluable"]
        report = attack(tmp_path, mutate)
        assert report["verdict"] == verify.REJECT
        assert "arm_evaluability_is_the_bases_evaluability" in gates(report)


# --------------------------------------------------------------------------- #
# The direction. Requirement 3: only the REQUESTED direction is represented.
# --------------------------------------------------------------------------- #
class TestOnlyTheRequestedTemporalDirectionIsRepresented:
    def test_every_arm_names_the_ordered_pair_of_the_bundle_it_lives_in(self, tmp_path):
        report = run(tmp_path)
        assert report["verdict"] == verify.ADMIT
        assert "arm_is_scoped_to_the_bundles_ordered_pair" not in gates(report)

    def test_the_reverse_direction_bundle_negates_every_base_delta(self, tmp_path):
        _, bundle_root, _ = _staged(tmp_path)
        fwd = FX.read_bundle(bundle_root, *PAIR)
        rev = FX.read_bundle(bundle_root, *REVERSE)
        rev_by_key = {b["base_key"]: b for b in rev["base_records"]}
        compared = 0
        for base in fwd["base_records"]:
            other = rev_by_key[base["base_key"]]
            if base["base_delta"] is None:
                assert other["base_delta"] is None
                continue
            assert other["base_delta"] == -base["base_delta"]
            compared += 1
        assert compared == 10 * FX.N_EVALUABLE_TARGETS

    def test_swapping_from_and_to_changes_the_arm_identity(self, tmp_path):
        _, bundle_root, _ = _staged(tmp_path)
        fwd = set(FX.read_bundle(bundle_root, *PAIR)["arm_keys"])
        rev = set(FX.read_bundle(bundle_root, *REVERSE)["arm_keys"])
        assert fwd.isdisjoint(rev)

    def test_a_bundle_whose_conditions_are_swapped_under_it_is_caught(self, tmp_path):
        def mutate(b):
            b["from_condition"], b["to_condition"] = b["to_condition"], b["from_condition"]
            b["bundle_key"] = f"temporal|{b['from_condition']}|{b['to_condition']}"
            for arm in b["arms"]:
                arm["from_condition"], arm["to_condition"] = \
                    arm["to_condition"], arm["from_condition"]
                arm["arm_key"] = "|".join(("temporal", arm["program_id"],
                                           arm["desired_change"], arm["from_condition"],
                                           arm["to_condition"]))
            b["arm_keys"] = sorted(a["arm_key"] for a in b["arms"])
            for base in b["base_records"]:
                base["from_condition"], base["to_condition"] = \
                    base["to_condition"], base["from_condition"]
        report = attack(tmp_path, mutate)
        assert report["verdict"] == verify.REJECT
        assert "bundle_directory_names_the_ordered_pair_it_carries" in gates(report)

    def test_a_bundle_that_keeps_its_pair_but_negates_nothing_is_caught_across_directions(
            self, tmp_path):
        """Copy the forward bundle's numbers into the reverse bundle. Both bundles are
        internally consistent; only the RELATIONSHIP between them is a lie."""
        release_root, bundle_root, _ = _staged(tmp_path)
        fwd = FX.read_bundle(bundle_root, *PAIR)
        fwd_bases = {b["base_key"]: b["base_delta"] for b in fwd["base_records"]}

        def mutate(b):
            for base in b["base_records"]:
                base["base_delta"] = fwd_bases[base["base_key"]]
                base["from_delta"], base["to_delta"] = base["to_delta"], base["from_delta"]
                for end in ("from", "to"):
                    pass
            for arm in b["arms"]:
                sign = 1 if arm["desired_change"] == "increase" else -1
                for rec in arm["records"]:
                    v = fwd_bases[rec["base_key"]]
                    rec["arm_value"] = None if v is None else (0.0 if v == 0 else sign * v)

        FX.reseal(release_root, bundle_root, REVERSE[0], REVERSE[1], mutate)
        report = _verify(release_root, bundle_root)
        assert report["verdict"] == verify.REJECT
        assert "reverse_direction_bundle_negates_every_base_delta" in gates(report)


# --------------------------------------------------------------------------- #
# The inventory: 6 x 20 = 120, complete, and each arm has exactly one home.
# --------------------------------------------------------------------------- #
class TestTheArmInventory:
    def test_a_missing_arm_is_caught_even_with_the_counts_corrected(self, tmp_path):
        def mutate(b):
            b["arms"].pop()
            b["n_arms"] = len(b["arms"])
            b["arm_keys"] = sorted(a["arm_key"] for a in b["arms"])
        report = attack(tmp_path, mutate)
        assert report["verdict"] == verify.REJECT
        assert "arm_inventory_is_every_program_x_every_desired_change" in gates(report)

    def test_a_duplicated_arm_is_caught(self, tmp_path):
        def mutate(b):
            b["arms"].append(json.loads(json.dumps(b["arms"][0])))
            b["n_arms"] = len(b["arms"])
            b["arm_keys"] = sorted(a["arm_key"] for a in b["arms"])
        report = attack(tmp_path, mutate)
        assert report["verdict"] == verify.REJECT
        assert "each_arm_key_appears_exactly_once_in_its_bundle" in gates(report)

    def test_a_whole_missing_bundle_is_caught(self, tmp_path):
        release_root, bundle_root, _ = _staged(tmp_path)
        FX.drop_bundle(release_root, bundle_root, *PAIR)
        report = _verify(release_root, bundle_root)
        assert report["verdict"] == verify.REJECT
        assert "every_ordered_pair_of_the_release_has_exactly_one_bundle" in gates(report)

    def test_an_invented_program_is_not_in_the_releases_admitted_set(self, tmp_path):
        def mutate(b):
            b["program_admission"]["programs"] = \
                b["program_admission"]["programs"] + ["FIXTURE_PROG_INVENTED"]
            b["program_admission"]["n_programs"] = \
                len(b["program_admission"]["programs"])
            b["n_programs"] = b["program_admission"]["n_programs"]
        report = attack(tmp_path, mutate)
        assert report["verdict"] == verify.REJECT
        assert "bundle_program_axis_is_the_bound_releases_admitted_set" in gates(report)

    def test_a_bundle_that_drops_a_program_is_incomplete(self, tmp_path):
        def mutate(b):
            dropped = b["program_admission"]["programs"][0]
            b["program_admission"]["programs"] = \
                [p for p in b["program_admission"]["programs"] if p != dropped]
            b["program_admission"]["n_programs"] = \
                len(b["program_admission"]["programs"])
            b["n_programs"] = b["program_admission"]["n_programs"]
            b["arms"] = [a for a in b["arms"] if a["program_id"] != dropped]
            b["n_arms"] = len(b["arms"])
            b["arm_keys"] = sorted(a["arm_key"] for a in b["arms"])
        report = attack(tmp_path, mutate)
        assert report["verdict"] == verify.REJECT
        assert "bundle_program_axis_is_the_bound_releases_admitted_set" in gates(report)


# --------------------------------------------------------------------------- #
# The RANKING BYTES each arm binds. Reopened, hashed, and RE-RANKED from disk.
# --------------------------------------------------------------------------- #
class TestTheBoundRankingBytes:
    def test_every_arm_binds_a_ranking_file_that_exists_and_hashes(self, tmp_path):
        _, bundle_root, _ = _staged(tmp_path)
        d = FX.pair_dir(bundle_root, *PAIR)
        bundle = FX.read_bundle(bundle_root, *PAIR)
        for arm in bundle["arms"]:
            binding = arm["ranking"]
            assert binding["path"].startswith("rankings/")
            raw = open(os.path.join(d, binding["path"]), "rb").read()
            assert binding["raw_sha256"] == canonical.sha256_hex(raw)
            assert json.loads(raw)["ranked"] == arm["records"]

    def test_a_tampered_ranking_file_is_refused_though_the_bundle_reseals_around_it(
            self, tmp_path):
        """The bundle, its provenance and the producer's verdict all agree. ONLY the bound
        ranking bytes disagree with the arm that binds them — the exact case an arm's own
        summary can never catch, because the arm is the thing being lied about."""
        release_root, bundle_root, _ = _staged(tmp_path)

        def bump_a_rank(ranking):
            ranked = [r for r in ranking["ranked"] if r["rank"] is not None]
            ranked[0]["rank"], ranked[1]["rank"] = ranked[1]["rank"], ranked[0]["rank"]

        FX.tamper_ranking(release_root, bundle_root, PAIR[0], PAIR[1], bump_a_rank)
        report = _verify(release_root, bundle_root)
        assert report["verdict"] == verify.REJECT
        assert "the_ranking_file_raw_sha256_matches_the_bytes_on_disk" in gates(report)

    def test_a_ranking_file_whose_rows_differ_from_the_arm_is_refused(self, tmp_path):
        release_root, bundle_root, _ = _staged(tmp_path)

        def drop_a_row(ranking):
            ranking["ranked"] = ranking["ranked"][:-1]

        FX.tamper_ranking(release_root, bundle_root, PAIR[0], PAIR[1], drop_a_row)
        report = _verify(release_root, bundle_root)
        assert report["verdict"] == verify.REJECT
        assert "the_ranking_file_raw_sha256_matches_the_bytes_on_disk" in gates(report)

    def test_an_EXTRA_fully_resealed_ranking_file_is_refused(self, tmp_path):
        """121 ranking files, 120 arms. The extra file is REAL: valid schema, correct
        hashes, listed in the inventory, and the inventory re-addresses itself around it.
        Every "does every named file exist and hash?" check passes perfectly — and the
        release still ships a ranking nobody re-derived, readable by path."""
        release_root, bundle_root, _ = _staged(tmp_path)
        d = FX.pair_dir(bundle_root, *PAIR)
        bundle = FX.read_bundle(bundle_root, *PAIR)

        # a genuine, well-formed ranking file — just one no arm binds
        real = bundle["arms"][0]
        extra = {"schema_version": schema.SCHEMA_RANKING,
                 "arm_key": real["arm_key"], "ranked": real["records"]}
        rel = f"{schema.RANKINGS_DIRNAME}/FIXTURE_PROG_00__stale.json"
        raw = canonical.canonical_json(extra).encode("utf-8")
        with open(os.path.join(d, rel), "wb") as fh:
            fh.write(raw)

        # ...hashed and resealed into the producer's inventory, which re-addresses itself
        ipath = os.path.join(bundle_root, schema.INVENTORY_FILENAME)
        with open(ipath) as fh:
            inv = json.load(fh)
        entry = next(b for b in inv["bundles"]
                     if b["relative_dir"] == os.path.basename(d))
        entry["rankings"][rel] = {"raw_sha256": canonical.sha256_hex(raw),
                                  "canonical_sha256": canonical.content_hash(extra)}
        inv.pop("release_id")
        inv["release_id"] = canonical.content_hash(inv)
        with open(ipath, "wb") as fh:
            fh.write(canonical.canonical_json(inv).encode("utf-8"))

        report = _verify(release_root, bundle_root)
        assert report["verdict"] == verify.REJECT
        assert {"the_inventorys_ranking_set_is_exactly_the_arms_that_were_reranked",
                "the_release_lists_exactly_one_ranking_file_per_logical_arm",
                "no_stale_ranking_file_sits_in_the_release_unbound_by_any_arm"} \
            <= gates(report)

    def test_a_stale_ranking_file_the_inventory_never_named_is_refused(self, tmp_path):
        """Not naming it does not remove it: it is still in the release, still readable."""
        release_root, bundle_root, _ = _staged(tmp_path)
        d = FX.pair_dir(bundle_root, *PAIR)
        with open(os.path.join(d, schema.RANKINGS_DIRNAME, "stale.json"), "w") as fh:
            json.dump({"schema_version": schema.SCHEMA_RANKING}, fh)
        report = _verify(release_root, bundle_root)
        assert report["verdict"] == verify.REJECT
        assert "no_stale_ranking_file_sits_in_the_release_unbound_by_any_arm" in \
            gates(report)

    def test_an_arm_binding_a_ranking_file_nobody_wrote_is_refused(self, tmp_path):
        """An arm citing evidence that does not exist is worse than one citing none."""
        release_root, bundle_root, _ = _staged(tmp_path)
        os.remove(os.path.join(FX.pair_dir(bundle_root, *PAIR),
                               FX.read_bundle(bundle_root, *PAIR)["arms"][0]["ranking"]
                               ["path"]))
        report = _verify(release_root, bundle_root)
        assert report["verdict"] == verify.REJECT
        assert "every_arm_binds_a_ranking_file_that_actually_exists" in gates(report)


# --------------------------------------------------------------------------- #
# The perturbation modality and the SUGGESTIVE modulation orientation Stage 3 acts on.
# --------------------------------------------------------------------------- #
class TestTheModalityAndTheModulationOrientation:
    def test_the_orientation_rederives_from_the_arm_value_on_every_record(self, tmp_path):
        _, bundle_root, _ = _staged(tmp_path)
        bundle = FX.read_bundle(bundle_root, *PAIR)
        assert bundle["perturbation"]["perturbation_modality"] == "CRISPRi_knockdown"
        assert bundle["perturbation"]["pharmacologic_reversibility_assumed"] is False
        for arm in bundle["arms"]:
            for rec in arm["records"]:
                v, ok = rec["arm_value"], rec["evaluable"]
                if not ok or v is None:
                    want = "not_evaluable"
                elif v > 0:
                    want = "supports_target_inhibition"
                elif v < 0:
                    want = "opposed_would_require_target_activation"
                else:
                    want = "no_directional_response"
                assert rec["desired_target_modulation"] == want

    def test_a_flipped_orientation_is_caught(self, tmp_path):
        def mutate(b):
            for arm in b["arms"]:
                for rec in arm["records"]:
                    if rec["desired_target_modulation"] == "supports_target_inhibition":
                        rec["desired_target_modulation"] = \
                            "opposed_would_require_target_activation"
        report = attack(tmp_path, mutate)
        assert report["verdict"] == verify.REJECT
        assert "desired_target_modulation_rederives_from_the_arm_value_and_evaluability" \
            in gates(report)

    def test_an_unevaluable_arm_may_not_be_given_a_direction(self, tmp_path):
        """A direction nobody measured is the one a reader would act on."""
        def mutate(b):
            for arm in b["arms"]:
                for rec in arm["records"]:
                    if rec["desired_target_modulation"] == "not_evaluable":
                        rec["desired_target_modulation"] = "supports_target_inhibition"
        report = attack(tmp_path, mutate)
        assert report["verdict"] == verify.REJECT
        assert "desired_target_modulation_rederives_from_the_arm_value_and_evaluability" \
            in gates(report)

    def test_assuming_pharmacologic_reversibility_is_refused(self, tmp_path):
        """An OPPOSED arm would need the target ACTIVATED. This screen knocked it down and
        cannot speak to that — an artifact that assumed otherwise would launder a knockdown
        into a prescription."""
        def mutate(b):
            b["perturbation"]["pharmacologic_reversibility_assumed"] = True
        report = attack(tmp_path, mutate)
        assert report["verdict"] == verify.REJECT
        assert "pharmacologic_reversibility_is_not_assumed" in gates(report)

    def test_a_confirmatory_modulation_claim_is_refused(self, tmp_path):
        def mutate(b):
            b["perturbation"]["is_suggestive_not_confirmatory"] = False
        report = attack(tmp_path, mutate)
        assert report["verdict"] == verify.REJECT
        assert "the_modulation_claim_is_suggestive_not_confirmatory" in gates(report)

    def test_a_changed_modality_is_refused(self, tmp_path):
        def mutate(b):
            b["base_records"][0]["perturbation_modality"] = "CRISPRa_activation"
        report = attack(tmp_path, mutate)
        assert report["verdict"] == verify.REJECT
        assert "every_base_record_declares_the_crispri_knockdown_modality" in gates(report)


# --------------------------------------------------------------------------- #
# The Stage-3 consumer contract: the JOIN, and the target IDENTITY it joins on.
# --------------------------------------------------------------------------- #
class TestTheArmToBaseJoinAndTheTargetIdentity:
    def test_every_arm_record_joins_to_exactly_one_base_record(self, tmp_path):
        _, bundle_root, _ = _staged(tmp_path)
        bundle = FX.read_bundle(bundle_root, *PAIR)
        bases = {}
        for b in bundle["base_records"]:
            assert b["base_key"] not in bases, "a base_key resolves to two rows"
            bases[b["base_key"]] = b
        joined = 0
        for arm in bundle["arms"]:
            for rec in arm["records"]:
                base = bases[rec["base_key"]]
                assert base["target_id"] == rec["target_id"]
                assert base["program_id"] == arm["program_id"]
                joined += 1
        assert joined == 20 * 6                       # every arm x every target

    def test_a_join_that_resolves_to_the_wrong_target_is_caught(self, tmp_path):
        """A join that resolves to the WRONG row is worse than one that fails: it returns
        a number."""
        def mutate(b):
            arm = b["arms"][0]
            other = next(r for r in arm["records"]
                         if r["base_key"] != arm["records"][0]["base_key"])
            arm["records"][0]["base_key"] = other["base_key"]
        report = attack(tmp_path, mutate)
        assert report["verdict"] == verify.REJECT
        assert "the_arm_to_base_join_resolves_to_the_same_target_and_program" in \
            gates(report)

    def test_a_duplicated_base_record_breaks_the_join_and_is_caught(self, tmp_path):
        def mutate(b):
            b["base_records"].append(json.loads(json.dumps(b["base_records"][0])))
            b["n_base_records"] = len(b["base_records"])
        report = attack(tmp_path, mutate)
        assert report["verdict"] == verify.REJECT
        assert "each_base_key_resolves_to_exactly_one_base_record" in gates(report)

    def test_the_target_identity_is_normalized_on_the_base_record(self, tmp_path):
        """The stable id is what every join runs on, and it is carried ONCE. With a Direct
        endpoint source the per-endpoint provenance is the DIRECT BUNDLE itself, which the
        release binds by id, sha256 and W10 admission — not a second copy restated here."""
        _, bundle_root, _ = _staged(tmp_path)
        bundle = FX.read_bundle(bundle_root, *PAIR)
        base = bundle["base_records"][0]
        for field in ("target_id", "base_key", "program_id"):
            assert base[field]
        es = bundle["endpoint_source"]
        assert es["from_direct_bundle_sha256"] and es["from_w10_report_sha256"]
        assert es["to_direct_bundle_sha256"] and es["to_w10_report_sha256"]

    def test_identity_is_never_duplicated_into_the_arm_records(self, tmp_path):
        """One statement of a target's identity per bundle. A second copy on the arm record
        would be a second identity that can drift from the first."""
        _, bundle_root, _ = _staged(tmp_path)
        bundle = FX.read_bundle(bundle_root, *PAIR)
        for arm in bundle["arms"]:
            for rec in arm["records"]:
                assert set(rec) == {"target_id", "base_key", "arm_value", "evaluable",
                                    "temporal_status", "desired_target_modulation",
                                    "rank"}

    def test_a_base_record_with_no_target_id_is_not_a_stable_identity(self, tmp_path):
        def mutate(b):
            b["base_records"][0]["target_id"] = None
        report = attack(tmp_path, mutate)
        assert report["verdict"] == verify.REJECT
        assert "base_record_carries_a_stable_namespaced_target_identity" in gates(report)

    def test_a_direct_sourced_endpoint_may_not_restate_the_decomposition(self, tmp_path):
        """A second copy of the panel/control means here would be a second chance to
        disagree with the Direct bundle they came from."""
        def mutate(b):
            b["base_records"][0]["from_panel_mean"] = 1.0
        report = attack(tmp_path, mutate)
        assert report["verdict"] == verify.REJECT
        assert "a_direct_sourced_endpoint_carries_no_second_copy_of_the_decomposition" in \
            gates(report)


# --------------------------------------------------------------------------- #
# The ranks. RETAINED-ROW semantics: every target stays, rank is null when not rankable.
# --------------------------------------------------------------------------- #
class TestTheRanks:
    def test_every_target_is_retained_and_an_unrankable_one_gets_a_null_rank(self, tmp_path):
        """Rows are RETAINED, never dropped: an absent row is indistinguishable from a row
        that was never asked about, and a consumer cannot tell which happened."""
        release_root, bundle_root, _ = _staged(tmp_path)
        bundle = FX.read_bundle(bundle_root, *PAIR)
        for arm in bundle["arms"]:
            assert len(arm["records"]) == arm["n_targets"] == len(FX.P.TARGETS)
            assert arm["n_ranked"] == arm["n_evaluable"] == FX.N_EVALUABLE_TARGETS
            retained = {r["target_id"]: r for r in arm["records"]}
            # the excluded target is STILL THERE, and its rank is null - not missing
            assert FX.UNEVALUABLE_TARGET in retained
            assert retained[FX.UNEVALUABLE_TARGET]["rank"] is None
            assert retained[FX.UNEVALUABLE_TARGET]["evaluable"] is False
            for rec in arm["records"]:
                if not rec["evaluable"] or rec["arm_value"] is None:
                    assert rec["rank"] is None
                else:
                    assert isinstance(rec["rank"], int)

    def test_a_dropped_unrankable_row_is_caught(self, tmp_path):
        def mutate(b):
            arm = b["arms"][0]
            arm["records"] = [r for r in arm["records"] if r["rank"] is not None]
            arm["n_targets"] = len(arm["records"])
        report = attack(tmp_path, mutate)
        assert report["verdict"] == verify.REJECT
        assert "every_arm_retains_a_row_for_every_target_in_the_bundle" in gates(report)
    def test_a_changed_rank_is_caught(self, tmp_path):
        def mutate(b):
            arm = b["arms"][0]
            ranked = [r for r in arm["records"] if r["rank"] is not None]
            ranked[0]["rank"], ranked[1]["rank"] = ranked[1]["rank"], ranked[0]["rank"]
        report = attack(tmp_path, mutate)
        assert report["verdict"] == verify.REJECT
        assert "rank_rederives_by_the_frozen_rule" in gates(report)

    def test_a_rank_handed_to_a_non_evaluable_target_is_caught(self, tmp_path):
        def mutate(b):
            arm = b["arms"][0]
            arm["records"][0]["rank"] = 999
        report = attack(tmp_path, mutate)
        assert report["verdict"] == verify.REJECT
        assert "rank_rederives_by_the_frozen_rule" in gates(report)


# --------------------------------------------------------------------------- #
# The bindings: content address, scorer view, run identity.
# --------------------------------------------------------------------------- #
class TestTheBindings:
    def test_a_forged_bundle_id_is_caught(self, tmp_path):
        """The id is forged and every hash around it is resealed over the forged bytes, so
        the ONLY thing left that can catch it is re-deriving the id from the content."""
        release_root, bundle_root, _ = _staged(tmp_path)
        FX.reseal(release_root, bundle_root, PAIR[0], PAIR[1],
                  lambda b: b.update({"bundle_id": "0" * 16}), reseal_bundle_id=False)
        report = _verify(release_root, bundle_root)
        assert report["verdict"] == verify.REJECT
        assert "bundle_id_covers_its_own_content" in gates(report)

    def test_a_scorer_view_hash_that_does_not_bind_the_release_is_caught(self, tmp_path):
        def mutate(b):
            b["program_admission"]["registry_scorer_view_sha256"] = "b" * 64
        report = attack(tmp_path, mutate)
        assert report["verdict"] == verify.REJECT
        assert "bundle_binds_the_scorer_view_of_the_bound_release" in gates(report)

    def test_a_fake_code_identity_on_a_NON_FIRST_bundle_is_caught(self, tmp_path):
        """The commit is fake but the bundle is perfect: the code_identity is internally
        self-consistent, the bundle id covers it, the inventory re-hashes it. And it is not
        on the FIRST sorted bundle — so a verifier that pinned only docs[0] would re-derive
        the honest build, admit, and print the honest commit into the envelope right over
        the top of the lie."""
        release_root, bundle_root, _ = _staged(tmp_path)
        victim = FX.ORDERED_PAIRS[3]                   # deliberately not the first
        assert victim != FX.ORDERED_PAIRS[0]

        def mutate(b):
            b["code_identity"] = dict(b["code_identity"])
            b["code_identity"]["commit"] = "f" * 40
            b["code_identity"]["manifest_sha256"] = "a" * 64
            b["code_identity"]["canonical_digest"] = "a" * 16

        FX.reseal(release_root, bundle_root, victim[0], victim[1], mutate)
        report = _verify(release_root, bundle_root)
        assert report["verdict"] == verify.REJECT
        assert "one_code_identity_produced_every_bundle_in_the_release" in gates(report)

    def test_the_method_must_be_one_method_across_the_whole_release(self, tmp_path):
        def mutate(b):
            b["method"]["temporal_method_sha256"] = "9" * 64
        report = attack(tmp_path, mutate)
        assert report["verdict"] == verify.REJECT
        assert "one_method_produced_every_bundle_in_the_release" in gates(report)

    def test_a_method_that_binds_no_effect_source_is_refused(self, tmp_path):
        def mutate(b):
            b["method"]["effect_source_sha256"] = None
        report = attack(tmp_path, mutate)
        assert report["verdict"] == verify.REJECT
        assert "method_binds_the_effect_source_it_differenced" in gates(report)

    def test_a_verdict_planted_in_a_producer_bundle_directory_is_caught(self, tmp_path):
        """The external admission is ONE file at the release root. A copy inside a producer
        bundle directory is a self-verdict, and it would look exactly like the real thing."""
        release_root, bundle_root, _ = _staged(tmp_path)
        with open(os.path.join(FX.pair_dir(bundle_root, *PAIR),
                               schema.ENVELOPE_FILENAME), "w") as fh:
            json.dump({"verdict": "ADMIT"}, fh)
        report = _verify(release_root, bundle_root)
        assert report["verdict"] == verify.REJECT
        assert "no_verdict_file_inside_a_producer_bundle_directory" in gates(report)

    def test_a_mutated_producer_inventory_is_caught(self, tmp_path):
        release_root, bundle_root, _ = _staged(tmp_path)
        ipath = os.path.join(bundle_root, schema.INVENTORY_FILENAME)
        with open(ipath) as fh:
            inv = json.load(fh)
        inv["n_logical_arms"] = 119
        with open(ipath, "wb") as fh:
            fh.write(canonical.canonical_json(inv).encode("utf-8"))
        report = _verify(release_root, bundle_root)
        assert report["verdict"] == verify.REJECT
        assert "the_inventory_release_id_covers_its_own_content" in gates(report)

    def test_a_missing_producer_inventory_is_caught(self, tmp_path):
        release_root, bundle_root, _ = _staged(tmp_path)
        os.remove(os.path.join(bundle_root, schema.INVENTORY_FILENAME))
        report = _verify(release_root, bundle_root)
        assert report["verdict"] == verify.REJECT
        assert "the_producer_release_inventory_is_on_disk" in gates(report)


# --------------------------------------------------------------------------- #
# The schema firewalls, on the SHIPPED BYTES.
# --------------------------------------------------------------------------- #
class TestTheFirewallsRunOnWhatLanded:
    def test_an_unknown_top_level_key_is_rejected(self, tmp_path):
        report = attack(tmp_path, lambda b: b.update({"surprise": 1}))
        assert report["verdict"] == verify.REJECT
        assert "bundle_keys_are_the_exact_allowlist" in gates(report)

    def test_an_unknown_NESTED_key_is_rejected(self, tmp_path):
        report = attack(tmp_path, lambda b: b["method"].update({"surprise": 1}))
        assert report["verdict"] == verify.REJECT
        assert "method_keys_are_the_exact_allowlist" in gates(report)

    def test_a_missing_required_key_is_rejected(self, tmp_path):
        report = attack(tmp_path, lambda b: b.pop("n_desired_changes"))
        assert report["verdict"] == verify.REJECT
        assert "bundle_keys_are_the_exact_allowlist" in gates(report)

    def test_an_inserted_q_value_is_rejected(self, tmp_path):
        def mutate(b):
            b["arms"][0]["records"][0]["q_value"] = 0.01
        report = attack(tmp_path, mutate)
        assert report["verdict"] == verify.REJECT
        assert {"no_p_q_fdr_or_significance_field",
                "arm_record_keys_are_the_exact_allowlist"} <= gates(report)

    def test_an_inserted_combined_objective_is_rejected(self, tmp_path):
        report = attack(tmp_path, lambda b: b.update({"combined_score": 1.0}))
        assert report["verdict"] == verify.REJECT
        assert "no_combined_balanced_or_weighted_objective" in gates(report)

    def test_an_inserted_pole_is_rejected(self, tmp_path):
        def mutate(b):
            b["arms"][0]["pole"] = "high"
        report = attack(tmp_path, mutate)
        assert report["verdict"] == verify.REJECT
        assert "no_pair_pareto_concordance_joint_role_pole_or_batch_field" in gates(report)

    def test_an_inserted_batch_field_is_rejected(self, tmp_path):
        def mutate(b):
            b["method"]["batch_policy_sha256"] = "a" * 64
        report = attack(tmp_path, mutate)
        assert report["verdict"] == verify.REJECT
        assert "no_pair_pareto_concordance_joint_role_pole_or_batch_field" in gates(report)

    def test_the_bundle_may_not_flip_its_own_prohibition_off(self, tmp_path):
        report = attack(tmp_path, lambda b: b.update({"bundle_carries_role_or_pole": True}))
        assert report["verdict"] == verify.REJECT
        assert "no_pair_pareto_concordance_joint_role_pole_or_batch_field" in gates(report)


# --------------------------------------------------------------------------- #
# The machine firewall (the W5 repair).
# --------------------------------------------------------------------------- #
class TestNoMachineReachesAPublishedArtifact:
    def test_the_honest_release_carries_no_absolute_path_at_any_depth(self, tmp_path):
        _, bundle_root, _ = _staged(tmp_path)
        for pair in FX.ORDERED_PAIRS:
            d = FX.pair_dir(bundle_root, *pair)
            for name in (schema.BUNDLE_FILENAME, schema.PROVENANCE_FILENAME,
                         schema.PREFLIGHT_FILENAME):
                with open(os.path.join(d, name)) as fh:
                    assert schema.machine_path_hits(json.load(fh)) == [], f"{pair} {name}"
        with open(os.path.join(bundle_root, schema.INVENTORY_FILENAME)) as fh:
            assert schema.machine_path_hits(json.load(fh)) == []

    def test_a_path_abs_injected_into_a_bundle_is_rejected(self, tmp_path):
        def mutate(b):
            b["method"]["path_abs"] = "/fixture-home/analyst/spot/out/bundle.json"
        report = attack(tmp_path, mutate)
        assert report["verdict"] == verify.REJECT
        assert "no_machine_path_hostname_or_private_address" in gates(report)

    def test_a_path_abs_injected_into_the_PROVENANCE_is_rejected(self, tmp_path):
        """Resealed path injection into a real shipped artifact: the provenance is rewritten
        and the ROOT INVENTORY re-hashes it, so every hash on disk agrees."""
        release_root, bundle_root, _ = _staged(tmp_path)
        ppath = os.path.join(FX.pair_dir(bundle_root, *PAIR), schema.PROVENANCE_FILENAME)
        with open(ppath) as fh:
            prov = json.load(fh)
        prov["verification_path_abs"] = "/fixture-home/analyst/spot/out/verification.json"
        with open(ppath, "wb") as fh:
            fh.write(canonical.canonical_json(prov).encode("utf-8"))
        FX.reseal_inventory(release_root, bundle_root)

        report = _verify(release_root, bundle_root)
        assert report["verdict"] == verify.REJECT
        assert "provenance_carries_no_machine_path_hostname_or_private_address" in \
            gates(report)

    def test_a_path_abs_injected_into_the_ROOT_INVENTORY_is_rejected(self, tmp_path):
        release_root, bundle_root, _ = _staged(tmp_path)
        ipath = os.path.join(bundle_root, schema.INVENTORY_FILENAME)
        with open(ipath) as fh:
            inv = json.load(fh)
        inv["bundles"][0]["path_abs"] = "/fixture-home/analyst/spot/out/arm_bundle.json"
        inv.pop("release_id")
        inv["release_id"] = canonical.content_hash(inv)[:16]
        with open(ipath, "wb") as fh:
            fh.write(canonical.canonical_json(inv).encode("utf-8"))

        report = _verify(release_root, bundle_root)
        assert report["verdict"] == verify.REJECT
        assert "inventory_carries_no_machine_path_hostname_or_private_address" in \
            gates(report)

    def test_a_private_address_hidden_in_a_string_value_is_rejected(self, tmp_path):
        def mutate(b):
            b["method"]["direct_method_version"] = "built on 192.168.1.7"
        report = attack(tmp_path, mutate)
        assert report["verdict"] == verify.REJECT
        assert "no_machine_path_hostname_or_private_address" in gates(report)


# --------------------------------------------------------------------------- #
# The release binding: conditions, and the shapes that are refused.
# --------------------------------------------------------------------------- #
class TestTheReleaseIsTheConditionAuthority:
    def test_the_pinned_condition_universe_is_checked_when_supplied(self, tmp_path):
        report = run(tmp_path, expect_conditions=FX.CONDITIONS)
        assert report["verdict"] == verify.ADMIT

    def test_a_reordered_condition_universe_is_refused(self, tmp_path):
        report = run(tmp_path, expect_conditions=list(reversed(FX.CONDITIONS)))
        assert report["verdict"] == verify.REJECT
        assert "release_conditions_match_the_pinned_universe" in gates(report)

    def test_a_forged_condition_is_refused(self, tmp_path):
        report = run(tmp_path, expect_conditions=[FX.CONDITIONS[0], FX.CONDITIONS[1],
                                                  "FixStim24"])
        assert report["verdict"] == verify.REJECT
        assert "release_conditions_match_the_pinned_universe" in gates(report)

    def test_a_missing_condition_is_refused(self, tmp_path):
        report = run(tmp_path, expect_conditions=FX.CONDITIONS[:2])
        assert report["verdict"] == verify.REJECT
        assert "release_conditions_match_the_pinned_universe" in gates(report)

    def test_the_legacy_release_shape_is_refused_at_a_named_gate(self, tmp_path):
        release_root, bundle_root, _ = _staged(tmp_path)
        FX.stage_release(release_root, mutate_release=FX.as_legacy_manifest)
        report = _verify(release_root, bundle_root)
        assert report["verdict"] == verify.REJECT
        assert "release_shape_is_the_current_stage1_v3_release" in gates(report)

    def test_a_pinned_scorer_view_prefix_that_does_not_match_is_refused(self, tmp_path):
        report = run(tmp_path, expect_scorer_view_prefix="deadbeef")
        assert report["verdict"] == verify.REJECT
        assert "scorer_view_binding_matches_the_pinned_prefix" in gates(report)

    def test_an_unexpected_directory_under_the_bundle_root_is_refused(self, tmp_path):
        release_root, bundle_root, _ = _staged(tmp_path)
        os.makedirs(os.path.join(bundle_root, "FixRest__to__FixRest"))
        report = _verify(release_root, bundle_root)
        assert report["verdict"] == verify.REJECT
        assert "no_bundle_directory_the_release_did_not_ask_for" in gates(report)
