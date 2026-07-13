"""SYNTHETIC FIXTURES for the INDEPENDENT temporal arm verifier. FIXTURE DATA ONLY.

=============================================================================
EVERY NUMBER, GENE, PROGRAM AND CONDITION IN THIS MODULE IS INVENTED. Nothing
here is measured, nothing is derived from GWCD4i or any other dataset, and NO
BIOLOGICAL CLAIM MAY BE READ OUT OF IT. The ids are spelled FIXTURE_* / Fix*
precisely so a number from this module can never be mistaken for a statement
about treg_like, th1_like, Rest, Stim8hr or anything else real.
=============================================================================

WHAT IT STAGES
--------------
* a synthetic Stage-1 v3 RELEASE in the CURRENT shape (``spot.stage01_v3_release.v1``,
  ``selector`` + ``components``) whose scorer view carries ``base_portable`` per program
  and NONE of the fields the real view does not have. It ships ELEVEN programs — ten
  base-portable and one explicitly not — so a hard-coded ten cannot pass;
* the six ordered-pair arm bundles the PRODUCER emits, written to disk by the producer
  itself. The producer is used here as an UNTRUSTED SOURCE OF BYTES; the verifier under
  test never imports it.

AND THE ATTACKS
---------------
``reseal`` mutates a shipped bundle and then makes the whole release SELF-CONSISTENT
again: the bundle id is recomputed over the tampered content, the verification file's raw
and canonical hashes are recomputed over the tampered bytes, the producer's own report is
rewritten to say ADMITTED, and the inventory is rebuilt. A mutation test that skipped the
reseal would only ever prove that the hashes work — the point is to prove the SCIENCE
gates fire when every hash already agrees.
"""
from __future__ import annotations

import json
import os
import shutil
from typing import Any, Callable, Optional

import fixtures_temporal_arms as P
from direct.temporal.arms import arm_emit
from verify_temporal_arms import canonical, schema

# The synthetic universe, taken from the producer's own fixture so the release and the
# bundles cannot silently disagree about which programs exist.
PORTABLE_IDS = list(P.PORTABLE_IDS)
NON_PORTABLE_ID = P.NON_PORTABLE_ID
CONDITIONS = list(P.CONDITIONS)
ORDERED_PAIRS = list(P.ORDERED_PAIRS)

RELEASE_SCHEMA = "spot.stage01_v3_release.v1"
VIEW_SCHEMA = "spot.stage01_stage2_registry_view.v1"
VIEW_KIND = "stage2_registry_view"
LEGACY_RELEASE_SCHEMA = "spot.stage01_release_manifest.v1"

RELEASE_FILENAME = "stage01_v3_release.json"
SCORER_VIEW_FILENAME = "scorer_view.json"


# --------------------------------------------------------------------------- #
# The staged Stage-1 v3 release.
# --------------------------------------------------------------------------- #
def scorer_view(*, break_panel_of: Optional[str] = None,
                extra_panel_gene: Optional[str] = None,
                reverse_panel_of: Optional[str] = None,
                flip_extra_field_of: Optional[str] = None) -> dict[str, Any]:
    """The FIXTURE executable scorer view, in the shape the real one has.

    Top keys: ``view_kind`` / ``method_version`` / ``effect_universe*`` / ``programs``.
    Deliberately NO ``view_id``, NO ``base_portable_programs``, NO
    ``base_portability_source_field`` and NO per-program ``method_hash`` — the real view
    has none of them, and a fixture that invented them would let the verifier read a field
    that does not exist in production.
    """
    programs = []
    for pid, prog in sorted(P.programs_registry().items()):
        # THE WHOLE RECORD, VERBATIM. The scorer view IS the registry: the per-program hash
        # is taken over the record exactly as Stage-1 emitted it, so a fixture that shipped
        # a trimmed copy would make the producer and the verifier hash two different records
        # and agree only by accident.
        record = dict(prog)
        panel = list(record["panel_ensembl"])
        if pid == extra_panel_gene:
            panel = panel + [P.GENES[-1]]
        if pid == reverse_panel_of:
            panel = list(reversed(panel))       # a REORDERING is a different record
        if pid == break_panel_of:
            panel = []
        record["panel_ensembl"] = panel
        record["control_ensembl"] = list(record["control_ensembl"])
        if pid == flip_extra_field_of:
            # a field the retired four-field derivation never looked at
            record["stage2_selectable"] = not record.get("stage2_selectable")
        programs.append(record)
    return {
        "schema_version": VIEW_SCHEMA,
        "view_kind": VIEW_KIND,
        "method_version": "fixture-stage1-v3",
        "effect_universe_id": "FIXTURE_UNIVERSE",
        "effect_universe_sha256": "c" * 64,
        "programs": programs,
    }


