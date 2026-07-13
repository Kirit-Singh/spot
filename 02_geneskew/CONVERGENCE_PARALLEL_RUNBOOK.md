# Convergence parallel execution smoke

This is an execution optimization only. The similarity metric, sorted pair order, Python
left-fold reduction, rounding, support threshold, convergence records and
`convergence_sha256` are unchanged. The producer commit and therefore the run's code identity
do change; a bundle from this commit is a new run and must pass the pinned independent W4
verifier before admission.

Run one full Reactome bundle first with eight workers. Do not run the other five bundles at
the same time. Use the exact Stage-1 release, Direct release, signature matrix, input pins and
environment lock from the admitted run manifest; the abbreviated placeholders below must be
replaced from that manifest, not guessed:

```bash
cd 02_geneskew
export PYTHONPATH=analysis
export MIN_MEM_AVAILABLE_GIB=35
export WATCHDOG_LOG="$RUN_ROOT/logs/rest-reactome-8w-memory.tsv"

analysis/run_with_memory_watchdog.sh \
  /usr/bin/time -v "$PYTHON" -m direct.run_pathway_arms \
  --condition Rest \
  --gene-sets "$RUN_ROOT/inputs/geneset-cache-ensembl/reactome_ensembl.genesets.json" \
  --signature-matrix-root "$RUN_ROOT/output/signatures" \
  --stage1-release "$STAGE1_RELEASE/stage01_v3_release.json" \
  --stage1-release-root "$STAGE1_RELEASE" \
  --registry "$STAGE1_RELEASE/01_programs/app/data/stage01_program_registry_v3.json" \
  --de-main "$DE_MAIN" \
  --by-guide "$BY_GUIDE" \
  --by-donors "$BY_DONORS" \
  --sgrna "$SGRNA" \
  --guide-manifest "$GUIDE_MANIFEST" \
  --source-registry "$SOURCE_REGISTRY" \
  --lane production --strict-replay \
  --pseudobulk "$PSEUDOBULK" \
  --env-lock "$ENV_LOCK" \
  --convergence-workers 8 \
  --convergence-chunk-size 500 \
  --out-root "$FRESH_UNADMITTED_OUT_ROOT"
```

Acceptance before increasing concurrency:

1. the watchdog never crosses the 35-GiB host-availability floor;
2. the producer exits zero and writes only beneath the fresh unadmitted root;
3. the separate W4 verifier re-derives every hash and returns `ADMIT`;
4. the convergence records and `convergence_sha256` equal a serial replay over the same
   source, condition and signatures;
5. peak aggregate PSS leaves enough room for the next planned bundle. Never infer safety
   from summed RSS because fork-shared pages are counted once per process there.

Only after this smoke may 16 workers be considered. Do not combine five outer bundle jobs
with 16 inner workers. GO-BP has more member signatures and requires its own full-size memory
observation before any concurrent launch.
