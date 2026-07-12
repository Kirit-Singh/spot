# Handoff → W12 (agent/ui-stage234): mirror the identical/cross-condition logic fix in `routingReason.ts`

_From the Stage-1 lane (branch `stage1-remediation`), 2026-07-12. The frozen-page half of this fix is
DONE on `stage1-remediation`; the TS twin below lives only in the W12 worktrees, so it is handed off._

## What was fixed here (frozen page)
`01_programs/app/01_page.html` `preflight()` — the "identical From/To" refusal now also requires the same
condition, so **same program + same direction across DIFFERENT timepoints** is no longer mislabeled
"identical". It falls through to the cross-condition branch → **`awaiting_estimator`** ("Cross-condition
analysis feature in progress"), consistent with the temporal estimator (`temporal_cross_condition_v1`,
status `not_implemented`). Both states stay `ok:false` / ID button disabled — nothing is newly enabled.

Guard applied (canonical page):
```js
if (A.program_id===B.program_id && axisA.direction===axisB.direction && axisA.condition===axisB.condition)
  return {ok:false, sev:'err', reason:'From and To are identical\nPick distinct programs or opposite directions'};
```

## What W12 must mirror — `_frontend/src/stage1/routingReason.ts`
This module is the **tested source** the frozen page mirrors (its own header says so). It is NOT present on
`stage1-remediation` (no `_frontend/src/stage1/` there), so the Stage-1 lane did not touch it.

**Bug:** `deriveRouting()` line ~47 tests only `aProgram===bProgram && aDirection===bDirection` and returns
`refused` / `objective_incompatible_same_pole` — this fires BEFORE the cross-condition branch (line ~61), so
same-pole across different timepoints is wrongly refused as identical.

**One-line fix** (add the condition term):
```ts
// before
if (s.aProgram === s.bProgram && s.aDirection === s.bDirection) {
// after
if (s.aProgram === s.bProgram && s.aDirection === s.bDirection && s.conditionA === s.conditionB) {
```
After this, same-pole + different timepoint falls through to the existing
`if (s.conditionA !== s.conditionB)` branch → `analysis_mode:'temporal_cross_condition'`,
`execution_status:'awaiting_estimator'`. This is an intended typed-contract change
(`refused` → `awaiting_estimator`) for these selections; confirm it in the Stage-1 → Stage-2 selection
contract wording.

## Tests — `_frontend/src/stage1/__tests__/routingReason.test.ts`
No existing assertion flips: the current "objective incompatible (same pole)" case uses
`conditionA===conditionB==='Stim48hr'`, so it still returns `refused` after the guard. **Add** a regression
test for the previously-broken case:
```ts
it('same pole across DIFFERENT timepoints → temporal awaiting_estimator (not identical)', () => {
  const r = deriveRouting({ ...base, bProgram: 'treg_like', bDirection: 'low',
                            conditionA: 'Rest', conditionB: 'Stim48hr' });
  expect(r.execution_status).toBe('awaiting_estimator');
  expect(r.analysis_mode).toBe('temporal_cross_condition');
  expect(r.reason_code).not.toBe('objective_incompatible_same_pole');
});
```
(`base` has `aProgram:'treg_like'`; setting `bProgram:'treg_like'`, `bDirection:'low'` makes it the same
pole as A once you also set `aDirection:'low'` — or adjust `base` accordingly so A and B are the identical
pole; the point of the case is same-program+direction with `conditionA !== conditionB`.)

## Cross-check (already verified in the frozen-page harness)
Truth table (branch order: identical+condition → pooled-All → cross-condition → portability → ready):
- same prog/dir/cond → **identical (refused/err)**
- same prog/dir, diff timepoint → **cross-condition (awaiting_estimator/warn)**  ← the fix
- opposite direction, same cond → ready
- pooled All → pick-timepoint (refused)
- Th9 pole → nonportable (refused)
