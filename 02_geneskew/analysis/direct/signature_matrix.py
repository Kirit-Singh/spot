"""The SHARED signature matrix + MANDATORY mask bitmap. One per condition, not per bundle.

W7's spec (PATHWAY_SIGNATURE_MATRIX_SPEC.md, sha 95d69302). Storage only: it changes no method,
no score, no rank and no biological claim.

WHY IT IS SHARED
----------------
A signature value depends on (condition, target, gene) — and on NOTHING else. The gene-set
source only selects WHICH targets are asked about; it cannot change what the answer is. So the
two bundles at a condition were writing byte-identical values for the ~6.7k targets they share.
The duplication is structural, not incidental: 521M rows, 4.894 GiB, and — the number that
actually decides it — a 29.5 GiB peak RSS on the worst bundle, so four concurrent pathway
workers would demand 118 GiB against 87 GiB available on a host with no swap left. That is an
OOM kill mid-run, not a slow run.

THE BITMAP IS NOT AN OPTIMISATION
---------------------------------
It is the only thing that distinguishes a MASKED cell from an unmasked value that happens to be
0.0. Drop it and those two stop being different, and the analysis quietly changes. So the mask
artifact is mandatory, and a matrix without one is refused.

An ALL-ZERO bitmap row means **NO SIGNATURE** — the target is unresolved (~139 per condition)
and `build_estimate_mask` returned no mask, so nothing may project for it. It does NOT mean
"nothing was masked". The values row still exists, so that row indices align and the matrix
stays a faithful image of the condition; it is simply excluded from signatures, from
`cosine_on_shared`, and from convergence.

Conversely, a RESOLVED row can never be all-ones: `build_estimate_mask` always masks the
target's own gene ("its own repression is QC, never skew evidence"), so every resolved row has
at least one 0 bit. An all-ones resolved row is a producer bug and is refused (P5).

DO NOT VECTORISE THE COSINE
---------------------------
A dense matrix invites replacing the dict cosine with a numpy reduction. The VALUES would be
identical and the SUMMATION ORDER would not: ~5e-07 apart, and `supportive` is a threshold at
0.5. ``reconstruct_signatures`` exists so consumers rebuild the dict and call production's own
``convergence.cosine_on_shared`` unchanged — the path W7 proved bitwise over 1,770 real pairs
(0 mismatches, max diff 0.0). It is the ONLY path a consumer may use.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from typing import Any, Optional

import numpy as np

from . import guides, identity, io_data, masks
from . import manifest as mf
from .hashing import content_hash, file_sha256

SCHEMA_VERSION = "spot.stage02_signature_matrix.v1"
REF_SCHEMA_VERSION = "spot.stage02_signature_ref.v1"

GENE_AXIS_FILE = "gene_axis.arrow"
MATRIX_FILE = "signatures.matrix.arrow"
MASK_FILE = "signatures.mask.arrow"
MANIFEST_FILE = "signature_manifest.json"
REF_FILE = "signature_ref.json"

DTYPE = "float64"
BYTE_ORDER = "little_endian"

# The reduction order production folds in. Recorded in every manifest, and the reason
# reconstruct_signatures exists at all.
REDUCTION_ORDER_ID = "spot.stage02.convergence.reduction.sorted_gene_left_fold.v1"
MASK_RULE_ID = "spot.stage02.direct.mask.build_estimate_mask.v1"
MEMBER_RULE_ID = "spot.stage02.pathway.members.genes_target_intersect_resolved.v1"

# ---- P-gates. Every one a refusal; none a warning. ----
REFUSE_INPUT_PIN_MISMATCH = "REFUSE_INPUT_PIN_MISMATCH"
REFUSE_MASK_NOT_DERIVED = "REFUSE_MASK_NOT_DERIVED"
REFUSE_GENE_AXIS_MISMATCH = "REFUSE_GENE_AXIS_MISMATCH"
REFUSE_ROW_ORDER = "REFUSE_ROW_ORDER"
REFUSE_RESOLVED_ROW_UNMASKED = "REFUSE_RESOLVED_ROW_UNMASKED"
REFUSE_PADDING_BITS = "REFUSE_PADDING_BITS"
REFUSE_NONFINITE_UNDECLARED = "REFUSE_NONFINITE_UNDECLARED"
REFUSE_MASK_ARTIFACT_ABSENT = "REFUSE_MASK_ARTIFACT_ABSENT"
REFUSE_NONDETERMINISTIC_WRITE = "REFUSE_NONDETERMINISTIC_WRITE"
REFUSE_WRITE_NOT_DETERMINISTIC = "REFUSE_WRITE_NOT_DETERMINISTIC"
REFUSE_BUNDLE_SHIPS_SIGNATURES = "REFUSE_BUNDLE_SHIPS_SIGNATURES"
REFUSE_REDUCTION_ORDER_UNDECLARED = "REFUSE_REDUCTION_ORDER_UNDECLARED"


class SignatureMatrixError(ValueError):
    """A named, fail-closed refusal. Never a warning, never a repair."""

    def __init__(self, gate: str, message: str):
        super().__init__(f"[{gate}] {message}")
        self.gate = gate


def _refuse(gate: str, message: str) -> None:
    raise SignatureMatrixError(gate, message)


def bitmap_width_bytes(n_genes: int) -> int:
    """ceil(n_genes/8). DERIVED — never a copied constant."""
    return (int(n_genes) + 7) // 8


def sorted_target_ids(target_ids) -> list[str]:
    """Ascending by the BYTES of the UTF-8 id. Deterministic, and not locale-dependent."""
    return sorted((str(t) for t in target_ids), key=lambda s: s.encode("utf-8"))


def build(*, condition: str, main: dict[str, Any],
          mask_sets: dict[str, Optional[set]],
          gene_ids: list[str]) -> dict[str, Any]:
    """The condition's values matrix and its mandatory bitmap. Rows sorted by target_id.

    ``mask_sets[target]`` is the target's masked-gene set, or ``None`` when the mask is
    UNRESOLVED — which is not an empty mask. An unresolved target's bitmap row is all zero,
    and that means NO SIGNATURE.
    """
    meta, gene_index = main["meta"], main["gene_index"]
    n_genes = len(gene_ids)

    # P3: the gene axis is var/gene_ids VERBATIM. A sorted axis silently transposes every
    # signature, and it would look perfectly canonical while doing it.
    if list(gene_ids) != [str(g) for g in main["gene_ids"]]:
        _refuse(REFUSE_GENE_AXIS_MISMATCH,
                "the gene axis is not var/gene_ids verbatim; a re-ordered axis transposes "
                "every signature in the matrix")

    load_order = [str(t) for t in meta["target_id"]]
    row_of = {t: i for i, t in enumerate(load_order)}
    targets = sorted_target_ids(load_order)          # P4

    missing = [t for t in targets if t not in mask_sets]
    if missing:
        _refuse(REFUSE_MASK_NOT_DERIVED,
                f"no mask was derived for {len(missing)} target(s) (e.g. {missing[:3]}); a "
                "target with no derived mask is not a target with an empty mask, and it may "
                "not be projected under one")

    values = np.empty((len(targets), n_genes), dtype="<f8")   # float64, little-endian
    bits = np.zeros((len(targets), n_genes), dtype=bool)

    for i, t in enumerate(targets):
        row = main["log_fc"][row_of[t]]
        # VERBATIM: the effect row as loaded. Masking is expressed by the bitmap, NEVER by
        # absence — that separation is exactly what makes the artifact condition-shared.
        values[i, :] = np.asarray(row, dtype="<f8")
        mask_set = mask_sets[t]
        if mask_set is None:
            continue                                  # unresolved -> all-zero row -> NO SIGNATURE
        for j, g in enumerate(gene_ids):
            if g in gene_index and g not in mask_set:
                bits[i, j] = True

    # numpy.packbits: MSB-first within each byte, and it zero-fills the trailing padding.
    packed = np.packbits(bits, axis=1)                # (n_targets, ceil(n_genes/8))
    if packed.shape[1] != bitmap_width_bytes(n_genes):
        _refuse(REFUSE_PADDING_BITS,
                f"packed bitmap width {packed.shape[1]} != {bitmap_width_bytes(n_genes)}")

    popcount = bits.sum(axis=1)
    resolved = np.array([mask_sets[t] is not None for t in targets])

    # P5: a resolved target ALWAYS has its own gene masked, so it can never be all-ones.
    unmasked_resolved = [targets[i] for i in np.nonzero(resolved & (popcount == n_genes))[0]]
    if unmasked_resolved:
        _refuse(REFUSE_RESOLVED_ROW_UNMASKED,
                f"{len(unmasked_resolved)} resolved target(s) have NO masked gene (e.g. "
                f"{unmasked_resolved[:3]}). build_estimate_mask always masks the intended "
                "target — its own repression is QC, never skew evidence — so an all-ones "
                "resolved row means the mask was not derived")

    # P6: bits beyond n_genes are padding and must be zero. Re-unpacked and checked, not
    # trusted to packbits.
    if n_genes % 8:
        tail = np.unpackbits(packed[:, -1:], axis=1)[:, n_genes % 8:]
        if tail.any():
            _refuse(REFUSE_PADDING_BITS, "trailing padding bits are not zero")

    all_finite = bool(np.isfinite(values).all())

    return {
        "condition": condition,
        "target_ids": targets,
        "values": values,
        "bitmap": packed,
        "n_targets": len(targets),
        "n_genes": n_genes,
        "n_resolved": int(resolved.sum()),
        "n_unresolved_no_signature": int((~resolved).sum()),
        "all_values_finite": all_finite,
        "popcount": popcount,
    }


def values_sha256(values: np.ndarray) -> str:
    """The PRECISION-BEARING digest: the row-major little-endian float64 buffer.

    A float32 downgrade changes it. A row reorder changes it. A transposed gene axis changes
    it. That is the point — none of those can be hidden by reformatting the container.
    """
    buf = np.ascontiguousarray(values, dtype="<f8")
    return hashlib.sha256(buf.tobytes()).hexdigest()


def bits_sha256(bitmap: np.ndarray) -> str:
    return hashlib.sha256(
        np.ascontiguousarray(bitmap, dtype=np.uint8).tobytes()).hexdigest()


# --------------------------------------------------------------------------- #
# Deterministic Arrow IPC (Feather v2). Uncompressed, ONE batch, no custom metadata:
# anything that varies between two identical runs must not be in the file.
# --------------------------------------------------------------------------- #
def _write_table(table, path: str) -> str:
    import pyarrow as pa

    with pa.OSFile(path, "wb") as sink:
        # options=None -> no body compression. A codec is another version-dependent producer
        # of bytes, and this file is supposed to hash the same twice.
        with pa.ipc.new_file(sink, table.schema) as writer:
            writer.write_table(table, max_chunksize=len(table))   # ONE record batch
    return file_sha256(path)


def write_gene_axis(out_root: str, gene_ids: list[str]) -> dict[str, Any]:
    """The readout universe, ONCE per run. Row order = var/gene_ids, verbatim."""
    import pyarrow as pa

    os.makedirs(out_root, exist_ok=True)
    path = os.path.join(out_root, GENE_AXIS_FILE)
    table = pa.table({"gene_id": pa.array([str(g) for g in gene_ids], type=pa.string())})
    raw = _write_table(table, path)
    return {"path": path, "raw_sha256": raw, "n_genes": len(gene_ids),
            "canonical_sha256": content_hash([str(g) for g in gene_ids])}


def write(built: dict[str, Any], *, out_root: str, gene_axis: dict[str, Any],
          sources: dict[str, Optional[str]],
          readout_universe_sha256: str) -> dict[str, Any]:
    """Write ONE condition's matrix + mandatory bitmap + manifest. Returns the manifest."""
    import pyarrow as pa

    cond_dir = os.path.join(out_root, built["condition"])
    os.makedirs(cond_dir, exist_ok=True)

    n_genes, width = built["n_genes"], bitmap_width_bytes(built["n_genes"])
    matrix_path = os.path.join(cond_dir, MATRIX_FILE)
    mask_path = os.path.join(cond_dir, MASK_FILE)

    # P7: all finite, or say so explicitly. A future release that is not finite must be a
    # decision, not a silence.
    if not built["all_values_finite"] and built.get("nonfinite_declared") is not True:
        _refuse(REFUSE_NONFINITE_UNDECLARED,
                "the values are not all finite and all_values_finite=false was not declared")

    vals = np.ascontiguousarray(built["values"], dtype="<f8")
    matrix_tbl = pa.table({
        "target_id": pa.array(built["target_ids"], type=pa.string()),
        "values": pa.FixedSizeListArray.from_arrays(
            pa.array(vals.reshape(-1), type=pa.float64()), n_genes),
    })
    matrix_raw = _write_table(matrix_tbl, matrix_path)

    bmp = np.ascontiguousarray(built["bitmap"], dtype=np.uint8)
    mask_tbl = pa.table({
        "target_id": pa.array(built["target_ids"], type=pa.string()),
        "unmasked_bits": pa.FixedSizeListArray.from_arrays(
            pa.array(bmp.reshape(-1), type=pa.uint8()), width),
    })
    mask_raw = _write_table(mask_tbl, mask_path)

    # P8: the mask artifact EXISTS. A matrix without a bitmap is not a valid artifact.
    if not os.path.exists(mask_path):
        _refuse(REFUSE_MASK_ARTIFACT_ABSENT,
                "the mask bitmap was not written; a matrix without one cannot tell a masked "
                "cell from an unmasked 0.0")

    # P10: write it again and confirm the bytes are the same bytes.
    if _write_table(matrix_tbl, matrix_path + ".probe") != matrix_raw:
        os.remove(matrix_path + ".probe")
        _refuse(REFUSE_WRITE_NOT_DETERMINISTIC,
                "the same table written twice produced different bytes; the artifact cannot "
                "be content-addressed")
    os.remove(matrix_path + ".probe")

    v_sha, b_sha = values_sha256(vals), bits_sha256(bmp)
    descriptor = {
        "schema_version": SCHEMA_VERSION,
        "condition": built["condition"],
        "dtype": DTYPE, "byte_order": BYTE_ORDER,
        "n_targets": built["n_targets"], "n_genes": n_genes,
        "gene_axis_sha256": gene_axis["raw_sha256"],
        "target_ids": built["target_ids"],
        "values_sha256": v_sha,
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "condition": built["condition"],
        "n_targets": built["n_targets"],
        "n_resolved": built["n_resolved"],
        "n_unresolved_no_signature": built["n_unresolved_no_signature"],
        "n_genes": n_genes,
        "bitmap_width_bytes": width,
        "dtype": DTYPE,
        "byte_order": BYTE_ORDER,
        # P12: declared, always. A consumer that does not know the reduction order will
        # eventually vectorise the cosine.
        "reduction_order_id": REDUCTION_ORDER_ID,
        "gene_axis": {"path_in_bundle": os.path.join("..", GENE_AXIS_FILE),
                      "raw_sha256": gene_axis["raw_sha256"],
                      "canonical_sha256": gene_axis["canonical_sha256"],
                      "readout_universe_sha256": readout_universe_sha256},
        "matrix": {"path_in_bundle": MATRIX_FILE, "raw_sha256": matrix_raw,
                   "canonical_sha256": content_hash(descriptor),
                   "values_sha256": v_sha},
        "mask": {"path_in_bundle": MASK_FILE, "raw_sha256": mask_raw,
                 "canonical_sha256": content_hash(
                     dict(descriptor, bits_sha256=b_sha, kind="mask")),
                 "bits_sha256": b_sha},
        "sources": dict(sources),
        "mask_rule_id": MASK_RULE_ID,
        "all_values_finite": built["all_values_finite"],
    }
    path = os.path.join(cond_dir, MANIFEST_FILE)
    with open(path, "w") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write("\n")
    manifest["manifest_sha256"] = file_sha256(path)
    return manifest


