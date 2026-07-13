"""THE GATES — every named check the arm-bundle verifier runs.

INDEPENDENCE RULE (test-enforced): imports nothing from the generator. Split out of
``verify_arm_bundle`` so each module keeps one job: this one states WHAT is checked, and
``verify_arm_bundle`` decides the ORDER, carries the report and owns the CLI.

Every gate is fail-closed and NAMED. A gate that cannot be evaluated does not abstain — it
fails, because "we could not check" and "we checked and it was fine" must never reach a
reader as the same verdict.
"""
from __future__ import annotations

import os
import re
import sys
from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import verify_arm_rules as AR  # noqa: E402
from verify_arm_report import (  # noqa: E402
    BUNDLE_RUN_ID_LEN,
    BUNDLE_SCHEMA,
    EXPECTED_FILES,
    INFERENCE_STATUS,
    LANES,
    PROVENANCE_FILE,
    PROVENANCE_SCHEMA,
    RELEASE_LANES,
    REQUEST_SCHEMA,
    RUNNER_ID,
    VERDICT_PENDING,
    VERIFICATION_FILE,
    VERIFICATION_SCHEMA,
    VERIFIER_MODULES,
    Report,
)

# --------------------------------------------------------------------------- #
# THE ARTIFACT GATES: what the bundle IS, what it BINDS, and what it may not carry.
# --------------------------------------------------------------------------- #
_PRODUCER_IMPORT = re.compile(
    r"^\s*(?:from\s+(?:\.|direct)[\w.]*\s+import\b|import\s+direct\b)", re.M)


def gate_independence(rep: Report) -> None:
    """GENERATOR != VERIFIER, asserted against the verifier's OWN SOURCE.

    Deliberately not a check of ``sys.modules``: whatever else is loaded in the process is
    a fact about the caller, not about this verifier. A test harness that drives the
    producer to build a fixture legitimately imports it, and that must not be mistaken for
    the checker importing the thing it checks. What matters is that these four modules do
    not — so that is what is read.
    """
    leaked = []
    for module in VERIFIER_MODULES:
        with open(os.path.join(_HERE, module)) as fh:
            for i, line in enumerate(fh, 1):
                if _PRODUCER_IMPORT.match(line):
                    leaked.append(f"{module}:{i}: {line.strip()}")
    rep.gate("the verifier's own modules import NOTHING from the generator",
             not leaked, f"{leaked[:3]}")


def gate_files(bundle_dir: str, rep: Report) -> Optional[dict]:
    present = {f for f in os.listdir(bundle_dir) if not f.startswith(".")}
    rep.gate("file inventory: exactly the bundle's shipped artifacts, no extras",
             present == EXPECTED_FILES,
             f"extra={sorted(present - EXPECTED_FILES)} "
             f"missing={sorted(EXPECTED_FILES - present)}")
    if not EXPECTED_FILES <= present:
        return None
    return {name: os.path.join(bundle_dir, name) for name in EXPECTED_FILES}


def gate_schemas(doc: dict, prov: dict, rep: Report) -> None:
    rep.gate("the bundle declares the allowlisted schema",
             doc.get("schema_version") == BUNDLE_SCHEMA,
             f"got {doc.get('schema_version')!r}")
    rep.gate("the provenance declares the allowlisted schema",
             prov.get("schema_version") == PROVENANCE_SCHEMA,
             f"got {prov.get('schema_version')!r}")
    binding = prov.get("run_binding") or {}
    request = binding.get("arm_bundle_request") or {}
    rep.gate("the request declares the allowlisted schema",
             request.get("schema_version") == REQUEST_SCHEMA,
             f"got {request.get('schema_version')!r}")
    rep.gate("the runner is the all-arm runner",
             binding.get("runner_id") == RUNNER_ID, f"got {binding.get('runner_id')!r}")
    rep.gate("the lane is allowlisted",
             binding.get("lane") in LANES, f"got {binding.get('lane')!r}")
    rep.gate("no p, q or FDR is claimed: inference_status is not_calibrated",
             prov.get("inference_status") == INFERENCE_STATUS,
             f"got {prov.get('inference_status')!r}")


