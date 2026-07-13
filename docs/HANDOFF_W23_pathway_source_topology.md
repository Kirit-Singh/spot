# HANDOFF → W23: `current.json` names Reactome as a released + active pathway source

The formal release is **GO-BP-only**. The `current.json` served at :8347 declares
`active_pathway_source: "reactome"` and `sources: [reactome, go_bp]`. This is **not** a data
problem — the deterministic UI packager *requires* that topology. **No manual live edit**: fix the
source and rebuild.

## Exact source file
`_frontend/deploy/pack_ui_projections.mjs` — **not present on `agent/public-packaging`**, so this
lane did not (and must not) fork it. It has **three divergent blobs**; W23 must fix the one that
builds :8347 and reconcile the rest:

| blob | branch |
|---|---|
| `d542d838…` | `origin/agent/ui-final-integration` |
| `ace61dd0…` | `origin/agent/p2s-ui-admitted-seam` |
| `2d4cb7ef…` | `origin/agent/ui-compact-stage2`, `ui-route-decouple`, `ui-deploy-staging-fix` |

## The defect (line numbers per `ui-final-integration`)
```js
84:  const PATHWAY_SOURCES = ['reactome', 'go_bp'];          // hard-coded topology
...
328: const pathwaySources = exactList(release.pathway_sources, PATHWAY_SOURCES,
329:   'stage2 route.compact_release.pathway_sources');       // exactList == EXACT match, incl. order
330: const activeSource = nStr(release.active_pathway_source,
331:   'stage2 route.compact_release.active_pathway_source'); // nStr forbids null
332: if (!pathwaySources.includes(activeSource)) fail('stage2 active_pathway_source is not released');
```
`exactList` (l.291) fails unless the list equals `['reactome','go_bp']` **exactly**, and `nStr`
rejects `null`. So the packager **cannot** emit a GO-BP-only release and **cannot** emit a null
active source — it *mandates* Reactome. The released list is asserted, not derived.

## Required change
1. **Derive** the released source list from the **admitted topology** — never assert a constant.
2. Allowed = `['go_bp']`. Reactome is **PARKED**: parked licence/history record only, never a
   released or active source.
3. While the pathway lane is unadmitted, `active_pathway_source` must be **`null`** (or the explicit
   marker `"go_bp:awaiting_admission"`) — **never** Reactome.

```js
// Reactome is PARKED — parked licence/history only, never released or active.
const PATHWAY_SOURCES_ALLOWED = ['go_bp'];
const PATHWAY_SOURCES_PARKED  = ['reactome'];

// derive from the admitted topology; refuse any parked/unknown source
const pathwaySources = subsetOf(release.pathway_sources, PATHWAY_SOURCES_ALLOWED,
  'stage2 route.compact_release.pathway_sources');

// null is LEGAL while unadmitted — do not use nStr here
const activeSource = release.active_pathway_source ?? null;
if (activeSource !== null && activeSource !== 'go_bp:awaiting_admission') {
  if (PATHWAY_SOURCES_PARKED.includes(activeSource)) {
    fail('active_pathway_source is PARKED (reactome) — the release is GO-BP-only');
  }
  if (!pathwaySources.includes(activeSource)) {
    fail('active_pathway_source is not an admitted source');
  }
}
```
An `active_pathway_source` of `'go_bp'` is only legal once an **admitted** GO-BP pathway artifact is
in the topology — otherwise `null`.

## Regression to add (UI lane)
- an envelope with `pathway_sources: ['reactome','go_bp']` → packager **fails**;
- an envelope with `pathway_sources: ['go_bp']`, `active_pathway_source: null` → packager **passes**;
- `active_pathway_source: 'reactome'` → **fails**, whatever the list says.

## Already enforced on the packaging side (independent of W23)
`deploy/assemble_release.py` now refuses, so the formal release can never ship this envelope even if
the UI packager is not yet fixed:
- `pathway_sources` / `sources` listing a parked source → refused;
- `active_pathway_source: reactome` → refused;
- `active_pathway_source: 'go_bp'` with **no admitted GO-BP pathway artifact staged** → refused
  (the active source must be *derived* from the admitted topology, not asserted);
- `null` or `go_bp:awaiting_admission` while unadmitted → accepted;
- the same check runs over the deployable `dist/`, so a `current.json` naming Reactome refuses.

Tests: `deploy/tests/test_assemble_release.py::test_envelope_naming_reactome_as_a_released_source_is_refused`,
`…::test_envelope_claiming_active_go_bp_without_an_admitted_pathway_is_refused`,
`…::test_envelope_active_source_null_while_unadmitted_is_accepted`,
`…::test_dist_current_json_naming_reactome_is_refused`.

## Reconciliation
When W23's GO-BP-only `current.json` correction lands on `agent/ui-final-integration`, re-run the
packaging dry test against the rebuilt dist:
```bash
python3 deploy/assemble_release.py --spec deploy/release_spec.closeout.json \
    --staging-dir <abs dir outside repo> --dry-run
```
It must stop reporting any Reactome/topology refusal. Nothing is uploaded or deployed from here.
