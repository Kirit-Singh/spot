"""A4/W7 — the INDEPENDENT verifier for the shared signature matrix + mandatory bitmap.

Implements V1–V10 of PATHWAY_SIGNATURE_MATRIX_SPEC.md (sha 95d6930266…) plus the W7 Step-0
amendment, against W18's producer (`signature_matrix.py`, commit `e5f71df`). It reads the
SHIPPED bytes off disk — the three shared artifacts and each bundle's `signature_ref.json` +
`convergence.json` + `pathway_provenance.json` — and re-derives every claim independently:

    V1        raw sha256 of every artifact recomputes and matches the manifest + every ref.
    V1_REFMAN every ref binds a NON-NULL manifest identity (raw + canonical) that re-derives
              to the shipped manifest — so a different condition's matrix is not substitutable.
    V2        values/bits/canonical digests recompute from re-read bytes; and the matrix VALUES
              re-derive from the pinned de_main log_fc (read via h5py) — the reseal-proof anchor.
    V3        the gene axis re-derives from de_main var/gene_ids — order AND hash.
    V4        the amended bitmap counts (n_resolved_all_ones, n_resolved_no_masked_readout_gene,
              their equality) and the source-mask identity re-derive from the bitmap and are
              bound into the run identity.
    V5        all-zero == n_unresolved_no_signature; the resolved all-ones set re-derives from
              the bitmap and equals the declared resolved_no_masked_readout_gene disposition;
              and the first-class resolution counts (n_resolved, n_resolved_masked_readout_genes)
              recount from the bitmap and their arithmetic closes (resolved + unresolved ==
              n_targets; masked + all-ones == resolved). A resolved all-ones row is the amended
              VALID state (its mask misses the readout axis); an all-zero row is unresolved / NO
              SIGNATURE, never an unmasked vector.
    V6        convergence re-derives from (matrix, bitmap) with the sorted-gene left fold,
              BITWISE — a 5e-07 numpy drift is a refusal.
    V7        member_target_ids re-derive from the bound gene sets ∩ condition targets ∩ resolved.
    V8        no pathway bundle ships signature bytes.
    V9        the recursive no-p/q/FDR firewall over every shipped document.
    V10       every reference resolves; every shared artifact is cited.
    V_IDENTITY the signature_ref on disk IS the one bound into a re-derivable pathway_run_id, so
              a forger who reseals the manifest/ref must also change the run id.
    V_SOLVER_LOCK the Stage-2 deterministic solver lock is bound into run_binding (→ run id) AND
              is the PINNED lock (sha 2983d140…). A missing or swapped lock refuses.
    V_QC      the per-target signature_qc.parquet re-derives — file, raw hash, content hash, row
              count, base-passed count — and every matrix target has exactly one QC row.
    V_STALE_SOURCE the manifest's sources.de_main_sha256 equals the de_main the auditor supplies:
              a signature root built from another DE source loads and means a different run.
    V_RELEASE_ROOT the pathway's stage1_release_hashes are the ones the ADMITTED Direct bundle
              records its arms were built on (checked against the external Direct provenance):
              a missing/stale/mismatched/resealed release describes a different experiment.

GENERATOR ≠ VERIFIER. It imports NO producer module — only ``h5py``/``numpy``/``json`` and the
verifier-side ``verify_rules`` / ``verify_run`` (primary h5ad reader) / ``verify_reconstruct``
(gene-set parse). The precision digests, canonical descriptors, ``reconstruct_signatures`` and
the cosine are re-implemented from the spec. The all-ones INTERSECTION correctness is the
producer's fail-closed responsibility; its ``source_mask_sha256`` and amended counts are bound
into the run identity, which this verifier re-derives. W18's producer does not admit itself.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from typing import Any

import numpy as np

# The verifier-side modules do bare imports (``import verify_rules``); put this dir on the path
# so the module runs standalone as ``python -m direct.verify_signature_matrix``, matching the
# house pattern in verify_pathway/verify_run.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from . import verify_reconstruct as VR  # noqa: E402
from . import verify_rules as R  # noqa: E402
from . import verify_run  # noqa: E402
from .temporal import admission  # noqa: E402

MATRIX_SCHEMA = "spot.stage02_signature_matrix.v1"
GENE_AXIS_FILE = "gene_axis.arrow"
MATRIX_FILE = "signatures.matrix.arrow"
MASK_FILE = "signatures.mask.arrow"
MANIFEST_FILE = "signature_manifest.json"
REF_FILE = "signature_ref.json"
PROVENANCE_FILE = "pathway_provenance.json"
REDUCTION_ORDER_ID = "spot.stage02.convergence.reduction.sorted_gene_left_fold.v1"
DTYPE, BYTE_ORDER = "float64", "little_endian"
MIN_SHARED_GENES = 10
RUN_ID_LEN = 16
# The manifest's own identity is stored INSIDE the file (its content hash over everything
# else) so a reloaded manifest can be bound non-null. These keys are excluded when recomputing.
IDENTITY_KEYS = ("manifest_sha256", "manifest_canonical_sha256")

PASS, FAIL = "pass", "fail"
ADMIT, REJECT = "admit", "reject"

V1 = "V1_raw_bytes_match_the_manifest_and_every_reference"
V1_REFMAN = "V1_signature_ref_binds_and_rederives_the_shared_manifest_identity"
V2_VALUES = "V2_values_sha256_recomputes_from_the_reread_matrix_bytes"
V2_BITS = "V2_bits_sha256_recomputes_from_the_reread_mask_bytes"
V2_CANON = "V2_canonical_descriptors_recompute_from_the_reread_bytes"
V2_ANCHOR = "V2_matrix_values_rederive_from_the_pinned_de_main"
V2_FINITE = "V2_all_values_are_finite_or_declared"
V3 = "V3_gene_axis_order_and_hash_rederive_from_de_main"
V4 = "V4_amended_bitmap_counts_and_source_mask_identity_rederive_and_are_bound"
V5 = "V5_all_zero_is_unresolved_and_the_resolved_all_ones_set_rederives_from_the_bitmap"
V6 = "V6_convergence_rederives_with_the_sorted_gene_left_fold"
V7 = "V7_member_target_ids_rederive_from_the_bound_gene_sets"
V8 = "V8_no_pathway_bundle_ships_signature_bytes"
V9 = "V9_no_forbidden_key_at_any_depth"
V10 = "V10_every_reference_resolves_and_every_shared_artifact_is_referenced"
V_IDENTITY = "the_signature_ref_is_bound_into_a_rederivable_pathway_run_id"
V_EXTERNAL_MASK = "the_source_mask_matches_the_external_independent_direct_mask_verification"
V_SOLVER_LOCK = "the_stage2_solver_lock_is_bound_into_the_run_identity"
V_QC = "the_per_target_signature_qc_rederives_from_the_shipped_qc_table"
V_STALE_SOURCE = "the_signature_artifact_was_built_from_the_bound_de_source"
V_RELEASE_ROOT = "the_pathway_stage1_release_is_the_one_the_direct_arms_were_built_on"

QC_FILE = "signature_qc.parquet"
QC_KEY = "qc"

# The Stage-2 deterministic solver lock, committed VERBATIM on the producer (W7,
# stage02_solver_lock.txt @ c1f8e80). Unlike a per-run value, this IS a frozen release pin:
# the gate exists precisely to check that the run bound THIS lock and not a swapped one.
STAGE2_SOLVER_LOCK_SHA256 = (
    "2983d140941f13d223dad93bae71434663882f23f25f6717c3debe59d2711abe")

SIGNATURE_BYTE_FILES = ("pathway_signatures.parquet", "signatures.parquet")

# The EXTERNAL Direct-mask verification (W10), bound into the run identity so W4 need not
# re-derive the biological mask itself (which would duplicate ~500 lines and import producer
# logic). W10 independently re-derives every mask from the pinned contributor manifest + sgRNA
# library under the target + 30 kb + contributing-guide off-target rule and admits them.
#
# The W10 VERIFIER IDENTITY. Only the stable verifier id is a fixed clean head; the verifier
# CODE hash, the gate inventory and the certified MASK are all PER-RUN values of W10's report
# and are NOT frozen here (freezing the synthetic 269b… mask would anchor every real bundle to
# a mask nobody computed on real data). The report's identity travels IN the anchor and is
# re-checked against the report bytes the auditor supplies.
W10_VERIFIER_ID = "spot.stage02.direct.arm_bundle.verifier.v1"


def _check(name, ok, detail=""):
    return {"check": name, "status": PASS if ok else FAIL, "detail": detail}


# --------------------------------------------------------------------------- #
# DIGESTS, DESCRIPTORS, RECONSTRUCT + COSINE — re-implemented from the spec.
# --------------------------------------------------------------------------- #
def values_sha256(values) -> str:
    return hashlib.sha256(np.ascontiguousarray(values, "<f8").tobytes()).hexdigest()


def bits_sha256(bitmap) -> str:
    return hashlib.sha256(np.ascontiguousarray(bitmap, np.uint8).tobytes()).hexdigest()


def _descriptor(cond, target_ids, values_sha, gene_axis_raw, n_genes):
    return {"schema_version": MATRIX_SCHEMA, "condition": cond, "dtype": DTYPE,
            "byte_order": BYTE_ORDER, "n_targets": len(target_ids), "n_genes": n_genes,
            "gene_axis_sha256": gene_axis_raw, "target_ids": list(target_ids),
            "values_sha256": values_sha}


def matrix_canonical(cond, target_ids, values_sha, gene_axis_raw, n_genes):
    return R.content_sha256(_descriptor(cond, target_ids, values_sha, gene_axis_raw, n_genes))


def mask_canonical(cond, target_ids, values_sha, bits_sha, gene_axis_raw, n_genes):
    d = _descriptor(cond, target_ids, values_sha, gene_axis_raw, n_genes)
    return R.content_sha256(dict(d, bits_sha256=bits_sha, kind="mask"))


def reconstruct_signatures(target_ids, values, bitmap, gene_ids, n_genes, want):
    """Production's exact dicts from (matrix, bitmap). All-zero row -> NO entry."""
    index = {str(t): i for i, t in enumerate(target_ids)}
    out: dict[str, dict[str, float]] = {}
    for t in want:
        i = index.get(str(t))
        if i is None:
            continue
        bits = np.unpackbits(np.asarray(bitmap[i], np.uint8))[:n_genes]
        if not bits.any():
            continue
        row = values[i]
        out[str(t)] = {gene_ids[j]: float(row[j]) for j in np.nonzero(bits)[0]}
    return out


