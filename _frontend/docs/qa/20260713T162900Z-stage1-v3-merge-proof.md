# Stage-1 v3 merge — integration proof + QA (20260713T162900Z)

Merged `origin/stage1-canonical-ui-cleanup` (184211a = v3 tip 9a2f6cf + hash-fallback 9e9ef08 + 5-route
cleanup) into agent/ui-stage234 → merge commit d8d72d8. Clean auto-merge, **0 conflicts** (the UI branch
never touched 01_programs/; the Stage-1 branch never touches _frontend/, so nav/drawer/styling/links are
preserved untouched). Branch's 01_programs/app/01_page.html now byte-identical to served
_frontend/public/01_page.html (570a6f07, v3). No scientific artifact or hash changed.

## Browser proof (preview :8351, commit d8d72d8)
| claim | result |
|---|---|
| same-condition A/B → v3 within_condition ready | ✅ schema spot.stage01_selection.v3, analysis_mode within_condition, execution_status **ready**, estimator available (diff_naive high vs diff_activated high @ Rest) |
| different ordered conditions → v3 temporal_cross_condition ready | ✅ analysis_mode temporal_cross_condition, execution_status **ready** (Rest→Stim8hr, estimator available) |
| Identify stores ONLY spot.stage01_selection.v3, routes to targets.html | ✅ v3 stored (both stores), v1 **not** stored; landed on /targets.html |
| no v1 emission/read | ✅ served 01_page.html: v3 key present, **zero** setItem(...v1); v1 never written |
| downstream joinPlan resolves the exact two Direct/temporal/pathway arm keys | ✅ contract embeds direct\|diff_naive\|decrease\|Rest + direct\|diff_activated\|increase\|Rest + the two pathway_arm_key bases; joinResolver 7/7 |

## QA (desktop 1440×900 + narrow 390×844, all 5 routes): PASS
0px overflow; consistent 5-route nav; Tier-2 labels resolve (no raw ids); single Methods & provenance
drawer on 02/03/04; no standalone methods/notebook/trace links; no visible banners, editorial blocks, or
fixture/demo content. 10 screenshots in the out-of-app evidence dir.

## Gate
tsc clean · 417 vitest · build ok · fixture-scan clean. :8347 NOT promoted.
