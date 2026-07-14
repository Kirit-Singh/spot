// GO-BP-ONLY RELEASE RULE — the negative gate.
//
// The critical-path release declares exactly ONE pathway source: go_bp. Reactome is PARKED. It is a
// real historical input and keeps its licence/history record in the repo, but it must never be
// DECLARED by anything the deploy serves:
//   · results/current.json must not name it in pathway_sources or as active_pathway_source
//   · the packed spec that produces current.json must be refused if it names it
//   · the served Pathways method manifest must not advertise it as a co-input (no data_input mention,
//     no source_chain record with a licence/URL/hashes, no coverage figure)
//
// A live audit of :8347 found current.json declaring ["reactome","go_bp"] with active "reactome"
// while the admitted projection was direct+temporal only (zero pathway arms). The bytes were honest;
// the METADATA was not. These tests make that state unreachable, at the trust boundary rather than by
// convention — the adapter is what the browser runs before it trusts anything current.json names.

import { describe, expect, it } from 'vitest';

import { parseUiResultsCurrent } from '../uiResultsCurrentAdapter';
import { buildStageMethodsManifest } from '../../mpa/stageMethods';

const H = 'a'.repeat(64);
const BINDING = {
  release_method_version: 'stage1-continuous-v3.0.1',
  registry_scorer_view_sha256: H,
  selection_schema_raw_sha256: H,
  release_self_sha256: H,
};
const CHAIN = {
  stage2_display_release_id: 'stage2-display-1',
  stage2_run_id: null,
  stage3_bundle_id: null,
  stage4_scorecard_set_id: null,
};

/** A GO-BP-only compact release — the ONLY shape the deploy may serve. */
const COMPACT_GO_BP = {
  schema_version: 'spot.ui_compact_stage2_release.v1',
  display_release_id: 'stage2-display-1',
  release_conditions: ['Rest', 'Stim8hr', 'Stim48hr'],
  pathway_sources: ['go_bp'],
  active_pathway_source: 'go_bp',
  projection_raw_sha256: H,
  projection_canonical_sha256: H,
  projection_self_sha256: H,
  independent_verifier: {
    verifier_id: 'spot.stage02.display_projection.independent_verifier.v1',
    receipt_path: 'stage02/display_projection.verification.json',
    receipt_raw_sha256: H,
    receipt_canonical_sha256: H,
  },
};

function current(compact: unknown): unknown {
  return {
    schema: 'spot.ui_results_current.v1',
    stage1_binding: BINDING,
    chain: CHAIN,
    routes: {
      targets: {
        manifest_path: 'manifests/targets.ui_release.json',
        content_hash: H,
        projection_path: 'stage02/stage2_display_projection.json',
        projection_content_hash: H,
        compact_stage2: compact,
      },
    },
  };
}

describe('results/current.json — GO-BP-only release, Reactome refused at the trust boundary', () => {
  it('ACCEPTS the GO-BP-only release', () => {
    const parsed = parseUiResultsCurrent(current(COMPACT_GO_BP));
    expect(parsed.routes.targets?.compact_stage2?.pathway_sources).toEqual(['go_bp']);
    expect(parsed.routes.targets?.compact_stage2?.active_pathway_source).toBe('go_bp');
  });

  it('REFUSES the exact live-audit finding: pathway_sources ["reactome","go_bp"], active "reactome"', () => {
    expect(() =>
      parseUiResultsCurrent(
        current({ ...COMPACT_GO_BP, pathway_sources: ['reactome', 'go_bp'], active_pathway_source: 'reactome' }),
      ),
    ).toThrow(/pathway_sources must be exactly \[go_bp\]/);
  });

  it('REFUSES Reactome in pathway_sources even when the active source is go_bp', () => {
    expect(() =>
      parseUiResultsCurrent(
        current({ ...COMPACT_GO_BP, pathway_sources: ['reactome', 'go_bp'], active_pathway_source: 'go_bp' }),
      ),
    ).toThrow(/pathway_sources must be exactly \[go_bp\]/);
  });

  it('REFUSES Reactome as the active source even when pathway_sources is go_bp-only', () => {
    expect(() =>
      parseUiResultsCurrent(current({ ...COMPACT_GO_BP, active_pathway_source: 'reactome' })),
    ).toThrow(/active_pathway_source must be "go_bp"/);
  });

  it('REFUSES a reordered / padded source list (go_bp must be the ONLY entry)', () => {
    for (const sources of [['go_bp', 'reactome'], ['go_bp', 'go_bp'], [], ['reactome']]) {
      expect(() =>
        parseUiResultsCurrent(current({ ...COMPACT_GO_BP, pathway_sources: sources })),
      ).toThrow(/pathway_sources must be exactly \[go_bp\]/);
    }
  });
});

describe('served Pathways method manifest — Reactome is not advertised as a released co-input', () => {
  it('the resolved Pathways manifest names GO-BP and mentions Reactome NOWHERE', async () => {
    const m = await buildStageMethodsManifest('pathways');
    const served = JSON.stringify(m);
    // GO-BP is the one released gene-set source, with its real licence + pinned bundle hash
    expect(m.provenance.source_chain.some((s) => /GO Biological/.test(s.label) && s.license === 'CC BY 4.0')).toBe(true);
    // …and Reactome appears in no field the page serves: not data_input, not a source record,
    // not a coverage figure, not a URL.
    expect(served).not.toMatch(/reactome/i);
  });

  it('every other stage manifest is likewise free of a Reactome declaration', async () => {
    for (const page of ['targets', 'drugs', 'pksafety'] as const) {
      const m = await buildStageMethodsManifest(page);
      expect(JSON.stringify(m)).not.toMatch(/reactome/i);
    }
  });
});
