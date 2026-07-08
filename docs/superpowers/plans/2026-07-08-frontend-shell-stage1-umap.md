# Frontend Shell + Stage-1 UMAP — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans. Steps use `- [ ]`.

**Goal:** Build the spot `_frontend` shell (5-tab funnel + progressive locking header) and
Stage-1 — an interactive CD4 phenotype UMAP tab — fed by the Claude Science phenotyping
artifact.

**Architecture:** React+Vite+TS+Tailwind SPA. A `pipeline` React context holds the locked
selection per stage and gates downstream tabs. Stage 1 renders a canvas UMAP colored by a
module score (default Treg) + a provenance panel; locking the program advances the
pipeline (header breadcrumb fills, stage 2 unlocks). Data = a portable JSON artifact the
Stage-1 CS specialist writes to `_frontend/public/stage01.json` (fallback: bundled fixture).

**Tech Stack:** React 18, Vite, TypeScript (strict), Tailwind v3, vitest +
@testing-library/react + jsdom, oxlint. Canvas 2D for the scatter (no new heavy dep).

## Global Constraints
- Node 22; TS strict; **≤500 lines/file**.
- **oxlint clean · tsc -b clean · vitest green** before every commit.
- Minimal deps — **remove `cytoscape`/`cytoscape-fcose`**; add no new runtime dep.
- Keep the light palette tokens in `tailwind.config.js`.
- Public data only; the fixture is synthetic. Work on branch `spot-v2-design`.
- Heavy analysis is NOT in the frontend — the Stage-1 CS specialist produces the data.

## File structure (`_frontend/src/`)
- `main.tsx`, `index.css` — keep.
- `App.tsx` — shell: `<PipelineProvider><Header/><Tabs/>{activeStage}</PipelineProvider>`.
- `shell/pipeline.tsx` — `STAGES`, `PipelineProvider`, `usePipeline()` (locked selections, active/unlocked).
- `shell/Header.tsx` — progressive breadcrumb.
- `shell/Tabs.tsx` — 5-tab nav; downstream tab disabled until prior stage locked.
- `stages/phenotypes/types.ts` — `PhenotypeArtifact` / `PhenotypeCell`.
- `stages/phenotypes/fixture.ts` — synthetic artifact.
- `stages/phenotypes/loadArtifact.ts` — fetch `public/stage01.json` → fixture fallback.
- `stages/phenotypes/UmapScatter.tsx` — canvas scatter.
- `stages/phenotypes/PhenotypesTab.tsx` — tab 1 (module selector + scatter + Lock + provenance).
- `stages/PlaceholderTab.tsx` — stages 2–5 stub.
- `provenance/ProvenancePanel.tsx` — source/method/markers with paper/CS-complement tags.
- **Remove:** `src/components/*`, `src/design/*`, `src/data/*` (fold any tokens into `tailwind.config.js`).

---

### Task 1: Reset `_frontend` to a clean shell
**Files:** modify `package.json` (name→`spot-frontend`, drop cytoscape deps), delete
`src/components/ src/design/ src/data/`, rewrite `src/App.tsx`; test `src/App.test.tsx`.
**Produces:** `App` renders the `spot` wordmark + an empty shell region.
- [ ] Write `src/App.test.tsx`: `render(<App/>)`; assert `screen.getByText('spot')` present.
- [ ] Run `npx vitest run src/App.test.tsx` → FAIL (App is old evidence-graph).
- [ ] `npm rm cytoscape cytoscape-fcose @types/cytoscape`; delete old dirs; rewrite `App.tsx` to a minimal `<div><h1>spot</h1></div>`.
- [ ] Run vitest → PASS; `npm run lint && npm run typecheck && npm run build` clean.
- [ ] Commit `reset(frontend): strip evidence-graph app, bare spot shell`.

