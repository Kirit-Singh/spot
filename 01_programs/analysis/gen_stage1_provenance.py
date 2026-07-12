#!/usr/bin/env python3
"""Integrate independently-verified Stage-1 PRIMARY-SOURCE provenance into the v3 registry.

This is a PROVENANCE-ONLY, deterministic, idempotent integration. It writes structured per-marker
`marker_provenance` into `stage01_program_registry_v3.json` (served + release-staging copies) by merging
three independently produced source artifacts:

  * prior 60-row marker ledger              (18 measured pairs already primary-located)
  * lineage primary-source completion       (14 measured pairs completed/corrected)
  * state/CTL primary-source completion      (21 measured pairs completed) + inherited aliases

It NEVER changes a panel gene, gene id, control, bin, seed, coefficient, normalization, score, coordinate,
validation result, or the scorer `method_version`. It updates only literature/provenance metadata and
recomputes the registry's internal canonical hash (`registry_sha256`, frozen rule: sha256 of sorted +
compact JSON, ensure_ascii=True, excluding only `registry_sha256`).

Run:  python3 gen_stage1_provenance.py
"""
import csv, hashlib, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "app", "data")
STAGING = os.path.join(HERE, "_t8_staging")
SRC = os.path.join(HERE, "provenance_sources")

REGISTRY_SERVED = os.path.join(DATA, "stage01_program_registry_v3.json")
REGISTRY_STAGED = os.path.join(STAGING, "stage01_program_registry_v3.candidate.json")

METHOD_VERSION = "stage1-continuous-v3.0.1"
PANEL_PROVENANCE_SCHEMA = "spot.stage01_panel_provenance.v1"
PROVENANCE_STATUS = "PRIMARY_LOCATORS_VERIFIED_BOUNDED"

# Pinned source-artifact SHA-256 (independently verified upstream). Build is fail-closed on mismatch.
SOURCE_ARTIFACTS = [
    {"role": "prior_marker_ledger", "file": "stage01_panel_provenance_ledger.csv",
     "sha256": "596a4435cbd729dbcbfa68df2adef730b1807fa9c0e8c39f0f102c284c4f3461"},
    {"role": "lineage_completion", "file": "lineage_primary_source_completion.csv",
     "sha256": "ff35c27cf210a225cab4c8e072ba3f585ec841a091b0518aff352ae6f22c8ff8"},
    {"role": "lineage_integration_map", "file": "LINEAGE_REGISTRY_INTEGRATION_MAP.md",
     "sha256": "776c75d905d0a0d76e4f7dacc154e48161993006e33449ba87662174be45678c"},
    {"role": "state_ctl_completion", "file": "state_ctl_primary_source_completion.csv",
     "sha256": "febef35db329de0ecae95ca2654d6b3afd0e1b3b804b19fd46d11e0fe76df42f"},
    {"role": "state_ctl_integration_map", "file": "STATE_CTL_REGISTRY_INTEGRATION_MAP.md",
     "sha256": "9a9afb132b9808bf1db51bebe90a8136d4b8051f65408f16ad746ffc43b03a22"},
]

PROV_TOP = ("citations_provenance_note", "registry_sha256",
            "panel_provenance_schema_version", "panel_provenance")