def gate_no_display_fields(doc: dict, prov: dict, columns: list[str],
                           rep: Report) -> None:
    """RECURSIVELY: no pair-derived, display-only or inference field, anywhere.

    Not "defaulted off" — ABSENT. A field that is not emitted cannot come back as a gate
    in a later pass, and a display label that could refuse a run is exactly M4b.
    """
    hits = AR.forbidden_hits(doc) + AR.forbidden_hits(prov)
    rep.gate("no pair / Pareto / concordance / joint_status / combined / p-q field "
             "appears anywhere in the bundle or its provenance",
             not hits, f"{len(hits)} hit(s): {hits[:4]}")
    col_hits = AR.forbidden_columns(columns)
    rep.gate("no arm ROW carries a pair-derived or display-only column",
             not col_hits, f"{col_hits[:4]}")
    allowed = set(AR.ARM_ROW_COLUMNS) | set(AR.ARM_ROW_EXTRA_COLUMNS)
    rep.gate("the arm table's columns are exactly the allowlisted arm columns",
             set(columns) == allowed,
             f"unexpected={sorted(set(columns) - allowed)} "
             f"missing={sorted(set(AR.ARM_ROW_COLUMNS) - set(columns))}")
    # ...and therefore NO display-only field can gate admission: there is none in the
    # artifact for a gate to read. This is the M4b property, stated as a fact about the
    # bytes rather than as a promise about the checker — a display field cannot decide
    # anything here because a display field cannot BE here.
    rep.gate("no display-only field is available to gate admission",
             not hits and not col_hits,
             "a pair-derived field is present, so admission could turn on one")


def gate_identity(prov: dict, doc: dict, rows: list[dict], rep: Report) -> None:
    """The run id RE-DERIVES from its own binding, and the arm bytes are an input to it."""
    binding = prov.get("run_binding") or {}
    full = AR.sha256_hex(AR.canonical_json(binding))
    rep.gate("the run id RE-DERIVES from its own binding",
             prov.get("arm_bundle_run_id") == full[:BUNDLE_RUN_ID_LEN]
             and prov.get("arm_bundle_run_sha256") == full,
             f"declared={prov.get('arm_bundle_run_id')!r} "
             f"derived={full[:BUNDLE_RUN_ID_LEN]!r}")
    rep.gate("the arm bytes are BOUND into the run identity",
             binding.get("arm_rows_sha256") == doc.get("arm_rows_sha256")
             == AR.rows_sha256(rows),
             "the rows hash in the binding is not the rows hash of the shipped table")

    request = dict(binding.get("arm_bundle_request") or {})
    declared = request.pop("request_sha256", None)
    rep.gate("the arm-bundle request is SELF-HASHED and re-derives",
             declared is not None and AR.content_sha256(request) == declared,
             f"declared={declared!r}")
    rep.gate("the request names a CONTEXT and no program pair",
             request.get("names_a_program_pair") is False and bool(request.get(
                 "condition")),
             f"names_a_program_pair={request.get('names_a_program_pair')!r}")

    stamped = {str(r.get("arm_bundle_run_id")) for r in rows}
    rep.gate("every shipped row is stamped with THIS bundle's run id",
             stamped == {str(prov.get("arm_bundle_run_id"))}, f"{sorted(stamped)[:3]}")


def gate_condition(doc: dict, prov: dict, rows: list[dict], condition: str,
                   rep: Report) -> None:
    binding = prov.get("run_binding") or {}
    request = binding.get("arm_bundle_request") or {}
    conds = {str(r["condition"]) for r in rows}
    rep.gate("the condition is ONE context, and the same one everywhere",
             doc.get("condition") == binding.get("condition")
             == request.get("condition") == condition and conds == {condition},
             f"doc={doc.get('condition')!r} binding={binding.get('condition')!r} "
             f"request={request.get('condition')!r} rows={sorted(conds)} "
             f"asked={condition!r}")


