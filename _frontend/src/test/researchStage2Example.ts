// Test/QA support: build a minimal VALID research-only Stage-2 artifact bound to a
// given research selection. Used to exercise the research-artifact adapter seam
// (selection-id / namespace / provenance binding). Not shipped in the default shell.

import { h64 } from '../fixtures/synthetic';

type SelectionRaw = { selection_id: string; contrast_id: string; namespace: string } & Record<string, unknown>;

export function makeResearchStage2(selection: SelectionRaw) {
  const canonical = h64('re5ea2c4');
  return {
    provenance: {
      artifact_id: `research_only:stage02:${selection.selection_id.toLowerCase().replace(/[^a-z0-9_]/g, '_')}@${canonical.slice(0, 12)}`,
      schema_version: 'spot.stage02_gene_lever_set.v1',
      namespace: 'research_only',
      production_eligible: false,
      hashes: { raw_sha256: h64('ab' + 're5ea2c4'), canonical_sha256: canonical },
      method: {
        method_id: 'target_masked_measured_effect_screen.research',
        config_id: 'research_config_demo',
        code_ref: 'git://spot/02_geneskew@research',
        env_ref: 'conda://spot-stage2-research',
      },
      sources: [],
      cs_session: { session_ref: 'research-session', frame_ref: 'research-frame' },
      upstream_ref: null,
    },
    selection,
    tested_family_size: 42,
    significance_calibrated: false,
    joint_ordering_method_id: 'pareto_joint_order.research.v1',
    levers: [
      {
        gene_id: 'RESEARCH_GENE_1',
        ensembl_id: 'ENSG00000000001',
        arms: {
          away_from_A: { evaluated: true, reason: null, effect: -0.37, rank: 1, coverage: 0.81 },
          toward_B: { evaluated: false, reason: 'B pole unrepresented at Stim48hr', effect: null, rank: null, coverage: null },
        },
        joint_status: 'a_only',
        pareto_tier: 1,
        marker_breadth: { supporting_markers: 3, single_marker_driven: false, detail: null },
        evidence: {
          guides: [{ guide_id: 'GUIDE_1', effect: -0.35, sign_agrees: true }],
          donor_support: { effective_n: 4, denominator: 'NTC guides at Stim48hr', pair_discordance: false },
          on_target_detected: true,
          perturb2state: 'direct_only',
          depmap: { status: 'non_essential', detail: null },
          support_status: 'screen_only',
          source_links: [{ label: 'stage02_screen', url: null, detail: 'row for RESEARCH_GENE_1' }],
        },
      },
    ],
    pathways: [],
  };
}
