# Perturb2State secondary-support UI seam — handoff

**Status: prepared, NOT deployed. Do not wire into the live UI until you (the UI owner) admit
it.** This is an isolated, self-contained adapter. It touches nothing in Direct / Temporal /
Pathway, imports none of their code, and cannot reorder any of their ranks.

## What it is

A read-only adapter over the already-admitted, verified P2S projection
`P2S_UI_SUPPORT_PROJECTION.json`
(schema `spot.stage02.p2s_ui_support_projection.v1`, file sha256
`b90c895198826459a8e4db52db6dd8d63d0baf233374dc6811de4c7c7b10c916`; verified by
`P2S_UI_PROJECTION_VERIFICATION.json`). Durable copy under the run root
`/home/tcelab/.spot-runs/20260713T-p2s-arms/p2s-secondary-smoke/`.

The projection carries **reconstruction-support coefficients only** — never a rank, p-value,
q-value, FDR, significance, combined/weighted score, validation claim, or causal effect. It is
**secondary and non-gating**.

## Files (drop-in, no dependencies beyond TS)

- `types.ts` — mirrors the projection schema.
- `p2sSecondarySupport.ts` — `loadP2sSecondarySupport(raw)` → guarded adapter.
- `p2sSecondarySupport.test.ts` — exact-binding + opposite-direction-symmetry + refusal tests.

## Wiring — Targets hover / details

```ts
import { loadP2sSecondarySupport } from './p2s/p2sSecondarySupport'

// once, at load: fetch the projection JSON (served as a static asset) and guard it
const p2s = loadP2sSecondarySupport(await fetch(P2S_PROJECTION_URL).then((r) => r.json()))

// in the Targets hover/details, bound EXACTLY by (target_id, arm_key):
const view = p2s.supportForTarget(target.id, arm.key)   // null if not this arm/target
if (view) {
  // compact reconstruction-support fields — display only, never sortable/rankable:
  //   view.coefficient   (signed; direction-correct)      view.sign ('supportive'|'opposed'|'zero')
  //   view.opposed       (label, not a verdict)           view.available
  //   view.robustness.{logFcSignConcordance, pcaOffSignConcordance, lodoSignConcordance}
  //     with their nLogFc / nPcaOff / nLodo denominators, and view.nRuns
}
```

`arm.key` is `direct|<program>|<increase|decrease>|<condition>`. The adapter binds its own arm
and its exact-negation sibling; the **decrease view is the exact negation of the increase view**
(coefficient negated, sign flipped, magnitude and concordances identical) — do not re-fetch or
re-compute it.

## Wiring — Methods drawer

```ts
const md = p2s.methodsDrawer()   // { laneRole, whatItIs, boundDirectRelease, provenance, guardrails, ... }
```

Render `md.whatItIs`, the bound Direct release / W10 ADMIT, the provenance hashes, and
`md.guardrails` verbatim.

## Guardrails (enforced, not just documented)

- `loadP2sSecondarySupport` **refuses** a projection that is not `secondary_non_gating`, that
  claims to be part of the admitted Direct result, that admits entering primary rank/order, or
  that carries any `rank / p_value / q_val / fdr / significance / combined / weighted / causal /
  validation / gating` field. A tampered projection cannot load.
- The adapter exposes **no** `rank()`, `sort()`, `top()`, `gate()`, or `combine()` — the only
  lookup is by `target_id`. There is no surface on which to reorder Direct/Temporal/Pathway.
- Do **not** merge, add, or combine these coefficients into any primary score, ordering, or
  gate. Do **not** present them as p-values, validation, causal effects, or a biological finding.

## Tests

`cd _frontend && npx vitest run src/p2s/` — 11 tests (exact binding, opposite-direction
symmetry, and every refusal). Typecheck: `npx tsc --noEmit -p tsconfig.app.json`. Lint:
`npx oxlint src/p2s/`.

## Apply

Isolated branch `agent/p2s-ui-secondary-seam`, or the `git format-patch` in the handoff. Nothing
here is deployed; integrate and ship only after you admit it.
