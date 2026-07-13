# Spot stage UI — design contract

Implementation contract extracted from the **approved live Stage-1 baseline** (`:8347/01_page.html`,
SHA-256 `c0a84e2f…`, snapshot `~/.spot-runs/20260712T021343Z/ui-baseline-8347/`). The Stage-2/3/4 shell
(`/02_page.html`) must match these tokens and structural rules so the five stages read as one product.
This is an engineering spec, not product copy.

## Type
Loaded from Google Fonts (`Inter+Tight:400,500,600`, `Newsreader:500` optical, `IBM+Plex+Mono:400,500`).
- **UI / body:** `'Inter Tight', system-ui, sans-serif`. Weights 400/500/600 only.
- **Serif accent** (`--serif`): `'Newsreader', serif` — used sparingly for display headings.
- **Mono / data** (`--mono`): `'IBM Plex Mono', monospace` — ids, hashes, numeric cells, code, the `NN` step numerals.
- Base UI text ~11–13px; nav uses `clamp(10.5px,1.2vw,13px)`; data cells 11–11.5px. No font below ~10px except the auto-fit `#lastrun` line (7px floor).

## Color tokens (CSS custom properties on `:root`)
| token | value | role |
|---|---|---|
| `--bg` | `#FAF9F7` | app background (warm off-white) |
| `--surface` | `#FFFFFF` | bars, rails, cards |
| `--sunken` | `#F4F2EE` | inset/disabled control fill |
| `--line` | `#E7E3DC` | all hairline borders/dividers |
| `--ink` | `#1E1B16` | primary text |
| `--ink2` | `#5C564C` | secondary text |
| `--muted` | `#8A8172` | tertiary/placeholder, inactive nav |
| `--accent` | `#3E7D8C` | teal — active state, focus, primary emphasis |
| `--treg` | `#9A3E9C` | magenta — regulatory-program semantic color; not an axis identity |
| `--pole-a` | `#2D7C8E` | teal — ordered A/From axis |
| `--pole-b` | `#D69834` | amber — ordered B/To axis |
Data heatmap cells use a viridis ramp (low→high); missing = neutral grey, degenerate = flat neutral (`rgb(176,172,164)`). Never introduce new hues outside this set without a token.

## Shape
- **Radii:** controls/selects/buttons `7px`; segmented groups + nav steps `9px`; cards/menus `11px`; small pills `3–6px`.
- **Borders:** `1px solid var(--line)` everywhere; no heavier rules.
- **Shadows** (only two): floating card/menu `0 8px 28px rgba(30,27,22,.16)`; small popover `0 2px 9px rgba(30,27,22,.12)`. Active selection uses an **inset** ring `inset 0 0 0 1.5px var(--accent)`, not a drop shadow.
- Density is compact and calm — generous line color contrast, tight control padding, no gradients except the viridis legend + the contrast belt.

## Structure
- Full-viewport `flex` column, `height:100vh; overflow:hidden`. Three bands top→bottom:
  1. **Top bar** — `height:50px`, `padding:0 20px`, `border-bottom:1px solid --line`, `background:--surface`. Left: `spot·` brand + subhead + citation. Right: `Links` and `Methods & provenance` tab-buttons (`.methodstab`).
  2. **Stage rail** (`.nav`) — horizontal, `padding:10px 20px`, hairline bottom border. Steps `.nstep` (`padding:6px 12px; radius:9px; color:--muted; weight:500`) separated by `›` in `#D9D3C8`. Active step `.on` = `--ink`, weight 600, inset accent ring, accent numeral. Available step = an `<a class="nstep step">` (base muted, `cursor:pointer`, hover→`--ink`). Disabled step `.off` = `opacity:.5; cursor:not-allowed`.
  3. **Body** — Stage 1 uses `minmax(0,1fr) 340px`: a main canvas plus a 340px information rail. Stage 2 retains that split where pathway support is a real secondary rail. Stages 3/4 use the full content width because their cards/scorecards are the primary object; do not add an empty 340px rail merely for symmetry.

## Controls
- **Select** (`.axsel`): `font-size:11.5px; radius:7px; border:1px solid --line; padding:4px 18px 4px 7px`, custom SVG chevron, `:hover{border-color:--accent}`. No native appearance.
- **Primary action button** (`.idbtn`): `height:27px; font 11px/600; radius:7px`. Enabled = accent-forward; disabled = `--sunken` fill, `--muted` text, `cursor:not-allowed`.
- **Segmented control** (`.seg`): `border:1px solid --line; radius:9px; overflow:hidden`; the selected segment is accent-filled. Used for condition/donor filters — reuse for any enum picker.
- Direction/pole chips follow the approved live `:8347` baseline: `A/From` = teal `--pole-a`, `B/To` = amber `--pole-b`. Program-semantic colors such as `--treg` do not redefine ordered axis identity.

## Data tables
- The programs-over-time grid is the table pattern: right-aligned `--mono` numeric cells on a **shared** viridis scale, compact row height, a mono column header row, hairline separators, an `ND` token for not-detected. Reuse this for Stage-2/3/4 tabular output — shared-scale heat cells, mono numerals, no zebra striping.

## Responsive
Breakpoints at `1080 / 1000 / 880 / 720 / 430 px`. Behavior to preserve:
- Right rail narrows then **stacks below** the main pane; the grid collapses to a single column.
- The stage rail becomes `overflow-x:auto; white-space:nowrap` (horizontal scroll) — never wraps.
- The contrast/action bar collapses behind a `Skew ▾` toggle on narrow widths.
- Use relative units + `max-width:100%`; the page body never scrolls horizontally (wide content scrolls inside its own container).

## Navigation
- Stage rail navigation routes to the hash-router shell: the cross-document Stage-1/Stage-2 transition is an anchor; in-shell Stage 2/3/4 transitions are semantic buttons that update the hash route. `Stage 02 → /02_page.html#/stage-2`, `03 → #/stage-3`, `04 → #/stage-4`. **Stage 05 stays disabled** (`.nstep.off`).
- Stage 1 hands off the selection by writing the **`spot.stage01_selection.v3`** contract (the exact shape `stage2_bridge/emit_selection_contract.build_contract` emits — verified byte-identical to the browser build in `test_selection_v3_browser.mjs`) to the single versioned `localStorage` key `spot.stage01_selection.v3` and to `window.__stage01SelectionArtifact`, then navigating to `/02_page.html#/stage-2`. The shell reads that key on load and MUST re-verify the contract with `verify_selection_contract` before use.
- The v3 contract carries typed routing (`execution_status` ∈ ready/refused/awaiting_estimator, `analysis_mode`, `estimator_id`/`estimator_status`, per-pole `effect_projection_status`), `canonical_content` bound to the citation-invariant **scorer VIEW** hash (`registry_scorer_view_sha256`, NOT the primary-registry hash), and `selection_id` + `full_contract_content_sha256` recomputed in-browser. There is **no** production/research split, `namespace`, or `production_gate_passed` field — those retired v2 fields must never reappear.
