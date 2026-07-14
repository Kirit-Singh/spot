"""Guide/donor support joins by stable ID, never row position (plan §5.6)."""
import numpy as np

from direct import projection as proj


def _mod(by_target, gene_index):
    return {"by_target": by_target, "gene_index": gene_index}


def test_lane_join_by_stable_id_not_position(gene_index, prog_a, prog_b):
    # Two targets stored in DIFFERENT row orders across two modalities.
    t1_vec = np.array([4.0, 8.0, 1.0, 1.0, 1.0])   # balanced_skew = -1.0
    t2_vec = np.array([0.0, 0.0, 1.0, 1.0, 1.0])   # balanced_skew =  0.0
    guide_1 = _mod({"ENSG_T1": t1_vec, "ENSG_T2": t2_vec}, gene_index)
    guide_2 = _mod({"ENSG_T2": t2_vec, "ENSG_T1": t1_vec}, gene_index)  # reversed order

    def bal(mod, t):
        row = mod["by_target"].get(t)
        return proj.project_balanced(row, prog_a, prog_b, mod["gene_index"],
                                     set(), 1, 1)

    # Same target id must yield the same balanced value regardless of storage order.
    assert bal(guide_1, "ENSG_T1") == bal(guide_2, "ENSG_T1")
    assert bal(guide_1, "ENSG_T2") == bal(guide_2, "ENSG_T2")
    # And the two targets differ (so we are truly keying on id, not position).
    assert bal(guide_1, "ENSG_T1") != bal(guide_1, "ENSG_T2")


def test_missing_target_returns_none(gene_index, prog_a, prog_b):
    mod = _mod({"ENSG_T1": np.ones(5)}, gene_index)
    assert mod["by_target"].get("ENSG_ABSENT") is None
