#!/usr/bin/env python3
"""INDEPENDENT standalone verifier for the Stage-1 primary-source PROVENANCE integration.

Adversarial design (generator != verifier): this file re-parses the three source artifacts and
re-derives the expected 53-pair coverage FROM SCRATCH. It does NOT import gen_stage1_provenance's
build helpers, so an attacker who edits the builder (or forges a marker_provenance record and
re-hashes the registry) is still caught here.

Fail-closed: exits non-zero on ANY failure. Verifies:
  0. the 5 source-artifact SHA-256 match their pinned values (reject a changed input checksum)
  1. every measured marker-program pair (53) carries a bounded primary locator (reject a missing locator)
  2. each registry marker_provenance record matches the independent source row for that EXACT (program,gene)
     (reject a swapped program/gene or a forged pmid/doi/locator)
  3. no marker_provenance record is sourced to Masopust (naming-framework-only, never marker support)
  4. every inherited alias (actadj + activation predictor) resolves to an existing base record
  5. the measured-provenance denominator is exactly 53 (18 prior + 14 lineage + 21 state/CTL); HLA-DRA
     stays intended-only and out of the denominator; aliases are never counted (reject an inflated denom)
  6. the registry's SCORING PROJECTION (provenance-only keys dropped) equals the pinned pre-integration
     value -- i.e. no score/panel/control/bin/coef/coordinate field moved under cover of provenance
  7. registry_sha256 recomputes under the frozen rule; method_version + panel_provenance status intact
"""
import csv, hashlib, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "app", "data")
SRC_DEFAULT = os.path.join(HERE, "provenance_sources")
REGISTRY = os.path.join(DATA, "stage01_program_registry_v3.json")

METHOD_VERSION = "stage1-continuous-v3.0.1"
PROVENANCE_STATUS = "PRIMARY_LOCATORS_VERIFIED_BOUNDED"
# The scoring projection of the registry (provenance- + Tier-2 display-only keys removed) must never move.
# One-time reseal 2026-07-12: display_label reclassified as Tier-2 (dropped from the projection + the
# registry), so this scorer-core invariant advanced 9621067b… → 008c1da1… ONCE. Future cosmetic relabels
# are Tier-2 and do NOT move it (nor registry_sha256, raw, or the Stage-2-bound scorer VIEW).
PRE_SCORING_PROJECTION_SHA256 = "008c1da121a1ea3b08871f1bc0339b120d5dc9b46d01619768eebd046331bd85"

PINNED_SOURCE_SHA = {
    "stage01_panel_provenance_ledger.csv": "38094c6a9d075ae6f74297152b4ac812ce8e27dd2031b7ef7bfdba09b502736d",
    "lineage_primary_source_completion.csv": "ff35c27cf210a225cab4c8e072ba3f585ec841a091b0518aff352ae6f22c8ff8",
    "LINEAGE_REGISTRY_INTEGRATION_MAP.md": "776c75d905d0a0d76e4f7dacc154e48161993006e33449ba87662174be45678c",
    "state_ctl_primary_source_completion.csv": "febef35db329de0ecae95ca2654d6b3afd0e1b3b804b19fd46d11e0fe76df42f",
    "STATE_CTL_REGISTRY_INTEGRATION_MAP.md": "9a9afb132b9808bf1db51bebe90a8136d4b8051f65408f16ad746ffc43b03a22",
    "stage01_citation_correction_v1.json": "db95a8d7e6780dd550f75c8c358bd561ae0561edba2c23c20efd99303d4da580",
}
CITATION_CORRECTION_FILE = "stage01_citation_correction_v1.json"

PROV_TOP = ("citations_provenance_note", "registry_sha256",
            "panel_provenance_schema_version", "panel_provenance")
# per-program keys removed from the scorer projection: Tier-1 provenance/rationale (not scoring inputs)
# + Tier-2 display-only fields (display_label) so a cosmetic relabel can never move the scorer-core invariant.
PROV_PROG = ("selection_rationale", "citations", "citations_verification_status", "marker_provenance",
             "display_label")
# Tier-2 display-only fields that must NEVER live in the Tier-1 scientific registry (S1-M2 standalone check).
DISPLAY_ONLY_FIELDS = ("display_label",)


