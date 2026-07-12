"""The independent checks. Reconstruction first, hashes second.

A verifier that only re-hashes what the generator declared proves that the generator can
hash. This one rebuilds the science from the evidence tables and then insists that the
generator's JSON and its parquet agree with the rebuild AND with each other.

Scope is explicit: a run without the original inputs is `partial`, and says so, rather
than returning an unqualified `pass`.
"""

from __future__ import annotations

import json
import os
from typing import Any

import pyarrow.parquet as pq

from . import canon
from .bindings import (
    binding_failures,
    duplicate_row_ids,
    empty_searches_are_empty,
    negative_searches_are_manifested,
    unique_potency_context_links,
)
from . import inputs as vinputs
from . import derived
from .columns import DELIVERY_REBUILT_FIELDS, REQUIRED_COLUMNS
from .criteria import check_criteria
from .prose import required_prose_failures, unbound_prose
from .delivery import rebuild_delivery
from .reconstruct import (
    load_method,
    load_tables,
    rebuild_cns_mpo,
    rebuild_eligibility,
    rebuild_margins,
    rebuild_nebpi,
)

FORBIDDEN_FIELD_DEFAULT = (
    "traffic_light", "green_amber_red", "safety_score", "tolerability_score",
    "clinical_recommendation", "recommendation", "prescribe", "is_safe",
    "overall_safety", "composite_score", "risk_score",
)


def _c(checks: list[dict], cid: str, ok: bool, detail: str) -> None:
    checks.append({"check_id": cid, "status": "pass" if ok else "fail", "detail": detail})


def _missing_required_columns(tables: dict[str, list[dict]]) -> dict[str, list[str]]:
    missing: dict[str, list[str]] = {}
    for table, cols in REQUIRED_COLUMNS.items():
        if table not in tables:
            missing[table] = ["<table absent>"]
            continue
        rows = tables[table]
        if not rows:
            continue  # an empty table carries no columns to check, and that is legal
        present = set(rows[0])
        gaps = [c for c in cols if c not in present]
        if gaps:
            missing[table] = gaps
    return missing


