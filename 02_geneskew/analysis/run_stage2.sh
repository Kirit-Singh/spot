#!/usr/bin/env bash
#
# Stage-2 Direct lane — the REAL invocations, one per lane/context.
#
# B3. The invocation matrix built its selection paths by NAME:
#
#     --stage1-v3-selection $SEL_WITHIN_$COND          # and $SEL_TEMPORAL_${PAIR// /_}
#
# Bash does not compose a variable name that way. `$SEL_WITHIN_$COND` is the (unset,
# empty) variable `SEL_WITHIN_` followed by `$COND`, so the flag received the bare string
# `Rest` — a CONDITION NAME where a FILE PATH belongs. It does not fail loudly: argparse
# accepts the string, and the run dies later reading a file called `Rest`, or worse, reads
# one that happens to exist. Under `set -u` the empty half is not even caught, because the
# concatenation is a valid expansion of two things.
#
# So the paths are CONCRETE, held in associative arrays keyed by the context, and every
# lookup is checked. There is no indirect expansion anywhere in this file.
#
# DRY RUN: `SPOT_DRY_RUN=1 ./run_stage2.sh` prints the exact argv of every invocation, one
# argument per line, and executes nothing. That is what the argv-capture test asserts on —
# a runbook nobody can inspect without running it is a runbook nobody checks.
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
usage: run_stage2.sh [step0|direct|temporal|pathway|verify-pathway|verify-release|all]
Required environment (no defaults — an unset input is a refusal, not a guess):
  SEL_DIR  V3_SCHEMA  REGISTRY  STAGE1_RELEASE  DE  GUIDE  DONOR  SGRNA
  MANIFEST  SRCREG  PB  ENV_LOCK  OUT
Also required for Step 0 (the shared signature matrix anchors its mask to Direct):
  W10_REPORT_DIR   per-condition W10 external Direct mask reports
Optional: SPOT_DRY_RUN=1 (print argv + the producer->consumer flow, execute nothing)
          LANE (default: production)
USAGE
  exit 2
}

