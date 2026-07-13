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
    PROVENANCE_SCHEMA,
    RELEASE_LANES,
    REQUEST_SCHEMA,
    RUNNER_ID,
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
    rep.gate("file inventory: exactly the bundle's three artifacts, no extras",
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


def gate_code_identity(binding: dict, rep: Report) -> None:
    """The code digest RE-DERIVED from the tree, and the tree it was taken from."""
    code = binding.get("code_identity") or {}
    root = os.path.dirname(os.path.dirname(_HERE))          # 02_geneskew/
    repo = os.path.dirname(root)
    files = []
    for base, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in {
            "__pycache__", ".pytest_cache", ".git", ".ruff_cache", ".mypy_cache",
            "node_modules", ".ipynb_checkpoints"})
        for name in sorted(names):
            if name.endswith((".py", ".json")):
                path = os.path.join(base, name)
                files.append({"path": os.path.relpath(path, repo).replace(os.sep, "/"),
                              "sha256": AR.sha256_file(path)})
    files.sort(key=lambda f: f["path"])
    manifest_sha = AR.content_sha256(files)

    rep.gate("the code manifest hash RE-DERIVES from the tree this run claims",
             code.get("manifest_sha256") == manifest_sha,
             f"declared={code.get('manifest_sha256')!r} derived={manifest_sha!r}")
    rep.gate("the canonical code digest is the manifest hash's own prefix",
             code.get("canonical_digest") == manifest_sha[:16],
             f"declared={code.get('canonical_digest')!r}")
    rep.gate("the code tree was CLEAN, or the run says out loud that it was not",
             code.get("clean_tree") is True
             or code.get("clean_checkout_required") is False,
             f"clean_tree={code.get('clean_tree')!r} "
             f"clean_checkout_required={code.get('clean_checkout_required')!r}")
    rep.gate("a release-grade lane REFUSES a dirty tree",
             not (binding.get("lane") in RELEASE_LANES
                  and code.get("clean_tree") is not True),
             "a release-grade run was taken from an uncommitted tree")


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
# an input a reader cannot check and a run cannot be reconstructed from.
CONSUMED_INPUT_BINDINGS = {
    "guide_manifest": "the contributor manifest the masks were resolved from",
    "mask_sha256": "the masks every base delta was taken under",
    "target_identity_map": "the run-level target-identity map, if one was supplied",
    "source_registry": "the source registry the contributor evidence resolves against",
}


def gate_consumed_inputs_bound(binding: dict, rep: Report) -> None:
    """Every CONSUMED scientific input is in the identity, or the bundle cannot be checked.

    The legacy pair runner already binds this pattern (``guide_manifest``, ``mask_sha256``,
    the full Stage-1 and input bindings). A bundle that omits them records COUNTS where it
    needs IDENTITIES: "29 rows, 18 scopes" cannot tell two different contributor manifests
    apart, and the masks they imply move every base delta in all |admitted| x 2 arms.
    """
    missing = sorted(k for k in ("guide_manifest", "mask_sha256")
                     if not binding.get(k))
    rep.gate("every CONSUMED scientific input is bound into the run identity — the "
             "contributor manifest and the masks the rows were computed under",
             not missing,
             f"absent from the binding: {missing} "
             f"({', '.join(CONSUMED_INPUT_BINDINGS[k] for k in missing)})")


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

    And then the thing the audit found missing: the BUNDLE DOCUMENT is not bound. The run
    id is a hash of the binding, and the binding carries the rows hash — but not the
    document that describes those rows. So the arm manifest, the slot counts and the
    embedded scorer view can all be edited while every advertised hash stays valid. A
    document nothing binds is a document anyone can rewrite.
    """
    shas = {name: AR.sha256_file(path) for name, path in sorted(paths.items())}
    rep.gate("every emitted artifact is present on disk and hashable",
             len(shas) == len(EXPECTED_FILES), f"{sorted(shas)}")

    binding = prov.get("run_binding") or {}
    body = {k: v for k, v in doc.items() if k != "arm_bundle_run_id"}
    declared = binding.get("arm_bundle_sha256") or doc.get("arm_bundle_sha256")
    rep.gate("the BUNDLE DOCUMENT itself is bound into the run identity — its arm "
             "manifest and counts cannot be rewritten while the hashes stay valid",
             bool(declared) and declared == AR.content_sha256(body),
             f"bound={declared!r} derived={AR.content_sha256(body)!r}")
    return shas


# --------------------------------------------------------------------------- #