def cosine_left_fold(a, b):
    """Production's reduction order EXACTLY: sorted-gene left fold, sqrt/sum, round-6."""
    shared = sorted(set(a) & set(b))
    n = len(shared)
    if n < MIN_SHARED_GENES:
        return None, n
    va = [a[g] for g in shared]
    vb = [b[g] for g in shared]
    na = sum(x * x for x in va) ** 0.5
    nb = sum(x * x for x in vb) ** 0.5
    if na == 0.0 or nb == 0.0:
        return None, n
    return round(sum(x * y for x, y in zip(va, vb)) / (na * nb), 6), n


# --------------------------------------------------------------------------- #
# READING THE SHIPPED BYTES.
# --------------------------------------------------------------------------- #
def _read_arrow(path):
    import pyarrow as pa

    with pa.memory_map(path, "rb") as src:
        return pa.ipc.open_file(src).read_all()


def _read_matrix(path, n_genes):
    t = _read_arrow(path)
    targets = [str(x) for x in t.column("target_id").to_pylist()]
    values = np.asarray(t.column("values").combine_chunks().flatten(),
                        "<f8").reshape(len(targets), n_genes)
    return targets, values


def _read_mask(path, width):
    t = _read_arrow(path)
    targets = [str(x) for x in t.column("target_id").to_pylist()]
    bitmap = np.asarray(t.column("unmasked_bits").combine_chunks().flatten(),
                        np.uint8).reshape(len(targets), width)
    return targets, bitmap


