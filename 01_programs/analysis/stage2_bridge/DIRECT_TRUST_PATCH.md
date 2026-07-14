# Direct trust-rule patch (paired Stage-1 → Stage-2 loader)

**Status:** patch artifact only. This document + `tests/test_direct_trust_compat.py` are the paired fix
for Direct's Stage-1 selectability trust rule. **The remote Direct worktree
(`spot-stage2-direct`) is NOT edited by this task** — apply this patch there separately.

Reference implementation (drop-in logic): `stage2_bridge/rederive_selectability.py::rederive` +
`stage2_bridge/build_gate_projection.py` (typed Direct-shape rows) + `stage2_bridge/constituents.py`
(constituent aggregation). The compatibility test proves the rule end-to-end against the frozen
constituent evidence.

## What Direct does today (the two defects the audit found)

1. **Conflated 9-gate list.** Direct treats all nine hard gates (7 measurement-validity + 2
   `stage2_base_portability`) as one production `hard_gates` AND. Portability is a SEPARATE Stage-2
   program-level verdict and must not gate Stage-1 measurement selectability.
2. **`observed_value` + null-only definedness.** Direct derives each gate from the frozen aggregate
   `observed_value` (an extremum over *defined* constituents) plus a null-only undefined rule, and its
   live `derive_selectable_pairs` rejects EVERY null as fatal. A finite aggregate can satisfy the
   comparator while the all-constituent check correctly fails on an **undefined** constituent
   (th2_like|Stim8hr LOMO ratio: 16 strata, 8 undefined, finite max 0.2196; th9_like|Rest control-draw
   ratio: 80 strata, 40 undefined, finite max 0.0). Trusting `observed_value` mis-licenses those.

## The corrected rule (apply to Direct's `derive_selectable_pairs`)

Consume the **typed** gate spec + Direct-shape rows (`build_gate_projection.build_all()`), never the
raw `observed_value` and never a stored `pass` boolean:

- **Two typed lists**, not one:
  - `measurement_hard_gates`: the SEVEN measurement subchecks
    (coverage 1 + condition 2 + LOMO 2 + control-draw 2).
  - `base_portability_checks`: the TWO program-level Stage-2 checks — evaluated as a SEPARATE
    `stage2_base_portable` verdict, never folded into the production AND.
- **Per measurement row** (mathematically-sufficient aggregation metadata is carried on the row):
  - `value is None` ⇒ require `measurement_state == "undefined"` **and** `n_undefined > 0` **and** the
    gate policy `undefined_is_fail` ⇒ **FAIL by policy** (never relabeled passed). An undeclared null,
    or a null with `n_undefined == 0`, is FATAL malformed input.
  - `value` numeric ⇒ require `measurement_state == "measured"`, `n_undefined == 0`, and completeness
    (`n_present == n_defined == n_expected`) ⇒ `passed = comparator(value, threshold)`. A numeric value
    under an `undefined` state is FATAL.
  - `subcheck_pass = complete && n_undefined == 0 && all(defined predicate_met)`; the lossy extremum is
    kept only as `source_worst_defined_value` and is NEVER used to pass a check. No numeric sentinel.
- **Production measurement-selectability** = AND over the SEVEN measurement subchecks ONLY.
  `stage2_base_portable` = AND over the TWO portability checks, reported separately. Stage-2 production
  eligibility requires BOTH poles measurement-valid AND base-portable.
- **Reject before evaluating:** duplicate `(program, condition, gate_id)` rows (last-write-wins is
  refused — see the saved `diff_memory|Rest` attack), an inexact program/condition/subcheck universe,
  and unknown programs/conditions/gates/thresholds.

## Frozen expected outcomes (reproduced by the compatibility test)

- `n_measurement_valid == 0` of 33 (production stays fail-closed).
- `n_base_portable == 10` of 11 (`th9_like` excluded: `n_panel_in_effect_universe == 0 < 3`).
- Exactly the frozen per-pair failing measurement-subcheck sets (portability excluded), including the
  two partially-undefined ratios that `observed_value` would have hidden.
