"""No unbound prose anywhere in the release.

`scorecards.json` is the document a human actually reads. Everything scientific in it is
reconstructed (components, classes, margins, eligibility, criteria) — but the SENTENCES were
not. They were typed into the emitter, hashed into nothing, and reconstructed by nothing. A
resealed release could have rewritten

    "CNS-MPO ... is not measured brain permeability ... It cannot satisfy any NEBPI branch."

into its opposite, or turned "'No relevant PD in NEB' is not established" into "established",
and every hash in the release would still have agreed. The machine-readable state beside the
sentence stayed honest; the sentence a reader believes did not.

The rule now, and it has no exemptions:

    EVERY string Stage 4 emits is either
      (A) declared in a method file          -> hashed into method_file_sha256 -> into the id;
      (B) a cell of a bound evidence-input row -> hashed into evidence_inputs_sha256 -> into the id;
      (C) part of the release's own identity  -> re-derived by `verifier/inputs.py`;
      (D) reconstructed exactly by `verifier/` (a margin transform, a field path);
    and there is no (E).

A string that is none of those is UNBOUND PROSE and this module fails the release. That is why
the interpolated explanations Stage 4 used to emit — `blocking_reason`, `margin_reason`,
`production_eligible.reason`, `missing_inputs.detail`, the delivery `rationale` it generated
itself — are TYPED CODES now, with their sentence declared in `method/stage4_prose_v1.json` and
in METHODS.md. A neighbouring machine code does not license unbound prose; it never did.

Imports nothing from `analysis/`.
"""

from __future__ import annotations

import json
import os
from typing import Any

import pyarrow.parquet as pq

from .inputs import input_columns

# The documents whose every string must be bound.
CHECKED_DOCS = ("scorecards.json", "selection.json")

# Derived tables carry generated cells too, and the same rule applies to them.
CHECKED_TABLES = ("delivery_evidence", "nebpi_decisions", "nebpi_criteria",
                  "exposure_evidence", "property_evidence", "safety_evidence",
                  "potency_evidence")

# Keys whose VALUE is a structural locator Stage 4 builds, not a sentence: they name a place in
# the document, and the ids they are built from are themselves bound. They are re-derived below
# rather than looked up.
RECONSTRUCTED_KEYS = ("field_path", "transform", "margin_transform", "unit_conversion")

# Tables whose EVERY cell is bound by identity, not by reconstruction:
#   source_catalog -> source_registry_sha256   (recomputed by verifier/inputs.py)
#   drug_forms     -> candidate_rows_sha256    (recomputed by verifier/inputs.py)
IDENTITY_TABLES = ("source_catalog", "drug_forms")

# Derived columns the verifier rebuilds cell-for-cell (derived.py, criteria.py, delivery.py).
# A scorecards.json copy of one of these is as bound as the cell it copies.
RECONSTRUCTED_COLUMNS: dict[str, tuple[str, ...]] = {
    "property_evidence": ("value_canonical_decimal", "value_in_base_units", "base_units",
                          "unit_conversion", "method_conformance", "component_score_t0",
                          "accepted", "rejection_reason_code"),
    "potency_evidence": ("value_canonical_decimal",),
    "exposure_evidence": ("concentration_canonical_decimal",
                          "quantitation_limit_canonical_decimal", "margin_status", "margin",
                          "margin_canonical_decimal", "margin_reason_code", "harmonized_units",
                          "exposure_harmonized", "potency_harmonized", "potency_id",
                          "potency_context_link_id", "margin_transform", "caveats"),
    "safety_evidence": ("renders_as_safe", "evidence_state_display"),
    "delivery_evidence": ("delivery_requirement", "nebpi_primary_gate", "reason_code",
                          "downgraded_from", "assignment_id", "conflicting_assignment_ids",
                          "evidence_source_record_id", "evidence_sha256"),
    "nebpi_decisions": ("nebpi_status", "nebpi_class", "nebpi_primary_gate",
                        "delivery_requirement", "derived_pk_level", "pd_state",
                        "radiographic_state", "pk_censored_bound_kind",
                        "pk_censored_bound_below_mec", "satisfied_branches",
                        "pk_margin_canonical_decimal", "pk_transform", "pk_blocked_code",
                        "pk_measurement_id", "pk_potency_id", "pk_detection_status",
                        "pk_censored_bound_source_string",
                        "pk_censored_bound_canonical_decimal", "pk_censored_bound_units",
                        "pk_censored_bound_over_mec_canonical_decimal", "reason_codes",
                        "method_id", "method_version"),
    "nebpi_criteria": ("status", "importance", "in_part_i_table",
                       "can_satisfy_part_ii_branch", "carried_the_assigned_class",
                       "evidence_lane_consumed", "requires_potency_context",
                       "n_observations", "observation_ids", "source_verbatim", "method_id"),
}


