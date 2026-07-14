# Visual/interaction QA — :8351 preview (commit f9d225e)

- **When (UTC):** 20260713T155937Z
- **Preview:** http://127.0.0.1:8351  (local; :8347 remains the frozen accepted deploy)
- **Viewports:** desktop 1440×900, narrow 390×844
- **Routes:** 01_page (Programs), targets, pathways, drugs, pksafety
- **Tooling:** pinned playwright-core + system Chrome, headless

## Result: PASS (no concrete visual defects)

| check | result |
|-------|--------|
| Horizontal overflow (all routes × both viewports) | 0px — none |
| Shared nav present + consistent | yes (5-route nav on every downstream route) |
| Tier-2 display labels on selection | "Naïve-like", "Activated" — resolved; **no raw ids** |
| Single "Methods & provenance" drawer on 02/03/04 | exactly 1 invoker; opens; BOTH methods+provenance sections; route-specific data-stage-label; no standalone methods/notebook/trace link inside |
| Standalone methods/notebook/trace links (any route) | none |
| Editorial/caveat blocks on canvas | none |
| Fixture/demo content (GENE_A/COMPOUND_A/fixture/demo/GBM context) | none |
| Banners on canvas | none on 02/03/04 |

## Single flag — investigated, NOT a defect
QA flagged one `role="alert"` on **programs.html only**: a HIDDEN, empty ARIA live-region
(`div.cterr`, the contrast-error announcer) — `visible=false`, empty text. This is a standard
accessibility live-region (populated only on a contrast error), not a visible editorial banner, and it
lives on the frozen Stage-1 baseline (not to be altered). All downstream 02/03/04 routes have zero
banner/alert elements. No code change made.

## Evidence
Screenshots (this dir): desktop__*/narrow__* per route, *__drawer (open drawer), targets__selected
(Tier-2 labels). Saved outside the served app.

## Human-visual spot check (screenshots opened)
- `desktop__targets__selected`: header "Naïve-like hi (at rest) → Activated hi (at rest)" (Tier-2 labels,
  no raw ids), single "Methods & provenance" button, 5-route nav (Targets active), neutral pending panel.
- `desktop__drugs__drawer`: single-title numbered-step drawer (Stage-1 grammar), route-specific Stage-3
  method/source/estimand/masks/upstream/method-id, one "No admitted Stage-3 bundle bound" status row
  (run rows omitted until admitted), References — no standalone links, no canvas editorial.
- `narrow__pksafety` (390px): graceful header truncation, drawer button collapses to icon, nav scrolls in
  its container, pending panel fits, no page overflow.

Screenshots (15) live in the out-of-app evidence dir (session scratchpad), not committed.
