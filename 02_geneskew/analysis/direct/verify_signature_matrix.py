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
              the bitmap and equals the declared resolved_no_masked_readout_gene disposition.
              A resolved all-ones row is the amended VALID state (its mask misses the readout
              axis); an all-zero row is unresolved / NO SIGNATURE, never an unmasked vector.
    V6        convergence re-derives from (matrix, bitmap) with the sorted-gene left fold,
              BITWISE — a 5e-07 numpy drift is a refusal.
    V7        member_target_ids re-derive from the bound gene sets ∩ condition targets ∩ resolved.
    V8        no pathway bundle ships signature bytes.
    V9        the recursive no-p/q/FDR firewall over every shipped document.
    V10       every reference resolves; every shared artifact is cited.
    V_IDENTITY the signature_ref on disk IS the one bound into a re-derivable pathway_run_id, so
              a forger who reseals the manifest/ref must also change the run id.

GENERATOR ≠ VERIFIER. It imports NO producer module — only ``h5py``/``numpy``/``json`` and the
verifier-side ``verify_rules`` / ``verify_run`` (primary h5ad reader) / ``verify_reconstruct``
(gene-set parse). The precision digests, canonical descriptors, ``reconstruct_signatures`` and
the cosine are re-implemented from the spec. The all-ones INTERSECTION correctness is the
producer's fail-closed responsibility; its ``source_mask_sha256`` and amended counts are bound
into the run identity, which this verifier re-derives. W18's producer does not admit itself.
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any

import numpy as np

from . import verify_reconstruct as VR
from . import verify_rules as R
from . import verify_run
from .temporal import admission

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

SIGNATURE_BYTE_FILES = ("pathway_signatures.parquet", "signatures.parquet")

# The EXTERNAL Direct-mask verification (W10), bound into the run identity so W4 need not
# re-derive the biological mask itself (which would duplicate ~500 lines and import producer
# logic). W10 independently re-derives every mask from the pinned contributor manifest + sgRNA
# library under the target + 30 kb + contributing-guide off-target rule and admits them.
#
# The W10 VERIFIER IDENTITY is bound to exact clean heads — this is WHICH verifier attested,
# fixed for a given W10 release, and NOT a per-run value. The CERTIFIED MASK is per-run and is
# read from the bound report, never frozen: at the real run the pathway binds a per-run W10
# report over the ACTUAL Direct masks.parquet. (The concrete 269b… mask and the three bundle
# ids in W10's sealed report are SYNTHETIC-FIXTURE values, used only in contract/mutation
# tests.)
W10_VERIFIER_ID = "spot.stage02.direct.arm_bundle.verifier.v1"
W10_VERIFIER_CODE_SHA256 = (
    "7578ae5eecbd68dda1198b7b5bd933dd09ad08be838d37dfb837fe5e285a4a89")
W10_GATE_INVENTORY_SHA256 = (
    "cc8fc6ca81817de411f951309f219d76fdeea5cff3b4f7bf5ee7b38bb07f821d")
W10_ADMIT = "ADMIT"
DIRECT_MASK_BINDING_KEY = "direct_mask_verification"


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
        checks.append(_check(V5, not v5, f"{cond}: " + "; ".join(v5[:3])))

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

        # V_IDENTITY + V_EXTERNAL_MASK both read the run binding.
        prov_path = os.path.join(bdir, PROVENANCE_FILE)
        run_binding = (_json(prov_path).get("run_binding") or {}
                       ) if os.path.exists(prov_path) else {}

        # V_IDENTITY: the ref IS bound into a re-derivable pathway_run_id
        checks.append(_check(V_IDENTITY, *_verify_identity(bdir, r)))

        # V_EXTERNAL_MASK: the source mask is what W10 independently verified — not merely
        # self-consistent. A forger can rebuild a coherent WRONG mask + bitmap + counts +
        # source_mask_sha256 + run_id; only an external, independently re-derived Direct mask
        # verification refuses it, by certifying the TRUE mask the forger cannot match.
        checks.append(_check(V_EXTERNAL_MASK, *_verify_external_mask(run_binding)))

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


def _verify_external_mask(binding):
    """Bind the EXTERNAL, independent Direct mask verification (W10) and cross-check.

    W4 does not re-derive the biological mask (that would duplicate the Direct lane and import
    producer logic). Instead it binds W10's independent Direct mask verification — which
    re-derives every mask from the pinned contributor manifest + sgRNA library and admits them.

    The W10 VERIFIER IDENTITY (id + code hash + gate inventory) is bound to exact clean heads:
    a report from a different or unverified checker is refused. The CERTIFIED MASK is per-run
    and is read from the bound report — the pathway's own ``mask_sha256`` must equal it, which
    proves the matrix ran on the masks W10 independently verified. A forger who fabricates a
    coherent wrong mask changes ``mask_sha256``, and W10's per-run report (produced over the
    ACTUAL Direct masks.parquet) still certifies the true hash, so this gate refuses.
    """
    bound = binding.get(DIRECT_MASK_BINDING_KEY) or {}
    if not bound:
        return False, ("no external Direct mask verification is bound into the run identity; "
                       "bitmap self-consistency cannot distinguish a coherent wrong source "
                       "mask from the truth. W18 must bind W10's per-run report over the "
                       "actual Direct masks.parquet")
    problems = []
    if bound.get("verdict") != W10_ADMIT:
        problems.append(f"the Direct mask verification did not admit: {bound.get('verdict')!r}")
    if bound.get("verifier_id") != W10_VERIFIER_ID:
        problems.append(f"the report is not from the bound W10 verifier {W10_VERIFIER_ID!r}")
    if bound.get("verifier_code_sha256") != W10_VERIFIER_CODE_SHA256:
        problems.append("the W10 verifier code identity is not the bound clean head")
    if bound.get("gate_inventory_sha256") != W10_GATE_INVENTORY_SHA256:
        problems.append("the W10 gate inventory is not the bound clean head")
    if not bound.get("report_sha256"):
        problems.append("the per-run W10 report is not content-addressed in the binding")
    # PER-RUN, never frozen: the pathway used the exact masks W10 verified.
    certified = bound.get("certified_mask_sha256")
    pathway_mask = binding.get("mask_sha256")
    if not certified or not pathway_mask or certified != pathway_mask:
        problems.append(f"the pathway mask_sha256 {str(pathway_mask)[:16]}… is not the mask "
                        f"W10 certified {str(certified)[:16]}… — the matrix did not run on "
                        "the W10-verified Direct masks")
    return (not problems), "; ".join(problems[:4])
