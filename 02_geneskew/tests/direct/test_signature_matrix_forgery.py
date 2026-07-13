"""W7/A4 — the independent signature-matrix verifier, and the resealed integrity probes.

Every attack corrupts the SHIPPED bytes of W18's real producer (commit 5628f84) and reseals
every internal hash a determined forger can reach — the manifest identity, the canonical
descriptors, the bundle reference, the run binding and the run id. Each still fails, at a
NAMED gate, because the anchor is either a primary input read independently (de_main via
h5py) or the EXTERNAL Direct mask table that W10 re-derived from the primary inputs. The
honest producer output ADMITs.

The cross-lane anchor is REAL here: the fixture builds an anchored bundle (Direct masks.parquet
+ a W10 report) exactly as W18's producer consumes them, and V_EXTERNAL_MASK independently
re-derives the per-target mask comparison from that shipped Direct table — a coherently forged
mask is refused because it disagrees with a table someone else computed. W10's sealed report
(48ff889b) and its 269b… mask are SYNTHETIC-fixture values, used only in the contract test
below and never frozen into the verifier; a real 60-arm release is NOT attested here.
"""
from __future__ import annotations

import json
import os

import numpy as np
import pyarrow as pa
import pytest
from direct import verify_rules as R
from direct import verify_signature_matrix as V
from fixtures_pathway import write_gene_sets
from fixtures_spec import TARGET_GENES, UNIVERSE

DIRECT_MASK = "a" * 64          # the Direct bundle's DECLARED mask hash (a run value)


def _direct_bundle(tmp_path, mask_sets, *, mask_sha=DIRECT_MASK, run_id="dir123"):
    """A stand-in for an ADMITTED Direct bundle: masks.parquet + provenance.json (W18's shape)."""
    import pandas as pd
    d = tmp_path / "direct"
    d.mkdir(parents=True, exist_ok=True)
    rows = []
    for t, ms in mask_sets.items():
        if ms is None:
            rows.append({"estimate_type": "main", "target_id": t,
                         "masked_gene_ensembl": None, "mask_reason": "mask_unresolved"})
            continue
        for g in sorted(ms):
            rows.append({"estimate_type": "main", "target_id": t,
                         "masked_gene_ensembl": g, "mask_reason": "target"})
    pd.DataFrame(rows).to_parquet(d / "masks.parquet")
    (d / "provenance.json").write_text(json.dumps({
        "arm_bundle_run_id": run_id,
        "run_binding": {"mask_sha256": mask_sha}}))
    return str(d)


def _w10_report(tmp_path, *, mask_sha=DIRECT_MASK, name="report.md"):
    """A stand-in W10 report — the SHAPE the producer parses; the VALUES are a run's."""
    p = tmp_path / name
    p.write_text(
        f"bound mask_sha256           : {mask_sha}\n"
        "verifier_id           spot.stage02.direct.arm_bundle.verifier.v1\n"
        f"verifier_code_sha256  {'b' * 64}\n"
        f"gate_inventory_sha256 {'c' * 64}\n")
    return str(p)


@pytest.fixture
def shipped(synthetic_run, tmp_path):
    from direct import io_data, run_pathway_arms
    from direct import run_screen as rs
    from direct import signature_matrix as sm
    from direct import universe as uni

    args = synthetic_run()
    ctx = rs.prepare(args)
    tu = uni.target_universe(ctx["identities_by_condition"])
    args.gene_sets = write_gene_sets(
        os.path.dirname(args.de_main), UNIVERSE, list(TARGET_GENES),
        ctx["gene_universe"]["sha256"], target_universe_sha256=tu["sha256"])
    args.condition = "StimX"
    args.out_root = str(tmp_path / "pw")
    args.signature_matrix_root = str(tmp_path / "signatures")

    # THE CROSS-LANE ANCHOR (W18 5628f84). The Direct masks.parquet is the SAME mask_sets this
    # lane derives, so an honest matrix is anchored and admits; a forged one disagrees.
    main = io_data.load_main(args.de_main, "StimX")
    mask_sets = sm.mask_sets_for_condition(args, "StimX", main)
    args.direct_bundle = _direct_bundle(tmp_path, mask_sets)
    args.direct_mask_report = _w10_report(tmp_path)

    sm.build_condition(args, "StimX", args.signature_matrix_root)
    res = run_pathway_arms.build_pathway_arms(args)
    return {"args": args, "matrix_root": args.signature_matrix_root,
            "bundle_dir": res["out_dir"], "cond": "StimX", "tmp_path": tmp_path,
            "mask_sets": mask_sets,
            "cond_dir": os.path.join(args.signature_matrix_root, "StimX")}


