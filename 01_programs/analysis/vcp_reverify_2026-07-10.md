# VCP data-provenance & reproducibility RE-VERIFICATION
Re-run: 2026-07-10 (independent of the 2026-07-09 20:24 EDT recorded trace)
Verdict: ALL CLAIMS REPEAT — no drift.

## 1. Provenance (vcp CLI)  — CONFIRMED
- vcp-cli installed from PyPI: version 0.54.1 (matches trace); `data` group active with [data] extra.
- `vcp data search "Primary Human CD4+ T Cell Perturb-seq"` resolves under namespace `billion-cell-project`.
- 12 per-donor x per-condition AnnData splits present: D1–D4 (x3 each) x {Rest, Stim8Hr, Stim48Hr} (x4 each) = full 4x3 grid.
- D1_Rest dataset id: 6946b5261d32b0e84ba87057 (matches trace).
- `vcp data describe … --full`:
    external_id : marson_D1_Rest.assigned_guide
    assay       : 10x gene expression flex (EFO:0022606)
    asset URL   : s3://genome-scale-tcell-perturb-seq/marson2025_data/D1_Rest.assigned_guide.h5ad
  (asset path matches trace exactly)

## 2. Remote S3 range-read (s3fs+h5py, obs/guide_type only) — CONFIRMED
- Object size: 142,828,875,662 bytes (142.8 GB). No full download.
- obs/guide_type categorical: categories = ['non-targeting','targeting']; codes shape = (3,074,496,)
- total cells : 3,074,496            (matches 3,074,496)
- non-targeting: 76,634  = 2.493%    (matches 76,634 / 2.5%)
- (targeting 2,203,483 = 71.67%; remaining ~25.8% unassigned/code -1 — not part of the headline claim)

## 3. Determinism + N_PERM=500 reproduction — CONFIRMED
- Determinism (structural audit): all randomness flows through one rng = np.random.default_rng(SEED=12345)
  (control-gene draws + size-matched permutation null). No unseeded np.random / RandomState / stdlib random /
  unseeded shuffle. Byte-exact re-run at fixed seed holds by construction; different seed shifts scores.
- Reproduction gate `verify_reproduce.py` (updated 2026-07-10 10:00 EDT, activation-conditioned CD4-CTL REFERENCE)
  run against deployed data/stage01_umap_seed.json:
    "OK — emitted overlay matches the reference (differentiation + function intact, match 100.0%)."
  REFERENCE func counts: —:33004 (82.5% no-call), Th1:4550, CD4-CTL:573, Treg:1051, Th2:528, Tfh:236, Th9:40, Th17:18
  overlay emitted_at 2026-07-10 10:06 EDT; genome GRCh38; 396,000 NTC cells / 40,000 shown.
- Note: earlier "func mismatch" was a mid-change snapshot (CD4-CTL scoring switch); resolved, matches at 100%.