### Task 2: Pipeline state + progressive header + 5-tab nav
**Files:** create `src/shell/pipeline.tsx`, `src/shell/Header.tsx`, `src/shell/Tabs.tsx`,
`src/stages/PlaceholderTab.tsx`; modify `App.tsx`; tests `src/shell/pipeline.test.tsx`.
**Interfaces (produces):**
```ts
// pipeline.tsx
export type StageId = 'phenotypes'|'geneskew'|'druglink'|'pkpd'|'trial'
export interface Stage { id: StageId; n: number; title: string; crumb: string }
export const STAGES: Stage[] // 5, titles "CD4 programs"… crumbs "Treg"…
export interface PipelineState { locks: Partial<Record<StageId,string>>; active: StageId }
export function usePipeline(): {
  state: PipelineState
  isUnlocked(id: StageId): boolean          // stage n unlocked iff stage n-1 locked (n=1 always)
  setActive(id: StageId): void
  lock(id: StageId, label: string): void    // record a locked selection label
}
export function PipelineProvider(props:{children:React.ReactNode}): JSX.Element
```
- [ ] Write `pipeline.test.tsx`: initial `active==='phenotypes'`, only `isUnlocked('phenotypes')` true; after `lock('phenotypes','Treg')`, `isUnlocked('geneskew')` true and `locks.phenotypes==='Treg'`.
- [ ] Run vitest → FAIL.
- [ ] Implement `pipeline.tsx` (context + reducer). `Header.tsx` renders `STAGES` as `crumb ›`… with locked selection labels shown; `Tabs.tsx` renders 5 buttons, disabled when `!isUnlocked`. `PlaceholderTab` shows "`<title>` — coming soon". `App.tsx` composes provider+header+tabs+active.
- [ ] Run vitest → PASS; add `src/shell/Header.test.tsx` (breadcrumb shows all 5 crumbs; locked stage shows its label) → PASS; lint/typecheck/build clean.
- [ ] Commit `feat(frontend): pipeline state + progressive header + tab gating`.

### Task 3: Stage-1 artifact schema + synthetic fixture
**Files:** create `src/stages/phenotypes/types.ts`, `src/stages/phenotypes/fixture.ts`;
test `src/stages/phenotypes/fixture.test.ts`.
**Interfaces (produces):**
```ts
export interface MarkerProv { gene: string; module: string; source: 'paper'|'CS-complement'; ref: string }
export interface PhenotypeCell { x: number; y: number; scores: Record<string, number>; donor: string; condition: string }
export interface PhenotypeArtifact {
  modules: string[]              // e.g. ['Treg','TH1',...]
  cells: PhenotypeCell[]
  provenance: { source: string; method: string; markers: MarkerProv[]; note?: string }
}
export const PHENOTYPE_MODULES_MIN = ['Treg']  // Treg must always be present
```
- [ ] Write `fixture.test.ts`: `fixture.modules.includes('Treg')`; every cell has a numeric `scores.Treg`; `provenance.markers` has ≥1 `source==='paper'` and ≥1 `'CS-complement'`.
- [ ] Run → FAIL.
- [ ] Implement `fixture.ts`: ~40 deterministic cells (2 donors × 2 conditions), modules `['Treg','TH1','TH17','Naive']`, a small `provenance` (source "Marson CD4 Perturb-seq (CZI)", method "scanpy score_genes, paper-anchored", markers FOXP3/CTLA4 paper + one CS-complement).
- [ ] Run → PASS; typecheck clean. Commit `feat(frontend): stage-1 artifact schema + fixture`.

### Task 4: Canvas UMAP scatter
**Files:** create `src/stages/phenotypes/UmapScatter.tsx`; test `.../UmapScatter.test.tsx`.
**Interfaces (produces):**
```ts
export function UmapScatter(props: {
  cells: PhenotypeCell[]; colorModule: string; onHover?: (i:number|null)=>void
}): JSX.Element   // <canvas>; points at (x,y) scaled to canvas; color = viridis(scores[colorModule] in [0,1])
```
- [ ] Write test: render with fixture; assert a `<canvas>` exists and the component exposes `data-points={cells.length}` on a wrapper div (used to assert draw count without a real GL context).
- [ ] Run → FAIL.
- [ ] Implement: `useRef` canvas; `useEffect` fits x/y to canvas box (min/max normalize + padding), clears, draws each cell as a 3px filled arc, fill from a small `viridis(t)` helper (5-stop lerp). Wrapper div carries `data-points`. `onHover` optional (nearest-point on mousemove).
- [ ] Run → PASS; lint/typecheck/build clean. Commit `feat(frontend): canvas UMAP scatter colored by module score`.