# --------------------------------------------------------------------------- #
# The W10 external Direct mask verification, bound into the run identity (simulated until W18
# binds it), + the run-identity re-derivation.
# --------------------------------------------------------------------------- #
# The exact sealed W10 report (agent/stage2-direct-arm-verifier @ 58f6305). Its concrete mask
# 269b… and bundle ids are SYNTHETIC-FIXTURE values — used only in the sealed-report contract
# test below, and NEVER frozen into the verifier.
W10_REPORT_SHA256 = "48ff889b2888ff73bf24dd6bfa4b7de966552f762fadc186b82dedafa18bfa3d"
W10_SYNTHETIC_MASK_SHA256 = (
    "269b42787813661036eb6d7b595207ab43a2b3f2e558e40e802120376c40ce0b")


def sync_identity(shipped):
    """Re-derive the run identity over whatever the artifacts currently say (a full reseal).

    Keeps ref == run_binding.signature_ref (INCLUDING the cross-lane anchor the producer put
    there) and recomputes pathway_run_id from the binding — so an attack that changed one
    artifact is caught at its OWN semantic gate, not incidentally at the identity gate.
    """
    man = _man(shipped)
    ref_path = os.path.join(shipped["bundle_dir"], V.REF_FILE)
    with open(ref_path) as fh:
        ref = json.load(fh)
    ref["signature_manifest_sha256"] = R.sha256_file(_man_path(shipped))
    ref["signature_manifest_raw_sha256"] = ref["signature_manifest_sha256"]
    ref["signature_manifest_canonical_sha256"] = man["manifest_canonical_sha256"]
    for k in ("matrix", "mask"):
        ref[f"{k}_raw_sha256"] = man[k]["raw_sha256"]
        ref[f"{k}_canonical_sha256"] = man[k]["canonical_sha256"]
    ref["matrix_values_sha256"] = man["matrix"]["values_sha256"]
    ref["mask_bits_sha256"] = man["mask"]["bits_sha256"]
    ref["gene_axis_raw_sha256"] = man["gene_axis"]["raw_sha256"]
    for k in ("n_unresolved_no_signature", "n_resolved_all_ones",
              "n_resolved_no_masked_readout_gene", "n_resolved_masked_readout_genes",
              "source_mask_sha256", "mask_is_externally_anchored", "direct_mask_anchor"):
        if k in man:
            ref[k] = man[k]
    with open(ref_path, "w") as fh:
        json.dump(ref, fh, sort_keys=True)

    prov_path = os.path.join(shipped["bundle_dir"], V.PROVENANCE_FILE)
    with open(prov_path) as fh:
        prov = json.load(fh)
    binding = prov["run_binding"]
    binding["signature_ref"] = ref
    full = R.content_sha256(binding)
    prov["pathway_run_id"] = full[:V.RUN_ID_LEN]
    prov["pathway_run_sha256"] = full
    with open(prov_path, "w") as fh:
        json.dump(prov, fh, sort_keys=True)


# --------------------------------------------------------------------------- #
# IO helpers.
# --------------------------------------------------------------------------- #
def verify(shipped):
    return V.verify(matrix_root=shipped["matrix_root"],
                    bundle_dirs=[shipped["bundle_dir"]], args=shipped["args"])


def failed(report):
    return {c["check"] for c in report["checks"] if c["status"] == V.FAIL}


def _json(path):
    with open(path) as fh:
        return json.load(fh)


def _man_path(shipped):
    return os.path.join(shipped["cond_dir"], "signature_manifest.json")