def _component(root: str, name: str, doc: dict[str, Any], role: str) -> dict[str, Any]:
    """A NATIVE component entry: repo-relative path, raw + canonical_content hashes, role."""
    from verify_temporal_arms import release as R

    path = os.path.join(root, name)
    raw = canonical.canonical_json(doc).encode("utf-8")
    with open(path, "wb") as fh:
        fh.write(raw)
    return {"path": name, "role": role, "raw_sha256": canonical.sha256_hex(raw),
            "canonical_content_sha256": R.canonical_content_sha256(doc)}


def stage_release(root, *, mutate_release: Optional[Callable] = None,
                  scorer_component_name: str = "scorer_view",
                  duplicate_scorer_view: bool = False,
                  drop_scorer_view: bool = False,
                  break_panel_of: Optional[str] = None,
                  extra_panel_gene: Optional[str] = None,
                  reverse_panel_of: Optional[str] = None,
                  flip_extra_field_of: Optional[str] = None) -> str:
    """Write a synthetic v3 release under ``root`` and return the staged root."""
    root = str(root)
    os.makedirs(root, exist_ok=True)

    from verify_temporal_arms import release as R

    view = scorer_view(break_panel_of=break_panel_of, extra_panel_gene=extra_panel_gene,
                       reverse_panel_of=reverse_panel_of,
                       flip_extra_field_of=flip_extra_field_of)
    registry = {"schema_version": "spot.stage01_program_registry.v3",
                "programs": [dict(p) for p in view["programs"]],
                "sensitivity_lanes": []}

    components: dict[str, Any] = {}
    if not drop_scorer_view:
        components[scorer_component_name] = _component(
            root, SCORER_VIEW_FILENAME, view, R.ROLE_SCORER_VIEW)
    if duplicate_scorer_view:
        components["second_view"] = _component(
            root, "scorer_view_copy.json", view, R.ROLE_SCORER_VIEW)
    components["registry_v3"] = _component(
        root, "registry_v3.json", registry, R.ROLE_PROGRAM_REGISTRY)
    # A component that is NOT the scorer view, so discovery has to go by schema/role and not
    # by a key name somebody chose.
    components["effect_universe"] = _component(
        root, "effect_universe.json",
        {"schema_version": "spot.stage01_effect_universe.v1",
         "universe_id": "FIXTURE_UNIVERSE", "n_genes": len(P.GENES)},
        "effect_universe_target_space")
    # ...and one staged OUT of the repo: bound by hash, with no path to open.
    components["scores_parquet"] = {
        "role": "continuous_program_scores_396k", "location": "staged_off_repo",
        "raw_sha256_staged": "f" * 64, "canonical_content_sha256": "e" * 64}

    admitted = sorted(p["program_id"] for p in view["programs"] if p["base_portable"])
    doc: dict[str, Any] = {
        # NATIVE: the key is "schema", not "schema_version"
        "schema": RELEASE_SCHEMA,
        "method_version": "fixture-stage1-v3",
        "registry_scorer_view_canonical_sha256": canonical.content_hash(view),
        "registry_scorer_projection_sha256": canonical.content_hash(
            R.registry_scorer_projection(registry)),
        "selector": {
            "conditions": list(CONDITIONS),
            "admitted_programs": admitted,
        },
        "components": components,
    }
    if mutate_release is not None:
        mutate_release(doc)
    # the release's own id follows its content — W20's rule, applied here
    doc.pop("self_release_sha256", None)
    doc["self_release_sha256"] = canonical.content_hash(doc)
    with open(os.path.join(root, RELEASE_FILENAME), "wb") as fh:
        fh.write(canonical.canonical_json(doc).encode("utf-8"))
    return root


def as_legacy_manifest(doc: dict[str, Any]) -> None:
    """Turn the staged release into the LEGACY manifest shape it must refuse."""
    doc["schema"] = LEGACY_RELEASE_SCHEMA
    doc["artifacts"] = doc.pop("components")
    doc.pop("selector", None)


def scorer_view_sha256(root: str) -> str:
    with open(os.path.join(str(root), SCORER_VIEW_FILENAME)) as fh:
        return canonical.content_hash(json.load(fh))