def _strings(node: Any, path: str, out: list[tuple[str, str]]) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            _strings(v, f"{path}.{k}", out)
    elif isinstance(node, list):
        for v in node:
            _strings(v, f"{path}[]", out)
    elif isinstance(node, str):
        out.append((path, node))


def method_strings(method_dir: str) -> set[str]:
    """(A) every string in every method file. Method files are hashed into the id."""
    out: set[str] = set()
    for name in sorted(os.listdir(method_dir)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(method_dir, name), encoding="utf-8") as fh:
            doc = json.load(fh)
        found: list[tuple[str, str]] = []
        _strings(doc, "$", found)
        out.update(v for _p, v in found)
        # keys too: a code emitted by Stage 4 is a KEY in the catalog, not a value
        _keys(doc, out)
    return out


def _keys(node: Any, out: set[str]) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            out.add(k)
            _keys(v, out)
    elif isinstance(node, list):
        for v in node:
            _keys(v, out)


def input_cell_strings(out_dir: str, version: str = "v1") -> set[str]:
    """(B) every string in a BOUND evidence-input cell. These feed evidence_inputs_sha256."""
    out: set[str] = set()
    for table, cols in input_columns(version).items():
        path = os.path.join(out_dir, f"{table}.parquet")
        if not os.path.exists(path):
            continue
        for row in pq.read_table(path).to_pylist():
            for c in cols:
                v = row.get(c)
                if isinstance(v, str):
                    out.add(v)
                elif isinstance(v, list):
                    out.update(x for x in v if isinstance(x, str))
    return out