def _man(shipped):
    return _json(_man_path(shipped))


def _read_matrix(path, n_genes):
    t = pa.ipc.open_file(pa.memory_map(path)).read_all()
    return ([str(x) for x in t.column("target_id").to_pylist()],
            np.asarray(t.column("values").combine_chunks().flatten(),
                       "<f8").reshape(-1, n_genes))


def _write_matrix(path, targets, values, *, compression=None):
    n = values.shape[1]
    tbl = pa.table({"target_id": pa.array(targets, pa.string()),
                    "values": pa.FixedSizeListArray.from_arrays(
                        pa.array(np.ascontiguousarray(values, "<f8").reshape(-1),
                                 pa.float64()), n)})
    opts = pa.ipc.IpcWriteOptions(compression=compression) if compression else None
    with pa.OSFile(path, "wb") as sink:
        with pa.ipc.new_file(sink, tbl.schema, options=opts) as w:
            w.write_table(tbl, max_chunksize=len(tbl))


def _read_mask(path, width):
    t = pa.ipc.open_file(pa.memory_map(path)).read_all()
    return ([str(x) for x in t.column("target_id").to_pylist()],
            np.asarray(t.column("unmasked_bits").combine_chunks().flatten(),
                       np.uint8).reshape(-1, width))


def _write_mask(path, targets, bitmap):
    tbl = pa.table({"target_id": pa.array(targets, pa.string()),
                    "unmasked_bits": pa.FixedSizeListArray.from_arrays(
                        pa.array(np.ascontiguousarray(bitmap, np.uint8).reshape(-1),
                                 pa.uint8()), bitmap.shape[1])})
    with pa.OSFile(path, "wb") as sink:
        with pa.ipc.new_file(sink, tbl.schema) as w:
            w.write_table(tbl, max_chunksize=len(tbl))


def write_manifest(shipped, man):
    """Rewrite the manifest, recomputing its own content identity, then re-sync the ref+id."""
    man.pop("manifest_sha256", None)
    man.pop("manifest_canonical_sha256", None)
    man["manifest_canonical_sha256"] = V.manifest_canonical(man)
    with open(_man_path(shipped), "w") as fh:
        json.dump(man, fh, indent=2, sort_keys=True)
        fh.write("\n")


def reseal_matrix(shipped, targets, values):
    cd = shipped["cond_dir"]
    m_path = os.path.join(cd, "signatures.matrix.arrow")
    _write_matrix(m_path, targets, values)
    man = _man(shipped)
    v_sha = V.values_sha256(values)
    man["matrix"]["raw_sha256"] = R.sha256_file(m_path)
    man["matrix"]["values_sha256"] = v_sha
    man["matrix"]["canonical_sha256"] = V.matrix_canonical(
        man["condition"], targets, v_sha, man["gene_axis"]["raw_sha256"], man["n_genes"])
    man["mask"]["canonical_sha256"] = V.mask_canonical(
        man["condition"], targets, v_sha, man["mask"]["bits_sha256"],
        man["gene_axis"]["raw_sha256"], man["n_genes"])
    write_manifest(shipped, man)
    sync_identity(shipped)


def reseal_mask(shipped, targets, bitmap):
    cd = shipped["cond_dir"]
    k_path = os.path.join(cd, "signatures.mask.arrow")
    _write_mask(k_path, targets, bitmap)
    man = _man(shipped)
    b_sha = V.bits_sha256(bitmap)
    man["mask"]["raw_sha256"] = R.sha256_file(k_path)
    man["mask"]["bits_sha256"] = b_sha
    man["mask"]["canonical_sha256"] = V.mask_canonical(
        man["condition"], targets, man["matrix"]["values_sha256"], b_sha,
        man["gene_axis"]["raw_sha256"], man["n_genes"])
    write_manifest(shipped, man)
    sync_identity(shipped)