# --------------------------------------------------------------------------- #
# The staged temporal arm release, written by the PRODUCER (an untrusted source).
# --------------------------------------------------------------------------- #
# ONE fixture target is deliberately NOT EVALUABLE (it fails base QC at both conditions).
# Without it, every row would be rankable and the RETAINED-ROW rule would be untested while
# appearing to be tested: "drop the unrankable rows" would drop nothing, and an attack that
# dropped them would look identical to an honest bundle.
UNEVALUABLE_TARGET_I = 0
UNEVALUABLE_TARGET = P.TARGETS[UNEVALUABLE_TARGET_I]
N_EVALUABLE_TARGETS = len(P.TARGETS) - 1


def _endpoints(condition: str):
    """Six synthetic endpoints, ONE of which the base QC excluded. Fixture only."""
    out = []
    for i in range(len(P.TARGETS)):
        if i == UNEVALUABLE_TARGET_I:
            out.append(P.endpoint(i, condition, base_qc_passed=False,
                                  base_qc_state="excluded_low_target_expression",
                                  base_qc_reasons="fixture_excluded_low_expression"))
        else:
            out.append(P.endpoint(i, condition))
    return out


# --------------------------------------------------------------------------- #
# The ADMITTED DIRECT all-arm bundles the temporal endpoints are built from.
# SYNTHETIC — but real in SHAPE: the schema, the increase/decrease rows and the W10
# admission are exactly what the production chain hands the temporal producer.
# --------------------------------------------------------------------------- #
DIRECT_BUNDLE_SCHEMA = "spot.stage02_direct_arm_bundle.v1"
# THE REAL W10 CONTRACT. Its native report — self-hashed, gate-listing, artifact-binding —
# and it carries NO ``admitted`` boolean. Requiring one would be requiring a field that does
# not exist, and would refuse a sound report.
W10_VERIFIER_ID = "spot.stage02.direct.arm_bundle.verifier.v1"
W10_REPORT_SCHEMA = "spot.stage02_direct_arm_bundle_verification.v1"
VERIFICATION_SLOT_SCHEMA = "spot.stage02_arm_bundle_verification.v1"

# The SYNTHETIC W10 verifier. It is not the production one and says so: the production spec,
# code and 90-gate profile are FROZEN, and a fixture cannot forge a gate list that hashes to
# the real inventory. So the suite pins its OWN, and
# ``TestTheW10Contract`` checks the production pins against the real frozen values and proves
# a weak report is refused under them.
FIXTURE_W10_SPEC_SHA256 = "a1" * 32
FIXTURE_W10_CODE_SHA256 = "b2" * 32
def _fixture_w10_gates():
    """The SECURITY-CRITICAL gates W10 must have run, plus filler.

    They are enforced ALWAYS — a fixture may override the exact-inventory hash (it cannot
    reproduce 80 gate names verbatim) but it may not thereby switch the gate CONTENT check
    off. So the fixture's inventory carries them, exactly as a real report would.
    """
    from verify_temporal_arms import w10

    return list(w10.REQUIRED_GATE_SUBSTRINGS) + [
        f"fixture filler gate {i:02d}" for i in range(4)]


FIXTURE_W10_GATES = _fixture_w10_gates()


def w10_pins():
    """The SYNTHETIC pins. ``is_production=False`` — this is not the production verifier."""
    from direct.hashing import content_hash
    from verify_temporal_arms import w10

    return w10.Pins(
        spec_sha256=FIXTURE_W10_SPEC_SHA256,
        verifier_code_sha256=FIXTURE_W10_CODE_SHA256,
        gate_inventory_sha256=content_hash(FIXTURE_W10_GATES),
        n_gates=len(FIXTURE_W10_GATES),
        expected_files=w10.EXPECTED_FILES,
        is_production=False)


