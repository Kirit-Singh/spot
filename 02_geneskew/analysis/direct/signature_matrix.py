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
QC_FILE = "signature_qc.parquet"
QC_KEY = "qc"
# The per-target QC a consumer needs to know WHICH targets are evaluable. The matrix carries
# the masked vectors; without these it carries no way to tell a target Direct refused from one
# it scored, and a consumer would either re-derive them (a SECOND source of truth for the same
# facts, free to disagree) or quietly project everything.
QC_COLUMNS = ("target_id", "base_state", "base_passed", "mask_resolved",
              "target_identity_resolved", "n_cells", "n_guides",
              "low_target_gex", "ontarget_significant")
REF_FILE = "signature_ref.json"

DTYPE = "float64"
BYTE_ORDER = "little_endian"

# The reduction order production folds in. Recorded in every manifest, and the reason
# reconstruct_signatures exists at all.
REDUCTION_ORDER_ID = "spot.stage02.convergence.reduction.sorted_gene_left_fold.v1"
MASK_RULE_ID = "spot.stage02.direct.mask.build_estimate_mask.v1"
MEMBER_RULE_ID = "spot.stage02.pathway.members.genes_target_intersect_resolved.v1"

# THE BITMAP RULE, amended after W7's production-size Step 0 (P5/V5/A5).
#
# The original gate asserted that a RESOLVED row can never be all-ones, on the reasoning that
# build_estimate_mask always masks the target's own gene. That reasoning is right about the
# BIOLOGICAL mask and wrong about the BITMAP, and the difference is a whole gene universe:
#
#   the mask is derived in the TARGET universe   (11,526 perturbed genes)
#   the bitmap is written over the READOUT axis  (10,282 measured genes)
#
# 1,217-1,243 resolved targets per condition have a perfectly good non-empty mask — the target,
# its 30kb neighbours, its contributing guides' off-targets — NONE of which is a readout gene.
# Their mask INTERSECTED WITH THE AXIS is empty, so no readout gene is masked, so the row is
# legitimately all-ones. The old gate called that a producer bug and refused ~11% of every
# condition.
#
# The rule that is actually true, and is what is enforced now:
#
#   the bitmap's ZERO bits == (source mask INTERSECT readout axis), EXACTLY.
#
# Everything else follows from it. An empty intersection means a valid all-ones row, and it
# carries an explicit disposition and the binding of its NON-EMPTY source mask, so "no readout
# gene was masked" can never be confused with "no mask was derived". A NON-empty intersection
# with an all-ones row is still a refusal — that one really is a bug.
BITMAP_RULE_ID = "spot.stage02.signature.bitmap_zeros_are_the_mask_axis_intersection.v2"
BITMAP_RULE = (
    "a bitmap zero bit means the readout gene is IN (source mask INTERSECT readout axis); the "
    "zeros equal that intersection exactly. An all-zero row means UNRESOLVED / no signature. "
    "An all-ones row is VALID iff the intersection is empty while the source mask is not — the "
    "mask lives in the 11,526-gene target universe and the axis is the 10,282-gene readout "
    "universe, so a real mask can miss the axis entirely")

# --------------------------------------------------------------------------- #
# THE CROSS-LANE ANCHOR. Without it, everything this module checks is self-consistency.
#
# The bitmap, the counts and source_mask_sha256 are all derived from the SAME mask_sets. So a
# forged-but-plausible biological mask, resealed, satisfies every one of them: the zeros still
# equal the (forged) mask INTERSECT axis, the counts still agree, the run id still re-derives.
# Demonstrated, not assumed — the forgery ADMITTED.
#
# A mask can only be contradicted from OUTSIDE. The Direct lane's mask table is independently
# re-derived by W10 from the contributor manifest and the sgRNA library, under the exact
# target + 30kb-neighbour + contributing-guide off-target rule, and its canonical table is
# shuffle-invariant (DIRECT_MASK_VERIFICATION_REPORT.md, 48ff889b). So the pathway lane's mask
# is checked AGAINST THE SHIPPED DIRECT BYTES: same masks, or nothing ships.
#
# The comparison is a DERIVATION, not a hash equality — the two lanes canonicalize the same
# fact differently (Direct: a row table over 14 identity columns; here: per-target gene sets).
# Project the Direct rows to {target: masked genes}, intersect with the READOUT AXIS, and
# compare to this bitmap's ZERO bits. Intersecting first is load-bearing: 1,217-1,243 resolved
# targets per condition have a real mask that misses the axis entirely, and comparing before
# the intersection would fire on honest output.
# --------------------------------------------------------------------------- #
ANCHOR_RULE_ID = "spot.stage02.signature.mask_anchored_to_independently_verified_direct.v1"
ANCHOR_RULE = (
    "the bitmap's zero bits per target equal the SHIPPED Direct mask table, projected to "
    "{target: masked genes} and intersected with the readout axis; the Direct table is the one "
    "an independent verifier re-derived from the contributor manifest and the sgRNA library")