# =========================================================================== #
# THE HONEST CONTROL
# =========================================================================== #
class TestTheHonestProducerOutputAdmits:
    def test_it_admits_with_no_failed_gate(self, shipped):
        r = verify(shipped)
        assert r["verdict"] == V.ADMIT, sorted(failed(r))
        assert r["n_failed"] == 0

    def test_every_gate_ran(self, shipped):
        names = {c["check"] for c in verify(shipped)["checks"]}
        for g in (V.V1, V.V1_REFMAN, V.V2_VALUES, V.V2_BITS, V.V2_CANON, V.V2_ANCHOR,
                  V.V3, V.V4, V.V5, V.V6, V.V7, V.V8, V.V9, V.V10, V.V_IDENTITY,
                  V.V_EXTERNAL_MASK):
            assert g in names, f"gate never ran: {g}"


# =========================================================================== #
# VALUE / AXIS FORGERIES — anchored to de_main (read via h5py)
# =========================================================================== #
class TestA1_PrecisionDowngrade:
    def test_float32_is_REJECTED(self, shipped):
        man = _man(shipped)
        t, v = _read_matrix(os.path.join(shipped["cond_dir"], "signatures.matrix.arrow"),
                            man["n_genes"])
        reseal_matrix(shipped, t, v.astype("<f4").astype("<f8"))
        r = verify(shipped)
        assert r["verdict"] == V.REJECT and V.V2_ANCHOR in failed(r)


class TestA2_RowReorder:
    def test_reorder_is_REJECTED(self, shipped):
        man = _man(shipped)
        t, v = _read_matrix(os.path.join(shipped["cond_dir"], "signatures.matrix.arrow"),
                            man["n_genes"])
        o = list(range(len(t)))[::-1]
        reseal_matrix(shipped, [t[i] for i in o], v[o])
        assert V.V2_ANCHOR in failed(verify(shipped))


class TestA6_CrossConditionSwap:
    def test_another_conditions_values_is_REJECTED(self, shipped):
        man = _man(shipped)
        t, v = _read_matrix(os.path.join(shipped["cond_dir"], "signatures.matrix.arrow"),
                            man["n_genes"])
        reseal_matrix(shipped, t, v + 1.0)
        assert V.V2_ANCHOR in failed(verify(shipped))


class TestA11_NonFinite:
    def test_a_NaN_is_REJECTED(self, shipped):
        man = _man(shipped)
        t, v = _read_matrix(os.path.join(shipped["cond_dir"], "signatures.matrix.arrow"),
                            man["n_genes"])
        v = v.copy()
        v[0, 0] = np.nan
        reseal_matrix(shipped, t, v)
        f = failed(verify(shipped))
        assert V.V2_ANCHOR in f or V.V2_FINITE in f


class TestA3_GeneAxisPermutation:
    def test_a_permuted_axis_is_REJECTED(self, shipped):
        axis_path = os.path.join(shipped["matrix_root"], "gene_axis.arrow")
        ids = [str(x) for x in pa.ipc.open_file(
            pa.memory_map(axis_path)).read_all().column("gene_id").to_pylist()]
        perm = ids[::-1]
        if perm == ids:
            pytest.skip("degenerate axis")
        with pa.OSFile(axis_path, "wb") as sink:
            with pa.ipc.new_file(sink, pa.table(
                    {"gene_id": pa.array(perm, pa.string())}).schema) as w:
                w.write_table(pa.table({"gene_id": pa.array(perm, pa.string())}),
                              max_chunksize=len(perm))
        man = _man(shipped)
        man["gene_axis"]["raw_sha256"] = R.sha256_file(axis_path)
        man["gene_axis"]["canonical_sha256"] = R.content_sha256(perm)
        man["gene_axis"]["readout_universe_sha256"] = R.content_sha256(perm)
        write_manifest(shipped, man)
        sync_identity(shipped)
        assert V.V3 in failed(verify(shipped))


# =========================================================================== #
# BITMAP COUNT FORGERIES — recounted from the bitmap
# =========================================================================== #
class TestA4_ForgedAllOnesBitmap:
    def test_all_ones_without_matching_counts_is_REJECTED(self, shipped):
        man = _man(shipped)
        t, bmp = _read_mask(os.path.join(shipped["cond_dir"], "signatures.mask.arrow"),
                            man["bitmap_width_bytes"])
        forged = np.full_like(bmp, 0xFF)
        pad = man["n_genes"] % 8
        if pad:
            forged[:, -1] = (0xFF << (8 - pad)) & 0xFF
        reseal_mask(shipped, t, forged)          # bits_sha256 resealed; counts NOT
        r = verify(shipped)
        assert r["verdict"] == V.REJECT and V.V5 in failed(r)