def _raw(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def _registry_sha256(reg):
    d = {k: v for k, v in reg.items() if k != "registry_sha256"}
    return hashlib.sha256(json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def _n(x):
    """Empty CSV cell -> None; else stripped string."""
    if x is None:
        return None
    x = x.strip()
    return x or None


def _rows(fname):
    with open(os.path.join(SRC, fname), newline="") as f:
        return list(csv.DictReader(f))


def verify_sources():
    for a in SOURCE_ARTIFACTS:
        got = _raw(os.path.join(SRC, a["file"]))
        if got != a["sha256"]:
            sys.exit(f"ABORT: source {a['file']} sha {got} != pinned {a['sha256']}")


# ----------------------------------------------------------------------------------------------------
# Build the per-(program,gene) marker_provenance records from the three source artifacts.
# ----------------------------------------------------------------------------------------------------
def build_records():
    """Return (base_by_prog_gene, intended_only, actadj_inherited, predictor_inherited, coverage_counts)."""
    ledger = _rows("stage01_panel_provenance_ledger.csv")
    lineage = _rows("lineage_primary_source_completion.csv")
    statectl = _rows("state_ctl_primary_source_completion.csv")

    completion_keys = set()  # (program_id, gene) covered by a supplement -> excluded from the "18"
    base = {}                # (program_id, gene) -> record
    counts = {"prior_ledger": 0, "lineage": 0, "state_ctl": 0}

    # ---- lineage supplement (14 measured pairs) ----
    for r in lineage:
        key = (r["program_id"], r["marker"])
        completion_keys.add(key)
        assert r["masopust_used_as_marker_support"].strip().lower() == "false", f"Masopust flagged: {key}"
        rec = {
            "source_type": "primary_research",
            "pmid": _n(r["pmid"]), "pmcid": _n(r["pmcid"]), "doi": _n(r["doi"]),
            "source_title": _n(r["source_title"]), "source_year": _n(r["year"]),
            "source_url": _n(r["source_url"]),
            "exact_locator": _n(r["exact_locator"]),
            "support_level": _n(r["support_level"]),
            "species_lineage_scope": _n(r["human_t_cell_scope"]),
            "claim_scope_limit": _n(r["claim_scope_and_limits"]),
            "bounded_rationale": _n(r["proposed_rationale_wording"]),
            "located_support_summary": _n(r["located_support_summary"]),
            "measured_in_object": True, "contributes_to_score": True, "provenance_inherited": False,
            "provenance_origin": "lineage_supplement",
            "completion_status": _n(r["completion_status"]),
        }
        base[key] = rec
        counts["lineage"] += 1

    # ---- state/CTL supplement: base gaps (21), inherited actadj alias (1), predictor aliases (5) ----
    actadj_inherited = {}      # gene -> record (cd4_ctl_like_actadj)
    predictor_inherited = {}   # gene -> record (activation_predictor)
    for r in statectl:
        scope = r["row_scope"]
        gene = r["marker"]
        if scope == "base_program_gap":
            key = (r["program_id"], gene)
            completion_keys.add(key)
            rec = {
                "source_type": "primary_research",
                "pmid": _n(r["pmid"]), "pmcid": _n(r["pmcid"]), "doi": _n(r["doi"]),
                "source_title": _n(r["title"]), "source_year": _n(r["year"]),
                "source_url": _n(r["source_url"]),
                "exact_locator": _n(r["exact_locator"]),
                "support_level": _n(r["support_level"]),
                "species_lineage_scope": _n(r["species_lineage_scope"]),
                "claim_scope_limit": _n(r["claim_scope_limit"]),
                "bounded_rationale": _n(r["proposed_rationale_wording"]),
                "measured_in_object": True, "contributes_to_score": True, "provenance_inherited": False,
                "provenance_origin": "state_ctl_supplement",
                "completion_status": _n(r["completion_status"]),
            }
            corr = _n(r["corroborating_pmid"])
            if corr:
                rec["corroborating_source"] = {
                    "pmid": corr, "pmcid": _n(r["corroborating_pmcid"]), "doi": _n(r["corroborating_doi"]),
                    "source_title": _n(r["corroborating_title"]), "source_year": _n(r["corroborating_year"]),
                    "source_url": _n(r["corroborating_url"]), "exact_locator": _n(r["corroborating_locator"]),
                    "evidence_class": "orthogonal_corroboration_separate_from_primary",
                }
            base[key] = rec
            counts["state_ctl"] += 1
        elif scope == "inherited_sensitivity_alias":
            actadj_inherited[gene] = {
                "provenance_inherited": True,
                "base_program_id": r["base_program_id"],
                "base_marker_provenance_ref": f"{r['base_program_id']}.marker_provenance.{gene}",
                "bounded_rationale": _n(r["proposed_rationale_wording"]),
                "measured_in_object": True, "contributes_to_score": True,
                "counted_in_primary_panel_totals": False,
            }
        elif scope == "activation_predictor_alias":
            predictor_inherited[gene] = {
                "provenance_inherited": True,
                "base_program_id": r["base_program_id"],
                "base_marker_provenance_ref": f"{r['base_program_id']}.marker_provenance.{gene}",
                "bounded_rationale": _n(r["proposed_rationale_wording"]),
                "is_panel_row": False, "counted_in_primary_panel_totals": False,
            }
        else:
            sys.exit(f"ABORT: unknown state/CTL row_scope {scope!r}")

    # ---- prior ledger: the 18 already-primary-located measured pairs + intended-only HLA-DRA + actadj bases ----
    intended_only = {}
    ledger_actadj = {}  # gene -> bounded rationale for the 5 non-KLRD1 actadj rows
    for r in ledger:
        prog, gene = r["program_id"], r["marker"]
        measured = r["measured_in_object"].strip().lower() == "true"
        inherited = r["provenance_inherited"].strip().lower() == "true"
        if prog == "cd4_ctl_like_actadj":
            ledger_actadj[gene] = _n(r["allowed_claim"])
            continue
        if not measured:  # HLA-DRA intended-only
            intended_only[(prog, gene)] = {
                "source_type": "intended_only_no_measured_locator",
                "pmid": None, "pmcid": None, "doi": None,
                "exact_locator": "INTENDED_ONLY: present in panel_genes_intended, absent from "
                                 "panel_genes_measured; contributes zero to the score.",
                "support_level": "intended_only_not_measured",
                "species_lineage_scope": _n(r["species_basis"]),
                "claim_scope_limit": "Intended-only; not measured in the object; carries no measured-marker "
                                     "primary locator and is outside the measured-provenance denominator.",
                "bounded_rationale": "HLA-DRA is an intended late-activation (MHC-II) marker that is ABSENT "
                                     "from panel_genes_measured and contributes zero to the score.",
                "measured_in_object": False, "contributes_to_score": False, "provenance_inherited": False,
                "in_measured_provenance_denominator": False,
                "provenance_origin": "prior_ledger_intended_only",
            }
            continue
        key = (prog, gene)
        if key in completion_keys:
            continue  # superseded/completed by a supplement -> not one of the "18"
        # remaining measured base rows are the already-primary-located "18"
        assert r["evidence_class"] == "directly_supported_primary", \
            f"unexpected non-primary base row not covered by a supplement: {key} ({r['evidence_class']})"
        rec = {
            "source_type": "primary_research",
            "pmid": _n(r["cited_pmid"]), "pmcid": None, "doi": _n(r["cited_doi"]),
            "source_title": _n(r["cited_title"]), "source_year": None, "source_url": None,
            "exact_locator": _n(r["source_locator"]),
            "support_level": _n(r["evidence_class"]),
            "support_basis": _n(r["support_basis"]),
            "species_lineage_scope": _n(r["species_basis"]),
            "claim_scope_limit": _n(r["specificity_limit"]),
            "bounded_rationale": _n(r["allowed_claim"]),
            "measured_in_object": True, "contributes_to_score": True, "provenance_inherited": False,
            "provenance_origin": "prior_ledger_primary_located",
            "citation_key": _n(r["citation_key"]),
        }
        ext = _n(r["external_primary_support"])
        if ext:
            rec["external_corroboration_note"] = ext
        base[key] = rec
        counts["prior_ledger"] += 1

    # merge the ledger actadj bounded rationale for the 5 non-KLRD1 inherited rows
    for gene, br in ledger_actadj.items():
        if gene in actadj_inherited:
            continue  # KLRD1 comes from the state/CTL supplement (more specific wording)
        actadj_inherited[gene] = {
            "provenance_inherited": True,
            "base_program_id": "cd4_ctl_like",
            "base_marker_provenance_ref": f"cd4_ctl_like.marker_provenance.{gene}",
            "bounded_rationale": br,
            "measured_in_object": True, "contributes_to_score": True,
            "counted_in_primary_panel_totals": False,
        }

    return base, intended_only, actadj_inherited, predictor_inherited, counts


# ----------------------------------------------------------------------------------------------------
# Apply the records to the registry.
# ----------------------------------------------------------------------------------------------------
def integrate(reg, base, intended_only, actadj_inherited, predictor_inherited, counts):
    measured_total = 0
    for prog in reg["programs"]:
        pid = prog["program_id"]
        measured = prog["panel_genes_measured"]
        mp = {}
        for gene in measured:
            key = (pid, gene)
            rec = base.get(key)
            assert rec is not None, f"no primary provenance for measured pair {key}"
            # corrected bounded rationale becomes the per-gene selection_rationale for completed genes
            if rec["provenance_origin"] in ("lineage_supplement", "state_ctl_supplement"):
                prog["selection_rationale"][gene] = rec["bounded_rationale"]
            mp[gene] = rec
            measured_total += 1
        # intended-only genes (e.g. HLA-DRA) are recorded but excluded from the measured denominator
        for (p2, gene), rec in intended_only.items():
            if p2 == pid:
                mp[gene] = rec
        # place marker_provenance right after citations
        _insert_after(prog, "citations", "marker_provenance", mp)
        prog["citations_verification_status"] = PROVENANCE_STATUS

    # activation-adjusted sensitivity lane: inheritance pointers only (no duplicate evidence)
    for lane in reg.get("sensitivity_lanes", []):
        if lane["program_id"] == "cd4_ctl_like_actadj":
            mp = {}
            for gene in lane["panel_genes_measured"]:
                assert gene in actadj_inherited, f"no inherited actadj record for {gene}"
                mp[gene] = actadj_inherited[gene]
            _insert_after(lane, "scoring_method", "marker_provenance", mp)
            ap = lane.get("activation_predictor")
            if ap is not None:
                pp = {}
                for gene in ap.get("panel_measured", []):
                    assert gene in predictor_inherited, f"no inherited predictor record for {gene}"
                    pp[gene] = predictor_inherited[gene]
                ap["predictor_provenance"] = pp

    assert measured_total == 53, f"measured pairs = {measured_total}, expected 53"
    assert counts == {"prior_ledger": 18, "lineage": 14, "state_ctl": 21}, counts

    # ---- top-level machine-readable provenance summary ----
    panel_provenance = {
        "schema": PANEL_PROVENANCE_SCHEMA,
        "status": PROVENANCE_STATUS,
        "status_note": "Every measured marker-program pair carries a bounded primary-source locator; "
                       "predictive/associative claims remain suggestive, never confirmatory.",
        "measured_marker_pairs_total": 53,
        "measured_marker_pairs_with_primary_locator": 53,
        "coverage_breakdown": {
            "already_primary_located_prior_ledger": counts["prior_ledger"],
            "lineage_supplement_completions": counts["lineage"],
            "state_ctl_supplement_completions": counts["state_ctl"],
        },
        "intended_only_excluded_from_denominator": ["diff_activated.HLA-DRA"],
        "inherited_aliases_not_counted": {
            "cd4_ctl_like_actadj.marker_provenance": sorted(actadj_inherited),
            "cd4_ctl_like_actadj.activation_predictor.predictor_provenance": sorted(predictor_inherited),
        },
        "masopust_scope": "naming_framework_only_never_attached_as_marker_support",
        "source_artifacts": [
            {"role": a["role"], "file": f"analysis/provenance_sources/{a['file']}", "sha256": a["sha256"]}
            for a in SOURCE_ARTIFACTS
        ],
        "method_version_unchanged": METHOD_VERSION,
        "not_a_scorer_method_revision": "Literature/provenance metadata revision only. Panels, gene ids, "
            "controls, bins, seeds, coefficients, normalization and all scores are byte-identical; this is "
            "an additive panel_provenance sub-schema, not a scorer method_version bump.",
        "not_a_production_or_selectability_promotion": "Provenance-only. The frozen 0/33 production-"
            "selectability result, overlay/app deployment gates, and the candidate pointer are unchanged.",
    }
    _insert_after(reg, "sensitivity_lanes", "panel_provenance", panel_provenance)
    reg["panel_provenance_schema_version"] = PANEL_PROVENANCE_SCHEMA
    reg["citations_provenance_note"] = (
        "Per-program `citations` remain program-level references; per-marker PRIMARY provenance is now "
        "carried in structured `marker_provenance` and summarized in `panel_provenance`. 53/53 measured "
        "marker-program pairs carry a bounded primary-source locator, independently completed by the "
        "lineage and state/CTL supplements (artifact SHA-256 in `panel_provenance.source_artifacts`). "
        "Intended-only HLA-DRA is excluded from the measured denominator. Masopust 2026 is recorded as a "
        "naming framework only and is never attached to any marker as evidence.")
    # move schema key next to schema_version, keep registry_sha256 last
    _reorder_top(reg)
    reg["registry_sha256"] = _registry_sha256(reg)
    return reg


def _insert_after(d, after_key, new_key, value):
    """Insert new_key:value into ordered dict d right after after_key (rebuild preserving order)."""
    items = [(k, v) for k, v in d.items() if k != new_key]
    out = {}
    for k, v in items:
        out[k] = v
        if k == after_key:
            out[new_key] = value
    if new_key not in out:  # after_key absent -> append
        out[new_key] = value
    d.clear(); d.update(out)


def _reorder_top(reg):
    """panel_provenance_schema_version right after schema_version; registry_sha256 stays last."""
    order = ["schema_version", "panel_provenance_schema_version", "method_version", "master_seed",
             "input_manifest", "coordinates_sha256", "scores_canonical_content_sha256",
             "programs", "sensitivity_lanes", "panel_provenance", "citations_provenance_note",
             "registry_sha256"]
    out = {k: reg[k] for k in order if k in reg}
    for k, v in reg.items():  # any unexpected key preserved
        if k not in out:
            out[k] = v
    reg.clear(); reg.update(out)


def main():
    verify_sources()
    reg = json.load(open(REGISTRY_SERVED))
    assert reg["method_version"] == METHOD_VERSION, "scorer method_version must not change"
    base, intended_only, actadj_inherited, predictor_inherited, counts = build_records()
    reg = integrate(reg, base, intended_only, actadj_inherited, predictor_inherited, counts)
    text = json.dumps(reg, indent=1, ensure_ascii=True, sort_keys=False)
    for path in (REGISTRY_SERVED, REGISTRY_STAGED):
        with open(path, "w") as f:
            f.write(text)   # no trailing newline (matches the frozen registry byte format)
    print("WROTE served + staged registry")
    print(f"  registry_sha256 = {reg['registry_sha256']}")
    print(f"  served raw       = {_raw(REGISTRY_SERVED)}")
    print(f"  staged raw       = {_raw(REGISTRY_STAGED)}")
    print(f"  coverage         = {counts}  measured_total=53")


if __name__ == "__main__":
    main()
