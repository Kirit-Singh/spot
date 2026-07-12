# Spot Stage 2/3/4 — generic workflow shell (design)

Date: 2026-07-12. Author: UI/Design (sole writer). Worktree: `spot-worktrees/spot-ui-stage234/_frontend`.
Status: approved design; implementation pending. **No commit/push; no deploy to 8347 without orchestrator approval.**

## Goal

Turn the fixtures-first Stage 2–4 preview into a **generic, data-driven workflow** that binds any
supported program A/B directions + analysis condition/mode, renders verified artifacts when supplied,
and — when none is bound — shows an **honest, visually useful workflow scaffold** that never
masquerades as scientific output. Visual baseline: live `100.117.50.59:8347/01_page.html`
(SHA `c0a84e2f…`, byte-identical to the frozen snapshot). Preserve Stage-1 layout/tokens/interactions.

## Hard constraints (carried)

- Main canvas = controls, values, results, provenance links, compact typed states only. No banners,
  repeated caveats, walls of prose, traffic-light moralizing, or fake fixture results on the default
  canvas. Methods + limitations appear **once** in the provenance drawer. (`stage234-no-editorial-canvas`.)
- No edits to the main repo or scientific worktrees. No commit/push. Serve review candidate on **:8348**;
  never replace :8347 without orchestrator verification.

## Modes (decided in code by the repository, never by a data field)

| Mode | Trigger | Canvas |
|---|---|---|
| `empty` (default) | no selection, no demo | Workflow scaffold: controls + output *shape* + typed region states (`select programs`, `no artifact for this selection`). Zero fake numbers. |
| `demo` | explicit `?demo=1` | Synthetic example artifacts, namespace `fixture`, `production_eligible=false`. Persistent `DEMO · synthetic` chip. Only place populated results render without a real artifact. |
| `research` | valid `spot.stage01_selection.v1` in localStorage | Binds real research artifacts by selection-id + namespace + provenance; missing → typed `analysis not generated`. |
| `production` | future | Unreachable today; `production_gate_passed=false` can never construct it. |

The scaffold and the demo share layout; they differ only in whether region content is a typed empty
state or synthetic data. A stage view is a pure function of `{controls, region-slots}` where each slot
is `loaded | empty | not_generated | rejected`.

## Data-driven, schema-versioned adapters

- Every artifact carries `schema_version`; adapters are selected by it and reject unknown versions
  (existing behaviour). Views render the fields the schema provides, not hard-coded columns.
- Firewall (existing) keeps: namespace bound in code, artifact-id namespace prefix match, no
  cross-namespace upstream pointer, missing-hash rejection, **numeric combined/balanced score rejection**.
- Firewall change: **permit exactly the typed ordering fields** `joint_status`, `pareto_tier`,
  `ordering_method_id`; continue rejecting `combined_score`, `balanced_score`, `balanced_a_to_b`,
  `rank_combined`, `rank_balanced`, `best_of`.

## Stage 2 — Targets (multi-objective / Pareto)

Authoritative, independent measurements (unchanged): `away_from_A`, `toward_B` — each `{evaluated,
reason, effect, rank, coverage}`, nullable, per-arm.

Added typed ordering (no averaging, no weighting):
- `joint_status ∈ { both_arms, a_only, b_only, opposed }` — replaces `cross_class`.
- `pareto_tier: number|null` — dominance tier (a target is dominated if another is ≥ on both arms and
  > on one); tier 1 = non-dominated. `null` when not evaluated.
- `ordering_method_id: string` — exact frozen ordering method (provenance).
- Per-target **marker diagnostic**: `marker_breadth: { supporting_markers, single_marker_driven,
  detail }` as a compact typed state.

Views (segmented control): `Away from A` · `Toward B` · `Joint · Pareto`. Away/Toward sort by that arm's
rank (nulls sink); Joint·Pareto orders by `pareto_tier` then shows `joint_status` per row. No combined
numeric column anywhere.

Pathways panel: convergent perturbation signatures — for each pathway node: contributing targets, arm
of support (`a | b | both`), enrichment evidence (value + state), and a `druggable` flag on nodes.

## Stage 3 — Drugs

Candidate `origin ∈ { direct_target, pathway_node }`, each with `mechanism_direction`. Every candidate
records the **exact supporting arm + direction** (`supporting_arm ∈ {away_from_A, toward_B}`,
`supporting_direction`) — never inferred from joint ordering. Existing evidence (forms, potency
verbatim, source conflicts, GBM-context state, disabled promotion) retained.

## Stage 4 — PK & safety

Panels: `delivery_requirement` (+ evidence), `exposure`, `nebpi` (neutral/typed state, no traffic
light), `treatment_context_safety`. Measurement states (`measured|calculated|label_derived|
not_evaluated|missing`) preserved; missing never coerced to zero.

## Components / boundaries

- `shell/` — TopBar, StageNav, SelectionContextBar (+ mode/demo chip), ProvenanceDrawer, StageState
  (typed empty/rejected rows), a new `RegionState` primitive for per-region typed empties.
- `domain/` — parameterized program/selection + stage2/3/4 models with the new typed fields.
- `adapters/` — schema-versioned parsers + firewall (typed-ordering allowlist).
- `repository/` — mode selection incl. `empty` + `demo` gate; region-slot resolution.
- `fixtures/` — synthetic demo artifacts (behind the gate), unmistakably synthetic.
- `stages/stage2|3|4/` — views composed from region slots; each independently reviewable.

## Testing / QA

- Unit: adapters + firewall (typed ordering allowed; numeric combined rejected), Pareto/joint logic,
  marker-breadth, empty-vs-demo mode selection, view toggles, Stage-3 arm tracing, Stage-4 states.
- Accessibility: landmark roles, `aria-current`, focus management, keyboard nav, segmented-control roles.
- No-editorial firewall: `noEditorialCanvas` scoped to `<main>`, positive route-specific assertions,
  extended forbidden patterns; empty/demo/research modes.
- Responsive + browser QA on built dist (desktop 1440×900, mobile 390×844): 0 overflow (document +
  shell root), active step visible, region scrollers not clipped, 0 console/page errors, demo chip
  present only in demo mode, no fake results in empty mode.

## Serving

Build → `dist/02_page.html` + hashed assets → serve on **:8348** (preview). Report dist hashes +
QA for orchestrator. :8347 untouched.

## Out of scope / open

- Real backend schemas still moving; this shell renders the agreed shapes and rejects unknown versions.
  When the orchestrator supplies verified artifacts + the current Stage-1 baseline, binding is a
  data-only step (no view rewrite).
- `cross_class` is replaced by `joint_status` (approved).