def _read_gene_axis(path):
    return [str(x) for x in _read_arrow(path).column("gene_id").to_pylist()]


def _json(path):
    with open(path) as fh:
        return json.load(fh)


def manifest_canonical(manifest):
    """The manifest's own content identity: content_hash over everything but the identity."""
    return R.content_sha256({k: v for k, v in manifest.items() if k not in IDENTITY_KEYS})


# --------------------------------------------------------------------------- #
# THE VERIFICATION.
# --------------------------------------------------------------------------- #
def verify(*, matrix_root, bundle_dirs, args) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    refs: list[tuple[str, dict]] = []
    man_by_cond: dict[str, Any] = {}

    for bdir in bundle_dirs:
        rp = os.path.join(bdir, REF_FILE)
        if os.path.exists(rp):
            refs.append((bdir, _json(rp)))
        else:
            checks.append(_check(V10, False, f"{bdir}: no {REF_FILE}"))

    # ---- V8: no bundle ships signature bytes ----
    bytefiles = [os.path.join(b, f) for b in bundle_dirs for f in SIGNATURE_BYTE_FILES
                 if os.path.exists(os.path.join(b, f))]
    bad_flag = [b for b, r in refs if r.get("ships_signature_bytes") is not False]
    checks.append(_check(V8, not bytefiles and not bad_flag,
                         f"a bundle ships signature bytes: {(bytefiles + bad_flag)[:3]} (A12)"))

    axis_path = os.path.join(matrix_root, GENE_AXIS_FILE)
    conditions = sorted({r["condition"] for _b, r in refs})
    referenced_matrix_raw = {r.get("matrix_raw_sha256") for _b, r in refs}

    for cond in conditions:
        cond_dir = os.path.join(matrix_root, cond)
        man_path = os.path.join(cond_dir, MANIFEST_FILE)
        if not (os.path.exists(man_path) and os.path.exists(axis_path)):
            checks.append(_check(V1, False, f"{cond}: a shared artifact is missing"))
            continue
        man = _json(man_path)
        n_genes, width = int(man["n_genes"]), int(man["bitmap_width_bytes"])
        m_path = os.path.join(cond_dir, MATRIX_FILE)
        k_path = os.path.join(cond_dir, MASK_FILE)
        cond_refs = [r for _b, r in refs if r["condition"] == cond]

        raw_axis = R.sha256_file(axis_path)
        raw_matrix = R.sha256_file(m_path)
        raw_mask = R.sha256_file(k_path)
        raw_man = R.sha256_file(man_path)

        # ---- V1: raw bytes match the manifest + every ref ----
        v1 = []
        if raw_matrix != man["matrix"]["raw_sha256"]:
            v1.append("matrix raw != manifest")
        if raw_mask != man["mask"]["raw_sha256"]:
            v1.append("mask raw != manifest")
        if raw_axis != man["gene_axis"]["raw_sha256"]:
            v1.append("gene_axis raw != manifest")
        for r in cond_refs:
            if r.get("matrix_raw_sha256") != raw_matrix:
                v1.append(f"{r['source']}: ref matrix_raw does not resolve")
            if r.get("mask_raw_sha256") != raw_mask:
                v1.append(f"{r['source']}: ref mask_raw does not resolve")
        checks.append(_check(V1, not v1, f"{cond}: " + "; ".join(v1[:4])))

        # ---- V1_REFMAN: non-null manifest identity, re-derived ----
        recomputed_canon = manifest_canonical(man)
        rm = []
        if man.get("manifest_canonical_sha256") != recomputed_canon:
            rm.append("the shipped manifest_canonical_sha256 does not recompute")
        for r in cond_refs:
            raw_ref = r.get("signature_manifest_raw_sha256") or r.get(
                "signature_manifest_sha256")
            canon_ref = r.get("signature_manifest_canonical_sha256")
            if not raw_ref or not canon_ref:
                rm.append(f"{r['source']}: manifest identity is null — a different "
                          "condition's matrix would be substitutable")
            else:
                if raw_ref != raw_man:
                    rm.append(f"{r['source']}: bound manifest raw != shipped manifest")
                if canon_ref != recomputed_canon:
                    rm.append(f"{r['source']}: bound manifest canonical does not re-derive")
        checks.append(_check(V1_REFMAN, not rm, f"{cond}: " + "; ".join(rm[:3])))

        try:
            m_targets, values = _read_matrix(m_path, n_genes)
            _kt, bitmap = _read_mask(k_path, width)
            axis = _read_gene_axis(axis_path)
        except Exception as exc:                                   # noqa: BLE001
            checks.append(_check(V2_VALUES, False, f"{cond}: bytes do not read: {exc}"))
            continue

        # ---- V2: the digests recompute from the re-read bytes ----
        got_v, got_b = values_sha256(values), bits_sha256(bitmap)
        checks.append(_check(V2_VALUES, got_v == man["matrix"]["values_sha256"],
                             f"{cond}: values_sha256 does not recompute"))
        checks.append(_check(V2_BITS, got_b == man["mask"]["bits_sha256"],
                             f"{cond}: bits_sha256 does not recompute"))
        checks.append(_check(
            V2_CANON,
            matrix_canonical(cond, m_targets, got_v, raw_axis, n_genes)
            == man["matrix"]["canonical_sha256"]
            and mask_canonical(cond, m_targets, got_v, got_b, raw_axis, n_genes)
            == man["mask"]["canonical_sha256"],
            f"{cond}: a canonical descriptor does not recompute"))

        # ---- de_main, read INDEPENDENTLY via h5py (verify_run) ----
        try:
            genes, meta, log_fc = verify_run.read_pooled(args.de_main, cond)
            gene_ids_primary = [str(g) for g in genes]
            de_targets = [str(t) for t in meta["target_contrast"]]
        except Exception as exc:                                   # noqa: BLE001
            checks.append(_check(V2_ANCHOR, False, f"{cond}: de_main did not read: {exc}"))
            checks.append(_check(V3, False, f"{cond}: de_main did not read: {exc}"))
            gene_ids_primary, de_targets, log_fc = axis, m_targets, None

        # ---- V3: gene axis order + hash re-derive from de_main ----
        v3 = []
        if axis != gene_ids_primary:
            v3.append("gene axis order != de_main var/gene_ids (a permuted axis transposes "
                      "every signature)")
        if R.content_sha256(gene_ids_primary) != man["gene_axis"].get(
                "readout_universe_sha256"):
            v3.append("readout_universe_sha256 != content_hash(de_main gene_ids)")
        if man["gene_axis"].get("canonical_sha256") != R.content_sha256(axis):
            v3.append("gene_axis canonical_sha256 does not recompute")
        checks.append(_check(V3, not v3, f"{cond}: " + "; ".join(v3[:3])))

        # ---- V2 anchor: the VALUES re-derive from de_main, in sorted target order ----
        if log_fc is not None:
            order = sorted(range(len(de_targets)), key=lambda i: de_targets[i])
            exp_targets = [de_targets[i] for i in order]
            exp_values = np.ascontiguousarray(log_fc[order], "<f8")
            anchor_ok = (m_targets == sorted(m_targets) and exp_targets == m_targets
                         and values_sha256(exp_values) == got_v)
            checks.append(_check(
                V2_ANCHOR, anchor_ok,
                f"{cond}: the matrix bytes do not equal the float64 de_main log_fc in sorted "
                "target order — a precision downgrade, a row reorder, a cross-condition swap "
                "or a non-finite payload changes these bytes and cannot be resealed away"))
        checks.append(_check(V2_FINITE,
                             bool(np.isfinite(values).all()) or man.get("all_values_finite")
                             is False, f"{cond}: a non-finite value is undeclared"))

        # ---- V4 / V5: the amended bitmap counts, recounted from the bitmap ----
        popcount = np.unpackbits(bitmap, axis=1)[:, :n_genes].sum(axis=1)
        n_zero = int((popcount == 0).sum())
        all_ones_targets = sorted(m_targets[i] for i in np.nonzero(popcount == n_genes)[0])
        n_all_ones = len(all_ones_targets)

        v4 = []
        if man.get("n_resolved_all_ones") != n_all_ones:
            v4.append(f"n_resolved_all_ones declared {man.get('n_resolved_all_ones')} != "
                      f"recounted {n_all_ones}")
        # the two are independent statements of one fact and must agree
        if man.get("n_resolved_no_masked_readout_gene") != n_all_ones:
            v4.append("n_resolved_no_masked_readout_gene != n_resolved_all_ones "
                      "(a resolved all-ones row is exactly a target whose mask misses the axis)")
        if not man.get("source_mask_sha256"):
            v4.append("source_mask_sha256 is absent — the non-empty source mask is not bound")
        for r in cond_refs:
            if r.get("n_resolved_all_ones") != n_all_ones:
                v4.append(f"{r['source']}: ref n_resolved_all_ones != recounted")
            if r.get("source_mask_sha256") != man.get("source_mask_sha256"):
                v4.append(f"{r['source']}: ref source_mask_sha256 != manifest")
        checks.append(_check(V4, not v4, f"{cond}: " + "; ".join(v4[:4])))

        v5 = []
        if n_zero != int(man["n_unresolved_no_signature"]):
            v5.append(f"{n_zero} all-zero rows vs declared "
                      f"{man['n_unresolved_no_signature']} unresolved")
        declared_ids = sorted(str(t) for t in
                              (man.get("resolved_no_masked_readout_gene_target_ids") or []))
        if declared_ids != all_ones_targets:
            v5.append("resolved_no_masked_readout_gene_target_ids does not equal the "
                      "resolved all-ones rows recounted from the bitmap")

        # THE FIRST-CLASS RESOLUTION FIELDS, recounted from the bitmap (Step-0, e5f71df).
        # A resolved row has ANY unmasked readout gene (popcount > 0); of those, a "masked
        # readout" row has at least one masked one (popcount < n_genes) and an all-ones row has
        # none. Every declared count is independently recomputed, and the arithmetic must close.
        n_resolved = int((popcount > 0).sum())
        n_masked = int(((popcount > 0) & (popcount < n_genes)).sum())
        n_targets = len(m_targets)
        if man.get("n_resolved") != n_resolved:
            v5.append(f"n_resolved declared {man.get('n_resolved')} != recounted {n_resolved}")
        if man.get("n_resolved_masked_readout_genes") != n_masked:
            v5.append(f"n_resolved_masked_readout_genes declared "
                      f"{man.get('n_resolved_masked_readout_genes')} != recounted {n_masked}")
        if n_resolved + n_zero != n_targets:
            v5.append("n_resolved + n_unresolved != n_targets — the resolution split does not "
                      "account for every row")
        if n_masked + n_all_ones != n_resolved:
            v5.append("n_resolved_masked_readout_genes + n_resolved_all_ones != n_resolved — "
                      "the two resolved dispositions do not partition the resolved rows")
        checks.append(_check(V5, not v5, f"{cond}: " + "; ".join(v5[:4])))

        # ---- V_QC: the per-target QC table re-derives (file, hash, rows, content) ----
        checks.append(_check(V_QC, *_verify_qc(cond_dir, man, m_targets)))

        # ---- V_STALE_SOURCE: the signature root was built from THIS de_main ----
        # A stale root is the quietest failure: same schema, same hashes, WRONG numbers. The
        # sha the producer bound must equal the de_main the auditor supplies — reseal-proof,
        # because the de_main file is the anchor, not a value inside the artifact.
        want_de = (man.get("sources") or {}).get("de_main_sha256")
        got_de = R.sha256_file(args.de_main) if os.path.exists(args.de_main) else None
        checks.append(_check(
            V_STALE_SOURCE, bool(want_de) and want_de == got_de,
            f"{cond}: the signature root was built from de_main "
            f"{str(want_de)[:16]}…, but this run is bound to {str(got_de)[:16]}… — the "
            "vectors would load and mean a different experiment"))

        man["_reread"] = {"targets": m_targets, "values": values, "bitmap": bitmap,
                          "gene_ids": axis, "n_genes": n_genes, "raw_matrix": raw_matrix}
        man_by_cond[cond] = man

    # ---- V6 / V7 / V9 / V_IDENTITY — per bundle ----
    for bdir, r in refs:
        man = man_by_cond.get(r["condition"])
        if man is None or "_reread" not in man:
            checks.append(_check(V6, False, f"{bdir}: its condition's matrix did not verify"))
            continue
        rr = man["_reread"]

        # V7: members = genes_target(bound sets) ∩ condition targets ∩ resolved
        gs_path = os.path.join(bdir, "gene_sets.source.json")
        checks.append(_check(V7, *_verify_members(r, gs_path, rr)))

        # V6: reconstruct + cosine, bitwise vs convergence.json
        conv_path = os.path.join(bdir, "convergence.json")
        if os.path.exists(conv_path):
            conv = _json(conv_path)
            checks.append(_check(V6, *_verify_convergence(conv, rr,
                                                          r.get("reduction_order_id"))))
            hits = admission.forbidden_keys(r) + admission.forbidden_keys(conv)
            checks.append(_check(V9, not hits, f"{bdir}: forbidden keys {sorted(set(hits))[:6]}"))
        else:
            checks.append(_check(V6, False, f"{bdir}: no convergence.json"))

        # V_IDENTITY: the ref (incl. its cross-lane anchor) IS bound into a re-derivable
        # pathway_run_id — so a forger who edits the anchor must also change the run id.
        checks.append(_check(V_IDENTITY, *_verify_identity(bdir, r)))

        # V_EXTERNAL_MASK: the mask is what W10 independently verified — re-derived HERE from
        # the shipped Direct masks.parquet, not merely trusted from the producer's anchor.
        checks.append(_check(V_EXTERNAL_MASK, *_verify_external_mask(r, rr, args)))

        # V_SOLVER_LOCK: the Stage-2 deterministic solver lock is BOUND into the run identity,
        # and it is the PINNED lock — not a loose file, not a swapped one, not absent.
        checks.append(_check(V_SOLVER_LOCK, *_verify_solver_lock(bdir)))

        # V_RELEASE_ROOT: the pathway enriches the SAME Stage-1 release the Direct arms came
        # from — checked against the EXTERNAL Direct bundle's provenance, so a resealed release
        # (self-consistent inside the pathway bundle) is refused.
        checks.append(_check(V_RELEASE_ROOT, *_verify_release_root(bdir, man, args)))

    # ---- V10 ----
    all_matrix_raw = {m["_reread"]["raw_matrix"] for m in man_by_cond.values()
                      if "_reread" in m}
    unref = all_matrix_raw - referenced_matrix_raw
    dangling = referenced_matrix_raw - all_matrix_raw
    checks.append(_check(V10, bool(refs) and not unref and not dangling,
                         f"unreferenced matrices {sorted(unref)[:2]}; dangling refs "
                         f"{sorted(dangling)[:2]}"))

    failures = [c for c in checks if c["status"] != PASS]
    return {
        "schema_version": "spot.stage02_signature_matrix_verification.v1",
        "verifier_id": "spot.stage02.signature_matrix.verifier.v1",
        "generator_is_not_verifier": True, "fail_closed": True,
        "reduction_order_id": REDUCTION_ORDER_ID,
        "n_bundles": len(refs), "n_conditions": len(conditions),
        "checks": checks, "n_failed": len(failures),
        "verdict": ADMIT if not failures else REJECT,
    }