require_env() {
  local missing=()
  for name in SEL_DIR V3_SCHEMA REGISTRY STAGE1_RELEASE DE GUIDE DONOR SGRNA \
              MANIFEST SRCREG PB ENV_LOCK OUT W10_REPORT_DIR; do
    [[ -n "${!name:-}" ]] || missing+=("$name")
  done
  if (( ${#missing[@]} )); then
    printf 'refusing to run: unset %s\n' "${missing[*]}" >&2
    exit 2
  fi
}

LANE="${LANE:-production}"

# The BUNDLE-SCOPED producers take a CONTEXT, never an A/B pair: a reusable arm keyed on
# whichever question happened to be asked first is not reusable. Only the temporal lane (W5)
# still consumes a v3 selection contract.
bundle_args() {
  printf '%s\n' \
    --registry "$REGISTRY" \
    --stage1-release "$STAGE1_RELEASE" \
    --de-main "$DE" --by-guide "$GUIDE" --by-donors "$DONOR" --sgrna "$SGRNA" \
    --guide-manifest "$MANIFEST" --source-registry "$SRCREG" \
    --lane "$LANE" --strict-replay --pseudobulk "$PB" \
    --env-lock "$ENV_LOCK"
}

# ---- the CONCRETE selection contracts. One file per context. No name-building. ----
declare -A SEL_WITHIN
declare -A SEL_TEMPORAL

init_selections() {
  SEL_WITHIN=(
    [Rest]="$SEL_DIR/within_Rest.v3.json"
    [Stim8hr]="$SEL_DIR/within_Stim8hr.v3.json"
    [Stim48hr]="$SEL_DIR/within_Stim48hr.v3.json"
  )
  # the SIX ORDERED pairs. `Rest->Stim48hr` and `Stim48hr->Rest` are different questions
  # and different contracts; a set-keyed map would silently answer one with the other.
  SEL_TEMPORAL=(
    [Rest__Stim8hr]="$SEL_DIR/temporal_Rest_to_Stim8hr.v3.json"
    [Stim8hr__Rest]="$SEL_DIR/temporal_Stim8hr_to_Rest.v3.json"
    [Rest__Stim48hr]="$SEL_DIR/temporal_Rest_to_Stim48hr.v3.json"
    [Stim48hr__Rest]="$SEL_DIR/temporal_Stim48hr_to_Rest.v3.json"
    [Stim8hr__Stim48hr]="$SEL_DIR/temporal_Stim8hr_to_Stim48hr.v3.json"
    [Stim48hr__Stim8hr]="$SEL_DIR/temporal_Stim48hr_to_Stim8hr.v3.json"
  )
}

SIGROOT=""   # set by main(): the shared signature artifacts live under $OUT/signatures

CONDITIONS=(Rest Stim8hr Stim48hr)
PAIRS=(Rest__Stim8hr Stim8hr__Rest Rest__Stim48hr Stim48hr__Rest
       Stim8hr__Stim48hr Stim48hr__Stim8hr)
SOURCES=(reactome go_bp)

# Look a path up BY KEY and prove it. An unknown key is a bug in this file, and a missing
# contract is a refusal — never an empty string handed to argparse as if it were a path.
selection_for() {
  local -n table="$1"; local key="$2"
  local path="${table[$key]:-}"
  if [[ -z "$path" ]]; then
    printf 'no selection contract is mapped for %s\n' "$key" >&2
    exit 2
  fi
  if [[ -z "${SPOT_DRY_RUN:-}" && ! -f "$path" ]]; then
    printf 'selection contract does not exist: %s\n' "$path" >&2
    exit 2
  fi
  printf '%s' "$path"
}

# Print the argv (dry run) or execute it. One argument per line, so a captured argv is
# unambiguous about where each one ends — `echo "$*"` would lose exactly the boundaries a
# quoting bug hides in.
# WHAT a step produces and what it consumes. Declared, so the dry run can PROVE the flow
# instead of a reader taking the ordering on trust.
declare -a STEP_PRODUCES=()
declare -a STEP_CONSUMES=()

produces() { STEP_PRODUCES+=("$1"); }
consumes() { STEP_CONSUMES+=("$1"); }

run() {
  local label="$1"; shift
  if [[ -n "${SPOT_DRY_RUN:-}" ]]; then
    printf '=== BEGIN %s\n' "$label"
    printf '%s\n' "$@"
    local x
    for x in "${STEP_PRODUCES[@]:-}"; do [[ -n "$x" ]] && printf '=== PRODUCES %s\n' "$x"; done
    for x in "${STEP_CONSUMES[@]:-}"; do [[ -n "$x" ]] && printf '=== CONSUMES %s\n' "$x"; done
    printf '=== END %s\n' "$label"
    STEP_PRODUCES=(); STEP_CONSUMES=()
    return 0
  fi
  STEP_PRODUCES=(); STEP_CONSUMES=()
  "$@"
}

# DISCOVER a content-addressed bundle. Its directory IS its run id, so it cannot be guessed —
# and a guessed path either finds nothing or finds a STALE bundle from another run.
direct_bundle_for() {
  local cond="$1"
  if [[ -n "${SPOT_DRY_RUN:-}" ]]; then
    printf '%s' "<discovered:direct:$cond>"      # not produced yet in a dry run
    return 0
  fi
  python -m analysis.direct.bundle_index \
    --root "$OUT/direct" --condition "$cond" --kind direct
}

common_args() {
  printf '%s\n' \
    --stage1-v3-schema "$V3_SCHEMA" \
    --registry "$REGISTRY" \
    --de-main "$DE" --by-guide "$GUIDE" --by-donors "$DONOR" --sgrna "$SGRNA" \
    --guide-manifest "$MANIFEST" --source-registry "$SRCREG" \
    --stage1-release "$STAGE1_RELEASE" \
    --lane "$LANE" --strict-replay --pseudobulk "$PB" \
    --env-lock "$ENV_LOCK"
}

# STEP 0 — the SHARED signature matrix + mandatory bitmap, ONCE per condition, BEFORE any
# pathway bundle. Infrastructure, not a bundle: it does not count toward the 15 and it is not
# completeness-bearing.
# STEP 0 — the SHARED signature matrix + mandatory bitmap. Infrastructure, not a bundle: it
# does not count toward the 15. It runs AFTER Direct, because it ANCHORS its mask to the Direct
# bundle's shipped mask table and to W10's independent re-derivation of it. Without that anchor
# the mask is only self-consistent, and a coherently forged mask is indistinguishable from a
# real one.
lane_step0() {
  local cond dbundle report
  for cond in "${CONDITIONS[@]}"; do
    dbundle="$(direct_bundle_for "$cond")"
    report="$W10_REPORT_DIR/direct_mask_report_${cond}.md"
    if [[ -z "${SPOT_DRY_RUN:-}" && ! -f "$report" ]]; then
      printf 'no W10 Direct mask report for %s at %s\n' "$cond" "$report" >&2
      exit 2
    fi
    consumes "direct:$cond"
    consumes "w10_report:$cond"
    produces "signatures:$cond"
    run "step0:$cond" python -m analysis.direct.signature_matrix \
      --condition "$cond" \
      --de-main "$DE" --sgrna "$SGRNA" --guide-manifest "$MANIFEST" \
      --source-registry "$SRCREG" \
      --direct-bundle "$dbundle" \
      --direct-mask-report "$report" \
      --env-lock "$ENV_LOCK" \
      --out-root "$SIGROOT"
  done
}

# 3 of the 15. The ALL-ARM Direct bundles: every admitted program's two arms, per condition.
lane_direct() {
  local cond
  for cond in "${CONDITIONS[@]}"; do
    mapfile -t bargs < <(bundle_args)
    produces "direct:$cond"
    run "direct:$cond" python -m analysis.direct.run_arms \
      --condition "$cond" \
      "${bargs[@]}" \
      --out-root "$OUT/direct"
  done
}

lane_temporal() {
  local pair sel
  for pair in "${PAIRS[@]}"; do
    sel="$(selection_for SEL_TEMPORAL "$pair")"
    mapfile -t common < <(common_args)
    run "temporal:$pair" python -m analysis.direct.temporal.cli \
      --stage1-v3-selection "$sel" \
      "${common[@]}" \
      --out-root "$OUT/temporal"
  done
}

# 6 of the 15. The ALL-ARM pathway bundles, REFERENCING the shared Step-0 artifacts.
lane_pathway() {
  local cond src
  for cond in "${CONDITIONS[@]}"; do
    for src in "${SOURCES[@]}"; do
      mapfile -t bargs < <(bundle_args)
      consumes "signatures:$cond"
      produces "pathway:$cond:$src"
      run "pathway:$cond:$src" python -m analysis.direct.run_pathway_arms \
        --condition "$cond" \
        "${bargs[@]}" \
        --gene-sets "$SEL_DIR/genesets_${src}.ensembl.json" \
        --signature-matrix-root "$SIGROOT" \
        --out-root "$OUT/pathway"
    done
  done
}

# DISCOVER the content-addressed pathway bundle for a (condition, source). Its directory is its
# run id and cannot be guessed — bundle_index refuses on none or on ambiguity.
pathway_bundle_for() {
  local cond="$1" src="$2"
  if [[ -n "${SPOT_DRY_RUN:-}" ]]; then
    printf '%s' "<discovered:pathway:$cond:$src>"
    return 0
  fi
  python -m analysis.direct.bundle_index \
    --root "$OUT/pathway" --condition "$cond" --kind pathway --source "$src"
}

# INDEPENDENT VERIFICATION (W4). generator != verifier: this is a SEPARATE gate, not part of the
# producer `all` flow. It reads the SHIPPED bytes and re-derives every claim — V1-V10, the
# cross-lane Direct mask anchor (re-derived from the shipped masks.parquet), the amended bitmap
# counts, the per-target QC, the stale-source refusal, and the pinned 2983… solver lock. Exit
# nonzero on ANY refusal; a deterministic, content-addressed report per bundle. The env lock is
# NOT passed here — it is read from the shipped provenance and checked against the pin.
lane_verify_pathway() {
  local cond src dbundle report pbundle
  [[ -n "${SPOT_DRY_RUN:-}" ]] || mkdir -p "$OUT/verification"
  for cond in "${CONDITIONS[@]}"; do
    dbundle="$(direct_bundle_for "$cond")"
    report="$W10_REPORT_DIR/direct_mask_report_${cond}.md"
    for src in "${SOURCES[@]}"; do
      pbundle="$(pathway_bundle_for "$cond" "$src")"
      consumes "pathway:$cond:$src"
      consumes "signatures:$cond"
      run "verify-pathway:$cond:$src" python -m analysis.direct.verify_signature_matrix \
        --signature-matrix-root "$SIGROOT" \
        --bundle "$pbundle" \
        --de-main "$DE" \
        --direct-bundle "$dbundle" \
        --direct-mask-report "$report" \
        --out "$OUT/verification/pathway_${cond}_${src}.json"
    done
  done
}

# RELEASE-LEVEL INDEPENDENT VERIFICATION (W4). The per-bundle gate above admits ONE cell; this
# admits the RELEASE. It is anchored OUTWARD, never to the bundles it judges: the condition x
# source UNIVERSE comes from the authoritative Stage-1 v3 release ($STAGE1_RELEASE), each cell's
# local validity from the INDEPENDENT per-bundle report emitted by verify-pathway (never the
# producer's own pathway_verification.json), the solver lock from the pinned constant, and the
# PENDING producer inventory is byte-bound and re-derived. It emits a lane-specific
# content-addressed pathway_arm_external_admission.json (ADMIT/REFUSE, exit nonzero on refusal).
# A SEPARATE gate that DEPENDS on verify-pathway (the six reports must already exist): the
# producer does not admit its own release.
lane_verify_release() {
  local cond src pbundle
  local -a bargs=()
  for cond in "${CONDITIONS[@]}"; do
    for src in "${SOURCES[@]}"; do
      pbundle="$(pathway_bundle_for "$cond" "$src")"
      bargs+=(--bundle "$pbundle")
      bargs+=(--bundle-report "$OUT/verification/pathway_${cond}_${src}.json")
      consumes "pathway:$cond:$src"
      consumes "verify-pathway:$cond:$src"
    done
  done
  consumes "pathway-release-inventory"
  [[ -n "${SPOT_DRY_RUN:-}" ]] || mkdir -p "$OUT/verification"
  run "verify-release" python -m analysis.direct.verify_pathway_release \
    "${bargs[@]}" \
    --release "$STAGE1_RELEASE" \
    --inventory "$OUT/pathway/pathway_arm_release.json" \
    --out "$OUT/verification/pathway_arm_external_admission.json"
}

main() {
  local what="${1:-all}"
  require_env
  init_selections
  SIGROOT="$OUT/signatures"
  case "$what" in
    step0)    lane_step0 ;;
    direct)   lane_direct ;;
    temporal) lane_temporal ;;
    pathway)  lane_pathway ;;
    verify-pathway) lane_verify_pathway ;;
    verify-release) lane_verify_release ;;
    # ORDER IS A DEPENDENCY, not a preference. Direct FIRST, because Step 0 anchors its mask to
    # the Direct bundle and to W10's independent report over it. Step 0 before pathway, because
    # a pathway bundle that rebuilt its own signatures would reintroduce the 29.5 GiB peak the
    # shared matrix removes.
    all)      lane_direct; lane_step0; lane_pathway; lane_temporal ;;
    *)        usage ;;
  esac
}

main "$@"