def read(manifest: dict[str, Any], cond_dir: str) -> dict[str, Any]:
    """mmap the shipped bytes. Zero-copy: a bundle pages in only the rows it touches."""
    import pyarrow as pa

    def _mmap(name):
        with pa.memory_map(os.path.join(cond_dir, name), "rb") as src:
            return pa.ipc.open_file(src).read_all()

    m = _mmap(manifest["matrix"]["path_in_bundle"])
    k = _mmap(manifest["mask"]["path_in_bundle"])
    n_genes = int(manifest["n_genes"])
    width = int(manifest["bitmap_width_bytes"])

    targets = [str(t) for t in m.column("target_id").to_pylist()]
    values = np.asarray(m.column("values").combine_chunks().flatten(),
                        dtype="<f8").reshape(len(targets), n_genes)
    bitmap = np.asarray(k.column("unmasked_bits").combine_chunks().flatten(),
                        dtype=np.uint8).reshape(len(targets), width)
    if [str(t) for t in k.column("target_id").to_pylist()] != targets:
        _refuse(REFUSE_ROW_ORDER,
                "the mask's row order differs from the matrix's; row i of one must BE row i "
                "of the other, or every mask is applied to the wrong signature")
    return {"target_ids": targets, "values": values, "bitmap": bitmap,
            "n_genes": n_genes}