def verify_release(out_dir: str, method_dir: str) -> dict[str, Any]:
    """Full independent verification of a written scorecard set."""
    checks: list[dict[str, Any]] = []

    with open(os.path.join(out_dir, "manifest.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)
    with open(os.path.join(out_dir, "scorecards.json"), encoding="utf-8") as fh:
        scorecards = json.load(fh)

    method = load_method(method_dir)
    tables = load_tables(out_dir)

    # --- -1. the release must actually be the shape this verifier reconstructs ---------
    # A release written by a different (older) Stage-4 is not "verified" — it is
    # unverifiable. Say so cleanly instead of crashing on a missing column.
    missing_cols = _missing_required_columns(tables)
    if missing_cols:
        _c(checks, "release_reconstructable", False,
           "this release does not carry the columns reconstruction needs (is it from an "
           f"older Stage-4?): {missing_cols}")
        return {
            "schema_id": "spot.stage04_verification.v2",
            "verifier": "04_PKPD/verifier (independent; imports no analysis logic)",
            "scope": "unverifiable_release_shape",
            "scorecard_set_id": manifest.get("scorecard_set_id"),
            "status": "fail",
            "n_checks": len(checks),
            "n_failed": len([c for c in checks if c["status"] == "fail"]),
            "checks": checks,
        }
    _c(checks, "release_reconstructable", True,
       "every table the reconstruction reads is present with the columns it needs")

    # --- 0. exact artifact allowlist ------------------------------------------------
    # An EXTRA file is always a failure: the audit dropped a production-looking artifact
    # into the directory and verification still passed. `verification.json` is the one
    # file that may legitimately be absent here — it is this verifier's own output, and
    # at emit time it has not been written yet. A standalone re-verify sees it present.
    allow = set(manifest.get("artifact_allowlist", []))
    present = set(os.listdir(out_dir))
    extra = sorted(present - allow)
    missing = sorted(allow - present - {"verification.json"})
    _c(checks, "artifact_allowlist_exact", not extra and not missing,
       f"extra={extra} missing={missing}")

    # --- 1. manifest self-hash + every file hash ------------------------------------
    declared = manifest.get("manifest_content_sha256")
    recomputed = canon.chash({k: v for k, v in manifest.items()
                              if k != "manifest_content_sha256"})
    _c(checks, "manifest_self_hash", declared == recomputed,
       f"declared={declared} recomputed={recomputed}")

    for art in manifest["artifacts"]:
        path = os.path.join(out_dir, art["filename"])
        if not os.path.exists(path):
            _c(checks, f"artifact_present::{art['filename']}", False, "missing")
            continue
        actual = canon.file_sha256(path)
        _c(checks, f"artifact_file_sha256::{art['filename']}",
           actual == art["file_sha256"], f"recomputed={actual}")
        if art["filename"].endswith(".parquet"):
            rows = pq.read_table(path).to_pylist()
            keys = art["sort_key"]
            ordered = sorted(rows, key=lambda r: canon.row_key(r, keys))
            _c(checks, f"artifact_row_order::{art['filename']}", rows == ordered,
               f"sorted by {keys}")
            _c(checks, f"artifact_content_sha256::{art['filename']}",
               canon.chash(ordered) == art["content_sha256"], "content hash of canonical rows")
            schema = pq.read_schema(path)
            _c(checks, f"artifact_columns::{art['filename']}",
               list(schema.names) == list(art["columns"]), "declared column order")

    # --- 2. code + environment are bound and enforced --------------------------------
    _c(checks, "analysis_code_bound", bool(manifest.get("analysis_code_sha256")),
       "an altered scoring implementation must move the scorecard_set_id")
    _c(checks, "analysis_code_in_id",
       manifest["scorecard_set_id_inputs"].get("analysis_code_sha256")
       == manifest.get("analysis_code_sha256"),
       "the code hash actually feeds the id")
    env = manifest.get("environment", {})
    _c(checks, "environment_matches_lock", env.get("observed_matches_lock") is True,
       f"divergent={env.get('divergent_packages')}")
    _c(checks, "namespace_bound_into_id",
       manifest["scorecard_set_id_inputs"]["stage3"].get("namespace") == manifest.get("namespace"),
       "namespace is part of content identity")
    _c(checks, "source_class_bound_into_id",
       bool(manifest["scorecard_set_id_inputs"].get("source_registry_sha256")),
       "the source provenance class feeds the id")

    # A crash is not a verdict. A tampered release can carry any string in any column —
    # an out-of-vocabulary requirement, a nonsense unit, an unknown criterion — and an
    # exception escaping here would leave the caller with no report at all rather than a
    # failure. Every check below therefore runs inside the guard, and an abort IS a fail.
    try:
        # --- 2a. IDENTITY: re-derived from the release, never read back from the generator ---
        # The re-audit resealed a release with a rewritten negative-search scope/source/date and
        # a rewritten link access-date/transform, kept the scorecard_set_id, and passed 193/193 —
        # because nothing here ever recomputed `evidence_inputs_sha256` from the emitted rows.
        # It does now: a tampered bound column fails this digest, or, if the tamperer also
        # rewrites the digest and the id key, the identity moves. There is no third outcome.
        id_key = manifest.get("scorecard_set_id_inputs", {})
        input_tables = vinputs.load_input_tables(out_dir)

        recomputed_inputs = vinputs.evidence_inputs_digest(input_tables)
        declared_inputs = id_key.get("evidence_inputs_sha256")
        _c(checks, "evidence_inputs_sha256_recomputed_from_the_release",
           recomputed_inputs == declared_inputs,
           f"recomputed={recomputed_inputs} declared={declared_inputs}")
        _c(checks, "evidence_inputs_sha256_agrees_with_the_manifest",
           manifest.get("evidence_inputs_sha256") == declared_inputs,
           "the manifest's headline digest is the one bound into the id")

        recomputed_sources = vinputs.source_registry_digest(input_tables)
        _c(checks, "source_registry_sha256_recomputed_from_the_release",
           recomputed_sources == id_key.get("source_registry_sha256"),
           f"recomputed={recomputed_sources} declared={id_key.get('source_registry_sha256')}")

        recomputed_method = vinputs.method_file_sha256(method_dir)
        _c(checks, "method_file_sha256_recomputed_from_the_method_files",
           recomputed_method == dict(sorted((id_key.get("method_file_sha256") or {}).items())),
           "the method files on disk are the ones bound into the id")

        # The candidate rows are hashed WHOLE into the id. The release now carries them whole,
        # so this recomputes that hash from the release rather than trusting it.
        recomputed_rows = vinputs.candidate_rows_sha256(input_tables)
        declared_rows = (id_key.get("stage3") or {}).get("candidate_rows_sha256")
        _c(checks, "candidate_rows_sha256_recomputed_from_the_release",
           recomputed_rows == declared_rows,
           f"recomputed={recomputed_rows} declared={declared_rows}")

        rederived_id = vinputs.rederive_scorecard_set_id(id_key)
        declared_id = manifest.get("scorecard_set_id")
        _c(checks, "scorecard_set_id_rederived_from_its_own_inputs",
           rederived_id == declared_id,
           f"rederived={rederived_id} declared={declared_id}")
        _c(checks, "scorecard_set_id_matches_the_release_directory",
           os.path.basename(os.path.abspath(out_dir.rstrip("/"))) == declared_id,
           "the release is sitting in the directory its own identity names")
        _c(checks, "scorecard_set_id_matches_the_scorecards",
           scorecards.get("scorecard_set_id") == declared_id,
           "the scorecards and the manifest name one identity")

        # --- 2a-bis. DERIVED CELLS: recomputed, never read back ------------------------
        # A derived column is a pure function of the bound inputs + the method, so a resealed
        # tamper can rewrite the cell and every hash around it but cannot make the arithmetic
        # come out. The full-column sweep found 20 such cells that nothing reconstructed.
        for label, problems in (
            ("property", derived.check_property_derived(
                tables.get("property_evidence", []), method)),
            ("potency", derived.check_potency_derived(tables.get("potency_evidence", []))),
            ("exposure", derived.check_exposure_derived(tables)),
            ("safety", derived.check_safety_derived(
                tables.get("safety_evidence", []), method)),
        ):
            _c(checks, f"derived_cells_recomputed::{label}", not problems,
               f"every derived cell is reproduced from the bound inputs: {problems}")

        # --- 2a-ter. NO UNBOUND PROSE ---------------------------------------------------
        # Every SENTENCE in the release is declared in a method file (hashed into the id), is a
        # bound evidence cell, is part of the identity, or is reconstructed. A sentence that is
        # none of those could be rewritten in a resealed release — "CNS-MPO is not measured brain
        # permeability" inverted, "no evidence found is NOT a finding of safety" deleted — while
        # every hash still agreed. There are no exemptions.
        prose_problems = unbound_prose(out_dir, method_dir)
        _c(checks, "no_unbound_prose", not prose_problems,
           "every sentence in the release is bound into identity or reconstructed: "
           f"{prose_problems}")

        # ...and the guards must be PRESENT. `no_unbound_prose` catches a rewrite; it cannot
        # catch a DELETION, and in a resealed release the artifact hashes would agree. Silence
        # is the cheapest way to lie.
        missing = required_prose_failures(out_dir, method_dir)
        _c(checks, "required_guards_present_verbatim", not missing,
           f"every guard sentence is present, exactly as the method declares it: {missing}")

    # --- 2b. PROVENANCE BINDING: every result-affecting row rests on acquired bytes -----
        # Re-derived here from the emitted tables + source_catalog, independently of the
        # engine's own pass over its input records. The audit created an NEBPI class from a
        # potency-context link citing `src.DOES_NOT_EXIST`, and set the NEBPI primary gate from
        # a delivery assignment citing the same, with both verifiers reporting all-pass.
        unbound = binding_failures(tables)
        _c(checks, "every_evidence_row_is_source_bound", not unbound,
           "a row that cites a source must cite one that exists, was acquired, and whose bytes "
           f"hash to what the row declares: {unbound}")

        dupes = duplicate_row_ids(tables)
        _c(checks, "no_duplicate_evidence_row_ids", not dupes,
           f"a row id is supplied exactly once, so nothing downstream can pick: {dupes}")

        link_clashes = unique_potency_context_links(tables)
        _c(checks, "one_relevance_link_per_potency_and_context", not link_clashes,
           f"two links for one (potency, tumour context) would depend on row order: {link_clashes}")

        unmanifested = negative_searches_are_manifested(tables)
        _c(checks, "negative_searches_carry_a_manifest", not unmanifested,
           f"'we looked and found nothing' needs the search it rests on: {unmanifested}")

        nonempty = empty_searches_are_empty(tables)
        _c(checks, "negative_search_manifests_returned_zero", not nonempty,
           f"a manifest backing a negative result returned 0 rows: {nonempty}")

        # --- 2c. RECONSTRUCTION: the delivery reduction -------------------------------------
        # Re-run the reducer on the ASSIGNMENT rows. `delivery_evidence` is what is being
        # checked here, never an input to the check: the audit changed local_CNS to uncertain by
        # reordering these rows, and nothing downstream could see it.
        rebuilt_delivery = rebuild_delivery(tables, method)
        for row in tables.get("delivery_evidence", []):
            key = (row["candidate_id"], row["context_id"])
            mine = rebuilt_delivery.get(key)
            if mine is None:
                _c(checks, f"delivery_rebuildable::{key}", False, "no context row")
                continue
            diffs = {f: (mine.get(f), row.get(f)) for f in DELIVERY_REBUILT_FIELDS
                     if mine.get(f) != row.get(f)}
            _c(checks, f"delivery_reduction::{key}", not diffs,
               f"rebuilt vs claimed (rebuilt, claimed): {diffs}" if diffs
               else "the reduction of the assignment rows reproduces the emitted decision")
            claimed_conflicts = list(row.get("conflicting_assignment_ids") or [])
            _c(checks, f"delivery_conflicts::{key}",
               sorted(claimed_conflicts) == sorted(mine.get("conflicting_assignment_ids") or []),
               f"rebuilt={mine.get('conflicting_assignment_ids')} claimed={claimed_conflicts}")

        # --- 3. RECONSTRUCTION: CNS-MPO ---------------------------------------------------
        rebuilt_mpo = rebuild_cns_mpo(tables, method)
        for cand in scorecards["candidates"]:
            cid = cand["candidate_id"]
            claimed = cand["lanes"]["cns_mpo"]
            mine = rebuilt_mpo.get(cid)
            if mine is None:
                _c(checks, f"cns_mpo_rebuildable::{cid}", False, "no property rows in the release")
                continue
            _c(checks, f"cns_mpo_status::{cid}", mine["status"] == claimed["status"],
               f"rebuilt={mine['status']} claimed={claimed['status']}")
            for p, v in mine["components"].items():
                cv = claimed["components"].get(p)
                ok = (v is None and cv is None) or (
                    v is not None and cv is not None and abs(v - cv) < 1e-9)
                _c(checks, f"cns_mpo_component::{cid}::{p}", ok, f"rebuilt={v} claimed={cv}")
            ok_total = (mine["total_published"] is None and claimed["total_published"] is None) or (
                mine["total_published"] is not None and claimed["total_published"] is not None
                and abs(mine["total_published"] - claimed["total_published"]) < 1e-9)
            _c(checks, f"cns_mpo_total::{cid}", ok_total,
               f"rebuilt={mine['total_published']} claimed={claimed['total_published']}")

        # --- 4. RECONSTRUCTION: exposure margins ------------------------------------------
        rebuilt_margins = rebuild_margins(tables)
        for row in tables.get("exposure_evidence", []):
            mid = row["measurement_id"]
            mine = rebuilt_margins[mid]
            _c(checks, f"margin_status::{mid}", mine["status"] == row["margin_status"],
               f"rebuilt={mine['status']} claimed={row['margin_status']}")
            _c(checks, f"margin_value::{mid}",
               mine["margin_canonical_decimal"] == row["margin_canonical_decimal"],
               f"rebuilt={mine['margin_canonical_decimal']} claimed={row['margin_canonical_decimal']}")
            if mine["status"] == "not_computable":
                _c(checks, f"margin_reason::{mid}",
                   mine["reason_code"] == row["margin_reason_code"],
                   f"rebuilt={mine['reason_code']} claimed={row['margin_reason_code']}")

        # --- 4b. RECONSTRUCTION: the criterion-level NEBPI table ---------------------------
        # NEBPI is a criterion-level evidence model, not a score. The table that says so is
        # rebuilt from the observations + the method, never read back from the generator.
        criteria_problems = check_criteria(tables, method)
        _c(checks, "nebpi_criteria_reconstructed", not criteria_problems,
           "every criterion's status, importance, branch capability and contribution is "
           f"reproduced from the evidence: {criteria_problems}")

        # --- 5. RECONSTRUCTION: NEBPI decision path ---------------------------------------
        rebuilt_nebpi = rebuild_nebpi(tables, method)
        for row in tables.get("nebpi_decisions", []):
            key = (row["candidate_id"], row["context_id"])
            mine = rebuilt_nebpi.get(key)
            if mine is None:
                _c(checks, f"nebpi_rebuildable::{key}", False, "no context row")
                continue
            _c(checks, f"nebpi_class::{key}", mine["nebpi_class"] == row["nebpi_class"],
               f"rebuilt={mine['nebpi_class']} claimed={row['nebpi_class']}")
            _c(checks, f"nebpi_status::{key}", mine["nebpi_status"] == row["nebpi_status"],
               f"rebuilt={mine['nebpi_status']} claimed={row['nebpi_status']}")
            _c(checks, f"nebpi_derived_pk::{key}",
               mine["derived_pk_level"] == row["derived_pk_level"],
               f"rebuilt={mine['derived_pk_level']} claimed={row['derived_pk_level']}")
            _c(checks, f"nebpi_reduced_states::{key}",
               mine["pd_state"] == row["pd_state"]
               and mine["radiographic_state"] == row["radiographic_state"],
               f"rebuilt pd={mine['pd_state']} rad={mine['radiographic_state']} "
               f"claimed pd={row['pd_state']} rad={row['radiographic_state']}")
            # The gate the NEBPI lane was read under comes from OUR reduction of the assignment
            # rows, not from the generator's delivery table.
            _c(checks, f"nebpi_primary_gate::{key}",
               mine["nebpi_primary_gate"] == row["nebpi_primary_gate"],
               f"rebuilt={mine['nebpi_primary_gate']} claimed={row['nebpi_primary_gate']}")
            # Absent evidence can never make a negative class.
            if row["nebpi_class"] in ("insufficiently_permeable", "impermeable"):
                _c(checks, f"nebpi_negative_needs_observed_absence::{key}",
                   row["pd_state"] == "observed_absent"
                   and row["radiographic_state"] == "observed_absent",
                   f"pd={row['pd_state']} rad={row['radiographic_state']}")
            # `impermeable` rests on "little to no drug in NEB", which carries Table 2
            # footnote (a). A censored measurement establishes it only when a source-declared
            # LOD/LLOQ is STRICTLY below the MEC.
            if row["derived_pk_level"] == "pk_little_to_none_in_neb":
                censored = row["pk_detection_status"] in ("not_detected", "below_lloq")
                _c(checks, f"nebpi_little_to_none_is_potency_bounded::{key}",
                   (not censored) or (row["pk_censored_bound_below_mec"] is True
                                      and bool(row["pk_censored_bound_kind"])),
                   f"detection={row['pk_detection_status']} "
                   f"bound_kind={row['pk_censored_bound_kind']} "
                   f"below_mec={row['pk_censored_bound_below_mec']}")
            if row["nebpi_class"] == "sufficiently_permeable":
                _c(checks, f"nebpi_positive_needs_qualifying_branch::{key}",
                   bool(row["satisfied_branches"]), f"branches={row['satisfied_branches']}")

        # criterion_states must come from the same reducer, not a last-row-wins scan.
        for cand in scorecards["candidates"]:
            for n in cand["lanes"]["nebpi"]:
                key = (cand["candidate_id"], n["context_id"])
                mine = rebuilt_nebpi.get(key)
                if mine is None:
                    continue
                _c(checks, f"nebpi_criterion_states::{key}",
                   mine["criterion_states"] == dict(sorted(n["criterion_states"].items())),
                   f"rebuilt={mine['criterion_states']} claimed={n['criterion_states']}")

        # --- 6. JSON <-> parquet agreement -------------------------------------------------
        checks.extend(_json_parquet_agreement(scorecards, tables))

        # --- 7. eligibility, namespace and the production gate ------------------------------
        ns = manifest.get("namespace")
        rebuilt_elig = rebuild_eligibility(tables, ns)
        for cand in scorecards["candidates"]:
            cid = cand["candidate_id"]
            claimed = cand["production_eligible"]["eligible"]
            mine = rebuilt_elig.get(cid, {}).get("production_eligible")
            _c(checks, f"production_eligibility::{cid}", mine == claimed,
               f"rebuilt={mine} claimed={claimed}")
        catalog = tables.get("source_catalog", [])
        if any(r["acquisition_status"] != "acquired_public" for r in catalog):
            _c(checks, "no_production_eligibility_on_nonpublic_evidence",
               not any(c["production_eligible"]["eligible"] for c in scorecards["candidates"]),
               "no candidate may be production-eligible while any consumed source is "
               "fixture/unacquired")

        # --- 8. no combined clinical verdict, anywhere ---------------------------------------
        forbidden = tuple(method["safety_taxonomy"]["prohibited_outputs"]["forbidden_field_names"])
        hits = _scan_forbidden(scorecards, forbidden)
        _c(checks, "no_composite_clinical_score", not hits, f"hits={hits}")
        _c(checks, "no_selection_emitted_without_public_sources", _selection_ok(out_dir, catalog),
           "a selection/ranking requires acquired public evidence")

    except Exception as exc:  # noqa: BLE001 - an aborted verifier must still return a verdict
        _c(checks, "verifier_completed", False,
           f"the verifier could not finish reconstructing this release "
           f"({type(exc).__name__}: {exc}). An unfinished verification is a failed one.")

    failed = [c for c in checks if c["status"] == "fail"]
    return {
        "schema_id": "spot.stage04_verification.v2",
        "verifier": "04_PKPD/verifier (independent; imports no analysis logic)",
        "scope": "full_reconstruction",
        "scorecard_set_id": manifest["scorecard_set_id"],
        "status": "fail" if failed else "pass",
        "n_checks": len(checks),
        "n_failed": len(failed),
        "checks": sorted(checks, key=lambda c: c["check_id"]),
    }


def _json_parquet_agreement(scorecards: dict, tables: dict) -> list[dict]:
    """The generator's two faces must say the same thing."""
    checks: list[dict] = []
    safety = {r["evidence_id"]: r for r in tables.get("safety_evidence", [])}
    nebpi = {(r["candidate_id"], r["context_id"]): r for r in tables.get("nebpi_decisions", [])}
    exposure = {r["measurement_id"]: r for r in tables.get("exposure_evidence", [])}

    for cand in scorecards["candidates"]:
        cid = cand["candidate_id"]
        for row in cand["lanes"]["safety"]["rows"]:
            p = safety.get(row["evidence_id"])
            _c(checks, f"json_parquet_safety::{row['evidence_id']}",
               p is not None and p["evidence_state"] == row["evidence_state"]
               and p["finding_text"] == row.get("finding_text"),
               "safety row agrees between scorecards.json and safety_evidence.parquet")
        for n in cand["lanes"]["nebpi"]:
            p = nebpi.get((cid, n["context_id"]))
            _c(checks, f"json_parquet_nebpi::{cid}::{n['context_id']}",
               p is not None and p["nebpi_class"] == n["nebpi_class"]
               and p["nebpi_status"] == n["nebpi_status"],
               "NEBPI decision agrees between JSON and parquet")
        for e in cand["lanes"]["exposure"]:
            p = exposure.get(e["measurement_id"])
            _c(checks, f"json_parquet_exposure::{e['measurement_id']}",
               p is not None and p["margin_status"] == e["margin_status"]
               and p["margin_canonical_decimal"] == e.get("margin_canonical_decimal"),
               "exposure margin agrees between JSON and parquet")
    return checks


def _scan_forbidden(node: Any, forbidden: tuple[str, ...], path: str = "$") -> list[str]:
    hits: list[str] = []
    low = {f.lower() for f in forbidden}
    if isinstance(node, dict):
        for k, v in node.items():
            if str(k).lower() in low:
                hits.append(f"{path}.{k}")
            hits.extend(_scan_forbidden(v, forbidden, f"{path}.{k}"))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            hits.extend(_scan_forbidden(v, forbidden, f"{path}[{i}]"))
    return hits


def _selection_ok(out_dir: str, catalog: list[dict]) -> bool:
    with open(os.path.join(out_dir, "selection.json"), encoding="utf-8") as fh:
        sel = json.load(fh)
    if not sel.get("selected"):
        return True
    return all(r["acquisition_status"] == "acquired_public" for r in catalog)
