# Stage-2 signature matrix — the independent verifier (W4) ⇄ producer (W18) ⇄ Direct (W10)

Implements V1–V10 of `PATHWAY_SIGNATURE_MATRIX_SPEC.md`
(sha256 `95d693026647bf70f01a54649932482a7856d955deb74f7abc3142ec9febdd99`) plus the W7 Step-0
amendment, against W18's producer at commit `e5f71df`. W18 owns the producer
(`signature_matrix.py`, `run_pathway_arms`); W4 owns this verifier
(`verify_signature_matrix.py`) and the resealed integrity probes
(`tests/direct/test_signature_matrix_forgery.py`). W10 owns the independent Direct mask
verification. They share no code — the independence probe (`test_audit_probes`) enforces that
a `verify_` module imports **no** producer module.

## What the verifier re-derives from the shipped bytes

| Gate | Independent re-derivation |
|---|---|
| `V1` | raw sha256 of every artifact recomputes; matches the manifest + every ref |
| `V1_REFMAN` | every ref binds a **non-null** manifest identity (raw + canonical) that re-derives — a different condition's matrix is not substitutable |
| `V2_*` | values/bits/canonical recompute from re-read bytes; **values re-derive from the pinned de_main log_fc read via `h5py`** (reseal-proof) |
| `V3` | gene axis order **and** hash re-derive from de_main var/gene_ids |
| `V4` | the amended counts (`n_resolved_all_ones == n_resolved_no_masked_readout_gene`) + `source_mask_sha256` re-derive from the bitmap and are bound in the ref |
| `V5` | all-zero == `n_unresolved_no_signature`; the resolved all-ones set re-derives from the bitmap == the declared disposition |
| `V6` | convergence re-derives from `(matrix, bitmap)` with the sorted-gene left fold, **bitwise** |
| `V7` | `member_target_ids` re-derive from the bound gene sets ∩ condition targets ∩ resolved |
| `V8` | no bundle ships signature bytes |
| `V9` | the recursive no-p/q/FDR firewall |
| `V10` | every reference resolves; every shared artifact is cited |
| `V_IDENTITY` | the ref on disk IS the one bound into a re-derivable `pathway_run_id` |
| `V_EXTERNAL_MASK` | the source mask is the one W10 **independently** verified (below) |

Imports only `h5py`/`numpy`/`json` and verifier-side `verify_rules` / `verify_run` (the h5ad
reader) / `verify_reconstruct` (gene-set parse). Digests, descriptors,
`reconstruct_signatures` and the cosine are re-implemented from the spec.

## The resealed integrity probes

Each corrupts a shipped byte and reseals every internal hash — manifest identity, canonical
descriptors, ref, run binding, run id — and still fails at a named gate: A1 float32 /
A2 reorder / A6 cross-condition / A11 non-finite → `V2_ANCHOR`; A3 **permuted** axis → `V3`;
A4 all-ones / A5 promotion → `V5`; A7 stale ref / A10 container reframe → `V1`; A8 member
padding → `V7`; A9 reduction drift → `V6`; A12 re-ship → `V8`; null manifest identity →
`V1_REFMAN`; **fully-resealed wrong source mask → `V_EXTERNAL_MASK`**.

## Why `V_EXTERNAL_MASK` — and the cross-lane binding to W10

Bitmap-recount + a self-bound run id is **not** enough: a forger can rebuild a coherent WRONG
biological source mask — new bitmap, new counts, new `source_mask_sha256`, new `mask_sha256`,
new run id — and every internal statement agrees. `V4`/`V5`/`V_IDENTITY` all pass. Only an
**external, independent** re-derivation of the Direct masks refuses it.

W4 does **not** re-derive the mask (that would duplicate ~500 lines of `masks.py`/`guides.py`
and, under the independence rule, is forbidden). Instead it binds **W10's** independent Direct
mask verification, which re-derives every mask from the pinned contributor manifest + sgRNA
library under the target + 30 kb + contributing-guide off-target rule and admits them.

**W10's report is sealed** at `.spot-runs/20260712T021343Z/DIRECT_MASK_VERIFICATION_REPORT.md`
(sha256 `48ff889b…`), verifier `spot.stage02.direct.arm_bundle.verifier.v1` @ `58f6305`
(code `7578ae5e…`, gate inventory `cc8fc6ca…`), producer W14 @ `41d9a9d`. `V_EXTERNAL_MASK`
binds the W10 **verifier identity to those exact clean heads**, and requires the **per-run**
certified mask to equal the pathway's own `mask_sha256`.

**Production distinction (do not violate).** The report's concrete `mask_sha256` `269b4278…`
and its three bundle ids are **synthetic-fixture** values — they appear only in contract /
mutation tests and are **never frozen into the verifier** (a test asserts `269b…` is absent
from the module source). At the real run the pathway binds a **per-run** W10 report over the
**actual** Direct `masks.parquet`; W7 runs W10 on real Direct output **before** real pathway
admission. The gate reads `certified_mask_sha256` from the bound per-run report — it never
hardcodes a mask.

**Still to land:** **W18** must bind, into `run_binding.direct_mask_verification` (and thus
`pathway_run_id`):
```
{ "report_sha256", "verdict": "ADMIT", "verifier_id",
  "verifier_code_sha256", "gate_inventory_sha256", "certified_mask_sha256" }
```
where `certified_mask_sha256 == run_binding.mask_sha256`. Until then the binding is simulated
in the test fixture; every other gate verifies **real** `e5f71df` producer bytes, and the
sealed W10 report is replayed from its exact sealed bytes.

Integration (W1) holds until W4 and W18 agree, W10's Direct mask verification is bound, and
production Step-0 reconfirms deterministic bytes + peak RSS (W7 measured 3.65–3.69 GiB,
~45 s/condition, seven artifacts byte-identical across two rebuilds).