def reconstruct_signatures(mat: dict[str, Any], gene_ids: list[str],
                           targets) -> dict[str, dict[str, float]]:
    """THE ONLY path a consumer may use. Rebuilds production's exact signature dicts.

    An all-zero bitmap row is NO SIGNATURE and yields NO entry — not an empty dict, which a
    caller could mistake for "measured, nothing survived the mask".

    This exists so ``convergence.cosine_on_shared`` runs UNCHANGED, folding left over
    ``sorted(shared)`` exactly as production does. A numpy reduction over the dense matrix
    would produce the same values in a different summation order — ~5e-07 apart — and
    `supportive` is a threshold at 0.5. W7 proved this path bitwise over 1,770 real pairs:
    0 mismatches, max diff 0.0.
    """
    index = {t: i for i, t in enumerate(mat["target_ids"])}
    n_genes = mat["n_genes"]
    out: dict[str, dict[str, float]] = {}

    for t in targets:
        i = index.get(str(t))
        if i is None:
            continue
        bits = np.unpackbits(mat["bitmap"][i])[:n_genes]
        if not bits.any():
            continue                      # all-zero row -> NO SIGNATURE. Not an empty one.
        row = mat["values"][i]
        out[str(t)] = {gene_ids[j]: float(row[j])
                       for j in np.nonzero(bits)[0]}
    return out