def identity_strings(out_dir: str) -> set[str]:
    """(C) the release's own identity: every string in the id key, re-derived elsewhere."""
    with open(os.path.join(out_dir, "manifest.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)
    out: set[str] = set()
    found: list[tuple[str, str]] = []
    _strings(manifest.get("scorecard_set_id_inputs", {}), "$", found)
    out.update(v for _p, v in found)
    out.add(manifest.get("scorecard_set_id", ""))
    out.update(manifest.get("artifact_allowlist", []))
    for art in manifest.get("artifacts", []):
        out.update(str(v) for v in (art.get("filename"), art.get("table")) if v)
    return out


def derived_cell_strings(out_dir: str) -> set[str]:
    """(D) cells the verifier RECONSTRUCTS elsewhere (derived.py, criteria.py, delivery.py).

    These are already checked cell-for-cell against a rebuild, so a scorecards.json copy of one
    is as bound as the cell it copies. What this must NOT do is bless a string that appears in a
    derived cell BECAUSE the generator put it in both places — so only the tables whose derived
    columns are reconstructed are read, and only their reconstructed columns.
    """
    out: set[str] = set()
    for table in IDENTITY_TABLES:
        path = os.path.join(out_dir, f"{table}.parquet")
        if os.path.exists(path):
            for row in pq.read_table(path).to_pylist():
                for v in row.values():
                    if isinstance(v, str):
                        out.add(v)
                    elif isinstance(v, list):
                        out.update(x for x in v if isinstance(x, str))
    for table, cols in RECONSTRUCTED_COLUMNS.items():
        path = os.path.join(out_dir, f"{table}.parquet")
        if not os.path.exists(path):
            continue
        for row in pq.read_table(path).to_pylist():
            for c in cols:
                v = row.get(c)
                if isinstance(v, str):
                    out.add(v)
                elif isinstance(v, list):
                    out.update(x for x in v if isinstance(x, str))
    return out


def _reconstructed_field_paths(out_dir: str) -> set[str]:
    """Provenance-chain field paths, rebuilt from the bound ids they are made of."""
    out: set[str] = set()
    with open(os.path.join(out_dir, "scorecards.json"), encoding="utf-8") as fh:
        sc = json.load(fh)
    for cand in sc.get("candidates", []):
        cid = cand["candidate_id"]
        for prop in ("clogp", "clogd_74", "mw", "tpsa", "hbd", "pka_most_basic"):
            out.add(f"candidates.{cid}.lanes.cns_mpo.components.{prop}")
        out.add(f"candidates.{cid}.lanes.cns_mpo.total_published")
        for d in cand["lanes"]["delivery"]:
            out.add(f"candidates.{cid}.lanes.delivery.{d['context_id']}.requirement")
        for n in cand["lanes"]["nebpi"]:
            out.add(f"candidates.{cid}.lanes.nebpi.{n['context_id']}.nebpi_class")
        for e in cand["lanes"]["exposure"]:
            mid = e["measurement_id"]
            out.add(f"candidates.{cid}.lanes.exposure.{mid}.concentration")
            out.add(f"candidates.{cid}.lanes.exposure.{mid}.margin")
        for t in cand["lanes"]["transporters"]["transporters"]:
            for o in t["observations"]:
                out.add(f"candidates.{cid}.lanes.transporters.{t['transporter']}."
                        f"{o['observation_id']}")
        for s in cand["lanes"]["safety"]["rows"]:
            out.add(f"candidates.{cid}.lanes.safety.{s['evidence_id']}")
    return out


def _reconstructed_transforms(out_dir: str, method_dir: str) -> set[str]:
    """(D) the provenance-chain transforms, rebuilt from the bound cells they are made of.

    Each is a sentence ABOUT a computation, and every operand in it is a bound cell — so it is
    reconstructed here rather than declared. A tampered transform (`"MDCKII-MDR1 ... (human)"`
    rewritten to say `mouse`) does not match the rebuild and fails.
    """
    out: set[str] = set()

    trp = os.path.join(out_dir, "transporter_evidence.parquet")
    if os.path.exists(trp):
        for o in pq.read_table(trp).to_pylist():
            out.add(f"{o['assay']} in {o['biological_system']} ({o['species']})")

    dlv = os.path.join(out_dir, "delivery_evidence.parquet")
    if os.path.exists(dlv):
        for d in pq.read_table(dlv).to_pylist():
            out.add(f"delivery_rules::{d.get('rule_id') or 'default'} ({d['reason_code']})")

    with open(os.path.join(method_dir, "nebpi_grossman2026_v1.json"), encoding="utf-8") as fh:
        nebpi = json.load(fh)
    out.add("NEBPI Part-II branch logic over the criterion observations listed in "
            "evidence_observation_ids")
    out.add("sum of the six equally weighted T0 components, rounded half-up to 1 dp")
    for prop in ("clogp", "clogd_74", "mw", "tpsa", "hbd", "pka_most_basic"):
        shape = "hump" if prop == "tpsa" else "monotonic decreasing"
        out.add(f"{prop} desirability (Wager 2010 Table 1 {shape})")
    del nebpi
    return out


def bound_strings(out_dir: str, method_dir: str, version: str = "v1") -> set[str]:
    return (method_strings(method_dir)
            | input_cell_strings(out_dir, version)
            | identity_strings(out_dir)
            | derived_cell_strings(out_dir)
            | _reconstructed_field_paths(out_dir)
            | _reconstructed_transforms(out_dir, method_dir))


def unbound_prose(out_dir: str, method_dir: str, version: str = "v1") -> dict[str, list[str]]:
    """-> {json path: [unbound strings]}. Empty means every sentence is bound."""
    bound = bound_strings(out_dir, method_dir, version)
    problems: dict[str, list[str]] = {}

    for name in CHECKED_DOCS:
        path = os.path.join(out_dir, name)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        found: list[tuple[str, str]] = []
        _strings(doc, f"{name}", found)
        for p, v in found:
            if v not in bound:
                problems.setdefault(p, [])
                if v not in problems[p]:
                    problems[p].append(v)

    for table in CHECKED_TABLES:
        path = os.path.join(out_dir, f"{table}.parquet")
        if not os.path.exists(path):
            continue
        for row in pq.read_table(path).to_pylist():
            for k, v in row.items():
                vals = v if isinstance(v, list) else [v]
                for x in vals:
                    if isinstance(x, str) and x not in bound:
                        p = f"{table}.{k}"
                        problems.setdefault(p, [])
                        if x not in problems[p]:
                            problems[p].append(x)

    return {k: sorted(v) for k, v in sorted(problems.items())}


# --------------------------------------------------------------- required prose

def required_prose_failures(out_dir: str, method_dir: str) -> list[str]:
    """The guards must be PRESENT, verbatim, where they belong.

    `unbound_prose` catches a REWRITE. It cannot catch a DELETION: removing
    "CNS-MPO ... cannot satisfy any NEBPI branch" leaves nothing unbound behind, and in a
    resealed release the artifact hashes would agree. Silence is the cheapest way to lie.

    So the guards are also REQUIRED: each must equal the method's declaration exactly, at the
    place the reader looks for it.
    """
    with open(os.path.join(method_dir, "stage4_prose_v1.json"), encoding="utf-8") as fh:
        prose = json.load(fh)
    with open(os.path.join(out_dir, "scorecards.json"), encoding="utf-8") as fh:
        sc = json.load(fh)

    bad: list[str] = []

    def want(where: str, got: Any, expected: str) -> None:
        if got != expected:
            bad.append(f"{where}: the release says {got!r}, the method declares {expected!r}")

    want("ordering.note", sc.get("ordering", {}).get("note"),
         prose["set_level"]["ordering_note"])
    want("set_level.lanes_are_independent", sc.get("set_level", {}).get("lanes_are_independent"),
         prose["set_level"]["lanes_are_independent"])
    want("schema_id", sc.get("schema_id"), prose["schema_ids"]["scorecard_set"])
    want("upstream.stage3_contract_status",
         sc.get("upstream", {}).get("stage3_contract_status"),
         prose["stage3_contract_status"])

    display = prose["safety"]["evidence_state_display"]
    for cand in sc.get("candidates", []):
        cid = cand.get("candidate_id")
        want(f"{cid}.cns_mpo.interpretation_guard",
             cand["lanes"]["cns_mpo"].get("interpretation_guard"),
             prose["cns_mpo"]["interpretation_guard"])
        want(f"{cid}.transporters.interpretation_guard",
             cand["lanes"]["transporters"].get("interpretation_guard"),
             prose["transporters"]["interpretation_guard"])
        for t in cand["lanes"]["transporters"]["transporters"]:
            want(f"{cid}.transporters.{t['transporter']}.unqualified_boolean_note",
                 t.get("unqualified_boolean_note"),
                 prose["transporters"]["unqualified_boolean_note"])
            if t.get("unqualified_boolean") is not None:
                bad.append(f"{cid}.transporters.{t['transporter']}: an unqualified boolean was "
                           "emitted. A transporter interaction is qualified by assay, species "
                           "and biological system; a bare boolean discards exactly that.")
        for row in cand["lanes"]["safety"]["scenario_matrix"]:
            want(f"{cid}.scenario_matrix[{row.get('gbm_scenario')}].display_text",
                 row.get("display_text"), display.get(row.get("evidence_state"), ""))
            if row.get("renders_as_safe"):
                bad.append(f"{cid}.scenario_matrix: a row renders as SAFE. No evidence state "
                           "does — not even no_evidence_found.")
        for n in cand["lanes"]["nebpi"]:
            cf = n.get("counterfactual") or {}
            if "hard_rule" in cf:
                want(f"{cid}.nebpi.{n['context_id']}.counterfactual.hard_rule",
                     cf["hard_rule"], prose["nebpi"]["counterfactual"]["hard_rule"])
    return sorted(bad)