def _verify_members(ref, gs_path, rr):
    if not os.path.exists(gs_path):
        return False, "the bound gene-set source copy is not shipped in the bundle"
    try:
        bundle = VR.parse_bundle(_json(gs_path))
    except Exception as exc:                                       # noqa: BLE001
        return False, f"the shipped gene-set source does not parse: {exc}"
    genes_target = {g for s in bundle["sets"].values() for g in s["genes_target"]}
    resolved = set(reconstruct_signatures(
        rr["targets"], rr["values"], rr["bitmap"], rr["gene_ids"], rr["n_genes"],
        sorted(genes_target & set(rr["targets"]))).keys())
    expected = sorted(resolved)
    declared = sorted(str(t) for t in (ref.get("member_target_ids") or []))
    if declared != expected:
        extra = sorted(set(declared) - set(expected))[:3]
        return False, (f"member_target_ids do not re-derive (padded {extra}); members are "
                       "genes_target ∩ condition targets ∩ resolved")
    if ref.get("n_member_targets") != len(expected):
        return False, "n_member_targets disagrees with the re-derived member list"
    return True, ""


def _verify_convergence(conv, rr, reduction_order_id):
    if reduction_order_id != REDUCTION_ORDER_ID:
        return False, (f"reduction_order_id {reduction_order_id!r} is not the sorted-gene "
                       "left fold; a vectorised cosine drifts ~5e-07 and flips supportive at 0.5")
    pairs = [p for s in conv.get("sets", []) for p in s.get("pairwise_support", [])]
    if not pairs:
        return True, ""
    wanted = sorted({p["target_a"] for p in pairs} | {p["target_b"] for p in pairs})
    sig = reconstruct_signatures(rr["targets"], rr["values"], rr["bitmap"], rr["gene_ids"],
                                 rr["n_genes"], wanted)
    for p in pairs:
        a, b = p["target_a"], p["target_b"]
        if a not in sig or b not in sig:
            return False, f"({a},{b}) has no reconstructable signature"
        sim, n_shared = cosine_left_fold(sig[a], sig[b])
        if sim != p.get("similarity") or n_shared != p.get("n_shared_unmasked_genes"):
            return False, (f"convergence does not re-derive BITWISE: ({a},{b}) re-derived "
                           f"{sim}/{n_shared} != emitted {p.get('similarity')}/"
                           f"{p.get('n_shared_unmasked_genes')}")
    return True, ""