# THE PRODUCER'S DIGEST RECIPE, RESTATED. Never imported from ``direct.code_digest``: a
# recipe the checker borrowed from the thing it is checking is a recipe nobody checked, and
# it would move the instant the producer's constant moved. The ids are restated as LITERALS
# for the same reason — they name WHICH recipe produced the hash, and an artifact does not get
# to tell the checker which rules it was checked under.
CODE_DIGEST_SUFFIXES = (".py", ".json")
CODE_DIGEST_EXCLUDE_DIRS = frozenset({
    "__pycache__", ".pytest_cache", ".git", ".ruff_cache", ".mypy_cache",
    "node_modules", ".ipynb_checkpoints"})
CODE_DIGEST_LEN = 16
CODE_DIGEST_ID = "spot.stage02.code_digest.v1"
CODE_INCLUDE_RULE_ID = "spot.stage02.code_digest.include_rule.py_json_sorted_relpath.v1"
CODE_BINDING_RULE_ID = (
    "spot.stage02.code_digest.binding_rule.commit_cleantree_manifest_digest.v1")


def _git(repo: str, *args: str) -> Optional[str]:
    """stdout on success; None if git could not answer. None is NOT the empty string.

    ``status --porcelain`` says "clean" by printing NOTHING, so a helper that folded a
    failed git call into "" would report a tree it never read as a clean one.
    """
    import subprocess
    try:
        r = subprocess.run(("git", "-C", repo) + args, capture_output=True, text=True,
                           timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def code_manifest(root: str, repo: str) -> tuple[str, int]:
    """(manifest hash, file count) of a code tree: every .py/.json under ``root``,
    repo-relative. The COUNT is returned because the artifact declares one, and a count the
    artifact declares is a count nobody checked."""
    files = []
    for base, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in CODE_DIGEST_EXCLUDE_DIRS)
        for name in sorted(names):
            if name.endswith(CODE_DIGEST_SUFFIXES):
                path = os.path.join(base, name)
                files.append({"path": os.path.relpath(path, repo).replace(os.sep, "/"),
                              "sha256": AR.sha256_file(path)})
    files.sort(key=lambda f: f["path"])
    return AR.content_sha256(files), len(files)