def stage_direct_bundles(root) -> tuple[dict[str, str], dict[str, str]]:
    """One admitted Direct all-arm bundle per condition, in the REAL MULTI-FILE shape.

    Each bundle directory carries its manifest, its rows (parquet), its provenance — and the
    producer's own ``verification.json`` PLACEHOLDER, which says in its own bytes that it is
    not an admission (``admitted=false``, ``verifier_id=null``, verdict pending). The
    INDEPENDENT admission is a SEPARATE file, and that is what the verifier is pointed at: a
    producer that could admit itself by shipping a file with the right name in the right
    place would not be admitted by anybody.
    """
    import pandas as pd
    from direct.hashing import canonical_num, content_hash
    from direct.temporal.arms import arm_env
    from direct.temporal.arms import arm_estimand as est

    root = str(root)
    os.makedirs(root, exist_ok=True)
    bundles, reports = {}, {}
    for cond in CONDITIONS:
        rows = []
        for i in range(len(P.TARGETS)):
            deltas = est.project_programs(P.effect_row(i, cond), P.admitted(),
                                          P.GENE_INDEX, set())
            passed = i != UNEVALUABLE_TARGET_I
            for pid in PORTABLE_IDS:
                d = deltas[pid]
                bd = canonical_num(d["delta"])
                for change in ("increase", "decrease"):
                    sign = 1 if change == "increase" else -1
                    value = None if bd is None else (0.0 if bd == 0 else sign * bd)
                    rows.append({
                        "arm_key": f"direct|{pid}|{change}|{cond}", "program_id": pid,
                        "desired_change": change, "condition": cond,
                        "target_id": P.TARGETS[i], "base_delta": bd,
                        "value": canonical_num(value), "rank": None, "evaluable": passed,
                        "projection_status": d["status"],
                        "base_state": ("base_qc_passed" if passed
                                       else "excluded_low_target_expression"),
                        "base_passed": passed,
                        "n_panel_surviving": d["n_panel_surviving"],
                        "n_control_surviving": d["n_control_surviving"]})

        run_id = f"direct-{cond}"
        rows_sha = content_hash(rows)
        d = os.path.join(root, f"direct_{cond}")
        os.makedirs(d, exist_ok=True)
        pd.DataFrame(rows).to_parquet(os.path.join(d, "arms.parquet"))
        with open(os.path.join(d, "arm_bundle.json"), "w") as fh:
            json.dump({"schema_version": DIRECT_BUNDLE_SCHEMA,
                       "arm_bundle_run_id": run_id, "condition": cond,
                       "arm_rows_sha256": rows_sha, "n_arm_rows": len(rows)}, fh)
        # THE EXACT ELEVEN FILES a Direct all-arm bundle is made of. W10 binds all of them,
        # and an artifact map that named fewer would leave the rest unadmitted.
        pd.DataFrame([{"target_id": t, "n": 1} for t in P.TARGETS]).to_parquet(
            os.path.join(d, "masks.parquet"))
        pd.DataFrame([{"target_id": t, "guide": "g1"} for t in P.TARGETS]).to_parquet(
            os.path.join(d, "contributing_guides.parquet"))
        pd.DataFrame([{"target_id": t, "n_guides": 2} for t in P.TARGETS]).to_parquet(
            os.path.join(d, "guide_support.parquet"))
        pd.DataFrame([{"target_id": t, "n_donors": 2} for t in P.TARGETS]).to_parquet(
            os.path.join(d, "donor_support.parquet"))
        for name, doc_ in (("input_manifest.json", {"inputs": []}),
                           ("gene_universe.json", {"genes": list(P.GENES)}),
                           ("target_identity.json",
                            {"targets": [{"target_id": t, "namespace": "fixture"}
                                         for t in P.TARGETS]})):
            with open(os.path.join(d, name), "w") as fh:
                json.dump(doc_, fh)

        with open(os.path.join(d, "provenance.json"), "w") as fh:
            json.dump({"run_binding": {
                "condition": cond, "scorer_view_sha256": "5" * 64,
                "gene_universe_sha256": "6" * 64,
                "environment_lock": {"sha256": arm_env.AUTHORITATIVE_ENV_LOCK_SHA256},
                "arm_rows_sha256": rows_sha}}, fh)
        # the producer's PLACEHOLDER SLOT — an empty slot, never a verdict
        with open(os.path.join(d, "verification.json"), "w") as fh:
            json.dump({"schema_version": VERIFICATION_SLOT_SCHEMA,
                       "arm_bundle_run_id": run_id, "verifier_id": None,
                       "verdict": "pending_independent_verification",
                       "admitted": False, "self_admitted": False}, fh)
        bundles[cond] = d

        # the SEPARATE independent admission, in W10's NATIVE shape
        w10 = os.path.join(root, f"w10_{cond}.json")
        with open(w10, "w") as fh:
            fh.write(canonical.canonical_json(
                w10_report(d, cond, run_id, rows_sha)))
        reports[cond] = w10
    return bundles, reports