def _verify_identity(bdir, ref_on_disk):
    """The ref IS the one bound into the run identity, and the id re-derives from the binding.

    This anchors the amended counts and source_mask_sha256 the ref carries: a forger who
    reseals the manifest and the ref must also produce a run id the binding hashes to.
    """
    prov_path = os.path.join(bdir, PROVENANCE_FILE)
    if not os.path.exists(prov_path):
        return False, f"{bdir}: no {PROVENANCE_FILE} to bind the reference into an identity"
    prov = _json(prov_path)
    binding = prov.get("run_binding") or {}
    if binding.get("signature_ref") != ref_on_disk:
        return False, ("the signature_ref on disk is not the one bound into run_binding; a "
                       "reference the run identity does not cover can be swapped freely")
    full = R.content_sha256(binding)
    if full != prov.get("pathway_run_sha256") or full[:RUN_ID_LEN] != prov.get(
            "pathway_run_id"):
        return False, "the run binding does not hash to the declared pathway_run_id"
    return True, ""


def _verify_solver_lock(bdir):
    """The Stage-2 deterministic solver lock is BOUND into the run identity — and is the PINNED
    lock, not a loose file. A committed lock nobody's identity depends on can be swapped or
    dropped and nothing notices; this reads it from the shipped run_binding and refuses a
    MISSING or SWAPPED lock at a named gate.
    """
    prov_path = os.path.join(bdir, PROVENANCE_FILE)
    if not os.path.exists(prov_path):
        return False, f"{bdir}: no {PROVENANCE_FILE} to carry the solver-lock binding"
    binding = _json(prov_path).get("run_binding") or {}
    lock = binding.get("environment_lock") or {}
    status = lock.get("status")
    sha = lock.get("sha256")
    if status != "locked" or not sha:
        return False, (f"the Stage-2 solver lock is not bound (status={status!r}); an "
                       "unbound environment is not a reproducible one")
    if sha != STAGE2_SOLVER_LOCK_SHA256:
        return False, (f"the bound environment lock {str(sha)[:16]}… is not the pinned "
                       f"Stage-2 solver lock {STAGE2_SOLVER_LOCK_SHA256[:16]}… — a swapped "
                       "lock, however self-consistent after the run id is resealed")
    return True, ""