MAIN_ESTIMATE_TYPE = "main"

DISPOSITION_UNRESOLVED = "unresolved_no_signature"
DISPOSITION_MASKED_READOUT = "resolved_masked_readout_genes"
DISPOSITION_NO_MASKED_READOUT = "resolved_no_masked_readout_gene"

# ---- P-gates. Every one a refusal; none a warning. ----
REFUSE_INPUT_PIN_MISMATCH = "REFUSE_INPUT_PIN_MISMATCH"
REFUSE_MASK_NOT_DERIVED = "REFUSE_MASK_NOT_DERIVED"
REFUSE_GENE_AXIS_MISMATCH = "REFUSE_GENE_AXIS_MISMATCH"
REFUSE_ROW_ORDER = "REFUSE_ROW_ORDER"
REFUSE_RESOLVED_ROW_UNMASKED = "REFUSE_RESOLVED_ROW_UNMASKED"
REFUSE_BITMAP_NOT_MASK_INTERSECTION = "REFUSE_BITMAP_NOT_MASK_INTERSECTION"
REFUSE_RESOLVED_SOURCE_MASK_EMPTY = "REFUSE_RESOLVED_SOURCE_MASK_EMPTY"
REFUSE_MANIFEST_IDENTITY_ABSENT = "REFUSE_MANIFEST_IDENTITY_ABSENT"
REFUSE_DIRECT_MASK_ANCHOR_ABSENT = "REFUSE_DIRECT_MASK_ANCHOR_ABSENT"
REFUSE_DIRECT_MASK_MISMATCH = "REFUSE_DIRECT_MASK_MISMATCH"
REFUSE_W10_REPORT_IS_ABOUT_ANOTHER_BUNDLE = "REFUSE_W10_REPORT_IS_ABOUT_ANOTHER_BUNDLE"
REFUSE_STALE_SIGNATURE_SOURCE = "signature_artifact_was_built_from_another_de_source"
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
    axis_set = set(gene_ids)

    # ---- P5 (AMENDED): the bitmap's ZEROS ARE the mask-axis intersection, exactly. ----
    dispositions: dict[str, str] = {}
    source_mask: dict[str, list[str]] = {}
    n_masked_readout: dict[str, int] = {}
    n_masked_source: dict[str, int] = {}
    no_masked_readout: list[str] = []

    for i, t in enumerate(targets):
        ms = mask_sets[t]
        if ms is None:
            dispositions[t] = DISPOSITION_UNRESOLVED
            continue

        # A resolved target's SOURCE mask is never empty — build_estimate_mask always masks
        # the target itself. An empty one means no mask was derived, and that is not the same
        # thing as a mask that misses the readout axis.
        if not ms:
            _refuse(REFUSE_RESOLVED_SOURCE_MASK_EMPTY,
                    f"resolved target {t!r} has an EMPTY source mask. build_estimate_mask "
                    "always masks the intended target — its own repression is QC, never skew "
                    "evidence — so an empty source mask means the mask was not derived")

        inter = sorted(set(map(str, ms)) & axis_set)
        zeros = {gene_ids[j] for j in np.nonzero(~bits[i])[0]}
        # THE RULE. Everything else is a consequence of it.
        if zeros != set(inter):
            _refuse(REFUSE_BITMAP_NOT_MASK_INTERSECTION,
                    f"target {t!r}: the bitmap's zero bits are not the mask-axis "
                    f"intersection ({len(zeros)} zeros vs {len(inter)} intersected genes). "
                    "A bitmap that does not say exactly which readout genes were masked is "
                    "not a mask")

        source_mask[t] = sorted(str(g) for g in ms)
        n_masked_source[t] = len(ms)
        n_masked_readout[t] = len(inter)
        if inter:
            dispositions[t] = DISPOSITION_MASKED_READOUT
        else:
            # VALID, and it must say so out loud: a real, non-empty mask that simply does not
            # touch the readout axis. Silence here would read as "nothing was masked".
            dispositions[t] = DISPOSITION_NO_MASKED_READOUT
            no_masked_readout.append(t)

    # RECOUNTED FROM THE BITMAP, not from the dispositions: two independent statements of the
    # same fact, so a drift between them can surface. A resolved row is all-ones iff its mask
    # missed the readout axis entirely, so these two counts MUST agree — and if they ever do
    # not, one of them is lying and the artifact does not ship.
    n_resolved_all_ones = int(sum(1 for i in range(len(targets))
                                  if resolved[i] and popcount[i] == n_genes))
    if n_resolved_all_ones != len(no_masked_readout):
        _refuse(REFUSE_BITMAP_NOT_MASK_INTERSECTION,
                f"{n_resolved_all_ones} resolved rows are all-ones in the BITMAP but "
                f"{len(no_masked_readout)} targets have an empty mask-axis intersection. A "
                "resolved row is all-ones exactly when its mask misses the axis; these two "
                "counts cannot disagree")

    # An all-ones row is a REFUSAL only when the intersection is NOT empty — that one is a bug.
    bad = [t for i, t in enumerate(targets)
           if resolved[i] and popcount[i] == n_genes and n_masked_readout.get(t, 0) > 0]
    if bad:
        _refuse(REFUSE_RESOLVED_ROW_UNMASKED,
                f"{len(bad)} resolved target(s) (e.g. {bad[:3]}) mask readout genes and yet "
                "their bitmap masks none. A row that claims to mask nothing while its mask "
                "intersects the axis has lost its mask")

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
        # THE AMENDED DISPOSITION. A resolved target whose non-empty mask does not touch the
        # readout axis is a legitimate all-ones row, and it is COUNTED and NAMED rather than
        # refused — W7 measured 1,217-1,243 of them per condition.
        "n_resolved_no_masked_readout_gene": len(no_masked_readout),
        "n_resolved_masked_readout_genes": int(resolved.sum()) - len(no_masked_readout),
        # the same fact, RECOUNTED from the bitmap itself
        "n_resolved_all_ones": n_resolved_all_ones,
        "resolved_no_masked_readout_gene_target_ids": sorted(no_masked_readout),
        "dispositions": dispositions,
        "source_mask_sha256": content_hash(source_mask),
        "n_masked_source": n_masked_source,
        "n_masked_readout": n_masked_readout,
        "all_values_finite": all_finite,
        "popcount": popcount,
    }