def w10_report(bundle_dir: str, condition: str, run_id: str, rows_sha: str,
               *, mutate=None, legacy_booleans: bool = True,
               n_targets: Optional[int] = None,
               n_arm_rows: Optional[int] = None) -> dict[str, Any]:
    """W10's NATIVE report: self-hashed, gate-listing, artifact-binding, and carrying NO
    ``admitted`` boolean — because it ships the evidence a boolean would have stood for."""
    from direct.hashing import content_hash
    from direct.temporal.arms import arm_env

    n_targets = len(P.TARGETS) if n_targets is None else n_targets
    n_arm_rows = (len(PORTABLE_IDS) * len(P.TARGETS) * 2 if n_arm_rows is None
                  else n_arm_rows)

    artifact_sha256 = {}
    for name in sorted(os.listdir(bundle_dir)):
        fp = os.path.join(bundle_dir, name)
        if os.path.isfile(fp):
            with open(fp, "rb") as fh:
                artifact_sha256[name] = canonical.sha256_hex(fh.read())

    gates = list(FIXTURE_W10_GATES)
    body = {
        "schema_version": W10_REPORT_SCHEMA,
        "verifier_id": W10_VERIFIER_ID,
        "spec_sha256": FIXTURE_W10_SPEC_SHA256,
        "verifier_code_sha256": FIXTURE_W10_CODE_SHA256,
        "independent_of_generator": True,
        "generator_modules_not_imported": ["direct.arm_bundle"],
        "gate_inventory": gates,
        "gate_inventory_sha256": content_hash(gates),
        "bound_artifact": {
            "arm_bundle_run_id": run_id,
            "condition": condition,
            "solver_lock_sha256": arm_env.AUTHORITATIVE_ENV_LOCK_SHA256,
            "arm_rows_sha256": rows_sha,
            "artifact_sha256": artifact_sha256,
            # PRODUCTION mode: every base delta re-derived, and the counts say so.
            # W10's DEFAULT is ``sample`` — a spot-check, wearing the same 90 gates.
            "recompute_mode": "all",
            "n_targets_recomputed": n_targets,
            "n_masks_rederived": n_targets,
            "n_targets_in_bundle": n_targets,
            "n_arm_rows": n_arm_rows,
        },
        "gates": [{"gate": g, "passed": True, "detail": ""} for g in gates],
        "n_gates": len(gates), "n_passed": len(gates), "n_failed": 0,
        "failed_gates": [],
        "verdict": "ADMIT",
    }
    if legacy_booleans:
        # W5-SIDE COMPATIBILITY SHIM, and nothing more. W5's ``arm_direct_source`` still
        # refuses a report carrying no ``admitted``/``self_admitted`` — fields W10's native
        # report does not have and never had. That is the rc17 MISSING_W10 false refusal, and
        # it is W5's to drop.
        #
        # THIS VERIFIER IGNORES THEM ENTIRELY. It validates the native report's own evidence:
        # the self-hash, the gate list, and the artifact map. The shim exists only so the
        # producer can still build a release for the suite to verify, and it must live INSIDE
        # the signed body — a key bolted on afterwards is exactly what the self-hash exists to
        # catch, and adding one would make an honest report look tampered.
        body.update({"admitted": True, "self_admitted": False})
    if mutate:
        mutate(body)
    return dict(body, report_sha256=content_hash(body))


def stage_bundles(release_root: str, out_root, direct=None, w10=None,
                  env_lock: Optional[str] = None) -> str:
    """Emit the six ordered-pair bundles from TWO ADMITTED DIRECT BUNDLES per pair.

    The endpoints are the Direct bundles' base deltas — never a fixture effect source. The
    temporal difference-in-differences is therefore a difference of two admitted Direct
    releases, which is the only thing that makes it checkable.
    """
    from direct.temporal.arms import arm_direct_source as src
    from verify_temporal_arms import release as R

    out_root = str(out_root)
    os.makedirs(out_root, exist_ok=True)
    bound = R.load_release(release_root)
    stage1 = {
        "release_self_sha256": bound.release_self_sha256,
        "scorer_view_raw_sha256": bound.scorer_view_raw_sha256,
        "scorer_view_canonical_sha256": bound.scorer_view_sha256,
        "selector_condition_sequence": list(bound.conditions),
        "per_program_projection_sha256": dict(bound.program_projection_sha256),
        "registry_scorer_projection_sha256": bound.scorer_projection_sha256,
    }
    from direct.temporal.arms import arm_env

    admitted = P.admitted()
    loaded = {c: src.load_direct_bundle(direct[c], expect_condition=c,
                                        w10_report=w10[c]) for c in CONDITIONS}
    # the REAL authoritative lock, verified from its bytes — not a synthetic stand-in
    lock_block = arm_env.env_lock_block(env_lock) if env_lock else None

    bundles = []
    for a, b in ORDERED_PAIRS:
        bundles.append(P.build(
            a, b, scorer_view_sha256=bound.scorer_view_sha256, stage1=stage1,
            from_endpoints=src.endpoints(loaded[a], admitted),
            to_endpoints=src.endpoints(loaded[b], admitted),
            endpoint_source=src.source_binding(loaded[a], loaded[b]),
            **({"env_lock": lock_block} if lock_block else {})))
    arm_emit.emit_release(bundles, out_root, expect_n_bundles=len(ORDERED_PAIRS))
    return out_root