class TestA5_UnresolvedPromotion:
    def test_flipping_an_all_zero_row_is_REJECTED(self, shipped):
        man = _man(shipped)
        t, bmp = _read_mask(os.path.join(shipped["cond_dir"], "signatures.mask.arrow"),
                            man["bitmap_width_bytes"])
        pop = np.unpackbits(bmp, axis=1)[:, :man["n_genes"]].sum(axis=1)
        zero = np.nonzero(pop == 0)[0]
        if not len(zero):
            pytest.skip("this fixture resolves every target")
        bmp = bmp.copy()
        bmp[int(zero[0]), 0] = 0b01010101
        reseal_mask(shipped, t, bmp)
        assert V.V5 in failed(verify(shipped))


# =========================================================================== #
# REFERENCE / MEMBER / CONVERGENCE / CONTAINER / RE-SHIP
# =========================================================================== #
class TestA7_StaleReference:
    def test_a_reference_that_no_longer_resolves_is_REJECTED(self, shipped):
        ref_path = os.path.join(shipped["bundle_dir"], V.REF_FILE)
        ref = _json(ref_path)
        ref["matrix_raw_sha256"] = "0" * 64
        with open(ref_path, "w") as fh:
            json.dump(ref, fh, sort_keys=True)
        sync_identity(shipped)     # note: sync restores matrix_raw from manifest...
        # ...so corrupt AFTER sync to leave it stale
        ref = _json(ref_path)
        ref["matrix_raw_sha256"] = "0" * 64
        with open(ref_path, "w") as fh:
            json.dump(ref, fh, sort_keys=True)
        r = verify(shipped)
        assert r["verdict"] == V.REJECT and V.V1 in failed(r)


class TestA8_MemberPadding:
    def test_a_padded_member_list_is_REJECTED(self, shipped):
        ref_path = os.path.join(shipped["bundle_dir"], V.REF_FILE)
        ref = _json(ref_path)
        ref["member_target_ids"] = sorted(ref["member_target_ids"] + ["ENSG09999999999"])
        ref["n_member_targets"] = len(ref["member_target_ids"])
        with open(ref_path, "w") as fh:
            json.dump(ref, fh, sort_keys=True)
        # bind the padded ref into the identity so V_IDENTITY passes and V7 is the finding
        prov_path = os.path.join(shipped["bundle_dir"], V.PROVENANCE_FILE)
        prov = _json(prov_path)
        prov["run_binding"]["signature_ref"] = ref
        full = R.content_sha256(prov["run_binding"])
        prov["pathway_run_id"], prov["pathway_run_sha256"] = full[:V.RUN_ID_LEN], full
        with open(prov_path, "w") as fh:
            json.dump(prov, fh, sort_keys=True)
        r = verify(shipped)
        assert r["verdict"] == V.REJECT and V.V7 in failed(r)


class TestA9_ReductionOrderDrift:
    def test_a_perturbed_similarity_is_REJECTED(self, shipped):
        cp = os.path.join(shipped["bundle_dir"], "convergence.json")
        conv = _json(cp)
        pairs = [p for s in conv.get("sets", []) for p in s.get("pairwise_support", [])]
        if not pairs:
            pytest.skip("no convergence pair in this fixture")
        pairs[0]["similarity"] = round(pairs[0]["similarity"] + 1e-6, 6)
        with open(cp, "w") as fh:
            json.dump(conv, fh, sort_keys=True)
        assert V.V6 in failed(verify(shipped))

    def test_a_vectorised_reduction_order_id_is_REJECTED(self, shipped):
        ref_path = os.path.join(shipped["bundle_dir"], V.REF_FILE)
        ref = _json(ref_path)
        ref["reduction_order_id"] = "spot.stage02.convergence.reduction.numpy_pairwise.v1"
        with open(ref_path, "w") as fh:
            json.dump(ref, fh, sort_keys=True)
        assert V.V6 in failed(verify(shipped))


