# spot frontend — design system

The signature screen **is** a central knowledge graph: one real hit at the
center radiating to context-matched public datasets. Light, scientific, crafted.
Synthesized from a Fable visual pass + a Claude Science data-grounded pass, and
mirrored in a Claude Design project ("spot — evidence graph") kept in sync via
`design-sync`.

## Tokens (code source of truth: `frontend/src/design/tokens.ts`)
- **Surfaces:** bg `#FAF9F7` (warm paper), surface `#FFFFFF`, sunken `#F4F2EE`, line `#E7E3DC`.
- **Text:** ink `#1E1B16`, ink-2 `#5C564C`, muted `#8A8172`.
- **Evidence type (hue owns "what kind"):** replication teal `#0E7C86` · consistency indigo `#4C56C0` · genetic violet `#9A3E9C` · predictive bronze `#9A6B12`.
- **State (reserved, orthogonal):** confirmed solid · untested dashed 45% · contradicted burnt-orange `#C2410C` (never red). Center hit ring `#111827` + gold confirm aura `#FFB020`.
- **Type:** Inter Tight (UI) · Newsreader serif (hit title + provenance headlines only) · IBM Plex Mono (every stat/query/ID).

## Encoding — three orthogonal channels
hue = evidence type · width = strength · dash/opacity/marker = state. Never
double-encode. **Shape singularity:** the center hit is the only rounded-
rectangle; every dataset node is a circle.

## Layout
Full-bleed graph canvas; left legend + filter rail; right provenance drawer (the
trust surface: claim in serif, mono stat block, the exact query, a passed/failed
checks ledger). Six fixed axis sectors: target · cell type · disease ·
population · context · modality.

## Motion
Edges "light up" (dashed->solid draw + a traveling pulse in the type hue) only
when a real check resolves; the center gold aura brightens with confirmed/total.

## Seed data
Centered on **RASA2** (CRISPRi, CD4+ T) from Marson2025 GWCD4i — a real hit with
an independent CAR-T replication dataset (Carnevale 2022). Full spec:
`frontend/src/data/seed_graph_spec.json` (Claude Science, grounded in the real
DE-stats columns).

## Build order
Cytoscape stylesheet + tokens (done) -> fixed-sector fcose layout -> provenance
drawer -> wire edge-resolve animation to the live confirmation stream (Lane A).