def signature_ref(*, manifest: dict[str, Any], condition: str, source: str,
                  member_target_ids: list[str]) -> dict[str, Any]:
    """The bundle's TINY reference. It ships NO signature bytes of its own (P11)."""
    return {
        "schema_version": REF_SCHEMA_VERSION,
        "condition": condition,
        "source": source,
        "signature_manifest_sha256": manifest.get("manifest_sha256"),
        "matrix_raw_sha256": manifest["matrix"]["raw_sha256"],
        "matrix_canonical_sha256": manifest["matrix"]["canonical_sha256"],
        "matrix_values_sha256": manifest["matrix"]["values_sha256"],
        "mask_raw_sha256": manifest["mask"]["raw_sha256"],
        "mask_canonical_sha256": manifest["mask"]["canonical_sha256"],
        "mask_bits_sha256": manifest["mask"]["bits_sha256"],
        "gene_axis_raw_sha256": manifest["gene_axis"]["raw_sha256"],
        "reduction_order_id": manifest["reduction_order_id"],
        "member_target_ids": sorted(str(t) for t in member_target_ids),
        "n_member_targets": len(set(str(t) for t in member_target_ids)),
        "member_rule_id": MEMBER_RULE_ID,
        # P11. The 29.5 GiB peak came back the moment a bundle kept its own copy
        # "for compatibility".
        "ships_signature_bytes": False,
    }