class TestA10_ContainerReframing:
    def test_a_compressed_container_is_REJECTED(self, shipped):
        man = _man(shipped)
        t, v = _read_matrix(os.path.join(shipped["cond_dir"], "signatures.matrix.arrow"),
                            man["n_genes"])
        _write_matrix(os.path.join(shipped["cond_dir"], "signatures.matrix.arrow"),
                      t, v, compression="zstd")     # raw changes, NOT resealed -> V1
        assert V.V1 in failed(verify(shipped))


class TestA12_BundleReshipsSignatures:
    def test_a_reshipped_parquet_is_REJECTED(self, shipped):
        with open(os.path.join(shipped["bundle_dir"], "pathway_signatures.parquet"),
                  "wb") as fh:
            fh.write(b"PAR1 for compatibility")
        assert V.V8 in failed(verify(shipped))


# =========================================================================== #
# MANIFEST IDENTITY (a different condition's matrix must not be substitutable)
# =========================================================================== #
class TestB_ManifestIdentity:
    def test_a_null_manifest_identity_is_REFUSED(self, shipped):
        ref_path = os.path.join(shipped["bundle_dir"], V.REF_FILE)
        ref = _json(ref_path)
        ref["signature_manifest_canonical_sha256"] = None
        ref["signature_manifest_sha256"] = None
        ref["signature_manifest_raw_sha256"] = None
        with open(ref_path, "w") as fh:
            json.dump(ref, fh, sort_keys=True)
        assert V.V1_REFMAN in failed(verify(shipped))

    def test_the_identity_REDERIVES_on_the_honest_control(self, shipped):
        assert V.V1_REFMAN not in failed(verify(shipped))


# =========================================================================== #
# THE CROSS-LANE ANCHOR — the mask is checked from OUTSIDE (W18 5628f84)
# =========================================================================== #
def _forge_one_targets_mask(shipped):
    """Mask a DIFFERENT gene for one resolved target, keeping the popcount (so the counts and
    every internal gate still agree). Returns the forged, re-sealed bitmap on disk."""
    man = _man(shipped)
    k_path = os.path.join(shipped["cond_dir"], "signatures.mask.arrow")
    t, bmp = _read_mask(k_path, man["bitmap_width_bytes"])
    n_genes = man["n_genes"]
    bits = np.unpackbits(bmp, axis=1)[:, :n_genes]
    # a resolved, partially-masked row (has both a 0 and a 1 among the readout genes)
    for i in range(len(t)):
        zeros = np.nonzero(bits[i] == 0)[0]
        ones = np.nonzero(bits[i] == 1)[0]
        if len(zeros) and len(ones):
            bits[i, zeros[0]] = 1           # unmask the gene the Direct table masks…
            bits[i, ones[0]] = 0            # …and mask one it does not. popcount unchanged.
            break
    else:
        pytest.skip("no partially-masked row to perturb")
    forged = np.packbits(bits, axis=1)
    reseal_mask(shipped, t, forged)