def _verify_release_root(bdir, manifest, args):
    """The pathway's Stage-1 release IS the one the Direct arms it enriches were built on.

    An enrichment computed over a different Stage-1 release than the ranking it enriches
    describes a different experiment — and every hash inside the pathway bundle would still
    agree with itself. So the release is checked against TWO things the pathway bundle does not
    own: the anchor the producer carried from the Direct bundle, and — reseal-proof — the
    EXTERNAL Direct bundle's own provenance, which a pathway forger cannot rewrite.
    """
    prov_path = os.path.join(bdir, PROVENANCE_FILE)
    if not os.path.exists(prov_path):
        return False, f"{bdir}: no {PROVENANCE_FILE} to carry the release binding"
    binding = _json(prov_path).get("run_binding") or {}
    mine = binding.get("stage1_release_hashes")
    if not mine:
        return False, ("the pathway run binds no stage1_release_hashes — a bundle that does "
                       "not name the Stage-1 release it was computed against could be "
                       "re-attributed to another one")
    if not binding.get("stage1_release_kind"):
        return False, "the pathway run binds no stage1_release_kind"
    problems = []

    # (a) the release the producer carried from the Direct bundle into the mask anchor
    anchor = (manifest.get("direct_mask_anchor") or {})
    declared = anchor.get("direct_stage1_release_hashes")
    if declared and dict(declared) != dict(mine):
        problems.append("the pathway release is not the one carried in the Direct mask anchor")

    # (b) RESEAL-PROOF: the EXTERNAL Direct bundle's own provenance. The pathway forger owns
    # neither this file nor the Direct arms; a resealed pathway release still disagrees with it.
    bundle_dir = getattr(args, "direct_bundle", None)
    if bundle_dir:
        dprov_path = os.path.join(bundle_dir, "provenance.json")
        if not os.path.exists(dprov_path):
            problems.append("the Direct bundle ships no provenance to anchor the release to")
        else:
            db = (_json(dprov_path).get("run_binding") or {})
            direct_rel = (db.get("arm_bundle_request") or {}).get("stage1_release_hashes") \
                or db.get("stage1_release_hashes")
            if direct_rel and dict(direct_rel) != dict(mine):
                problems.append("the pathway release is not the release the ADMITTED Direct "
                                "bundle records its arms were built on")
    return (not problems), "; ".join(problems[:3])