def gate_code_identity(binding: dict, producer_code_root: Optional[str],
                       rep: Report) -> dict:
    """The code identity, RE-DERIVED from the PRODUCER's tree — never the verifier's own.

    THE DEFECT THIS CLOSES. This gate used to walk the verifier's own package directory and
    compare the manifest it got to the one the artifact declared. That number is a fact about
    the checkout the CHECKER is running from, and the run under test was not taken from it.
    Run the verifier out of the producer's tree and it hashes itself, agrees with itself and
    admits — the generator signing its own homework by another route. Run it out of any OTHER
    tree, which is the only independent way to run it, and no honest release can ever be
    admitted, because the manifest it derives is not the manifest the run bound.

    So the producer's tree is an INPUT to verification, exactly like the H5AD: supplied, named
    and checked. Three claims must hold before the digest means anything at all —

      * the tree is a git checkout we can actually interrogate;
      * its HEAD is EXACTLY the commit the run bound (not an ancestor, not a descendant);
      * its working state is the one the run DECLARED — a run may not call an uncommitted
        tree clean, and this is the only place that lie can be caught, because a dirty tree
        and a clean one at the same commit carry the same commit id;

    — and only then is the manifest re-derived from those bytes. On a RELEASE-GRADE lane the
    root may not BE the verifier's own tree: that is the self-check mode, in which every gate
    here lines up by construction because the checker is hashing itself. It is refused, not
    reported. The verifier's OWN identity stays separate (``verifier_code_sha256``): which
    checker ran is a different question from which code was checked, and one may never stand
    in for the other.

    Fail-closed: every gate below is EMITTED on every path. A root that is missing does not
    skip the checks — it fails them, because "we could not check" and "we checked and it was
    fine" must never reach a reader as the same verdict.
    """
    code = binding.get("code_identity") or {}
    declared_commit = code.get("commit")
    declared_clean = code.get("clean_tree")

    root = os.path.abspath(str(producer_code_root)) if producer_code_root else None
    repo = os.path.dirname(root) if root else None
    head = _git(repo, "rev-parse", "HEAD") if repo and os.path.isdir(root) else None
    status = _git(repo, "status", "--porcelain") if head is not None else None

    # THE SELF-CHECK MODE. The supplied root IS the tree this verifier is running from. Every
    # check below would then line up by construction — the checker hashes itself and agrees
    # with itself — and self-agreement is not independence. For a lane that can SHIP, the two
    # trees being SEPARATE is the claim, so it is enforced here, not merely reported. The
    # synthetic lane is exempt by the asymmetry this codebase draws everywhere else (gate
    # profiles, dirty trees): a fixture is a test input, not a provenance record, and its
    # harness necessarily drives the producer out of the checkout under test.
    verifier_tree = os.path.dirname(os.path.dirname(_HERE))          # 02_geneskew/
    is_verifier_tree = bool(root) and os.path.realpath(root) == os.path.realpath(verifier_tree)
    release_grade = binding.get("lane") in RELEASE_LANES

    supplied = bool(root) and os.path.isdir(root) and head is not None
    rep.gate("the PRODUCER's code root is SUPPLIED to the verifier, and it is a git "
             "checkout — a verifier that hashed its OWN tree would be certifying the "
             "checkout it happens to be running from, not the one the run was taken from",
             supplied and not (release_grade and is_verifier_tree),
             (f"--producer-code-root={producer_code_root!r} is the VERIFIER's own Stage-2 "
              f"tree ({verifier_tree!r}). A release-grade run must be verified from a "
              "SEPARATE checkout of the producer's commit: a checker that hashes the tree it "
              "is running from certifies itself, and every gate below would line up by "
              "construction."
              if supplied and release_grade and is_verifier_tree else
              f"--producer-code-root={producer_code_root!r} is not a git checkout on disk. "
              "Supply the producer's Stage-2 tree (02_geneskew) at the commit the run bound"))

    rep.gate("the producer tree's git HEAD IS the commit the run bound",
             supplied and bool(declared_commit) and head == declared_commit,
             f"bound={declared_commit!r} HEAD={head!r} — the supplied tree is not the tree "
             "this run was taken from, so its bytes cannot identify this run")

    observed_clean = (status == "") if status is not None else None
    rep.gate("the producer tree's working state is the one the run DECLARED — a run may not "
             "call an uncommitted tree clean",
             observed_clean is not None and observed_clean == declared_clean,
             f"declared clean_tree={declared_clean!r} observed={observed_clean!r}"
             + (f" ({len(status.splitlines())} uncommitted path(s))" if status else ""))

    # THE WHOLE BLOCK DESCRIBES THIS TREE, or it describes nothing. `manifest_sha256` binds the
    # BYTES; every other field is prose the artifact wrote about itself — and downstream READS
    # and CITES it. A run that hashed 3 files honestly and wrote "n_files: 141" beside the hash
    # has a provenance record whose numbers a reader would check the tree against. So they are
    # re-derived from the same walk, under ids restated here, and a lie in any of them refuses
    # at this gate: one claim, one gate name, no new inventory.
    manifest_sha, n_files = code_manifest(root, repo) if supplied else (None, None)
    declared_root = os.path.relpath(root, repo).replace(os.sep, "/") if supplied else None
    # the producer's dirty-path rule, restated: a porcelain line with a path after column 3
    n_dirty = len([ln for ln in (status or "").splitlines() if ln[3:]]) \
        if status is not None else None

    lies = [] if supplied else ["the producer code root was not supplied, so nothing about "
                                "the declared code identity could be re-derived"]
    if supplied:
        for field, declared, derived in (
                ("manifest_sha256", code.get("manifest_sha256"), manifest_sha),
                ("digest_id", code.get("digest_id"), CODE_DIGEST_ID),
                ("include_rule_id", code.get("include_rule_id"), CODE_INCLUDE_RULE_ID),
                ("binding_rule_id", code.get("binding_rule_id"), CODE_BINDING_RULE_ID),
                ("digest_root", code.get("digest_root"), declared_root),
                ("n_files", code.get("n_files"), n_files),
                ("n_dirty_paths", code.get("n_dirty_paths"), n_dirty)):
            if declared != derived:
                lies.append(f"{field}: declared={declared!r} re-derived={derived!r}")

    rep.gate("the code manifest hash RE-DERIVES from the tree this run claims",
             not lies,
             f"{lies} (walked {root!r}, paths relative to {repo!r})")
    rep.gate("the canonical code digest is the manifest hash's own prefix",
             manifest_sha is not None
             and code.get("canonical_digest") == manifest_sha[:CODE_DIGEST_LEN],
             f"declared={code.get('canonical_digest')!r}")

    rep.gate("the code tree was CLEAN, or the run says out loud that it was not",
             declared_clean is True or code.get("clean_checkout_required") is False,
             f"clean_tree={declared_clean!r} "
             f"clean_checkout_required={code.get('clean_checkout_required')!r}")

    # OBSERVED, not merely declared. The old form asked the artifact whether it was clean; a
    # release-grade lane must be told by the TREE.
    rep.gate("a release-grade lane REFUSES a dirty tree",
             not (release_grade
                  and (declared_clean is not True or observed_clean is not True)),
             f"a release-grade run was taken from an uncommitted tree "
             f"(declared clean_tree={declared_clean!r}, observed={observed_clean!r})")

    return {"producer_code_commit": head if supplied else None,
            "producer_code_manifest_sha256": manifest_sha,
            "producer_code_clean_tree": observed_clean,
            # WHETHER THE CHECK WAS INDEPENDENT AT ALL. Refused outright above on a
            # release-grade lane; reported here so a reader of ANY report can see, without
            # re-running anything, whether the tree hashed as the producer's was the
            # verifier's own.
            "producer_code_root_is_the_verifier_tree": is_verifier_tree}


