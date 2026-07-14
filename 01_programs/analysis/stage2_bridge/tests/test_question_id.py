"""question_id: the BIOLOGY-ONLY ordered-question identity (identifier hierarchy).

question_id = sha256(canonical_json({A:{program_id,direction,condition:from}, B:{program_id,direction,
condition:to}, analysis_mode}))[:16] — NO method/input binding, so the SAME biological question keeps ONE
question_id across method/registry/source revisions. selection_id (over canonical_content) additionally binds
the scorer VIEW + source h5ad + method version, so it is the method/input-bound identity. Independent: the
recipe is re-stated here, not imported from the emitter; a tampered/reforged question_id is refused.
"""
import hashlib

import canonical
import emit_selection_contract as sc
import verify_selection_contract as vc


def _qid(a_prog, a_dir, ca, b_prog, b_dir, cb, mode):
    qc = {"A": {"program_id": a_prog, "direction": a_dir, "condition": ca},
          "B": {"program_id": b_prog, "direction": b_dir, "condition": cb},
          "analysis_mode": mode}
    return hashlib.sha256(canonical.canonical_json(qc).encode()).hexdigest()[:16]


def _reseal(c):
    body = {k: v for k, v in c.items() if k != "full_contract_content_sha256"}
    c["full_contract_content_sha256"] = hashlib.sha256(canonical.canonical_json(body).encode()).hexdigest()
    return c


def test_question_id_present_16hex_and_rederives():
    c = sc.build_contract("treg_like", "high", "th1_like", "high", ["Stim8hr", "Stim48hr"])
    q = c["question_id"]
    assert isinstance(q, str) and len(q) == 16 and all(ch in "0123456789abcdef" for ch in q)
    assert q == _qid("treg_like", "high", "Stim8hr", "th1_like", "high", "Stim48hr", "temporal_cross_condition")
    ok, r = vc.verify_contract(c)
    assert ok, r


def test_question_id_distinct_from_selection_id():
    c = sc.build_contract("treg_like", "high", "th1_like", "high", ["Stim8hr", "Stim48hr"])
    assert c["question_id"] != c["selection_id"]


def test_question_id_is_biology_only():
    # re-derive from ONLY the biology fields; canonical_content additionally carries the method/input binding
    # (registry_scorer_view_sha256, source_h5ad_sha256, stage1_method_version) that binds selection_id, NOT this.
    c = sc.build_contract("treg_like", "high", "th1_like", "high", ["Stim8hr", "Stim48hr"])
    ccc = c["canonical_content"]
    assert c["question_id"] == _qid(ccc["A"]["program_id"], ccc["A"]["direction"], ccc["conditions"][0],
                                    ccc["B"]["program_id"], ccc["B"]["direction"], ccc["conditions"][-1],
                                    c["analysis_mode"])
    for method_field in ("registry_scorer_view_sha256", "source_h5ad_sha256", "stage1_method_version"):
        assert method_field in ccc            # these bind selection_id but are NOT inputs to question_id


def test_question_id_is_ordered_from_to():
    a = sc.build_contract("treg_like", "high", "th1_like", "high", ["Stim8hr", "Stim48hr"])
    b = sc.build_contract("treg_like", "high", "th1_like", "high", ["Stim48hr", "Stim8hr"])
    assert a["question_id"] != b["question_id"] and a["selection_id"] != b["selection_id"]


def test_reforged_question_id_refused():
    c = sc.build_contract("treg_like", "high", "th1_like", "high", ["Stim8hr", "Stim48hr"])
    # graft a DIFFERENT valid question's id, then reseal so the structural hash gate passes
    c["question_id"] = _qid("th2_like", "low", "Rest", "cd4_ctl_like", "high", "Rest", "within_condition")
    _reseal(c)
    ok, r = vc.verify_contract(c)
    assert not ok, "a reforged question_id must be refused"
    assert not any("full_contract_content_sha256 does not rederive" in x for x in r), r
    assert any("question_id does not rederive" in x for x in r), r


def test_within_question_id_shares_condition_both_poles():
    c = sc.build_contract("th2_like", "high", "cd4_ctl_like", "low", ["Rest"])
    assert c["question_id"] == _qid("th2_like", "high", "Rest", "cd4_ctl_like", "low", "Rest", "within_condition")
    ok, r = vc.verify_contract(c)
    assert ok, r