def _verify_qc(cond_dir, manifest, matrix_targets):
    """The per-target QC table re-derives from the shipped bytes: file, hash, rows, content.

    Without the QC a consumer cannot tell which targets Direct REFUSED — it would project the
    ones that failed base QC. The QC block binds the raw bytes, a content hash over the rows,
    the row count and the base-passed count; all four re-derive here from the shipped parquet,
    and every matrix target must have exactly one QC row.
    """
    import pandas as pd

    qc = manifest.get(QC_KEY) or {}
    path = os.path.join(cond_dir, QC_FILE)
    if not os.path.exists(path):
        return False, f"{QC_FILE} is absent: the matrix says what every vector IS and nothing " \
                      "about which target may be USED"
    if R.sha256_file(path) != qc.get("raw_sha256"):
        return False, "the shipped signature_qc.parquet does not hash to the bound raw_sha256"
    df = pd.read_parquet(path)
    rows = df.to_dict("records")
    for r in rows:                                  # NaN (a null that round-tripped) -> None
        for k, v in list(r.items()):
            if isinstance(v, float) and v != v:
                r[k] = None
    rows.sort(key=lambda r: str(r["target_id"]).encode("utf-8"))
    problems = []
    if R.content_sha256(rows) != qc.get("canonical_sha256"):
        problems.append("the QC rows do not re-derive the bound canonical_sha256")
    if len(rows) != qc.get("n_rows"):
        problems.append(f"{len(rows)} QC rows vs bound {qc.get('n_rows')}")
    n_passed = sum(1 for r in rows if r.get("base_passed"))
    if n_passed != qc.get("n_base_passed"):
        problems.append(f"{n_passed} base-passed vs bound {qc.get('n_base_passed')}")
    qc_targets = sorted(str(r["target_id"]) for r in rows)
    if qc_targets != sorted(matrix_targets):
        problems.append("the QC targets are not exactly the matrix targets — a target with a "
                        "vector but no QC row could be projected past the QC that refused it")
    return (not problems), "; ".join(problems[:3])


def direct_masked_genes(masks_parquet):
    """The shipped Direct mask table, projected to {target: masked genes} — re-implemented.

    Only the POOLED-MAIN rows project into a signature bitmap; the guide/donor rows describe
    estimates nothing here projects. Re-derived independently of the producer (pandas is a
    reader, not producer logic).
    """
    import pandas as pd

    df = pd.read_parquet(masks_parquet)
    if "estimate_type" in df.columns:
        df = df[df["estimate_type"] == "main"]
    out: dict[str, set] = {}
    for t, g in zip(df["target_id"], df["masked_gene_ensembl"]):
        if g is None or (isinstance(g, float) and g != g):
            out.setdefault(str(t), set())
            continue
        out.setdefault(str(t), set()).add(str(g))
    return out


