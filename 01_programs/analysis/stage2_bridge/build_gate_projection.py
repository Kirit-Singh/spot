"""CP3b — build the TYPED Direct-shape gate projection from constituent evidence.

Replaces the earlier lossy nine-item conflated gate list. Two typed lists:
  * measurement_hard_gates  : the SEVEN Stage-1 measurement-validity subchecks
    (coverage 1 + condition 2 + LOMO 2 + control-draw 2);
  * base_portability_checks : the TWO separate Stage-2 program-level checks.

Each Direct-shape validation row carries mathematically-sufficient aggregation metadata
(n_expected / n_defined / n_undefined / worst_defined_value) so the evaluator derives
`pass = (n_defined == n_expected && n_undefined == 0 && comparator(worst, threshold))`
WITHOUT trusting any stored pass boolean and WITHOUT a numeric sentinel. The evaluated
`value` is null whenever `n_undefined > 0` (measurement_state:"undefined"); the lossy frozen
extremum is preserved separately as `source_worst_defined_value`.
"""
from __future__ import annotations

import json
import os

import canonical
import constituents as C

METHOD_VERSION = "stage1-continuous-v3.0.1"
GATE_SPEC_SCHEMA = "spot.stage01_gate_spec.typed.v1"
ROWS_SCHEMA = "spot.stage01_validation.direct_rows.typed.v1"
OP2CMP = {">=": "ge", ">": "gt", "<=": "le", "<": "lt", "==": "eq"}

HERE = os.path.dirname(os.path.abspath(__file__))
STAGING = os.path.join(HERE, "_release_staging")


def build_typed_gate_spec() -> dict:
    def spec(sid, meta, grid_kind):
        fam, cls, op, thr, kind = meta
        return {"comparator": OP2CMP[op], "threshold": thr, "source_operator": op,
                "gate_family": fam, "gate_class": cls, "grid_kind": kind}
    thresholds = {}
    for sid, meta in {**C.MEASUREMENT_SUBCHECKS, **C.PORTABILITY_SUBCHECKS}.items():
        thresholds[sid] = spec(sid, meta, meta[4])
    return {
        "schema_version": GATE_SPEC_SCHEMA,
        "method_version": METHOD_VERSION,
        "measurement_hard_gates": list(C.MEASUREMENT_SUBCHECKS),
        "base_portability_checks": list(C.PORTABILITY_SUBCHECKS),
        "thresholds": thresholds,
        "policies": {
            "undefined_is_fail": True,
            "no_numeric_sentinel": True,
            "measurement_states": ["measured", "undefined"],
            "comparators": {"ge": ">=", "gt": ">", "le": "<=", "lt": "<", "eq": "=="},
            "subcheck_pass_rule": ("n_present == n_expected AND n_undefined == 0 AND "
                                   "comparator(worst_defined_value, threshold)"),
            "production_selectable_rule": "AND over the SEVEN measurement_hard_gates ONLY",
            "base_portable_rule": "AND over the TWO base_portability_checks (separate; never gates production)",
            "value_semantics": ("value is the worst_defined_value when measurement_state=='measured' "
                                "(n_undefined==0); value is null when measurement_state=='undefined' "
                                "(n_undefined>0). A null value can never be relabeled passed; a numeric "
                                "value under an 'undefined' state is refused."),
        },
    }


def _measurement_row(agg: dict, condition: str, origin: str) -> dict:
    measured = agg["measurement_state"] == "measured"
    row = {
        "program_id": agg["program_id"],
        "condition": condition,
        "gate_id": agg["subcheck_id"],
        "gate_class": agg["gate_class"],
        "value": agg["worst_defined_value"] if measured else None,
        "measurement_state": agg["measurement_state"],
        "n_expected": agg["n_expected"],
        "n_present": agg["n_present"],
        "n_defined": agg["n_defined"],
        "n_undefined": agg["n_undefined"],
        "source_worst_defined_value": agg["worst_defined_value"],
        "operator": agg["operator"],
        "threshold": agg["threshold"],
        "origin": origin,
    }
    if not measured:
        row["undefined_reasons"] = agg["undefined_reasons"]
    return row


def build_validation_rows(aggregates: dict) -> dict:
    """Direct-shape rows: 11 programs x 3 conditions x 7 measurement subchecks = 231 rows
    (coverage replicated across the 3 conditions), plus 22 program-level portability rows."""
    rows = []
    null_rows = []
    for (pid, cond, sid), agg in aggregates.items():
        if sid not in C.MEASUREMENT_SUBCHECKS:
            continue
        if cond is None:                       # program-level (coverage): replicate to each condition
            for c in C.CONDS:
                r = _measurement_row(agg, c, "program_level_replicated")
                rows.append(r)
                if r["value"] is None:
                    null_rows.append({k: r[k] for k in ("program_id", "condition", "gate_id")})
        else:
            r = _measurement_row(agg, cond, "program_condition")
            rows.append(r)
            if r["value"] is None:
                null_rows.append({k: r[k] for k in ("program_id", "condition", "gate_id")})

    portability = []
    for (pid, cond, sid), agg in aggregates.items():
        if sid not in C.PORTABILITY_SUBCHECKS:
            continue
        portability.append({
            "program_id": pid, "gate_id": sid, "gate_class": agg["gate_class"],
            "value": agg["worst_defined_value"], "n_expected": agg["n_expected"],
            "n_defined": agg["n_defined"], "n_undefined": agg["n_undefined"],
            "operator": agg["operator"], "threshold": agg["threshold"],
        })
    rows.sort(key=lambda r: (r["gate_id"], r["program_id"], r["condition"]))
    portability.sort(key=lambda r: (r["gate_id"], r["program_id"]))
    return {
        "schema_version": ROWS_SCHEMA,
        "method_version": METHOD_VERSION,
        "note": ("Typed Direct-shape rows derived from the constituent evidence table. Every "
                 "value is either an exact worst_defined_value over defined constituents "
                 "(measurement_state:measured) or null (measurement_state:undefined, n_undefined>0). "
                 "No numeric sentinel; no stored pass boolean is carried as the evaluator."),
        "n_programs": len({r["program_id"] for r in rows}),
        "conditions": list(C.CONDS),
        "n_measurement_rows": len(rows),
        "n_portability_rows": len(portability),
        "n_null_rows": len(null_rows),
        "null_rows": null_rows,
        "measurement_rows": rows,
        "portability_rows": portability,
    }


def _sources():
    mirror = os.path.join(STAGING, "stage01_gate_constituents_v1.json.gz")
    manifest = os.path.join(STAGING, "stage01_gate_constituents_v1.manifest.json")
    return mirror, manifest


def build_all():
    mirror, manifest = _sources()
    rows, man = C.load_constituents(mirror, manifest)
    n_markers = C.load_registry_markers()
    aggregates = C.aggregate(rows, n_markers)
    gate_spec = build_typed_gate_spec()
    validation = build_validation_rows(aggregates)
    return gate_spec, validation, aggregates, man


if __name__ == "__main__":
    gate_spec, validation, aggregates, man = build_all()
    print("measurement_hard_gates:", len(gate_spec["measurement_hard_gates"]))
    print("base_portability_checks:", len(gate_spec["base_portability_checks"]))
    print("measurement rows:", validation["n_measurement_rows"], "| null rows:", validation["n_null_rows"])
    print("portability rows:", validation["n_portability_rows"])
    print("gate_spec canonical:", canonical.canonical_content_sha256(gate_spec))
    print("validation canonical:", canonical.canonical_content_sha256(validation))
    for nr in validation["null_rows"]:
        print("  null:", nr["program_id"], nr["condition"], nr["gate_id"])
