"""INDEPENDENT arm-identity attack + exhaustive materializer sweep (ROUND4_ADDENDUM c4773562).

generator != verifier: this module imports NO arm_keys. It re-states the frozen (role, pole) -> desired_change
mapping and the arm-key string formats as LOCAL literals, so a shared-helper bug or key-format drift in the
producer (arm_keys) cannot also mask itself here. Every expected/mutated key is built from these literals.

Two guarantees:
  1. MUTATION gates — each identity forgery (wrong desired_change for any of the four role x pole combos, role
     swap, pole swap, condition swap, temporal from/to swap, pathway base-format change) is REJECTED at a named
     semantic gate EVEN AFTER the full contract is re-sealed (full_contract_content_sha256 recomputed valid).
  2. EXHAUSTIVE sweep — all 20 program x pole states across 3 within conditions + 6 ordered temporal pairs
     (3,600 tuples) yield EXACTLY 3,540 ready + EXACTLY 60 within-condition identical (program, pole, condition)
     refusals; every admitted contract's two arms independently recompute and semantically verify.
"""
import functools
import hashlib

import build_registry_view as rv
import canonical
import emit_selection_contract as sc
import verify_selection_contract as vc

# ---- LOCAL frozen rules (independently re-stated; NOT imported from arm_keys) ----
FROZEN = {("away_from_A", "high"): "decrease", ("away_from_A", "low"): "increase",
          ("toward_B", "high"): "increase", ("toward_B", "low"): "decrease"}
CONDITIONS = ("Rest", "Stim8hr", "Stim48hr")
ORDERED_PAIRS = [(a, b) for a in CONDITIONS for b in CONDITIONS if a != b]   # 6


def dkey(pid, dc, cond):
    return "direct|%s|%s|%s" % (pid, dc, cond)


def pbase(pid, dc, cond):
    return "pathway|%s|%s|%s" % (pid, dc, cond)


def tkey(pid, dc, frm, to):
    return "temporal|%s|%s|%s|%s" % (pid, dc, frm, to)


def _reseal(c):
    """Recompute the full-contract hash so the mutation passes the STRUCTURAL hash gate; only a SEMANTIC gate
    can then catch it. This is the attack a naive hash-only check would miss."""
    body = {k: v for k, v in c.items() if k != "full_contract_content_sha256"}
    c["full_contract_content_sha256"] = hashlib.sha256(canonical.canonical_json(body).encode()).hexdigest()
    return c


def _assert_semantic_reject(c, gate_substr):
    ok, reasons = vc.verify_contract(c)
    assert not ok, "identity forgery slipped past the verifier"
    # the STRUCTURAL hash gates must NOT be what caught it (reseal made them valid) — a SEMANTIC gate must
    assert not any("full_contract_content_sha256 does not rederive" in r for r in reasons), reasons
    assert any(gate_substr in r for r in reasons), (gate_substr, reasons)


# ---------- MUTATION GATES ----------

def test_mut_wrong_desired_change_each_of_four_role_pole():
    # cover all four (role, pole): flip desired_change + its keys to the WRONG value while keeping the arm
    # internally consistent, reseal -> the verifier's LOCAL re-derivation must still reject it.
    for a_dir, b_dir in (("high", "low"), ("low", "high")):     # spans all four role x pole combos
        for role in ("away_from_A", "toward_B"):
            c = sc.build_contract("th1_like", a_dir, "th2_like", b_dir, ["Rest"])
            arm = c["arms"][role]
            pid, pole = arm["program_id"], arm["pole_direction"]
            right = FROZEN[(role, pole)]
            wrong = "increase" if right == "decrease" else "decrease"
            arm["desired_change"] = wrong
            arm["direct_arm_key"] = dkey(pid, wrong, "Rest")
            arm["pathway_arm_key_base"] = pbase(pid, wrong, "Rest")
            _reseal(c)
            _assert_semantic_reject(c, f"arms.{role} does not rederive")


def test_mut_role_swap():
    c = sc.build_contract("th1_like", "high", "th2_like", "low", ["Rest"])
    c["arms"]["away_from_A"], c["arms"]["toward_B"] = c["arms"]["toward_B"], c["arms"]["away_from_A"]
    _reseal(c)
    _assert_semantic_reject(c, "does not rederive")


def test_mut_pole_swap():
    c = sc.build_contract("th1_like", "high", "th2_like", "low", ["Rest"])
    c["arms"]["away_from_A"]["pole_direction"] = "low"   # canonical_content.A.direction stays 'high'
    _reseal(c)
    _assert_semantic_reject(c, "arms.away_from_A does not rederive")