def gate_inputs(binding: dict, paths: dict[str, str], rep: Report) -> None:
    """Every bound input's bytes, re-hashed from disk. And no PAIR among them."""
    declared = {i["name"]: i for i in (binding.get("stage2_inputs") or [])}

    missing = [n for n in declared if n not in paths or not paths[n]]
    rep.gate("every bound Stage-2 input was supplied to the verifier",
             not missing, f"not supplied: {missing}")

    bad = []
    for name, entry in declared.items():
        path = paths.get(name)
        if not path or not os.path.exists(path):
            continue
        if AR.sha256_file(path) != entry.get("sha256"):
            bad.append(f"{name}: bytes differ from the pinned sha256")
        elif os.path.getsize(path) != entry.get("size_bytes"):
            bad.append(f"{name}: size differs from the pinned size")
    rep.gate("every bound Stage-2 input's BYTES match the hash the run pinned",
             not bad, f"{bad[:3]}")

    # THE POINT OF THE MIGRATION: a reusable bundle's identity may not be a function of a
    # pair. If a pair SELECTION is hashed into the binding, then the same measurement,
    # requested for two pairs, is two bundles again — and the arms cannot be reused. The
    # audit reproduced exactly this: identical rows, two run ids, because an UNUSED pair
    # file moved.
    pair_inputs = sorted(n for n in declared
                         if "selection" in n.lower() or "contract" in n.lower())
    rep.gate("the bundle's identity binds NO pair selection — a reusable arm may not be "
             "keyed by the question that asked for it",
             not pair_inputs, f"pair-scoped input(s) hashed into the run id: "
                              f"{pair_inputs}")


# WHAT THE ROWS WERE ACTUALLY COMPUTED FROM. A consumed input absent from the identity is
# an input a reader cannot check and a run cannot be reconstructed from. (Audit BLOCKER 4.)
CONSUMED_INPUT_BINDINGS = {
    "contributor_manifest": "the contributor manifest the masks were resolved from",
    "mask_sha256": "the masks every base delta was taken under",
    "source_registry_raw_sha256":
        "the source registry the contributor evidence resolves against",
    "target_identity_map": "the run-level target-identity map, supplied or explicitly not",
}


def gate_consumed_inputs_bound(binding: dict, rep: Report) -> None:
    """Every CONSUMED scientific input is in the identity, or the bundle cannot be checked.

    A bundle that omits them records COUNTS where it needs IDENTITIES: "29 rows, 18 scopes"
    cannot tell two different contributor manifests apart, and the masks they imply move
    every base delta in all |admitted| x 2 arms at once.

    ``target_identity_map`` is required to be PRESENT, not to be supplied: a run that used
    no map must say so out loud (``status: not_supplied``), because absence and silence are
    different claims and only one of them can be checked.
    """
    missing = sorted(k for k in CONSUMED_INPUT_BINDINGS if k not in binding)
    empty = sorted(k for k in ("contributor_manifest", "mask_sha256")
                   if not binding.get(k))
    rep.gate("every CONSUMED scientific input is bound into the run identity — the "
             "contributor manifest, the masks, the source registry and the target-identity "
             "map",
             not missing and not empty,
             f"absent={missing} empty={empty} "
             f"({', '.join(CONSUMED_INPUT_BINDINGS[k] for k in missing + empty)})")