def _verify_external_mask(ref, rr, args):
    """INDEPENDENTLY re-derive the cross-lane anchor: this lane's mask IS the Direct mask.

    The bitmap, the counts and source_mask_sha256 all come from the SAME mask_sets, so a
    coherently forged mask satisfies every internal check — the forgery ADMITS on
    self-consistency alone. A mask can only be contradicted from OUTSIDE, by a table someone
    else derived from the primary inputs. W10 re-derives the Direct mask from the contributor
    manifest + sgRNA library; W4 REPEATS that comparison here from the shipped Direct
    masks.parquet, so it does not merely trust the producer's own anchor block.

    Fail-closed: an UNANCHORED matrix, or one whose masked readout genes disagree with the
    Direct table, is refused.
    """
    anchor = ref.get("direct_mask_anchor")
    if not ref.get("mask_is_externally_anchored") or not anchor:
        return False, ("the mask is not externally anchored to an independently-verified "
                       "Direct mask; bitmap self-consistency cannot distinguish a coherent "
                       "wrong mask from the truth (W18: pass --direct-bundle + "
                       "--direct-mask-report)")
    problems = []
    if anchor.get("verifier_id") != W10_VERIFIER_ID:
        problems.append(f"the anchor is not from the W10 verifier {W10_VERIFIER_ID!r}")
    if not anchor.get("report_sha256"):
        problems.append("the per-run W10 report is not content-addressed in the anchor")
    if not anchor.get("direct_mask_sha256"):
        problems.append("the anchor binds no Direct mask hash")

    # INDEPENDENT re-derivation from the shipped Direct bytes, when the auditor supplies them.
    bundle_dir = getattr(args, "direct_bundle", None)
    report_path = getattr(args, "direct_mask_report", None)
    if bundle_dir and report_path:
        if R.sha256_file(report_path) != anchor.get("report_sha256"):
            problems.append("the anchored report_sha256 is not the report supplied")
        try:
            direct = direct_masked_genes(os.path.join(bundle_dir, "masks.parquet"))
        except Exception as exc:                                # noqa: BLE001
            return False, f"the Direct masks.parquet did not read: {exc}"
        axis = set(rr["gene_ids"])
        n_genes = rr["n_genes"]
        bits = np.unpackbits(rr["bitmap"], axis=1)[:, :n_genes]
        mism = []
        for i, t in enumerate(rr["targets"]):
            if not bits[i].any():
                continue                       # unresolved -> no signature -> nothing to anchor
            if t not in direct:
                mism.append(f"{t}: absent from the Direct mask table")
                continue
            zeros = {rr["gene_ids"][j] for j in np.nonzero(bits[i] == 0)[0]}
            expect = direct[t] & axis          # INTERSECT the axis FIRST (axis-missing masks)
            if zeros != expect:
                mism.append(f"{t}: {len(zeros)} masked here vs {len(expect)} in the "
                            "independently-verified Direct table")
        if mism:
            problems.append(f"{len(mism)} target(s) are masked differently from the Direct "
                            f"table W10 re-derived (e.g. {mism[:3]}) — a coherent wrong mask")
    else:
        problems.append("the Direct bundle + W10 report were not supplied for independent "
                        "re-derivation; the anchor is bound but not re-checked from outside")
    return (not problems), "; ".join(problems[:4])


# --------------------------------------------------------------------------- #
# A MINIMAL DETERMINISTIC CLI. Explicit inputs, an explicit persisted report, nonzero exit on
# any refusal. The persisted report is CONTENT-ADDRESSED: it carries only the verdict and the
# per-gate pass/fail — no absolute paths, no timestamps — so the runbook can bind report_sha256.
# See STAGE2_SOLVER_LOCK_GATE_SPEC.md / the W18 coordination note for the producer output shape.
# --------------------------------------------------------------------------- #
def _deterministic_report(result: dict[str, Any]) -> dict[str, Any]:
    """The bound report: verdict + per-gate status, with all free-text detail stripped.

    Details name absolute bundle paths, which would make the report machine-specific; the
    binding is over the VERDICT and the gate results, which depend only on the shipped bytes.
    """
    return {
        "schema_version": result.get("schema_version"),
        "verifier_id": result.get("verifier_id"),
        "generator_is_not_verifier": True,
        "fail_closed": True,
        "n_bundles": result.get("n_bundles"),
        "n_conditions": result.get("n_conditions"),
        "verdict": result.get("verdict"),
        "n_failed": result.get("n_failed"),
        "gates": [{"check": c["check"], "status": c["status"]}
                  for c in result.get("checks", [])],
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m direct.verify_signature_matrix",
        description="Independent Stage-2 pathway signature-matrix verifier (V1-V10 + the "
                    "cross-lane Direct mask anchor + the solver-lock binding). Reads the "
                    "SHIPPED bytes and re-derives every claim; imports no producer module. "
                    "Exit 0 = ADMIT, nonzero = REJECT.")
    ap.add_argument("--signature-matrix-root", required=True,
                    help="the shared Step-0 artifacts: gene_axis.arrow + <condition>/ dirs")
    ap.add_argument("--bundle", required=True, action="append", dest="bundles",
                    metavar="DIR", help="a pathway bundle dir (repeatable) — carries "
                    "signature_ref.json, convergence.json, pathway_provenance.json, "
                    "gene_sets.source.json")
    ap.add_argument("--de-main", required=True,
                    help="the pinned DE h5ad the producer read (values/axis re-derivation)")
    ap.add_argument("--direct-bundle", default=None,
                    help="the admitted Direct arm bundle (masks.parquet + provenance.json) "
                         "for the independent cross-lane mask re-derivation")
    ap.add_argument("--direct-mask-report", default=None,
                    help="the per-run W10 Direct mask verification report")
    ap.add_argument("--out", required=True,
                    help="path to write the deterministic, content-addressed report JSON")
    args = ap.parse_args(argv)

    try:
        result = verify(matrix_root=args.signature_matrix_root,
                        bundle_dirs=list(args.bundles), args=args)
    except Exception as exc:                       # a crash IS a verification failure
        result = {"schema_version": "spot.stage02_signature_matrix_verification.v1",
                  "verifier_id": "spot.stage02.signature_matrix.verifier.v1",
                  "verdict": REJECT, "n_failed": 1,
                  "checks": [{"check": "verifier_completed_without_error",
                              "status": FAIL,
                              "detail": f"{type(exc).__name__}: {exc}"}]}

    report = _deterministic_report(result)
    report_bytes = json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    report_sha256 = hashlib.sha256(report_bytes).hexdigest()
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(dict(report, report_sha256=report_sha256), fh, indent=2, sort_keys=True)
        fh.write("\n")

    print(json.dumps({"verdict": report["verdict"], "n_failed": report["n_failed"],
                      "report": args.out, "report_sha256": report_sha256}, indent=2))
    if report["verdict"] != ADMIT:
        for c in result.get("checks", []):
            if c["status"] != PASS:
                print(f"  REFUSE [{c['check']}] {c.get('detail', '')}", file=sys.stderr)
    return 0 if report["verdict"] == ADMIT else 1


if __name__ == "__main__":
    sys.exit(main())