# --------------------------------------------------------------------------- #
# STEP 0: emit the shared artifacts ONCE, before any pathway bundle.
# --------------------------------------------------------------------------- #
def mask_sets_for_condition(args, cond: str, main: dict[str, Any]) -> dict[str, Optional[set]]:
    """Masks, DERIVED by ``masks.build_estimate_mask`` from the contributor manifest and the
    sgRNA library (P2). There is no ad-hoc mask here and no default-empty one: a target whose
    mask cannot be derived gets ``None``, which means NO SIGNATURE, not "nothing masked".
    """
    from . import domain

    identity_map = identity.load_identity_map(getattr(args, "target_identity_map", None))
    raw = io_data.load_main_identity_universe(args.de_main)
    identities_by_condition = {
        c: {t: identity.resolve(r["released_estimate_id"], r["target_id"],
                                r["target_symbol"], identity_map)
            for t, r in targets.items()}
        for c, targets in raw.items()
    }
    if cond not in identities_by_condition:
        _refuse(REFUSE_INPUT_PIN_MISMATCH,
                f"the release ships no pooled-main estimate for condition {cond!r}")
    identities = identities_by_condition[cond]

    source_registry = io_data.load_source_registry(getattr(args, "source_registry", None))
    manifest_doc = mf.load(
        args.guide_manifest, domain.global_pooled_main_scopes(identities_by_condition),
        source_registry,
        base_dir=os.path.dirname(os.path.abspath(args.source_registry))
        if getattr(args, "source_registry", None) else "")
    manifest_index = (guides.build_manifest_index(manifest_doc["rows"])
                      if manifest_doc is not None else None)
    library = guides.build_library(io_data.load_sgrna_rows_by_target(args.sgrna))

    meta = main["meta"]
    out: dict[str, Optional[set]] = {}
    for i, target in enumerate(str(t) for t in meta["target_id"]):
        ident = identities[target]
        est = guides.Estimate(
            estimate_type=guides.MAIN, estimate_id="main",
            released_estimate_id=ident.released_estimate_id,
            target_id=target, target_ensembl=ident.target_ensembl,
            condition=cond,
            n_guides=_f(meta["n_guides"][i]), n_cells=_f(meta["n_cells_target"][i]),
            target_id_namespace=ident.target_id_namespace,
            target_symbol=ident.target_symbol,
            released_target_ensembl=ident.released_target_ensembl)
        contrib = guides.resolve(est, library, manifest_index)
        m = masks.build_estimate_mask(est, contrib, library.get(ident.target_ensembl))
        out[target] = m["gene_set"]          # None when UNRESOLVED
    return out