### Task 5: PhenotypesTab — selector + scatter + lock
**Files:** create `src/stages/phenotypes/PhenotypesTab.tsx`; modify `App.tsx` (route
active `phenotypes`→this); test `.../PhenotypesTab.test.tsx`.
**Consumes:** `usePipeline`, `PhenotypeArtifact`, `UmapScatter`. **Produces:** the stage-1 UI.
- [ ] Write test: render inside `PipelineProvider` with fixture (passed as prop for now); a `<select>` of modules (default 'Treg') recolors (assert `UmapScatter` gets `colorModule` via a `data-color` passthrough); clicking **Lock program** calls `lock('phenotypes','Treg')` → breadcrumb shows "Treg" and stage-2 tab enabled.
- [ ] Run → FAIL.
- [ ] Implement: module `<select>` (state `colorModule`, default 'Treg'), `<UmapScatter cells colorModule/>`, a "Lock program" button → `lock('phenotypes', colorModule)` + `setActive` stays (user advances via tab). Show cell count.
- [ ] Run → PASS; lint/typecheck/build clean. Commit `feat(frontend): stage-1 phenotypes tab (UMAP + module lock)`.

### Task 6: Provenance panel
**Files:** create `src/provenance/ProvenancePanel.tsx`; modify `PhenotypesTab.tsx`;
test `.../ProvenancePanel.test.tsx`.
**Interfaces:** `ProvenancePanel(props:{ provenance: PhenotypeArtifact['provenance'] })`.
- [ ] Write test: renders `source`, `method`, and each marker with a visible tag badge
  ('paper' vs 'CS-complement'); a paper marker and a CS-complement marker both shown.
- [ ] Run → FAIL. Implement (source/method lines + a small markers list, badge colored by source). Wire under the scatter in `PhenotypesTab`.
- [ ] Run → PASS; lint/typecheck/build clean. Commit `feat(frontend): provenance panel (paper vs CS-complement)`.

### Task 7: Artifact loader + real-data wiring
**Files:** create `src/stages/phenotypes/loadArtifact.ts`; modify `PhenotypesTab.tsx`
(load on mount); create `_frontend/public/.gitkeep`; test `.../loadArtifact.test.ts`.
**Interfaces:** `async function loadPhenotypeArtifact(): Promise<PhenotypeArtifact>` —
`fetch('/stage01.json')`; on non-ok/parse-fail return `fixture`; validate shape (modules incl Treg, cells array) else fixture.
- [ ] Write test: mock `fetch` → 404 returns fixture; mock → valid JSON returns parsed; mock → malformed returns fixture.
- [ ] Run → FAIL. Implement loader; `PhenotypesTab` calls it in `useEffect`, holds artifact in state (fixture as initial). 
- [ ] Run → PASS; build clean. Commit `feat(frontend): stage-1 artifact loader (public/stage01.json → fixture)`.
- [ ] **Handoff note (not a code step):** the Stage-1 CS specialist writes its portable table as `_frontend/public/stage01.json` matching `PhenotypeArtifact`; document this contract in `01_phenotypes/README.md`.

### Task 8: Frontend CI
**Files:** create `.github/workflows/frontend.yml`.
- [ ] Add workflow: on push/PR, Node 22, `working-directory: _frontend`, `npm ci` then
  `npm run lint`, `npm run typecheck`, `npm run test`, `npm run build` as named jobs.
- [ ] Push; confirm the 4 jobs pass on `spot-v2-design`.
- [ ] Commit `ci(frontend): lint/typecheck/test/build for _frontend`.

## Self-review
- **Spec coverage:** Stage-1 tab + UMAP + provenance + progressive header + pipeline gating
  ✔ (spec §Frontend, §Stage 1, §Pipeline+provenance). Stages 2–5 = placeholders this
  sub-project (own plans later). CS-produces-the-data ✔ (Task 7 handoff).
- **Placeholders:** none — Stage 2–5 stubs are an explicit scope boundary, not TBDs.
- **Type consistency:** `PhenotypeArtifact`/`PhenotypeCell`/`StageId`/`usePipeline` names
  used identically across Tasks 2–7.