# THE AUTHORITATIVE STAGE-2 SOLVER LOCK — the REAL one, not a synthetic stand-in.
#
# It is the file Direct, pathway and the real run are pinned to. The suite uses ITS ACTUAL
# BYTES: a fixture that invented a lock would verify the lock machinery against a lock
# nobody uses, and the one thing this gate exists to catch — a lane pinned to a DIFFERENT
# environment — is exactly what an invented lock cannot catch.
#
# It lives on the Direct lane's branch, so it is read out of git rather than copied into
# this one: copying it would create a second authoritative lock, which is the defect.
AUTHORITATIVE_LOCK_PATH = "02_geneskew/analysis/stage02_solver_lock.txt"
AUTHORITATIVE_LOCK_SHA256 = (
    "2983d140941f13d223dad93bae71434663882f23f25f6717c3debe59d2711abe")
AUTHORITATIVE_LOCK_REFS = ("HEAD", "agent/stage2-direct-v3", "agent/stage2-integration")
ENV_LOCK_FILENAME = "stage02_solver_lock.txt"


def authoritative_lock_bytes() -> bytes:
    """The real lock's bytes, and they must hash to the authoritative sha or we do not use
    them: a lock that does not hash to 2983d140... is not the lock every lane is pinned to."""
    import subprocess

    repo = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    for ref in AUTHORITATIVE_LOCK_REFS:
        out = subprocess.run(("git", "-C", repo, "show",
                              f"{ref}:{AUTHORITATIVE_LOCK_PATH}"),
                             capture_output=True)
        if out.returncode == 0 and \
                canonical.sha256_hex(out.stdout) == AUTHORITATIVE_LOCK_SHA256:
            return out.stdout
    raise RuntimeError(
        f"the authoritative Stage-2 solver lock ({AUTHORITATIVE_LOCK_PATH}, sha "
        f"{AUTHORITATIVE_LOCK_SHA256[:16]}...) was not found on any of "
        f"{list(AUTHORITATIVE_LOCK_REFS)}. The suite will not substitute an invented one")


def env_lock_sha256() -> str:
    return AUTHORITATIVE_LOCK_SHA256


def stage_env_lock(root) -> str:
    """Stage the AUTHORITATIVE lock's real bytes for the verifier to re-hash."""
    os.makedirs(str(root), exist_ok=True)
    path = os.path.join(str(root), ENV_LOCK_FILENAME)
    with open(path, "wb") as fh:
        fh.write(authoritative_lock_bytes())
    return path


def bind_env_lock(release_root: str, bundle_root: str, env_lock_path: str) -> None:
    """Bind the env lock into every bundle's build identity, and reseal.

    The producer does not yet emit ``env_lock_sha256``; this stands in for it, so the rest
    of the suite can exercise the gate. ``stage_all`` leaves it out, and
    ``TestTheEnvironmentLock`` runs on the bytes exactly as the producer emits them.
    """
    with open(env_lock_path, "rb") as fh:
        sha = canonical.sha256_hex(fh.read())
    for name in sorted(os.listdir(bundle_root)):
        d = os.path.join(bundle_root, name)
        bpath = os.path.join(d, schema.BUNDLE_FILENAME)
        if not os.path.isdir(d) or not os.path.exists(bpath):
            continue
        with open(bpath) as fh:
            bundle = json.load(fh)
        bundle["code_identity"]["env_lock_sha256"] = sha
        bundle["code_identity"]["env_lock_name"] = os.path.basename(env_lock_path)
        _reseal_dir(release_root, bundle_root, d, bundle)