def direct_masked_genes(masks_parquet: str) -> dict[str, set]:
    """The SHIPPED Direct mask table, projected to {target: masked genes}.

    Only the POOLED-MAIN estimate's rows project into a signature bitmap. The guide and donor
    rows describe estimates nothing here projects, and folding them in would make every target
    look over-masked.
    """
    import pandas as pd

    df = pd.read_parquet(masks_parquet)
    if "estimate_type" in df.columns:
        df = df[df["estimate_type"] == MAIN_ESTIMATE_TYPE]
    out: dict[str, set] = {}
    for t, g in zip(df["target_id"], df["masked_gene_ensembl"]):
        if g is None or (isinstance(g, float) and g != g):
            out.setdefault(str(t), set())          # an UNRESOLVED mask row: no masked gene
            continue
        out.setdefault(str(t), set()).add(str(g))
    return out


def anchor_to_direct(built: dict[str, Any], gene_ids: list[str],
                     direct_masked: dict[str, set]) -> dict[str, Any]:
    """REFUSE unless this lane's mask IS the independently-verified Direct mask.

    The one check in this module that a forged mask cannot satisfy by being consistent with
    itself, because the thing it is compared to was derived by somebody else from the primary
    inputs.
    """
    axis = set(gene_ids)
    n_genes = built["n_genes"]
    bits = np.unpackbits(built["bitmap"], axis=1)[:, :n_genes]

    mismatched: list[str] = []
    checked = 0
    for i, t in enumerate(built["target_ids"]):
        if built["dispositions"][t] == DISPOSITION_UNRESOLVED:
            continue                     # no signature; the Direct table has no mask to compare
        if t not in direct_masked:
            mismatched.append(f"{t}: absent from the Direct mask table")
            continue
        zeros = {gene_ids[j] for j in np.nonzero(bits[i] == 0)[0]}
        expect = direct_masked[t] & axis          # INTERSECT FIRST. See ANCHOR_RULE.
        if zeros != expect:
            mismatched.append(
                f"{t}: {len(zeros)} masked readout genes here, {len(expect)} in the "
                "independently-verified Direct table")
        checked += 1

    if mismatched:
        _refuse(REFUSE_DIRECT_MASK_MISMATCH,
                f"{len(mismatched)} target(s) are masked differently from the Direct table an "
                f"independent verifier re-derived (e.g. {mismatched[:3]}). A mask that only "
                "agrees with itself is not evidence: this artifact and the Direct bundle claim "
                "to have masked the same experiment")

    return {
        "anchor_rule_id": ANCHOR_RULE_ID,
        "anchor_rule": ANCHOR_RULE,
        "n_targets_anchored": checked,
        "masked_readout_sha256": content_hash({
            t: sorted({gene_ids[j] for j in np.nonzero(bits[i] == 0)[0]})
            for i, t in enumerate(built["target_ids"])
            if built["dispositions"][t] != DISPOSITION_UNRESOLVED}),
    }