def _f(v):
    if v is None:
        return None
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return None
    return None if fv != fv else fv


def build_condition(args, cond: str, out_root: str) -> dict[str, Any]:
    """ONE condition's shared artifacts. Infrastructure — NOT a bundle, not completeness-bearing."""
    main = io_data.load_main(args.de_main, cond)
    gene_ids = [str(g) for g in main["gene_ids"]]

    mask_sets = mask_sets_for_condition(args, cond, main)
    built = build(condition=cond, main=main, mask_sets=mask_sets, gene_ids=gene_ids)

    axis = write_gene_axis(out_root, gene_ids)
    return write(built, out_root=out_root, gene_axis=axis,
                 sources={
                     "de_main_sha256": file_sha256(args.de_main),
                     "guide_manifest_sha256": (file_sha256(args.guide_manifest)
                                               if args.guide_manifest else None),
                     "sgrna_sha256": file_sha256(args.sgrna) if args.sgrna else None,
                 },
                 readout_universe_sha256=content_hash(gene_ids))


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="python -m direct.signature_matrix",
        description="STEP 0: emit ONE condition's shared signature matrix + mandatory mask "
                    "bitmap. Infrastructure, not a bundle — it is not completeness-bearing "
                    "and does not count toward the 15.")
    ap.add_argument("--condition", required=True)
    ap.add_argument("--de-main", required=True)
    ap.add_argument("--sgrna", required=True)
    ap.add_argument("--guide-manifest", default=None)
    ap.add_argument("--source-registry", default=None)
    ap.add_argument("--target-identity-map", default=None)
    ap.add_argument("--env-lock", default=None)
    ap.add_argument("--out-root", required=True)
    return ap


def main(argv=None) -> dict[str, Any]:
    args = build_parser().parse_args(argv)
    m = build_condition(args, args.condition, args.out_root)
    print(json.dumps({
        "condition": m["condition"],
        "n_targets": m["n_targets"],
        "n_resolved": m["n_resolved"],
        "n_unresolved_no_signature": m["n_unresolved_no_signature"],
        "n_genes": m["n_genes"],
        "matrix_raw_sha256": m["matrix"]["raw_sha256"],
        "matrix_values_sha256": m["matrix"]["values_sha256"],
        "mask_bits_sha256": m["mask"]["bits_sha256"],
        "reduction_order_id": m["reduction_order_id"],
        "all_values_finite": m["all_values_finite"],
    }, indent=2))
    return m


if __name__ == "__main__":
    main()
