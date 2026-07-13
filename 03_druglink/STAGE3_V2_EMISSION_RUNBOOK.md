# Stage-3 v2 real emission — everything is staged except W3's bridge

Ready to run. The only substitution left is the three W3 bridge paths.

## The universe store is REAL, LOCAL, and ADMITTED

| | |
|---|---|
| delivered source | `/home/tcelab/.spot-runs/stage3-universe-20260713/store` |
| source store_id | `bdf41b69df2be61d3f625aafa0429e643581fe50823698e77e079054c6145160` |
| file-list hash | `a347d2b5c96f70cad891696d611e1d965ad8e9b215b3043b16940d73723caa72` ✓ |
| byte-check | identical to the copy verified against tcefold |
| **ADMITTED store** | **`/home/tcelab/.spot-runs/stage3-universe-20260713/store_w3tokens`** |
| **admitted store_id** | **`625c921fce2daf60b69fb0ae33570a9f074a0a0042b1717ee2111f81c1160bff`** |
| typed universe | `1c19db2b5d666a8f33c715cb634cf111953c7cdd6c23d082e9b375643a3e7cc8` |

**Why two stores.** The delivered bytes carry the OLD namespace vocabulary
(`ensembl_gene` / `symbol`); Stage-2 serializes `ensembl_gene_id` / `gene_symbol`. Byte-equal
tokens across two versioned schemas would refuse **every real Ensembl row and yield zero edges**,
so the store was re-pinned onto Stage-2's vocabulary — the only change is the token. Proven:
the **scientific content hash with the namespace projected out is identical** before and after,
the row set is bijective, and every count holds.

`store_w3tokens` is **regenerable from the delivered bytes at any time** — it is a derivation,
not a second source of truth:

```bash
python -c "from druglink import universe_repin as R; \
  R.emit(src_dir='/home/tcelab/.spot-runs/stage3-universe-20260713/store', \
         dest_dir='<dest>', created_at='2026-07-13T00:00:00Z')"
```

`bdf41b69…` (the old vocabulary) is on the REFUSED list so it cannot creep back in.

**Recomputed from the admitted store, matching the integration numbers exactly:**
11,526 typed targets · **505 drugged targets** · **2,227 ChEMBL drug rows** · 1,923 molecules.
No ChEMBL/UniProt re-acquisition — these are the delivered public bytes.

## The command

```bash
cd 03_druglink
PYTHONPATH=analysis python -m druglink.run_stage3 --v2 \
  --artifact-class        analysis \
  --universe-store        /home/tcelab/.spot-runs/stage3-universe-20260713/store_w3tokens \
  --stage2-manifest       <W3>/stage2_run_manifest.json \
  --stage2-report         <W3>/stage2_aggregate_verification.json \
  --bundles-root          <W3>/ \
  --stage1-release        <W3>/<stage-1 v3 release FILE> \
  --stage2-bridge         <W3>/stage3_bridge.json \
  --stage2-bridge-report  <W3>/stage3_bridge_verification.json \
  --stage2-bridge-receipt <W3>/stage2_stage3_receipt.json \
  --output-root           /home/tcelab/.spot-runs/stage3-universe-20260713/v2_bundle
```

Then the independent verifier over that exact emitted bundle:

```bash
PYTHONPATH=analysis python -m verifier.verify_stage3_v2 \
  --bundle <OUT>/drug_annotation.v2.json  --artifact-class analysis  ... (same inputs)
```

**`<W3>` is the only unknown.** Everything else is staged and verified.

## What it will refuse today, and why that is correct

W3's bridge is still code-only — no `stage3_bridge.json` exists on this host. The v2 path
therefore refuses at `the_stage3_bridge_consumer_is_not_implemented_yet` (exit 3, **nothing
written**).

That refusal is the honest state, not an obstacle. The native ranking rows carry
`{target_id, arm_value, evaluable, rank}` — **no namespace, no modality**. Those two facts exist
only in the bridge. A run without it would have to infer identity from an id's string shape and
default a modality from a config constant — a *setting* wearing the costume of an assay. Stage-3
refuses rather than invent them.

## Architecture held

- the public store is **global and selection-independent**; a selection is a **projection**
- **no combined candidate rank**, no combined objective, no p/q/FDR at any depth
- typed origins stay separate; pathway is CONTEXT and never sources a drug edge
- an untested inverse is **hypothesis-only** — queued for a look, never observed support
