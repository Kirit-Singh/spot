"""CP3b — the typed, constituent-aware re-derivation (generator != evaluator).

Production measurement-selectability is the AND over the SEVEN measurement subchecks ONLY;
`base_portability` (two checks) is derived SEPARATELY and never gates production. Nothing
here reads a stored `pass`/`selectable` boolean, infers definedness from a numeric zero or a
metric name, or substitutes a numeric sentinel for a null.

Per measurement row the corrected rule is:
  * value is null  -> requires measurement_state=='undefined' AND n_undefined>0 AND policy
                      undefined_is_fail  -> FAILS by policy (never relabeled passed);
                      an undeclared null, or n_undefined==0 with a null, is FATAL malformed.
  * value numeric  -> requires measurement_state=='measured' AND n_undefined==0 AND
                      n_present==n_defined==n_expected (completeness) -> passed =
                      comparator(value, threshold) over the defined extremum; a numeric value
                      under an 'undefined' state is FATAL.
Duplicate (program, condition, gate_id) rows and an inexact program/condition/subcheck
universe are rejected before anything is evaluated.
"""
from __future__ import annotations

import constituents as C

COMPARATORS = {
    "ge": lambda v, t: v >= t, "gt": lambda v, t: v > t,
    "le": lambda v, t: v <= t, "lt": lambda v, t: v < t, "eq": lambda v, t: v == t,
}
UNDEFINED_STATE = "undefined"
MEASURED_STATE = "measured"
EXPECTED_PROGRAMS = ("th1_like", "th2_like", "th17_like", "tfh_like", "treg_like",
                     "cd4_ctl_like", "th9_like", "diff_naive", "diff_activated",
                     "diff_memory", "diff_checkpoint")


class RederiveError(ValueError):
    """A row could not be re-derived. Refuse; never downgrade to pass."""


def _require(cond, msg):
    if not cond:
        raise RederiveError(msg)


def _eval_measurement_row(row: dict, gate_spec: dict) -> bool:
    gate = row["gate_id"]
    spec = gate_spec["thresholds"].get(gate)
    _require(isinstance(spec, dict), f"gate spec: no threshold for {gate!r}")
    comparator = spec["comparator"]
    _require(comparator in COMPARATORS, f"gate spec: unknown comparator {comparator!r} for {gate!r}")
    policies = gate_spec.get("policies") or {}
    _require(policies.get("undefined_is_fail") is True, "gate spec: policy undefined_is_fail must be true")

    for k in ("value", "measurement_state", "n_expected", "n_present", "n_defined", "n_undefined", "threshold"):
        _require(k in row, f"row {gate} {row.get('program_id')}|{row.get('condition')}: missing {k!r}")
    value = row["value"]
    state = row["measurement_state"]
    n_exp, n_pre, n_def, n_und = row["n_expected"], row["n_present"], row["n_defined"], row["n_undefined"]
    _require(n_def + n_und == n_pre, f"row {gate}: n_defined+n_undefined != n_present")

    if value is None:
        _require(state == UNDEFINED_STATE,
                 f"row {gate} {row['program_id']}|{row['condition']}: null value without "
                 "measurement_state=='undefined' is malformed (a null cannot be relabeled passed)")
        _require(n_und > 0, f"row {gate}: null value with n_undefined==0 is malformed")
        return False                                    # undefined -> fail by policy
    _require(state in (None, MEASURED_STATE),
             f"row {gate}: measurement_state={state!r} with a numeric value is refused")
    _require(n_und == 0, f"row {gate}: numeric value with n_undefined>0 is refused")
    _require(n_pre == n_exp and n_def == n_exp,
             f"row {gate} {row['program_id']}|{row['condition']}: incomplete "
             f"(present {n_pre}, defined {n_def}, expected {n_exp})")
    return bool(COMPARATORS[comparator](float(value), float(row["threshold"])))


def rederive(validation: dict, gate_spec: dict) -> dict:
    measurement_gates = list(gate_spec["measurement_hard_gates"])
    portability_gates = list(gate_spec["base_portability_checks"])
    _require(len(measurement_gates) == 7, "expected exactly 7 measurement_hard_gates")
    _require(len(portability_gates) == 2, "expected exactly 2 base_portability_checks")

    # ---- measurement rows: reject duplicates + inexact universe BEFORE evaluating ----
    rows = validation["measurement_rows"]
    seen = set()
    by_pair = {}
    for r in rows:
        pid, cond, gate = r["program_id"], r["condition"], r["gate_id"]
        _require(pid in EXPECTED_PROGRAMS, f"unknown program_id {pid!r}")
        _require(cond in C.CONDS, f"unknown condition {cond!r}")
        _require(gate in measurement_gates, f"unknown/non-measurement gate_id {gate!r}")
        key = (pid, cond, gate)
        _require(key not in seen, f"duplicate measurement row {key} (last-write-wins refused)")
        seen.add(key)
        by_pair.setdefault((pid, cond), {})[gate] = r
    # exact universe: every program x condition x measurement subcheck present, nothing extra
    expected_keys = {(p, c, g) for p in EXPECTED_PROGRAMS for c in C.CONDS for g in measurement_gates}
    _require(seen == expected_keys,
             f"measurement universe mismatch: missing {sorted(expected_keys - seen)[:3]}, "
             f"extra {sorted(seen - expected_keys)[:3]}")

    measurement_valid = set()
    pair_evidence = {}
    for (pid, cond), gates in sorted(by_pair.items()):
        passes = {g: _eval_measurement_row(gates[g], gate_spec) for g in measurement_gates}
        failing = [g for g in measurement_gates if not passes[g]]
        valid = len(failing) == 0
        if valid:
            measurement_valid.add((pid, cond))
        pair_evidence[f"{pid}|{cond}"] = {
            "measurement_valid_derived": valid,
            "failing_subchecks": failing,
            "subcheck_pass": passes,
        }

    # ---- base portability: SEPARATE program-level AND over the two checks ----
    prow = {}
    pseen = set()
    for r in validation["portability_rows"]:
        pid, gate = r["program_id"], r["gate_id"]
        _require(gate in portability_gates, f"unknown portability gate {gate!r}")
        key = (pid, gate)
        _require(key not in pseen, f"duplicate portability row {key}")
        pseen.add(key)
        prow.setdefault(pid, {})[gate] = r
    base_portable = set()
    portability_evidence = {}
    for pid in EXPECTED_PROGRAMS:
        gates = prow.get(pid, {})
        _require(set(gates) == set(portability_gates), f"program {pid}: incomplete portability checks")
        oks = {}
        for g in portability_gates:
            r = gates[g]
            oks[g] = bool(COMPARATORS[gate_spec["thresholds"][g]["comparator"]](float(r["value"]), float(r["threshold"])))
        portable = all(oks.values())
        if portable:
            base_portable.add(pid)
        portability_evidence[pid] = {"base_portable_derived": portable, "checks": oks}

    return {
        "measurement_valid_pairs": frozenset(measurement_valid),
        "n_pairs_evaluated": len(by_pair),
        "n_measurement_valid": len(measurement_valid),
        "base_portable_programs": frozenset(base_portable),
        "n_base_portable": len(base_portable),
        "pair_evidence": pair_evidence,
        "portability_evidence": portability_evidence,
        "derivation": ("production selectability = AND over the 7 measurement subchecks only; "
                       "base_portability derived separately; undefined subchecks fail by policy; "
                       "no stored boolean, numeric sentinel, or name/zero heuristic was used"),
    }