def stage_all(tmp_path) -> tuple[str, str]:
    """A complete release: the Stage-1 root and the temporal bundle root.

    The bytes are the PRODUCER'S, exactly as it emits them — bundle, provenance, preflight,
    rankings, and the immutable content-addressed root inventory. NOTHING is repaired here:
    an independent verifier that pre-fixed the artifact before judging it would be judging
    its own edit.
    """
    return stage_full(tmp_path)[:2]


def stage_full(tmp_path):
    """The complete PRODUCTION shape: the Stage-1 release, the admitted Direct all-arm
    bundles and their W10 admissions, the authoritative Stage-2 solver lock, and the
    temporal release built from all of them. No fixture effect source anywhere."""
    release_root = stage_release(os.path.join(str(tmp_path), "stage1"))
    direct, w10 = stage_direct_bundles(os.path.join(str(tmp_path), "direct"))
    lock = stage_env_lock(os.path.join(str(tmp_path), "env"))
    bundle_root = stage_bundles(release_root, os.path.join(str(tmp_path), "temporal"),
                                direct, w10, env_lock=lock)
    return release_root, bundle_root, direct, w10, lock


def pair_dir(bundle_root: str, from_condition: str, to_condition: str) -> str:
    return os.path.join(str(bundle_root), f"{from_condition}__to__{to_condition}")


def read_bundle(bundle_root: str, from_condition: str, to_condition: str) -> dict:
    with open(os.path.join(pair_dir(bundle_root, from_condition, to_condition),
                           schema.BUNDLE_FILENAME)) as fh:
        return json.load(fh)


def reseal_inventory(release_root: str, bundle_root: str) -> None:
    """Rebuild the producer's ROOT INVENTORY over the (tampered) bytes now on disk.

    This is what a competent attacker does last: every file and ranking hash is recomputed
    and the inventory re-addresses itself, so the release is once again internally perfect
    and only the SCIENCE is wrong.
    """
    ipath = os.path.join(bundle_root, schema.INVENTORY_FILENAME)
    if not os.path.exists(ipath):
        return
    with open(ipath) as fh:
        inv = json.load(fh)

    kept = []
    for entry in inv["bundles"]:
        d = os.path.join(bundle_root, entry["relative_dir"])
        bpath = os.path.join(d, schema.BUNDLE_FILENAME)
        if not os.path.exists(bpath):
            # reseal AROUND the gap rather than leave a dangling entry: the inventory then
            # looks internally perfect and is simply short
            continue
        kept.append(entry)
        with open(bpath) as fh:
            bundle = json.load(fh)
        entry["bundle_id"] = bundle["bundle_id"]
        entry["n_arms"] = bundle["n_arms"]
        entry["arm_keys"] = list(bundle["arm_keys"])
        for group in ("files", "rankings"):
            rebuilt = {}
            for rel in sorted(entry.get(group) or {}):
                fp = os.path.join(d, rel)
                if not os.path.exists(fp):
                    continue
                with open(fp, "rb") as fh:
                    raw = fh.read()
                rebuilt[rel] = {"raw_sha256": canonical.sha256_hex(raw),
                                "canonical_sha256": canonical.content_hash(json.loads(raw))}
            entry[group] = rebuilt

    inv["bundles"] = kept
    inv["n_bundles"] = len(kept)
    inv["n_logical_arms"] = sum(len(b["arm_keys"]) for b in kept)
    inv["arm_keys"] = sorted(k for b in kept for k in b["arm_keys"])
    inv.pop("release_id", None)
    inv["release_id"] = canonical.content_hash(inv)
    with open(ipath, "wb") as fh:
        fh.write(canonical.canonical_json(inv).encode("utf-8"))