# THE PINNED STAGE-2 SOLVER LOCK. Restated here as a LITERAL, never imported from the
# producer's `envlock`: a pin the checker borrowed from the thing it is checking is a pin
# nobody checked, and it would move the instant the producer's constant moved.
PINNED_SOLVER_LOCK_SHA256 = \
    "2983d140941f13d223dad93bae71434663882f23f25f6717c3debe59d2711abe"
SOLVER_LOCK_FILENAME = "stage02_solver_lock.txt"
STAGE1_SOLVER_LOCK_FILENAME = "stage01_solver_lock.txt"


def gate_solver_lock(binding: dict, lock_path: Optional[str],
                     rep: Report) -> Optional[str]:
    """THE ENVIRONMENT the result was computed in — hashed here, and hard-pinned.

    A result whose environment is unrecorded cannot be reproduced, and one whose environment
    is UNBOUND can be re-attributed to a different environment after the fact. So the lock is
    in the run identity, and this gate re-derives it from the bytes rather than reading the
    number the artifact wrote down.

    The pin is a LITERAL here. The decisive attack is the SELF-CONSISTENT FORGERY: swap the
    lock file, and honestly reseal the artifact's `environment_lock` block so its `sha256`,
    its `expected_sha256` and its `verified: true` all agree with each other and the run id
    re-derives. Everything is internally consistent — and it is still the wrong environment.
    Self-consistency is not authenticity, so the ONLY thing that can refuse it is a pin the
    artifact does not get a vote on.
    """
    lock = binding.get("environment_lock") or {}

    supplied = bool(lock_path) and os.path.exists(str(lock_path))
    rep.gate("the Stage-2 solver lock is SUPPLIED to the verifier",
             supplied,
             f"no --env-lock on disk at {lock_path!r}; a run whose environment is unrecorded "
             "cannot be reproduced")

    actual = AR.sha256_file(str(lock_path)) if supplied else None
    is_stage1 = supplied and os.path.basename(str(lock_path)) == \
        STAGE1_SOLVER_LOCK_FILENAME
    hint = (" — that is the STAGE-1 lock: a valid lock for a DIFFERENT environment. The two "
            "lanes do not run the same environment and their locks are not interchangeable"
            if is_stage1 else "")
    rep.gate("the supplied solver lock's BYTES hash to the hard-pinned Stage-2 lock",
             actual == PINNED_SOLVER_LOCK_SHA256,
             f"supplied={actual!r} pinned={PINNED_SOLVER_LOCK_SHA256!r}{hint}. A lock whose "
             "bytes are decided by whoever supplies them pins whatever the supplier wanted")

    rep.gate("the bundle BINDS a solver lock into its run identity",
             bool(lock) and lock.get("status") == "locked"
             and lock.get("verified") is True,
             f"environment_lock={lock or None!r}")

    # THE HARD PIN, applied to the ARTIFACT's own claim. A self-consistent forgery agrees with
    # itself about everything; it cannot agree with a number it does not get to choose.
    rep.gate("the lock the bundle bound IS the hard-pinned Stage-2 lock — a self-consistent "
             "forgery agrees with itself, and that is not the same as being right",
             lock.get("sha256") == PINNED_SOLVER_LOCK_SHA256,
             f"bound={lock.get('sha256')!r} pinned={PINNED_SOLVER_LOCK_SHA256!r}")
    rep.gate("the lock's own EXPECTATION is the hard pin — an artifact may not declare what "
             "it was supposed to be",
             lock.get("expected_sha256") == PINNED_SOLVER_LOCK_SHA256,
             f"declared={lock.get('expected_sha256')!r} "
             f"pinned={PINNED_SOLVER_LOCK_SHA256!r}")

    rep.gate("the lock the bundle bound is the lock the verifier HASHED — the bytes on disk "
             "and the bytes in the identity are the same bytes",
             actual is not None and lock.get("sha256") == actual,
             f"bound={lock.get('sha256')!r} hashed={actual!r}")
    return lock.get("sha256")