def test_mut_condition_swap():
    c = sc.build_contract("th1_like", "high", "th2_like", "low", ["Rest"])
    a = c["arms"]["away_from_A"]
    a["condition"] = "Stim8hr"
    a["direct_arm_key"] = dkey(a["program_id"], a["desired_change"], "Stim8hr")
    a["pathway_arm_key_base"] = pbase(a["program_id"], a["desired_change"], "Stim8hr")
    _reseal(c)
    _assert_semantic_reject(c, "arms.away_from_A does not rederive")


def test_mut_temporal_from_to_swap():
    c = sc.build_contract("th1_like", "high", "th2_like", "low", ["Stim8hr", "Stim48hr"])
    a = c["arms"]["away_from_A"]
    a["temporal_arm_key"] = tkey(a["program_id"], a["desired_change"], "Stim48hr", "Stim8hr")   # swapped order
    _reseal(c)
    _assert_semantic_reject(c, "arms.away_from_A.temporal_arm_key does not rederive")


def test_mut_pathway_base_format():
    c = sc.build_contract("th1_like", "high", "th2_like", "low", ["Rest"])
    a = c["arms"]["away_from_A"]
    a["pathway_arm_key_base"] = "pathway|%s|high|Rest" % a["program_id"]   # pole-keyed forgery, not desired_change
    _reseal(c)
    _assert_semantic_reject(c, "arms.away_from_A.pathway_arm_key_base does not rederive")


# ---------- EXHAUSTIVE SWEEP ----------

def _base_portable_programs():
    """Independently (of arm_keys) read the 10 base-portable programs from the v3 scorer VIEW."""
    view = rv.build_and_hash()[0]
    return sorted(p["program_id"] for p in view["programs"] if p.get("base_portable"))


def test_exhaustive_3600_tuples_3540_ready_60_refused():
    programs = _base_portable_programs()
    assert len(programs) == 10
    states = [(p, d) for p in programs for d in ("high", "low")]          # 20 program x pole states
    assert len(states) == 20
    contexts = [[c] for c in CONDITIONS] + [list(p) for p in ORDERED_PAIRS]   # 3 within + 6 temporal
    assert len(contexts) == 9

    # memoize the constant file/view reads for the duration of the sweep only, then restore
    saved = (rv.build_and_hash, sc._sha_file, sc._canonical_content_sha, vc._raw)
    rv.build_and_hash = functools.lru_cache(maxsize=1)(rv.build_and_hash)
    sc._sha_file = functools.lru_cache(maxsize=None)(sc._sha_file)
    sc._canonical_content_sha = functools.lru_cache(maxsize=None)(sc._canonical_content_sha)
    vc._raw = functools.lru_cache(maxsize=None)(vc._raw)
    try:
        ready = 0
        refused = []                # (program, pole, condition) identical refusals
        unexpected = []
        for conds in contexts:
            within = len(conds) == 1
            for (pa, da) in states:
                for (pb, db) in states:
                    try:
                        c = sc.build_contract(pa, da, pb, db, conds)
                    except sc.SelectionError as e:
                        assert e.reason == "objective_incompatible_same_pole", e.reason
                        refused.append((pa, da, pb, db, tuple(conds)))
                        continue
                    if c["execution_status"] != "ready":
                        unexpected.append((pa, da, pb, db, tuple(conds), c["execution_status"]))
                        continue
                    ready += 1
                    # INDEPENDENT recompute of the two arms (local frozen rules; no arm_keys) + semantic verify
                    cond_a, cond_b = conds[0], conds[-1]
                    for role, pid, pole, cond in (("away_from_A", pa, da, cond_a), ("toward_B", pb, db, cond_b)):
                        dc = FROZEN[(role, pole)]
                        arm = c["arms"][role]
                        assert arm["desired_change"] == dc
                        assert arm["pole_direction"] == pole and arm["condition"] == cond
                        assert arm["direct_arm_key"] == dkey(pid, dc, cond)
                        assert arm["pathway_arm_key_base"] == pbase(pid, dc, cond)
                        if not within:
                            assert arm["temporal_arm_key"] == tkey(pid, dc, conds[0], conds[1])
                    ok, reasons = vc.verify_contract(c)
                    assert ok, reasons
    finally:
        rv.build_and_hash, sc._sha_file, sc._canonical_content_sha, vc._raw = saved

    assert unexpected == [], unexpected[:5]
    assert ready == 3540, ready
    assert len(refused) == 60, len(refused)
    # every refusal is a within-condition, exactly-identical (program, pole, condition) tuple
    assert all(len(t[4]) == 1 and t[0] == t[2] and t[1] == t[3] for t in refused)
    assert len({(t[0], t[1], t[4][0]) for t in refused}) == 60   # 10 programs x 2 poles x 3 conditions