REFUSE_W10_NOT_ADMITTED = "the_w10_report_is_not_a_full_admission"
REFUSE_W10_MASK_GATE_ABSENT = "the_w10_report_does_not_carry_the_named_mask_rederivation_gates"

# The NAMED gates W10 must have passed before this lane may read a mask hash out of a Direct
# bundle. A report that admitted the bundle WITHOUT re-deriving its mask has admitted the arms,
# not the mask — and the mask is the only thing this lane is anchoring to.
REQUIRED_W10_MASK_GATES = (
    "the MASK's identity is bound into the run and RE-DERIVES from the shipped mask",
    "every SHIPPED mask is the one the verifier independently derives from the cont",
)


def w10_anchor(report_path: str, direct_bundle_dir: str) -> dict[str, Any]:
    """Bind the PER-RUN W10 report over the ACTUAL Direct bundle. TYPED JSON — never prose.

    The first cut of this REGEXED a line out of a markdown report:

        bound mask_sha256           : 269b4278...

    W10's real, final report is TYPED JSON and has no such line. Scraping prose for a hash is a
    parser that works until somebody reformats a sentence — and the correct response to "the
    line is missing" is emphatically NOT to manufacture the line. So the report is now READ as
    the typed document it is.

    THE ORDER MATTERS, and it is the whole point:

      1. the report must be a FULL ADMISSION (verdict ADMIT, zero failed gates);
      2. it must be bound to THIS bundle — by `bound_artifact.arm_bundle_run_id` AND by the
         `artifact_sha256["provenance.json"]` of the very file we are about to read. A green
         report about another bundle, or about a different copy of this one, is not a check of
         the bytes in front of us;
      3. it must carry the NAMED mask re-derivation gates, PASSED. A report that admitted the
         bundle without independently re-deriving its mask has admitted the arms, not the mask;
      4. ONLY THEN is `mask_sha256` read out of the bundle's own provenance.

    Reading the mask hash first and checking the report afterwards would be the same mistake in
    a different order: the hash would already be in hand, and the check would be a formality.
    """
    if not os.path.exists(report_path):
        _refuse(REFUSE_DIRECT_MASK_ANCHOR_ABSENT,
                f"no W10 Direct mask report at {os.path.basename(report_path)!r}. The pathway "
                "mask is self-consistent by construction; without an external re-derivation to "
                "contradict it, a coherently forged mask is indistinguishable from a real one")
    with open(report_path) as fh:
        try:
            report = json.load(fh)
        except json.JSONDecodeError:
            _refuse(REFUSE_DIRECT_MASK_ANCHOR_ABSENT,
                    f"{os.path.basename(report_path)!r} is not a typed W10 JSON report. The "
                    "prose-scraping parser this replaced is exactly the bug: a hash lifted out "
                    "of a sentence is a hash nobody bound")

    # ---- 1. a FULL admission ----
    verdict = str(report.get("verdict", "")).upper()
    n_failed = report.get("n_failed", 1)
    if verdict != "ADMIT" or n_failed != 0:
        _refuse(REFUSE_W10_NOT_ADMITTED,
                f"the W10 report is verdict={verdict!r} n_failed={n_failed}. A pathway mask may "
                "only be anchored to a Direct bundle an independent verifier ADMITTED; a "
                "refusal, or an admission that contradicts its own gates, is not one")

    bound = report.get("bound_artifact") or {}
    art = bound.get("artifact_sha256") or {}

    # ---- 2. bound to THIS bundle, and to THIS provenance file ----
    run_id = os.path.basename(direct_bundle_dir.rstrip("/"))
    if bound.get("arm_bundle_run_id") != run_id:
        _refuse(REFUSE_W10_REPORT_IS_ABOUT_ANOTHER_BUNDLE,
                f"the W10 report admits bundle {bound.get('arm_bundle_run_id')!r}, but this "
                f"anchor is for {run_id!r}. A green report about another run is not a "
                "verification of this one")

    prov_path = os.path.join(direct_bundle_dir, "provenance.json")
    if not os.path.exists(prov_path):
        _refuse(REFUSE_DIRECT_MASK_ANCHOR_ABSENT,
                f"no Direct bundle provenance at {prov_path!r}")
    prov_raw = file_sha256(prov_path)
    admitted_prov = art.get("provenance.json")
    if admitted_prov != prov_raw:
        _refuse(REFUSE_W10_REPORT_IS_ABOUT_ANOTHER_BUNDLE,
                f"W10 admitted provenance.json {str(admitted_prov)[:16]}..., but the file on "
                f"disk hashes to {prov_raw[:16]}.... The report admitted DIFFERENT BYTES than "
                "the ones this run is about to read")

    # ---- 3. the NAMED mask re-derivation gates, PASSED ----
    gates = {str(g.get("gate", "")): bool(g.get("passed")) for g in (report.get("gates") or [])}
    missing = []
    for needle in REQUIRED_W10_MASK_GATES:
        hit = [name for name in gates if needle in name]
        if not hit or not all(gates[h] for h in hit):
            missing.append(needle)
    if missing:
        _refuse(REFUSE_W10_MASK_GATE_ABSENT,
                f"the W10 report does not carry a PASSED mask re-derivation gate for "
                f"{missing}. It may have admitted the ARMS; this lane is anchoring to the MASK, "
                "and a report that never re-derived the mask cannot contradict a forged one")

    # ---- 4. ONLY NOW read the mask hash out of the ADMITTED provenance ----
    with open(prov_path) as fh:
        direct_prov = json.load(fh)
    binding = direct_prov["run_binding"]
    bundle_mask = binding.get("mask_sha256")
    if not bundle_mask:
        _refuse(REFUSE_DIRECT_MASK_ANCHOR_ABSENT,
                "the admitted Direct provenance carries no mask_sha256")

    return {
        # WHO checked, and with what. Stable identity, whatever the run.
        "verifier_id": report.get("verifier_id"),
        "verifier_code_sha256": report.get("verifier_code_sha256"),
        "gate_inventory_sha256": report.get("gate_inventory_sha256"),
        # WHAT was checked. PER-RUN, read from the bytes in front of us.
        "report_sha256": file_sha256(report_path),
        "report_verdict": verdict,
        "report_n_passed": report.get("n_passed"),
        "report_n_gates": report.get("n_gates"),
        "direct_mask_sha256": bundle_mask,
        "direct_arm_bundle_run_id": run_id,
        "direct_provenance_raw_sha256": prov_raw,
        "direct_masks_parquet_sha256": file_sha256(
            os.path.join(direct_bundle_dir, "masks.parquet")),
        "direct_contributor_manifest": binding.get("contributor_manifest"),
        "direct_stage1_release_kind":
            (binding.get("arm_bundle_request") or {}).get("stage1_release_kind"),
        "direct_stage1_release_hashes":
            (binding.get("arm_bundle_request") or {}).get("stage1_release_hashes"),
        "attests_real_60_arm_release": False,
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

    # THE PER-TARGET QC. Without it the matrix says what every target's masked vector IS and
    # nothing about which targets may be USED — so a consumer projects the ones Direct refused.
    from . import emit as _emit
    qc_rows = built.get("qc_rows") or []
    qc_path = os.path.join(cond_dir, QC_FILE)
    _emit.write_parquet(qc_rows, qc_path, ["target_id"])

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
        # AMENDED (P5/V5/A5). A resolved target whose non-empty mask does not intersect the
        # readout axis has a legitimately all-ones row. W7 measured 1,217-1,243 per condition.
        # Named and counted, never silent: "no readout gene was masked" and "no mask was
        # derived" are different states and must not print the same.
        "bitmap_rule_id": BITMAP_RULE_ID,
        "bitmap_rule": BITMAP_RULE,
        "n_resolved_masked_readout_genes": built["n_resolved_masked_readout_genes"],
        "n_resolved_no_masked_readout_gene": built["n_resolved_no_masked_readout_gene"],
        # FIRST-CLASS, and recounted from the bitmap rather than restated from the
        # disposition. W4 recomputes it as #{resolved rows with popcount == n_genes}.
        "n_resolved_all_ones": built["n_resolved_all_ones"],
        "resolved_no_masked_readout_gene_target_ids":
            built["resolved_no_masked_readout_gene_target_ids"],
        # THE NON-EMPTY SOURCE MASK, bound. It is what proves an all-ones row had a real mask
        # that simply missed the axis — rather than no mask at all.
        "source_mask_sha256": built["source_mask_sha256"],
        "dispositions": {
            "unresolved_no_signature": DISPOSITION_UNRESOLVED,
            "resolved_masked_readout_genes": DISPOSITION_MASKED_READOUT,
            "resolved_no_masked_readout_gene": DISPOSITION_NO_MASKED_READOUT,
        },
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
        QC_KEY: {"path_in_bundle": QC_FILE,
                 "columns": list(QC_COLUMNS),
                 "raw_sha256": file_sha256(qc_path),
                 "canonical_sha256": content_hash(qc_rows),
                 "n_rows": len(qc_rows),
                 "n_base_passed": sum(1 for r in qc_rows if r["base_passed"])},
        "mask": {"path_in_bundle": MASK_FILE, "raw_sha256": mask_raw,
                 "canonical_sha256": content_hash(
                     dict(descriptor, bits_sha256=b_sha, kind="mask")),
                 "bits_sha256": b_sha},
        "sources": dict(sources),
        "environment_lock": sources.get("environment_lock"),
        "mask_rule_id": MASK_RULE_ID,
        # WHOSE independent re-derivation this mask was checked against, and over WHICH Direct
        # bundle. Absent means UNANCHORED, and absent says so — it is not defaulted to a green.
        "direct_mask_anchor": built.get("direct_mask_anchor"),
        "mask_is_externally_anchored": built.get("direct_mask_anchor") is not None,
        "all_values_finite": built["all_values_finite"],
    }
    # The manifest's CONTENT hash goes INSIDE the manifest, so the shipped file carries its own
    # canonical identity and a consumer that reloads it can bind a non-null hash. (The RAW hash
    # of the file cannot live inside the file; it is recomputed from the bytes on read.)
    manifest["manifest_canonical_sha256"] = content_hash(manifest)
    path = os.path.join(cond_dir, MANIFEST_FILE)
    with open(path, "w") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write("\n")
    manifest["manifest_sha256"] = file_sha256(path)
    return manifest


