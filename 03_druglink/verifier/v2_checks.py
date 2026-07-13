"""Every CHECK the Stage-3 v2 verifier makes. Imports NOTHING from ``druglink``.

Split from :mod:`verifier.verify_stage3_v2` (which orchestrates them and owns the CLI) at the
500-line gate. The order in that module is the order of trust: nothing a bundle SAYS about
anything else stands until it proves who it is.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

import pandas as pd

from . import canon, policy, reconstruct as rc, science_registry as sreg
from . import v2_admission as v2
from . import v2_contract as C
from . import v2_tables as T
from .report import Report


def _gate(rep: Report, gate: str, sentence: str, ok: Any, detail: str = "") -> bool:
    return rep.check(f"[{gate}] {sentence}", ok, detail)


def read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def read_table(bundle: str,
               name: str) -> Optional[tuple[list[dict[str, Any]], list[str]]]:
    """The table as it is ON DISK. An unreadable table is a NAMED refusal, not a traceback."""
    path = os.path.join(bundle, f"{name}.parquet")
    if not os.path.exists(path):
        return None
    try:
        frame = pd.read_parquet(path)
    except Exception:
        return None
    rows = [{k: rc.cell(v) for k, v in row.items()} for row in frame.to_dict("records")]
    return rows, [str(c) for c in frame.columns]


def _content_hash(name: str, rows: list[dict[str, Any]]) -> str:
    """The hash the BUNDLE binds: display columns excluded, row order irrelevant."""
    return T.content_hash(name, rows)


# --------------------------------------------------------------------------- #
# 1. The bundle's own identity. Nothing it says about anything else stands until it
#    proves who it is (B6: a forged manifest_sha256 sailed through all 60 v1 checks).
# --------------------------------------------------------------------------- #
def check_identity(rep: Report, *, bundle: str, manifest: dict[str, Any],
                   doc: dict[str, Any], artifact_class: str) -> None:
    declared = manifest.get("manifest_sha256")
    recomputed = canon.chash(canon.without(manifest, C.MANIFEST_IDENTITY_EXCLUDED))
    _gate(rep, C.GATE_BUNDLE_MANIFEST_SELF_HASH,
          "manifest_sha256 recomputes from the manifest's OWN canonical content (excluding "
          "manifest_sha256, which cannot cover itself, and the non-semantic created_at). "
          "NOTHING else is excluded, so no semantic field can hide outside the identity",
          recomputed == declared,
          f"declares {str(declared)[:16]}…, content hashes to {recomputed[:16]}…")

    content = canon.without(doc, C.DOC_IDENTITY_EXCLUDED)
    content_sha = canon.chash(content)
    _gate(rep, C.GATE_DOCUMENT_IDENTITY,
          "canonical_content_sha256 recomputes from the document's own scientific content "
          "(paths and timestamps stay OUTSIDE content addressing, so the same inputs rebuild "
          "the same bundle)",
          doc.get("canonical_content_sha256") == content_sha,
          f"declares {str(doc.get('canonical_content_sha256'))[:16]}…, recomputed "
          f"{content_sha[:16]}…")
    _gate(rep, C.GATE_DOCUMENT_IDENTITY,
          "document_sha256 recomputes from the document's own content",
          doc.get("document_sha256")
          == canon.chash(canon.without(doc, ("document_sha256",))))

    want_id = C.BUNDLE_ID_PREFIX[artifact_class] + content_sha[:16]
    _gate(rep, C.GATE_BUNDLE_ID_NOT_DERIVED,
          "the bundle id is DERIVED from the canonical content it commits to, and carries "
          "its artifact class in the prefix (an id nobody can re-derive is a label)",
          doc.get("bundle_id") == want_id == manifest.get("bundle_id"),
          f"doc={doc.get('bundle_id')!r} manifest={manifest.get('bundle_id')!r} "
          f"derived={want_id!r}")

    files = {f["file"]: f for f in (manifest.get("files") or [])}
    bad = []
    for name, entry in sorted(files.items()):
        path = os.path.join(bundle, name)
        if not os.path.exists(path):
            bad.append(f"{name}: missing")
        elif canon.file_sha256(path) != entry.get("file_sha256"):
            bad.append(f"{name}: file hash drift")
    _gate(rep, C.GATE_FILE_HASH_DRIFT,
          "every bundle file hashes to its manifest entry (a display-only column tampered "
          "with in a parquet is caught here even though it is not in the content hash)",
          not bad, "; ".join(bad[:3]))

    present = {f for f in os.listdir(bundle) if not f.startswith(".")}
    expected = set(files) | {"manifest.json"}
    extra = sorted(present - expected - {"verification.json"})
    _gate(rep, C.GATE_BUNDLE_INVENTORY,
          "the bundle inventory is exact — no extra, no stale, no missing file",
          not extra and not (expected - present),
          f"extra={extra} missing={sorted(expected - present)}")


def check_schema_and_firewall(rep: Report, *, manifest: dict[str, Any],
                              doc: dict[str, Any], artifact_class: str,
                              aggregate: Optional[dict[str, Any]]) -> None:
    want = C.DOC_FILE[artifact_class]
    _gate(rep, C.GATE_DOCUMENT_FILENAME,
          f"the document is named exactly what the contract publishes ({want}), and the "
          "manifest, the document and the file on disk all agree. Stage 4 opens this file BY "
          "NAME: a producer writing 'drug_annotation.v2.json' and a consumer opening "
          "'drug_annotation_v2.json' do not fail loudly — the reader finds nothing, and 'no "
          "candidates' becomes indistinguishable from 'no file'",
          manifest.get("document_file") == want and doc.get("document_file") == want,
          f"manifest={manifest.get('document_file')!r} document={doc.get('document_file')!r} "
          f"contract={want!r}")

    _gate(rep, C.GATE_SCHEMA_ALLOWLIST,
          f"the bundle declares the frozen v2 schema set ({C.DOC_SCHEMA} + "
          f"{C.MANIFEST_SCHEMA}) — v2 is a deliberate schema-ID bump, never a widened v1 enum",
          doc.get("schema_version") == C.DOC_SCHEMA
          and manifest.get("schema_version") == C.MANIFEST_SCHEMA,
          f"doc={doc.get('schema_version')!r} manifest={manifest.get('schema_version')!r}")

    _gate(rep, C.GATE_SCHEMA_ALLOWLIST,
          f"the document declares exactly the three typed v2 origins {list(v2.ORIGINS)} and "
          "no combined objective",
          sorted(doc.get("origin_types") or []) == sorted(v2.ORIGINS)
          and doc.get("combined_objective_permitted") is False,
          f"origin_types={doc.get('origin_types')!r} "
          f"combined={doc.get('combined_objective_permitted')!r}")

    # STAGE 2 DECLARES NO ARTIFACT CLASS, and never did — so it is not in this comparison. The
    # retired check read `aggregate["artifact_class"]`, a field the native release does not have:
    # it compared None against 'analysis' and called the disagreement a firewall. The real
    # firewall on the RELEASE is Stage-2's own admission (verifier.v2_reconstruct); THIS is
    # Stage-3's declaration about Stage-3's output, and the analysis path is additionally pinned
    # to the ADMITTED store and universe by literal (verifier.v2_store).
    classes = {"requested": artifact_class, "document": doc.get("artifact_class"),
               "manifest": manifest.get("artifact_class")}
    _gate(rep, C.GATE_FIXTURE_FIREWALL,
          "the requested artifact class, the document and the manifest all declare the SAME "
          "class (a sealed fixture can never be laundered into the analysis path — a synthetic "
          "number on its way to Stage 4 is a fabricated candidate)",
          len(set(classes.values())) == 1
          and artifact_class in C.ARTIFACT_CLASSES, str(classes))
    if aggregate is not None:
        _gate(rep, C.GATE_STAGE2_ADMISSION_NOT_CARRIED,
              "the Stage-2 release this bundle stands on was admitted by the pinned aggregate "
              f"verifier ({C.STAGE2_AGGREGATE_VERIFIER_ID}) with the verdict {C.ADMIT!r} — "
              "asserted as EXACT VALUES, because a key that is merely present is a binding "
              "nobody has",
              aggregate.get("aggregate_verifier_id") == C.STAGE2_AGGREGATE_VERIFIER_ID
              and aggregate.get("aggregate_verdict") == C.ADMIT,
              f"verifier={aggregate.get('aggregate_verifier_id')!r} "
              f"verdict={aggregate.get('aggregate_verdict')!r}")


def check_hygiene(rep: Report, *, doc: dict[str, Any], manifest: dict[str, Any],
                  emitted: dict[str, list[dict[str, Any]]],
                  columns: dict[str, list[str]]) -> None:
    payload: Any = [doc, {k: v for k, v in manifest.items() if k != "files"}, emitted]

    objective = (C.objective_keys_in(payload)
                 + C.true_objective_declarations(payload)
                 + [f"{name}:{c}" for name, cols in columns.items()
                    for c in cols if C.is_objective_key(c)])
    _gate(rep, C.GATE_COMBINED_OBJECTIVE,
          "no combined / balanced / weighted / fused objective at ANY depth, in the document "
          "OR in a table column (the three origins are reported side by side; a single number "
          "over them is a claim no measurement supports, and a synonym does not launder it)",
          not objective, str(objective[:4]))

    stats = C.stat_keys_in(payload) + [
        f"{name}:{c}" for name, cols in columns.items()
        for c in cols if C.is_stat_key(c)]
    _gate(rep, C.GATE_SIGNIFICANCE_ALIAS,
          "no p / q / FDR significance alias at ANY depth, in the document OR in a table "
          "column. Stage 3 computes no significance, and a field that names one wears the "
          "authority of a statistic nobody ran",
          not stats, str(stats[:4]))

    unknown = {name: sorted(set(cols) - set(C.TABLES[name][0]))
               for name, cols in columns.items()
               if set(cols) - set(C.TABLES[name][0])}
    _gate(rep, C.GATE_UNKNOWN_COLUMN,
          "every table's columns are EXACTLY the v2 contract's allowlist (an unknown column "
          "is a field nobody agreed to, and no downstream consumer can be expected to refuse "
          "it)",
          not unknown, str(unknown))

    leaks = policy.contains_local_path(doc) + policy.contains_local_path(
        canon.without(manifest, ("files",)))
    _gate(rep, C.GATE_LOCAL_PATH_LEAK,
          "the bundle leaks no machine-local path (a /home/... path names the producer's "
          "machine and can be resolved nowhere else)",
          not leaks, str(leaks[:3]))

    _gate(rep, C.GATE_COMBINED_OBJECTIVE,
          "no retired promotion/eligibility vocabulary survives at any depth",
          not policy.retired_keys_in(doc), str(policy.retired_keys_in(doc)[:3]))


def check_bindings(rep: Report, *, doc: dict[str, Any], aggregate: dict[str, Any],
                   store: dict[str, Any], digest: str,
                   expected_code: Optional[str], expected_env: Optional[str]) -> None:
    """Every upstream identity the bundle stands on, re-derived and compared."""
    bound = doc.get("stage2_aggregate") or {}
    report = bound.get("independent_report") or {}
    want = {
        "manifest_raw_sha256": aggregate["manifest_raw_sha256"],
        "manifest_canonical_sha256": aggregate["manifest_canonical_sha256"],
        "manifest_self_hash": aggregate["manifest_self_hash"],
        "stage1_release_sha256": aggregate["stage1_release_sha256"],
    }
    drift = {k: (bound.get(k), v) for k, v in want.items() if bound.get(k) != v}
    if report.get("raw_sha256") != aggregate["report_raw_sha256"]:
        drift["independent_report.raw_sha256"] = (report.get("raw_sha256"),
                                                  aggregate["report_raw_sha256"])
    # THE NATIVE REPORT BINDING. There is no `admits{}` block — Stage 2 has never emitted one,
    # and reading `report.get("admits") or {}` against the real bytes checks a field that does
    # not exist. The report binds the manifest TOP-LEVEL, and BOTH its claim and its own
    # recomputation must equal the semantic self-hash THIS verifier derived from the bytes.
    if report.get("manifest_sha256") != aggregate["manifest_self_hash"] \
            or report.get("manifest_sha256_recomputed") != aggregate["manifest_self_hash"]:
        drift["independent_report.manifest_sha256"] = (
            report.get("manifest_sha256"), aggregate["manifest_self_hash"])
    # EXACT VALUES, asserted — key-presence is not enough, and a null is a refusal.
    if report.get("verifier_id") != C.STAGE2_AGGREGATE_VERIFIER_ID \
            or report.get("verdict") != C.ADMIT:
        drift["independent_report.verdict"] = (
            f"{report.get('verifier_id')!r}/{report.get('verdict')!r}",
            f"{C.STAGE2_AGGREGATE_VERIFIER_ID!r}/{C.ADMIT!r}")
    _gate(rep, C.GATE_REPORT_BINDS_ANOTHER_MANIFEST,
          "the bundle binds the EXACT Stage-2 release this verifier just re-admitted from disk — "
          "the manifest by raw, canonical AND semantic self-hash; the SEPARATE report's bytes; "
          f"the pinned verifier id ({C.STAGE2_AGGREGATE_VERIFIER_ID}) and its {C.ADMIT!r} "
          "verdict, asserted as values rather than merely present as keys; the report's own "
          "recomputation of the manifest; and the Stage-1 release",
          not drift, str({k: (str(a)[:24], str(b)[:24]) for k, (a, b) in drift.items()}))

    inventory = {b["bundle_key"]: b["raw_sha256"] for b in aggregate["bundles"]}
    lanes = {a.get("bundle_key"): a.get("raw_sha256")
             for a in (bound.get("lane_artifacts") or [])}
    _gate(rep, C.GATE_BUNDLE_BYTES_MOVED,
          f"the bundle binds every one of the {C.N_BUNDLES} consumed lane artifacts by hash, "
          f"and the {C.N_ARM_SLOTS} arm slots it resolved",
          lanes == inventory and bound.get("n_bundles") == len(aggregate["bundles"])
          and bound.get("n_arm_slots") == len(aggregate["arms"]),
          f"n_bundles={bound.get('n_bundles')!r} n_arm_slots={bound.get('n_arm_slots')!r} "
          f"lane_artifacts={len(lanes)}")

    binding = doc.get("universe_store") or {}
    _gate(rep, C.GATE_TYPED_UNIVERSE_HASH_MISMATCH,
          "the bundle binds the typed universe and the store artifacts this verifier "
          "re-derived from the store's own bytes (never the store's claimed hash, copied)",
          binding.get("typed_universe_sha256") == store["typed_universe_sha256"]
          and binding.get("store_id") == store["store_id"],
          f"universe={str(binding.get('typed_universe_sha256'))[:16]}… vs derived "
          f"{store['typed_universe_sha256'][:16]}…")

    # The LICENCE and the exact source bytes, bound per source and not once per bundle.
    releases = store["release_binding"]
    licence_drift = [k for k in ("chembl_release", "chembl_source_sha256", "chembl_license",
                                 "uniprot_release", "uniprot_license")
                     if binding.get(k) != releases.get(k)]
    _gate(rep, C.GATE_LICENSE_BINDING_MISSING,
          "the bundle binds the ChEMBL/UniProt releases, source hashes and LICENCES this "
          "verifier read from the store's own manifest (ChEMBL is CC BY-SA 3.0 and its "
          "attribution is REQUIRED: a derived layer travelling without them is a licence "
          "breach, not a missing nicety)",
          not licence_drift and bool(binding.get("chembl_license")), str(licence_drift))

    method = doc.get("method") or {}
    _gate(rep, C.GATE_TABLE_HASH_DRIFT,
          "the bundle binds the direction-vocabulary digest this verifier recomputed from "
          "the frozen vocabulary (a silent reclassification moves the digest, so it cannot "
          "hide behind a drug that quietly started ranking)",
          method.get("direction_vocabulary_digest") == digest,
          f"bundle={str(method.get('direction_vocabulary_digest'))[:16]}… recomputed "
          f"{digest[:16]}…")

    code, env = method.get("code_tree_sha256"), method.get("env_lock_sha256")
    ok = bool(code) and bool(env)
    if expected_code:
        ok = ok and code == expected_code
    if expected_env:
        ok = ok and env == expected_env
    _gate(rep, C.GATE_CODE_ENV_PINS,
          "the bundle binds the code-tree and environment identity it was produced under, "
          "and they are the ones expected",
          ok, f"code={str(code)[:16]}… env={str(env)[:16]}… "
              f"(expected code={str(expected_code)[:16]}… env={str(expected_env)[:16]}…)")


def check_v2_admission_contract(rep: Report, *, doc: dict[str, Any],
                                edges: list[dict[str, Any]], digest: str,
                                artifact_class: str) -> None:
    """Integrate the FROZEN v2 admission rule set. It is not test-only."""
    swapped = [e.get("edge_id") for e in edges
               if C.ORIGIN_FOR_LANE.get(str(e.get("lane"))) != e.get("origin_type")]
    _gate(rep, C.GATE_ORIGIN_SWAP,
          "every edge's typed origin agrees with the LANE of the Stage-2 bundle it came from "
          "(a same-condition Direct effect and a cross-time difference-in-differences are "
          "different estimands; a swapped origin is a consumer reading the wrong one)",
          not swapped, f"{len(swapped)}: {swapped[:3]}")

    v2.check_origins_are_typed_and_separate(rep, edges)
    v2.check_no_combined_score(rep, doc)
    v2.check_ordered_axes_and_conditions(rep, edges)
    v2.check_direction_is_engine_decided(rep, edges, expected_vocabulary_digest=digest)
    if artifact_class == C.ANALYSIS:
        # These two bind the ANALYSIS pins — the exact admitted store and the absence of any
        # fixture substitution. A fixture bundle is refused by the firewall above instead.
        v2.check_no_fixture_fallback(rep, doc)
        v2.check_universe_store_binding(rep, doc)


def check_science_registry(rep: Report, *, doc: dict[str, Any],
                           root: Optional[str]) -> None:
    refs = sreg.collect_refs(doc.get("candidates") or [],
                             "disease_context_review_evidence_refs")
    if not refs:
        rep.check("no Claude Science record is referenced, and none is claimed", True)
        return
    rep.check("a Science registry is bound whenever Science records are referenced",
              bool(root), f"{len(refs)} reference(s), registry={root!r}")
    fails = sreg.verify_refs(root, refs) if root else ["no registry supplied"]
    rep.check("every referenced Science record RESOLVES and its bytes RE-HASH to what the "
              "reference binds", not fails, "; ".join(fails[:3]))
