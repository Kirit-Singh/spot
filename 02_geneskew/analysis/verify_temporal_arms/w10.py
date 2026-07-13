"""THE W10 ADMISSION CONTRACT — the whole of it, not the parts that were easy to parse.

A partial parser is a forger's specification. Check the schema, the id, the verdict and a
self-hash, and you have described exactly the document an attacker will write: correct on
every field you looked at, and a fabrication everywhere else. A self-hashed report with one
invented passing gate, no spec or code identity, and an artifact map naming a single file
satisfies all of that — and admits nothing.

So this module checks the report against WHAT W10 IS, not against what a reader hoped to find:

  THE VERIFIER'S OWN IDENTITY
    ``spec_sha256`` and ``verifier_code_sha256`` pin WHICH verifier, running WHICH spec,
    produced the verdict. Without them "an independent lane admitted it" names no lane, and
    any process could have written the sentence.

  THE GATE PROFILE
    ``n_gates`` and ``gate_inventory_sha256`` pin WHAT WAS CHECKED. A report that ran one gate
    and passed it is a passing report; it is not an admission. The gate RECORDS must also
    agree with the inventory they claim — same names, same order, no duplicates, every one
    passed, and the counts consistent with the records rather than merely with each other.

  THE ARTIFACT MAP
    The EXACT, COMPLETE file set W10 binds. Not a subset: an admission that named only
    ``arm_bundle.json`` would leave every other byte in the bundle unadmitted while looking
    like an admission of the whole of it. Not a superset, and no duplicates. And every file must
    still hash to what it hashed to when the report was written.

  THE BOUND ARTIFACT
    Every field present and non-null, and each cross-checked against the bundle in hand.

The production pins below are FROZEN. They are the default, so a caller who supplies nothing
gets the strict check; a synthetic fixture must say out loud that it is not the production
verifier.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Optional

from .canonical import content_hash, file_sha256

W10_REPORT_SCHEMA = "spot.stage02_direct_arm_bundle_verification.v1"
W10_VERIFIER_ID = "spot.stage02.direct.arm_bundle.verifier.v1"
W10_ADMIT = "ADMIT"

# The producer's empty slot. PENDING, un-admitted, and it says so in its own bytes.
VERIFICATION_SLOT_SCHEMA = "spot.stage02_arm_bundle_verification.v1"
PENDING_VERDICT = "pending_independent_verification"

# --------------------------------------------------------------------------- #
# THE FROZEN PRODUCTION PINS. WHICH verifier, WHICH spec, and WHAT it checked.
#
# Pinned to a COMMIT, not to a branch. A branch moves; a verification does not — and a pin
# that follows a branch is not a pin. ``test_the_w10_code_sha_rederives_from_the_pinned_commit``
# re-derives the code hash from that commit with W10's own recipe (sha256 of the canonical
# {module: sha256} map over its eight modules), so a stale or mistyped pin fails loudly here
# rather than silently admitting a verifier nobody checked.
#
# The PRODUCTION BUNDLE profile is the invocation that actually admits: it binds the Stage-1
# v3 release, pins the H5AD object, and recomputes EVERY target
# (``--stage1-v3-release --expect-h5ad-sha256 --recompute all``). 80 gates, exactly, in order.
# --------------------------------------------------------------------------- #
W10_PINNED_VERIFIER_COMMIT = "9965d64e50cd4a38fb6067a35c00bd7a5a7babef"
W10_VERIFIER_MODULES = (
    "verify_arm_bundle.py", "verify_arm_gates.py", "verify_arm_report.py",
    "verify_arm_rules.py", "verify_arm_science.py", "verify_arm_view.py",
    "verify_arm_recompute.py", "verify_direct_release.py",
)

FROZEN_SPEC_SHA256 = (
    "c477356278c5b7d2842659f5354792c9db7203ee774f8dd70653921124477a9f")
FROZEN_VERIFIER_CODE_SHA256 = (
    "3bc55ba51f6a8a619e9a8f47e4fd8d6318811c92048948159e8d03a93210a834")

PROFILE_BUNDLE_PRODUCTION = "spot.stage02.direct.bundle.production.v1"
FROZEN_GATE_INVENTORY_SHA256 = (
    "d98200175b528dec569655e558944d065c1280c19874c4e555ff0bbdb66c1cc4")
FROZEN_N_GATES = 80

# THE GATES THAT MUST HAVE RUN — whatever profile is pinned.
#
# The exact-inventory hash is the strong check, and a caller may override it (a synthetic
# fixture cannot reproduce 80 gate names verbatim). But an override must not turn the gate
# content check OFF: that would leave a fixture-pinned run checking no gates at all, and a
# resealed report that quietly deleted the mask check would sail through.
#
# So these substrings are enforced ALWAYS, pins or no pins. They are the security-critical
# gates, matched as substrings so W10 can reword a detail without silently dropping the
# requirement.
REQUIRED_GATE_SUBSTRINGS = (
    "matches the BYTES ON DISK",
    "the MASK's identity is bound into the run and RE-DERIVES from the shipped "
    "masks.parquet",
    "every SHIPPED mask is the one the verifier independently derives",
    "the supplied solver lock's BYTES hash to the hard-pinned Stage-2 lock",
    "the lock the bundle bound IS the hard-pinned Stage-2 lock",
    "the PRODUCER did not admit its own output",
    "the bundle's admitted set EQUALS the independently derived set",
    "every arm value is the EXACT sign transform",
    "every rank RE-DERIVES per arm",
    "every emitted base delta RE-DERIVES from the bound DE data",
    "the run id RE-DERIVES from its own binding",
)

# THE EXACT, COMPLETE artifact set a Direct all-arm bundle is made of. Eleven files, and an
# admission binds all eleven: a map naming fewer would leave the others unadmitted while
# reading as an admission of the whole bundle.
EXPECTED_FILES = frozenset({
    "arm_bundle.json", "provenance.json", "arms.parquet", "masks.parquet",
    "contributing_guides.parquet", "guide_support.parquet", "donor_support.parquet",
    "input_manifest.json", "gene_universe.json", "target_identity.json",
    "verification.json",
})

# Every field the bound artifact must carry. A null here is a binding that binds nothing.
BOUND_REQUIRED = (
    "arm_bundle_run_id", "condition", "solver_lock_sha256", "arm_rows_sha256",
    "artifact_sha256", "recompute_mode", "n_targets_recomputed", "n_masks_rederived",
    "n_targets_in_bundle", "n_arm_rows",
)

# THE PRODUCTION RECOMPUTE MODE.
#
# W10's ``--recompute`` DEFAULTS TO ``sample`` — it re-derives a handful of targets and
# reports on those. That is a DIAGNOSTIC, and it is a perfectly good one; it is not an
# admission. A sample report carries the same 90 gate names and the same inventory hash as a
# full one, so a checker that stopped at the gate profile would take a spot-check of eight
# targets for a verification of the bundle, and every number the temporal lane then
# differenced would stand on numbers nobody re-derived.
#
# ``all`` is the production mode: EVERY base delta re-derived. And "all" has to mean all —
# the counts must show it, against the bundle actually in hand.
RECOMPUTE_ALL = "all"
RECOMPUTE_SAMPLE = "sample"


@dataclass(frozen=True)
class Pins:
    """WHICH W10 must have signed this. Production by default; a fixture must say otherwise."""
    spec_sha256: str = FROZEN_SPEC_SHA256
    verifier_code_sha256: str = FROZEN_VERIFIER_CODE_SHA256
    gate_inventory_sha256: str = FROZEN_GATE_INVENTORY_SHA256
    n_gates: int = FROZEN_N_GATES
    expected_files: frozenset = EXPECTED_FILES
    is_production: bool = True


def check(f, rep: dict[str, Any], *, condition: str, bundle_dir: str,
          rows_sha256: Optional[str], solver_lock_sha256: str, where: str,
          pins: Optional[Pins] = None,
          bundle_facts: Optional[dict[str, int]] = None) -> None:
    """The WHOLE contract. Every gate below is one an attacker would otherwise walk through."""
    pins = pins or Pins()

    # ---- WHOSE report is this ----
    verdict = str(rep.get("verdict") or "")
    if not f.check("the_w10_report_is_the_native_independent_direct_verifiers_report",
                   rep.get("schema_version") == W10_REPORT_SCHEMA
                   and rep.get("verifier_id") == W10_VERIFIER_ID
                   and rep.get("schema_version") != VERIFICATION_SLOT_SCHEMA
                   and verdict != PENDING_VERDICT, where,
                   f"schema {rep.get('schema_version')!r} / verifier "
                   f"{rep.get('verifier_id')!r} / verdict {verdict!r}"):
        return

    # ---- WHICH verifier, running WHICH spec. Without this, "independent" names no lane ----
    f.check("the_w10_report_names_the_frozen_verifier_spec_and_code",
            rep.get("spec_sha256") == pins.spec_sha256
            and rep.get("verifier_code_sha256") == pins.verifier_code_sha256, where,
            f"spec={str(rep.get('spec_sha256'))[:16]}… "
            f"code={str(rep.get('verifier_code_sha256'))[:16]}…; the pinned verifier is "
            f"spec {pins.spec_sha256[:16]}… code {pins.verifier_code_sha256[:16]}…. A report "
            "that does not say WHICH verifier produced it could have been written by any "
            "process at all")
    f.check("the_w10_report_was_written_by_a_lane_that_did_not_produce_the_bytes",
            rep.get("independent_of_generator") is True, where,
            "a report that imported the generator is the generator's opinion of itself")

    _gates(f, rep, pins, where)
    _self_hash(f, rep, where)
    _bound(f, rep, condition, bundle_dir, rows_sha256, solver_lock_sha256, pins, where)
    _recompute(f, rep, bundle_facts or {}, where)


def _gates(f, rep: dict[str, Any], pins: Pins, where: str) -> None:
    """WHAT WAS CHECKED. A report that ran one gate and passed it is not an admission."""
    inventory = list(rep.get("gate_inventory") or [])
    records = list(rep.get("gates") or [])

    f.check("the_w10_report_ran_the_pinned_gate_profile",
            rep.get("gate_inventory_sha256") == pins.gate_inventory_sha256
            and int(rep.get("n_gates") or 0) == pins.n_gates, where,
            f"gate_inventory_sha256={str(rep.get('gate_inventory_sha256'))[:16]}… "
            f"n_gates={rep.get('n_gates')!r}; the pinned profile is "
            f"{pins.gate_inventory_sha256[:16]}… over {pins.n_gates} gates. A report that "
            "ran a different set of gates checked a different thing")
    f.check("the_w10_gate_inventory_hash_covers_the_gates_it_lists",
            rep.get("gate_inventory_sha256") == content_hash(inventory), where,
            "the gate inventory does not hash to what the report says it hashes to")

    # ENFORCED ALWAYS, pins or no pins. Overriding the exact-inventory hash (as a synthetic
    # fixture must) may not turn the gate CONTENT check off — that would leave a run checking
    # no gates at all, and a resealed report that quietly deleted the mask check would sail
    # through on a hash it chose for itself.
    listed = "\n".join(str(x) for x in inventory)
    absent = [g for g in REQUIRED_GATE_SUBSTRINGS if g not in listed]
    f.check("the_w10_inventory_contains_every_security_critical_gate", not absent, where,
            f"{[a[:48] for a in absent[:3]]} did not run. A report that dropped one of these "
            "checked less than it says it did, whatever its inventory hashes to")

    # THE RECORDS MUST BE THE INVENTORY. Not merely the same length: the same gates, in the
    # same order, each appearing once. A report whose records and inventory disagree is a
    # report that lists one set of checks and evidences another.
    names = [str(g.get("gate")) for g in records]
    f.check("the_w10_gate_records_ARE_the_inventory_they_claim",
            names == [str(x) for x in inventory], where,
            f"{len(names)} records against {len(inventory)} listed gates; "
            f"missing={sorted(set(inventory) - set(names))[:3]} "
            f"unexpected={sorted(set(names) - set(inventory))[:3]}")
    f.check("no_w10_gate_is_listed_twice", len(set(names)) == len(names), where,
            "a duplicated gate is a gate counted twice and run once")

    passed = [g for g in records if g.get("passed") is True]
    f.check("every_w10_gate_actually_PASSED",
            len(passed) == len(records) and len(records) == pins.n_gates, where,
            f"{len(passed)}/{len(records)} passed, over {pins.n_gates} pinned gates")
    f.check("the_w10_counts_agree_with_the_records_they_count",
            int(rep.get("n_gates") or 0) == len(records)
            and int(rep.get("n_passed") or 0) == len(passed)
            and int(rep.get("n_failed") or 0) == len(records) - len(passed), where,
            f"n_gates={rep.get('n_gates')!r} n_passed={rep.get('n_passed')!r} "
            f"n_failed={rep.get('n_failed')!r} over {len(records)} records")
    f.check("the_w10_report_actually_ADMITS_this_direct_bundle",
            str(rep.get("verdict")) == W10_ADMIT
            and int(rep.get("n_failed") or 0) == 0
            and not (rep.get("failed_gates") or []), where,
            f"verdict={rep.get('verdict')!r} n_failed={rep.get('n_failed')!r} "
            f"failed_gates={(rep.get('failed_gates') or [])[:3]}")


def _self_hash(f, rep: dict[str, Any], where: str) -> None:
    """A report that could be edited after it was cited is a claim, not a result."""
    body = {k: v for k, v in rep.items() if k != "report_sha256"}
    f.check("the_w10_report_sha256_covers_its_own_content",
            rep.get("report_sha256") == content_hash(body), where,
            f"shipped {str(rep.get('report_sha256'))[:16]}…, its own content hashes to "
            f"{content_hash(body)[:16]}…")


def _bound(f, rep: dict[str, Any], condition: str, bundle_dir: str,
           rows_sha256: Optional[str], solver_lock_sha256: str, pins: Pins,
           where: str) -> None:
    """WHICH bundle it admitted — checked against the bundle actually in hand."""
    bound = rep.get("bound_artifact") or {}

    nulls = sorted(k for k in BOUND_REQUIRED if bound.get(k) in (None, "", {}, []))
    f.check("every_bound_artifact_field_is_present_and_non_null", not nulls, where,
            f"{nulls} are null. A binding that binds nothing is not a binding")

    f.check("the_w10_report_admitted_THIS_condition",
            str(bound.get("condition")) == str(condition), where,
            f"the report admits condition {bound.get('condition')!r}; this endpoint is "
            f"{condition!r}. An admission of another condition admits something else")
    if rows_sha256:
        f.check("the_w10_report_admitted_THESE_arm_rows",
                bound.get("arm_rows_sha256") == str(rows_sha256), where,
                f"the report admits rows {str(bound.get('arm_rows_sha256'))[:16]}…; the rows "
                f"on disk hash to {str(rows_sha256)[:16]}…")
    f.check("the_w10_report_admitted_a_bundle_solved_under_the_authoritative_lock",
            bound.get("solver_lock_sha256") == solver_lock_sha256, where,
            f"the report admits a bundle solved under "
            f"{str(bound.get('solver_lock_sha256'))[:16]}…, not the authoritative "
            f"{solver_lock_sha256[:16]}…")

    _artifact_map(f, bound, bundle_dir, pins, where)


def _recompute(f, rep: dict[str, Any], facts: dict[str, int], where: str) -> None:
    """DID IT ACTUALLY RE-DERIVE THE BUNDLE, or just look at some of it?

    A ``sample`` report is a spot-check. It carries the same gates and the same inventory
    hash as a full one, so the gate profile cannot tell them apart — and taking one for the
    other means every temporal number rests on numbers nobody re-derived.
    """
    bound = rep.get("bound_artifact") or {}
    mode = bound.get("recompute_mode")

    f.check("the_w10_report_recomputed_the_bundle_in_FULL_not_a_sample",
            mode == RECOMPUTE_ALL, where,
            f"recompute_mode={mode!r}. {RECOMPUTE_SAMPLE!r} is W10's DEFAULT and it is a "
            f"DIAGNOSTIC: it re-derives a handful of targets. {RECOMPUTE_ALL!r} is the "
            "production mode — every base delta re-derived. A spot-check is not an "
            "admission, and it wears the same 90 gates")

    n_in_bundle = bound.get("n_targets_in_bundle")
    f.check("the_w10_recomputation_covered_EVERY_target_in_the_bundle",
            bound.get("n_targets_recomputed") == n_in_bundle
            and bound.get("n_masks_rederived") == n_in_bundle
            and isinstance(n_in_bundle, int) and n_in_bundle > 0, where,
            f"recomputed {bound.get('n_targets_recomputed')!r} targets and re-derived "
            f"{bound.get('n_masks_rederived')!r} masks, over {n_in_bundle!r} in the bundle. "
            "'all' has to mean all, and the counts are what say whether it did")

    # ...and the counts must be about THIS bundle, not some other one.
    if "n_targets" in facts:
        f.check("the_w10_target_count_is_the_bundles_own",
                n_in_bundle == facts["n_targets"], where,
                f"the report says {n_in_bundle!r} targets; the bundle on disk has "
                f"{facts['n_targets']!r}")
    if "n_arm_rows" in facts:
        f.check("the_w10_arm_row_count_is_the_bundles_own",
                bound.get("n_arm_rows") == facts["n_arm_rows"], where,
                f"the report says {bound.get('n_arm_rows')!r} arm rows; the bundle on disk "
                f"has {facts['n_arm_rows']!r}")


def _artifact_map(f, bound: dict[str, Any], bundle_dir: str, pins: Pins,
                  where: str) -> None:
    """THE EXACT, COMPLETE FILE SET. Not a subset, not a superset, no duplicates.

    An admission naming only ``arm_bundle.json`` would leave every other byte in the bundle
    unadmitted while reading, to anyone who did not look, as an admission of the whole of it.
    """
    amap = bound.get("artifact_sha256")
    if not f.check("the_w10_artifact_map_names_the_files_it_admitted",
                   isinstance(amap, dict) and bool(amap), where,
                   "the report binds no artifact map; an admission that does not say WHICH "
                   "bytes it admitted cannot be checked against them"):
        return

    got = {os.path.basename(str(k)) for k in amap}
    f.check("the_w10_artifact_map_is_the_EXACT_COMPLETE_bundle_file_set",
            got == set(pins.expected_files), where,
            f"missing={sorted(set(pins.expected_files) - got)} "
            f"unexpected={sorted(got - set(pins.expected_files))}. A SUBSET leaves bytes "
            "unadmitted while reading as an admission of the whole bundle; a SUPERSET admits "
            "files the bundle is not made of")
    f.check("no_file_is_named_twice_in_the_w10_artifact_map",
            len(got) == len(amap), where, "a duplicated path is one file counted twice")

    drift = []
    for rel, sha in sorted(amap.items()):
        fp = os.path.join(bundle_dir, os.path.basename(str(rel)))
        if not os.path.exists(fp):
            drift.append(f"{rel}:absent")
        elif file_sha256(fp) != sha:
            drift.append(f"{rel}:changed")
    f.check("every_file_the_w10_report_admitted_still_hashes_to_what_it_admitted",
            not drift, where,
            f"{drift[:4]}. The admission is of bytes that are no longer on disk")