def load_manifest(cond_dir: str) -> dict[str, Any]:
    """Load a shipped manifest AND its non-null identity. The raw hash is of the BYTES."""
    path = os.path.join(cond_dir, MANIFEST_FILE)
    with open(path) as fh:
        doc = json.load(fh)
    doc["manifest_sha256"] = file_sha256(path)
    if not doc.get("manifest_canonical_sha256"):
        _refuse(REFUSE_MANIFEST_IDENTITY_ABSENT,
                f"the shipped manifest at {MANIFEST_FILE!r} carries no "
                "manifest_canonical_sha256; it cannot be bound by content")
    return doc


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
                  member_target_ids: list[str],
                  manifest_raw_sha256: Optional[str] = None,
                  manifest_canonical_sha256: Optional[str] = None) -> dict[str, Any]:
    """The bundle's TINY reference. It ships NO signature bytes of its own (P11).

    THE MANIFEST IDENTITY IS MANDATORY AND NON-NULL. It was silently None: ``write()`` adds
    ``manifest_sha256`` to the dict AFTER dumping the JSON, so the manifest ON DISK never
    carries it, and a consumer that reloads the shipped file got ``None`` from ``.get()``.

    A null manifest hash is not a cosmetic gap. It is the one binding that says WHICH shared
    matrix this bundle is entitled to read, and without it Rest's matrix can be served as
    Stim8hr's — the schemas are identical, so nothing else would notice. So it is refused,
    not defaulted: a reference that cannot name the artifact it references is not a reference.
    """
    raw = manifest_raw_sha256 or manifest.get("manifest_sha256")
    canonical = manifest_canonical_sha256 or manifest.get("manifest_canonical_sha256")
    if not raw or not canonical:
        _refuse(REFUSE_MANIFEST_IDENTITY_ABSENT,
                f"signature_ref for {condition!r}/{source!r} has no manifest identity "
                f"(raw={raw!r}, canonical={canonical!r}). Without it, another condition's "
                "matrix can be substituted for this one and the schemas would agree")
    return {
        "schema_version": REF_SCHEMA_VERSION,
        "condition": condition,
        "source": source,
        # THE EXACT shared manifest this bundle is bound to. Never null.
        "signature_manifest_sha256": raw,
        "signature_manifest_raw_sha256": raw,
        "signature_manifest_canonical_sha256": canonical,
        "matrix_raw_sha256": manifest["matrix"]["raw_sha256"],
        "matrix_canonical_sha256": manifest["matrix"]["canonical_sha256"],
        "matrix_values_sha256": manifest["matrix"]["values_sha256"],
        "mask_raw_sha256": manifest["mask"]["raw_sha256"],
        "mask_canonical_sha256": manifest["mask"]["canonical_sha256"],
        "mask_bits_sha256": manifest["mask"]["bits_sha256"],
        "gene_axis_raw_sha256": manifest["gene_axis"]["raw_sha256"],
        "reduction_order_id": manifest["reduction_order_id"],
        # THE AMENDED BITMAP COUNTS, carried INTO the bundle's run identity — not merely
        # covered by the manifest hash. W4 recounts each from the shipped bitmap:
        #   n_unresolved_no_signature      = #{rows with popcount == 0}
        #   n_resolved_all_ones            = #{resolved rows with popcount == n_genes}
        #   n_resolved_no_masked_readout_gene = #{resolved targets whose mask misses the axis}
        # The last two are independent statements of one fact and must agree.
        "bitmap_rule_id": manifest["bitmap_rule_id"],
        # THE CROSS-LANE ANCHOR, carried into the bundle's run identity. `False` here is a
        # STATE, not a gap: an unanchored mask is self-consistent and nothing more, and the
        # bundle says so rather than leaving a reader to assume it was checked.
        "mask_is_externally_anchored": manifest["mask_is_externally_anchored"],
        "direct_mask_anchor": manifest["direct_mask_anchor"],
        "n_unresolved_no_signature": manifest["n_unresolved_no_signature"],
        "n_resolved_all_ones": manifest["n_resolved_all_ones"],
        "n_resolved_no_masked_readout_gene":
            manifest["n_resolved_no_masked_readout_gene"],
        "n_resolved_masked_readout_genes": manifest["n_resolved_masked_readout_genes"],
        "source_mask_sha256": manifest["source_mask_sha256"],
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
def scan_condition(args, cond: str, main: dict[str, Any]) -> dict[str, Any]:
    """The masks AND the per-target QC, from ONE pass over the same inputs.

    They must come from the same scan. A consumer that took the mask from here and the QC from
    its own re-derivation would hold two statements about one target that are free to disagree,
    and nothing would notice which one it acted on.
    """
    from . import disposition

    mask_sets = mask_sets_for_condition(args, cond, main)
    identity_map = identity.load_identity_map(getattr(args, "target_identity_map", None))
    raw = io_data.load_main_identity_universe(args.de_main)
    identities = {
        t: identity.resolve(r["released_estimate_id"], r["target_id"],
                            r["target_symbol"], identity_map)
        for t, r in raw[cond].items()
    }
    meta = main["meta"]
    qc_rows = []
    for i, target in enumerate(str(t) for t in meta["target_id"]):
        ident = identities[target]
        n_guides = _f(meta["n_guides"][i])
        n_cells = _f(meta["n_cells_target"][i])
        resolved = mask_sets[target] is not None
        low = _b(meta["low_target_gex"][i])
        sig = _b(meta["ontarget_significant"][i])
        state, passed, _reasons = disposition.base_qc(
            row_present=True, mask_resolved=resolved, n_cells=n_cells,
            low_target_gex=low, ontarget_significant=sig, n_guides=n_guides,
            target_identity_resolved=ident.ensembl_resolved)
        qc_rows.append({
            "target_id": target,
            "base_state": state,
            "base_passed": bool(passed),
            "mask_resolved": bool(resolved),
            "target_identity_resolved": bool(ident.ensembl_resolved),
            "n_cells": n_cells,
            "n_guides": n_guides,
            "low_target_gex": low,
            "ontarget_significant": sig,
        })
    qc_rows.sort(key=lambda r: r["target_id"].encode("utf-8"))
    return {"mask_sets": mask_sets, "qc_rows": qc_rows}


def _b(v):
    return None if v is None else bool(v)


def check_not_stale(manifest: dict[str, Any], de_main_sha256: str) -> None:
    """The artifact must have been built from THE SAME DE source the consumer is bound to.

    A stale signature root is the quietest failure available here: the schemas match, the hashes
    are internally consistent, the vectors load — and they are last week's numbers.
    """
    built_from = (manifest.get("sources") or {}).get("de_main_sha256")
    if built_from != de_main_sha256:
        _refuse(REFUSE_STALE_SIGNATURE_SOURCE,
                f"this signature artifact was built from DE source {str(built_from)[:16]}..., "
                f"but the run is bound to {de_main_sha256[:16]}.... The vectors would load and "
                "the hashes would agree with themselves; they would simply be another run's "
                "numbers")


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

    scanned = scan_condition(args, cond, main)
    mask_sets, qc_rows = scanned["mask_sets"], scanned["qc_rows"]
    built = build(condition=cond, main=main, mask_sets=mask_sets, gene_ids=gene_ids)
    built["qc_rows"] = qc_rows

    # THE CROSS-LANE ANCHOR. Everything above is self-consistency; this is the only check a
    # coherently forged mask cannot satisfy, because it is compared to a table somebody else
    # derived from the primary inputs.
    bundle_dir = getattr(args, "direct_bundle", None)
    report = getattr(args, "direct_mask_report", None)
    if bundle_dir and report:
        anchor = w10_anchor(report, bundle_dir)
        anchor.update(anchor_to_direct(
            built, gene_ids,
            direct_masked_genes(os.path.join(bundle_dir, "masks.parquet"))))
        built["direct_mask_anchor"] = anchor
    elif bundle_dir or report:
        _refuse(REFUSE_DIRECT_MASK_ANCHOR_ABSENT,
                "--direct-bundle and --direct-mask-report go together: a bundle with no report "
                "is unverified, and a report with no bundle is about nothing")

    axis = write_gene_axis(out_root, gene_ids)
    from . import envlock
    return write(built, out_root=out_root, gene_axis=axis,
                 sources={
                     "environment_lock": envlock.block(getattr(args, "env_lock", None)),
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
    ap.add_argument("--direct-bundle", default=None,
                    help="the ADMITTED Direct arm bundle for this condition. Its shipped "
                         "masks.parquet is the external referent this lane's mask is checked "
                         "against.")
    ap.add_argument("--direct-mask-report", default=None,
                    help="the PER-RUN W10 external Direct mask report over that bundle. Never "
                         "a frozen one: a report about another run is not a check of this one.")
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