def gate_not_self_admitted(verification: dict, rep: Report) -> None:
    """The PRODUCER may not admit its own output.

    ``verification.json`` ships as an empty slot — verdict pending, ``admitted: false``,
    ``verifier_id: null``. A bundle that arrived already admitting itself is refused
    outright: a generator that signs its own homework is the same process asserting twice,
    and the signature would be worth exactly nothing while looking like everything.
    """
    rep.gate("the shipped verification slot declares the allowlisted schema",
             verification.get("schema_version") == VERIFICATION_SCHEMA,
             f"got {verification.get('schema_version')!r}")
    rep.gate("the PRODUCER did not admit its own output — the verification slot ships "
             "un-admitted, naming no verifier, for an independent one to fill",
             verification.get("admitted") is False
             and verification.get("self_admitted") is False
             and verification.get("verifier_id") is None
             and verification.get("verdict") == VERDICT_PENDING,
             f"verdict={verification.get('verdict')!r} "
             f"admitted={verification.get('admitted')!r} "
             f"verifier_id={verification.get('verifier_id')!r}")


def gate_support_unavailable(binding: dict, columns: list[str], rep: Report) -> None:
    """Guide/donor support carries no contributor evidence in this pass, and no arm may
    stand on a denominator it does not have."""
    domain = binding.get("evidence_domain") or {}
    rep.gate("the run declares the pooled-main evidence domain it actually stood on",
             bool(domain.get("domain_id")) and domain.get("n_main_estimates_in_"
                                                          "analysis_condition") is not None,
             f"{domain!r}")
    support_cols = [c for c in columns
                    if "support" in c.lower() or "donor" in c.lower()
                    or "guide_slot" in c.lower()]
    rep.gate("no arm row carries a guide- or donor-support field: support is out of this "
             "pass's evidence domain and may not enter a denominator",
             not support_cols, f"{support_cols}")


def gate_on_disk(paths: dict[str, str], doc: dict, prov: dict,
                 rep: Report) -> dict[str, str]:
    """Re-open every emitted file FROM DISK and hash its raw bytes.

    The bundle SHIPS an artifact manifest naming every file it wrote and the hash of each.
    That manifest is checked against the bytes actually on disk — a citation whose target
    has moved underneath it is worse than no citation, because it still looks like one.

    ``verification.json`` is deliberately outside the manifest: it is the slot THIS verifier
    fills, so a bundle that hashed it would be pinning a verdict before anyone reached one.
    """
    shas = {name: AR.sha256_file(path) for name, path in sorted(paths.items())}
    rep.gate("every emitted artifact is present on disk and hashable",
             len(shas) == len(EXPECTED_FILES), f"{sorted(shas)}")

    declared = {e["name"]: e for e in (prov.get("artifacts") or [])}
    # The provenance cannot list itself (it is written last and would have to contain its
    # own hash), and the verification slot is what THIS verifier fills. Everything else the
    # bundle wrote must be named.
    expected = EXPECTED_FILES - {VERIFICATION_FILE, PROVENANCE_FILE}
    rep.gate("the shipped artifact manifest names every file the bundle wrote",
             set(declared) == expected,
             f"unlisted={sorted(expected - set(declared))} "
             f"phantom={sorted(set(declared) - expected)}")

    drifted = sorted(name for name, entry in declared.items()
                     if name in shas and entry.get("raw_sha256") != shas[name])
    rep.gate("every artifact's shipped hash matches the BYTES ON DISK — no file moved "
             "underneath its own citation",
             not drifted, f"{drifted}")

    rep.gate("the verification slot is NOT hashed into the bundle's own manifest — a "
             "bundle cannot pin a verdict nobody has reached yet",
             VERIFICATION_FILE not in declared,
             f"{VERIFICATION_FILE} appears in the shipped artifact manifest")
    return shas


# --------------------------------------------------------------------------- #