def _reseal_dir(release_root: str, bundle_root: str, d: str, bundle: dict, *,
                reseal_bundle_id: bool = True, reseal_rankings: bool = True) -> None:
    """Make ONE bundle directory self-consistent again after a mutation.

    Rewrites the ranking bytes each arm binds, the bundle, its provenance and the producer's
    verdict file — so every hash agrees and the producer still says ADMIT. Only the SCIENCE
    is left wrong, which is the only interesting kind of attack.
    """
    if reseal_bundle_id:
        payload = {k: v for k, v in bundle.items() if k != "bundle_id"}
        bundle["bundle_id"] = canonical.content_hash(payload)[:16]

    if reseal_rankings:
        for arm in bundle.get("arms", []):
            binding = arm.get("ranking")
            if not isinstance(binding, dict) or "path" not in binding:
                continue
            obj = {"schema_version": schema.SCHEMA_RANKING, "arm_key": arm["arm_key"],
                   "ranked": arm["records"]}
            rraw = canonical.canonical_json(obj).encode("utf-8")
            rpath = os.path.join(d, binding["path"])
            os.makedirs(os.path.dirname(rpath), exist_ok=True)
            with open(rpath, "wb") as fh:
                fh.write(rraw)
            binding["raw_sha256"] = canonical.sha256_hex(rraw)
            binding["canonical_sha256"] = canonical.content_hash(obj)
        # the ranking hashes are bundle content, so the id covers them
        if reseal_bundle_id:
            payload = {k: v for k, v in bundle.items() if k != "bundle_id"}
            bundle["bundle_id"] = canonical.content_hash(payload)[:16]

    raw = canonical.canonical_json(bundle).encode("utf-8")
    with open(os.path.join(d, schema.BUNDLE_FILENAME), "wb") as fh:
        fh.write(raw)

    ppath = os.path.join(d, schema.PROVENANCE_FILENAME)
    if os.path.exists(ppath):
        with open(ppath) as fh:
            prov = json.load(fh)
        prov["bundle_id"] = bundle.get("bundle_id")
        prov["bundle_key"] = bundle.get("bundle_key")
        prov["bundle_raw_sha256"] = canonical.sha256_hex(raw)
        prov["bundle_canonical_sha256"] = canonical.content_hash(bundle)
        for k in ("n_programs", "n_arms", "n_targets", "n_base_records"):
            if k in bundle:
                prov[k] = bundle[k]
        praw = canonical.canonical_json(prov).encode("utf-8")
        with open(ppath, "wb") as fh:
            fh.write(praw)
    else:
        praw = b""

    reseal_inventory(release_root, bundle_root)


def reseal(release_root: str, bundle_root: str, from_condition: str, to_condition: str,
           mutate: Callable[[dict], None], *, reseal_bundle_id: bool = True) -> None:
    """Mutate ONE bundle and make the WHOLE release self-consistent again."""
    d = pair_dir(bundle_root, from_condition, to_condition)
    with open(os.path.join(d, schema.BUNDLE_FILENAME)) as fh:
        bundle = json.load(fh)
    mutate(bundle)
    _reseal_dir(release_root, bundle_root, d, bundle,
                reseal_bundle_id=reseal_bundle_id)


def tamper_ranking(release_root: str, bundle_root: str, from_condition: str,
                   to_condition: str, mutate_ranking: Callable[[dict], None]) -> None:
    """Change a RANKING FILE's bytes while the bundle JSON is fully resealed around it.

    The bundle, its provenance and the producer's verdict all agree with each other. ONLY
    the bound ranking bytes disagree with the arm that binds them — which is exactly the
    case an arm's own summary can never detect, because the arm is the thing being lied
    about.
    """
    d = pair_dir(bundle_root, from_condition, to_condition)
    with open(os.path.join(d, schema.BUNDLE_FILENAME)) as fh:
        bundle = json.load(fh)
    # reseal the bundle FIRST (rankings included), then tamper with the ranking file alone
    _reseal_dir(release_root, bundle_root, d, bundle)

    arm = bundle["arms"][0]
    rpath = os.path.join(d, arm["ranking"]["path"])
    with open(rpath) as fh:
        ranking = json.load(fh)
    mutate_ranking(ranking)
    with open(rpath, "wb") as fh:
        fh.write(canonical.canonical_json(ranking).encode("utf-8"))


def inject_into_inventory(bundle_root: str, key: str, value: Any) -> None:
    """Put a machine path (or any other contraband) into the release index, sealed."""
    ipath = os.path.join(bundle_root, schema.INVENTORY_FILENAME)
    with open(ipath) as fh:
        inventory = json.load(fh)
    inventory["bundles"][0][key] = value
    with open(ipath, "wb") as fh:
        fh.write(canonical.canonical_json(inventory).encode("utf-8"))


def drop_bundle(release_root: str, bundle_root: str, from_condition: str,
                to_condition: str) -> None:
    """Remove one whole ordered-pair bundle, and reseal the index around the gap."""
    shutil.rmtree(pair_dir(bundle_root, from_condition, to_condition))
    reseal_inventory(release_root, bundle_root)