class TestTheCrossLaneAnchor:
    """A coherent wrong mask: rebuild bitmap/counts/source_mask/ref/run id together.

    Bitmap-recount + a self-bound run id ADMIT it — every internal statement agrees. Only the
    Direct mask table an independent verifier (W10) re-derived from the primary inputs refuses
    it: this lane and the Direct lane claim to have masked the same experiment, and they did not.
    """

    def test_a_fully_resealed_wrong_mask_is_REJECTED(self, shipped):
        _forge_one_targets_mask(shipped)        # re-seals bitmap, counts, ref, run id
        r = verify(shipped)
        assert r["verdict"] == V.REJECT
        assert V.V_EXTERNAL_MASK in failed(r)
        # the internal statements are all self-consistent — nothing else catches it
        assert V.V_IDENTITY not in failed(r) and V.V4 not in failed(r) and V.V5 not in failed(r)

    def test_ANOTHER_bundles_mask_is_REJECTED(self, shipped):
        # The auditor hands the verifier a DIFFERENT Direct bundle — masks that are not this
        # run's. The honest pathway bitmap no longer matches that table.
        other = dict(shipped["mask_sets"])
        victim = next(t for t, v in other.items() if v)
        other[victim] = set(other[victim]) | {UNIVERSE[0]}     # one extra masked gene
        shipped["args"].direct_bundle = _direct_bundle(
            shipped["tmp_path"] / "other", other)
        r = verify(shipped)
        assert r["verdict"] == V.REJECT and V.V_EXTERNAL_MASK in failed(r)

    def test_an_UNANCHORED_matrix_is_fail_closed(self, shipped, synthetic_run, tmp_path):
        # A matrix built WITHOUT the Direct bundle + W10 report: self-consistent, unanchored.
        from direct import run_pathway_arms
        from direct import run_screen as rs
        from direct import signature_matrix as sm
        from direct import universe as uni
        args = synthetic_run()
        ctx = rs.prepare(args)
        tu = uni.target_universe(ctx["identities_by_condition"])
        args.gene_sets = write_gene_sets(
            os.path.dirname(args.de_main), UNIVERSE, list(TARGET_GENES),
            ctx["gene_universe"]["sha256"], target_universe_sha256=tu["sha256"])
        args.condition = "StimX"
        args.out_root = str(tmp_path / "pw2")
        args.signature_matrix_root = str(tmp_path / "sig2")
        sm.build_condition(args, "StimX", args.signature_matrix_root)   # NO anchor args
        res = run_pathway_arms.build_pathway_arms(args)
        r = V.verify(matrix_root=args.signature_matrix_root,
                     bundle_dirs=[res["out_dir"]], args=args)
        assert r["verdict"] == V.REJECT and V.V_EXTERNAL_MASK in failed(r)

    def test_a_missing_report_for_rederivation_is_fail_closed(self, shipped):
        # The anchor is bound, but the auditor does not supply the Direct bundle to re-check it.
        shipped["args"].direct_bundle = None
        assert V.V_EXTERNAL_MASK in failed(verify(shipped))


# =========================================================================== #
# THE EXACT SEALED W10 REPORT — its bytes, and the scope caveat (contract only)
# =========================================================================== #
W10_REPORT_PATH = ("/home/tcelab/.spot-runs/20260712T021343Z/"
                   "DIRECT_MASK_VERIFICATION_REPORT.md")


class TestTheSealedW10Report:
    """The exact bytes W10 sealed. 269b… and the bundle ids are SYNTHETIC — contract only."""

    @pytest.mark.skipif(not os.path.exists(W10_REPORT_PATH),
                        reason="the sealed W10 report is not on this host")
    def test_the_report_hashes_to_its_sealed_identity(self):
        assert R.sha256_file(W10_REPORT_PATH) == W10_REPORT_SHA256

    @pytest.mark.skipif(not os.path.exists(W10_REPORT_PATH),
                        reason="the sealed W10 report is not on this host")
    def test_the_report_states_it_is_NOT_a_real_60_arm_release(self):
        with open(W10_REPORT_PATH) as fh:
            body = fh.read()
        assert V.W10_VERIFIER_ID in body
        assert "VERDICT: **ADMIT**" in body
        assert "has **not** been produced or admitted on real data" in body
        assert W10_SYNTHETIC_MASK_SHA256 in body     # present, but never frozen

    def test_the_verifier_does_NOT_freeze_the_synthetic_values(self):
        import inspect

        from direct import verify_signature_matrix
        src = inspect.getsource(verify_signature_matrix)
        assert W10_SYNTHETIC_MASK_SHA256 not in src
        assert W10_REPORT_SHA256 not in src

    def test_the_producer_anchor_declares_fixture_scope(self, shipped):
        # attests_real_60_arm_release=False is carried in the anchor: fixture, not real release.
        ref = _json(os.path.join(shipped["bundle_dir"], V.REF_FILE))
        assert ref["direct_mask_anchor"]["attests_real_60_arm_release"] is False