def _raw(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest() if os.path.exists(path) else None


def _canon(obj):
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def _n(x):
    if x is None:
        return None
    x = x.strip()
    return x or None


def _scoring_projection(reg):
    out = {k: v for k, v in reg.items() if k not in PROV_TOP and k not in ("programs", "sensitivity_lanes")}
    def strip(p):
        q = {k: v for k, v in p.items() if k not in PROV_PROG}
        if isinstance(q.get("activation_predictor"), dict):
            q["activation_predictor"] = {k: v for k, v in q["activation_predictor"].items()
                                         if k != "predictor_provenance"}
        return q
    out["programs"] = [strip(p) for p in reg.get("programs", [])]
    out["sensitivity_lanes"] = [strip(p) for p in reg.get("sensitivity_lanes", [])]
    return out


def _rows(src_dir, fname):
    with open(os.path.join(src_dir, fname), newline="") as f:
        return list(csv.DictReader(f))


def independent_source_model(src_dir):
    """Re-derive, from the raw CSVs, the expected (program,gene) -> {pmid,doi,exact_locator,bounded} map
    plus the intended-only set, the actadj/predictor alias bases, and the 18/14/21 split. No builder import."""
    expected = {}                 # (program, gene) -> dict
    origin = {}                   # (program, gene) -> 'prior'|'lineage'|'state_ctl'
    completion_keys = set()

    for r in _rows(src_dir, "lineage_primary_source_completion.csv"):
        key = (r["program_id"], r["marker"]); completion_keys.add(key)
        expected[key] = {"pmid": _n(r["pmid"]), "doi": _n(r["doi"]), "pmcid": _n(r["pmcid"]),
                         "exact_locator": _n(r["exact_locator"]), "bounded": _n(r["proposed_rationale_wording"]),
                         "masopust": r["masopust_used_as_marker_support"].strip().lower() == "true"}
        origin[key] = "lineage"

    intended_only = set()
    actadj_alias, predictor_alias = {}, {}
    for r in _rows(src_dir, "state_ctl_primary_source_completion.csv"):
        gene = r["marker"]
        if r["row_scope"] == "base_program_gap":
            key = (r["program_id"], gene); completion_keys.add(key)
            expected[key] = {"pmid": _n(r["pmid"]), "doi": _n(r["doi"]), "pmcid": _n(r["pmcid"]),
                             "exact_locator": _n(r["exact_locator"]), "bounded": _n(r["proposed_rationale_wording"]),
                             "masopust": False}
            origin[key] = "state_ctl"
        elif r["row_scope"] == "inherited_sensitivity_alias":
            actadj_alias[gene] = r["base_program_id"]
        elif r["row_scope"] == "activation_predictor_alias":
            predictor_alias[gene] = r["base_program_id"]

    for r in _rows(src_dir, "stage01_panel_provenance_ledger.csv"):
        prog, gene = r["program_id"], r["marker"]
        if prog.endswith("_actadj"):
            continue
        measured = r["measured_in_object"].strip().lower() == "true"
        if not measured:
            intended_only.add((prog, gene)); continue
        key = (prog, gene)
        if key in completion_keys:
            continue
        expected[key] = {"pmid": _n(r["cited_pmid"]), "doi": _n(r["cited_doi"]),
                         "pmcid": None, "exact_locator": _n(r["source_locator"]),
                         "bounded": _n(r["allowed_claim"]),
                         "masopust": "masopust" in (r["citation_key"] or "").lower(),
                         "evidence_class": r["evidence_class"]}
        origin[key] = "prior"

    return expected, origin, intended_only, actadj_alias, predictor_alias


def run_checks(reg, src_dir=SRC_DEFAULT):
    """Return a list of failure strings (empty == pass). Pure: operates on an in-memory registry dict."""
    fails = []

    # 0) source-artifact checksums
    for fname, want in PINNED_SOURCE_SHA.items():
        got = _raw(os.path.join(src_dir, fname))
        if got is None:
            fails.append(f"source_missing:{fname}")
        elif got != want:
            fails.append(f"source_checksum_changed:{fname}")

    try:
        expected, origin, intended_only, actadj_alias, predictor_alias = independent_source_model(src_dir)
    except Exception as ex:  # noqa: BLE001
        return fails + [f"source_parse_error:{ex}"]

    # walk registry measured pairs
    measured_pairs = 0
    split = {"prior": 0, "lineage": 0, "state_ctl": 0}
    base_records = {}  # (program, gene) -> record, for alias resolution
    for p in reg.get("programs", []):
        pid = p["program_id"]
        mp = p.get("marker_provenance", {})
        for gene in p["panel_genes_measured"]:
            key = (pid, gene)
            base_records[key] = mp.get(gene)
            rec = mp.get(gene)
            if rec is None:
                fails.append(f"no_marker_provenance:{pid}.{gene}"); continue
            if not _n(rec.get("exact_locator")):
                fails.append(f"missing_locator:{pid}.{gene}")
            if rec.get("provenance_inherited") is not False:
                fails.append(f"base_row_not_inherited_false:{pid}.{gene}")
            if not rec.get("measured_in_object") or not rec.get("contributes_to_score"):
                fails.append(f"measured_flags_wrong:{pid}.{gene}")
            exp = expected.get(key)
            if exp is None:
                fails.append(f"unexpected_measured_pair_or_swap:{pid}.{gene}")
            else:
                measured_pairs += 1
                split[origin[key]] += 1
                for f in ("pmid", "doi", "exact_locator"):
                    if _n(rec.get(f)) != exp[f]:
                        fails.append(f"source_field_mismatch:{pid}.{gene}:{f}")
                if _n(rec.get("bounded_rationale")) != exp["bounded"]:
                    fails.append(f"bounded_rationale_mismatch:{pid}.{gene}")
                # completed genes must carry the bounded wording as the per-gene selection_rationale too
                if origin[key] in ("lineage", "state_ctl") and _n(p["selection_rationale"].get(gene)) != exp["bounded"]:
                    fails.append(f"selection_rationale_not_bounded:{pid}.{gene}")
            # Masopust must never appear as marker evidence
            blob = json.dumps(rec, ensure_ascii=False).lower()
            if "masopust" in blob:
                fails.append(f"masopust_as_marker_source:{pid}.{gene}")
        # intended-only markers present must be flagged, not measured, out of denominator
        for gene, rec in mp.items():
            if gene not in p["panel_genes_measured"]:
                if (pid, gene) not in intended_only:
                    fails.append(f"unknown_non_measured_marker:{pid}.{gene}")
                if rec.get("measured_in_object") is not False or rec.get("contributes_to_score") is not False:
                    fails.append(f"intended_only_not_zeroed:{pid}.{gene}")
                if rec.get("in_measured_provenance_denominator") is not False or _n(rec.get("pmid")):
                    fails.append(f"intended_only_has_measured_locator:{pid}.{gene}")

    # 4) inherited aliases resolve to a base record
    for lane in reg.get("sensitivity_lanes", []):
        for gene, rec in lane.get("marker_provenance", {}).items():
            if rec.get("provenance_inherited") is not True or rec.get("counted_in_primary_panel_totals") is not False:
                fails.append(f"actadj_alias_not_inherited:{lane['program_id']}.{gene}")
            ref = rec.get("base_marker_provenance_ref", "")
            bp, bg = rec.get("base_program_id"), ref.split(".")[-1]
            if (bp, bg) not in base_records or base_records[(bp, bg)] is None or bg != gene:
                fails.append(f"unresolvable_alias:{lane['program_id']}.{gene}")
        ap = lane.get("activation_predictor", {}) or {}
        for gene, rec in (ap.get("predictor_provenance", {}) or {}).items():
            if rec.get("provenance_inherited") is not True or rec.get("counted_in_primary_panel_totals") is not False:
                fails.append(f"predictor_alias_not_inherited:{lane['program_id']}.{gene}")
            bp, bg = rec.get("base_program_id"), rec.get("base_marker_provenance_ref", "").split(".")[-1]
            if (bp, bg) not in base_records or base_records[(bp, bg)] is None or bg != gene:
                fails.append(f"unresolvable_predictor_alias:{lane['program_id']}.{gene}")
        if lane["program_id"] == "cd4_ctl_like_actadj" and lane.get("stage2_selectable") is not False:
            fails.append("actadj_stage2_selectable_not_false")

    # 5) denominator exactly 53 with the 18/14/21 split; panel_provenance must not inflate it
    if measured_pairs != 53:
        fails.append(f"denominator_not_53:{measured_pairs}")
    if split != {"prior": 18, "lineage": 14, "state_ctl": 21}:
        fails.append(f"coverage_split_wrong:{split}")
    pp = reg.get("panel_provenance", {})
    if pp.get("measured_marker_pairs_total") != 53 or pp.get("measured_marker_pairs_with_primary_locator") != 53:
        fails.append("panel_provenance_denominator_inflated_or_wrong")
    cb = pp.get("coverage_breakdown", {})
    if (cb.get("already_primary_located_prior_ledger"), cb.get("lineage_supplement_completions"),
            cb.get("state_ctl_supplement_completions")) != (18, 14, 21):
        fails.append("panel_provenance_coverage_breakdown_mismatch")
    if pp.get("status") != PROVENANCE_STATUS or "UNVERIFIED" in str(pp.get("status")):
        fails.append("panel_provenance_status_not_bounded")

    # 5b) W17 citation-correction overlay applied VERBATIM from the pinned artifact (generator != verifier:
    #     re-read the pin directly here; its sha is checked in step 0). Mouse paper retained as main origin;
    #     verified direct human primary added as human_primary_support; FOXP3 nested support_level corrected.
    try:
        corr = json.load(open(os.path.join(src_dir, CITATION_CORRECTION_FILE)))
    except Exception as ex:  # noqa: BLE001
        corr = None
        fails.append(f"citation_correction_unreadable:{ex}")
    if corr is not None:
        for pg, spec in corr.get("human_primary_additions", {}).items():
            prog, gene = pg.split(".")
            rec = base_records.get((prog, gene))
            if rec is None:
                fails.append(f"citation_correction_pair_missing:{pg}"); continue
            if rec.get("pmid") != spec["mouse_mechanistic_origin_pmid"]:
                fails.append(f"citation_correction_main_pmid_not_mouse_origin:{pg}")   # mouse paper retained as origin
            if rec.get("mouse_mechanistic_origin_pmid") != spec["mouse_mechanistic_origin_pmid"]:
                fails.append(f"citation_correction_mouse_origin_missing:{pg}")
            if rec.get("species_lineage_scope") != spec["corrected_species_lineage_scope"]:
                fails.append(f"citation_correction_scope_not_applied:{pg}")
            if rec.get("human_primary_support") != spec["human_primary_support"]:
                fails.append(f"citation_correction_human_block_mismatch:{pg}")
            hps = rec.get("human_primary_support") or {}
            if hps.get("verification_status") != "verified" or hps.get("species_lineage_scope") != "human":
                fails.append(f"citation_correction_human_block_not_verified_human:{pg}")
        for pg, spec in corr.get("nested_support_level_corrections", {}).items():
            prog, gene = pg.split(".")
            block = (base_records.get((prog, gene)) or {}).get(spec["nested_key"]) or {}
            if block.get("pmid") != spec["pmid"]:
                fails.append(f"citation_correction_nested_pmid_mismatch:{pg}")
            if block.get("support_level") != spec["to_support_level"]:
                fails.append(f"citation_correction_nested_support_level_not_applied:{pg}")
            if block.get("verification_status") != spec["verification_status"]:
                fails.append(f"citation_correction_nested_not_verified:{pg}")

    # 6) scoring projection unchanged
    if _canon(_scoring_projection(reg)) != PRE_SCORING_PROJECTION_SHA256:
        fails.append("scoring_projection_changed")

    # 7) registry_sha256 recomputes; method_version intact
    d = {k: v for k, v in reg.items() if k != "registry_sha256"}
    if _canon(d) != reg.get("registry_sha256"):
        fails.append("registry_sha256_does_not_recompute")
    if reg.get("method_version") != METHOD_VERSION:
        fails.append("method_version_changed")

    # 8) Tier-2 display fields must NOT live in the Tier-1 scientific registry (S1-M2). A resealed
    #    display_label reinsert re-hashes registry_sha256 so check 7 passes — this catches the leak directly,
    #    so the STANDALONE verifier rejects it, not only the reproduce-path protected checker.
    leaked = sorted({p.get("program_id") or p.get("score_field")
                     for grp in ("programs", "sensitivity_lanes") for p in reg.get(grp, [])
                     if any(f in p for f in DISPLAY_ONLY_FIELDS)})
    if leaked:
        fails.append(f"tier2_field_in_tier1_registry:{leaked}")

    return fails


def main(argv):
    reg_path = argv[1] if len(argv) > 1 else REGISTRY
    src_dir = argv[2] if len(argv) > 2 else SRC_DEFAULT
    reg = json.load(open(reg_path))
    fails = run_checks(reg, src_dir)
    for f in fails:
        print(f"  [FAIL] {f}")
    if fails:
        print(f"\nPROVENANCE VERIFIER: FAIL ({len(fails)} issue(s))")
        sys.exit(1)
    print("PROVENANCE VERIFIER: PASS  (53/53 measured pairs primary-located; projection + hashes intact)")
    sys.exit(0)


if __name__ == "__main__":
    main(sys.argv)
