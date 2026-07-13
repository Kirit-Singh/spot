// REAL per-tab method-DEFINITION manifest (coordinator integration blocker + science/deploy audit):
//  · the drawer carries real method_id / estimand / sources, content-addressed against a PINNED hash
//    (not self-sealed), loaded INDEPENDENT of admission;
//  · stage_label AND source_tissue are pinned INSIDE the hashed content — a one-byte mutation of
//    EITHER (or of any bound source hash) is REJECTED (content_hash_mismatch), and a manifest cannot
//    be relabelled onto another stage (stage_label_mismatch firewall);
//  · reproduce_command is NULL on every route until an admitted bundle is bound — a command may
//    reproduce only an admitted artifact, never a generic --help-valid invocation;
//  · the drawer RENDERS each PRESENT source hash; an absent raw/canonical subfield is OMITTED (never
//    an "unavailable" filler row);
//  · UNBOUND run provenance collapses to ONE terse route status row with ZERO "unavailable" filler
//    (null definition fields are omitted); a command shows only when it reproduces an admitted artifact;
//  · targets / pathways / drugs / pksafety differ; NO batch / confound / replicate wording;
//  · manifestFromProvenance never promotes a cs_session frame_ref into cs_notebook_url.

import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import {
  buildStageMethodsManifest,
  stageMethodsRaw,
  STAGE_METHODS_HASHES,
  computeStageMethodsHashes,
  stageLabelFor,
} from '../stageMethods';
import { parseStageMethodsManifest } from '../../adapters/methodsManifestAdapter';
import { AdapterError } from '../../adapters/errors';
import { manifestFromProvenance } from '../../domain/methodsManifest';
import type { Provenance } from '../../domain/common';
import { StageIsland } from '../StageIsland';
import { ProvenanceDrawer } from '../../shell/ProvenanceDrawer';
import { mergeAdmittedManifest } from '../../adapters/uiReleaseManifestAdapter';
import { UI_RELEASE_SCHEMA_VERSION } from '../../domain/uiReleaseManifest';
import type { UiReleaseManifest } from '../../domain/uiReleaseManifest';
import { PAGES } from '../pages';
import type { PageKey } from '../pages';

const NO_BATCH = /batch|confound|replicate|reliab/i;
const DOWNSTREAM = ['targets', 'pathways', 'drugs', 'pksafety'] as const;

// verified content addresses used in rendering assertions (from the geneset-cache provenance +
// GWCD4i.DE_stats primary source; see stageMethods.ts constants)
const MARSON_DE_RAW = 'c355f535ff32cf7ba1edc49cf9c6039fe84f2c9ebe4d005515cba75790cfbb62';
const REACTOME_CANON = '9cc416d14a16ff4bdbf700780e67d40a6f88c5235690fadc79abab83fd68218e';
const GO_CANON = '5b62e8bc36cb798ec615c078bc1c8ee2d3331d61dafb24d80cac6b18ab3bc310';

function methodText(m: Awaited<ReturnType<typeof buildStageMethodsManifest>>): string {
  const mm = m.methods;
  return [
    mm.data_input, mm.source_tissue, mm.estimand, mm.masks_qc, mm.upstream_model, ...mm.limitations,
    mm.method_id, mm.environment, mm.reproduce_command,
    ...m.provenance.source_chain.map((s) => `${s.label} ${s.record_id} ${s.license ?? ''}`),
  ].filter(Boolean).join(' \n ');
}

describe('buildStageMethodsManifest — real, method-def vs run-status', () => {
  it('binds real method-definition fields + public sources for every page', async () => {
    const t = await buildStageMethodsManifest('targets');
    expect(t.stage_label).toBe('Targets'); // canonical label — PART of the hashed content
    expect(t.methods.method_id).toBe('spot.stage02.direct.masked_program_projection · spot.stage02.pareto.two_arm.v1 · spot.stage02.temporal_cross_condition.v1');
    expect(t.methods.estimand).toMatch(/difference-in-differences/);
    expect(t.provenance.source_chain.some((s) => /Marson GWCD4i/.test(s.label) && s.raw_sha256)).toBe(true);
    expect(t.provenance.release_revision).toBeNull(); // Stage-1 release is UPSTREAM only
    expect(t.provenance.source_chain.some((s) => /upstream/i.test(s.label) && s.canonical_sha256)).toBe(true);

    const p = await buildStageMethodsManifest('pathways');
    expect(p.methods.method_id).toBe('spot.stage02.pathway.ranked_arm_enrichment.v2 · spot.stage02.pathway.signature_convergence.v2');
    expect(p.provenance.source_chain.some((s) => s.label === 'Reactome' && s.license === 'CC0-1.0' && s.url)).toBe(true);
    expect(p.provenance.source_chain.some((s) => /GO Biological/.test(s.label) && s.license === 'CC-BY-4.0' && s.url)).toBe(true);

    const d = await buildStageMethodsManifest('drugs');
    expect(d.methods.method_id).toBe('stage3-druglink-v4-workflow-states · schema spot.stage03_drug_annotation.v1');
    expect(d.provenance.source_chain.some((s) => s.label === 'ChEMBL 37' && s.license === 'CC BY-SA 3.0' && s.url)).toBe(true);
    expect(d.provenance.source_chain.some((s) => /UniProt/.test(s.label) && s.license === 'CC BY 4.0' && s.url)).toBe(true);

    const k = await buildStageMethodsManifest('pksafety');
    expect(k.methods.method_id).toBe('stage4-evidence-v2 · cns_mpo_wager2010_v1 · nebpi_source_framing_v2 · safety_taxonomy_v2');
    expect(k.provenance.source_chain.some((s) => /Grossman/.test(s.label) && s.license === 'CC BY 4.0' && s.canonical_sha256)).toBe(true);
  });

  it('the canonical stage_label agrees with the nav route label for every downstream page', () => {
    for (const page of DOWNSTREAM) {
      const nav = PAGES.find((pg) => pg.key === page);
      expect(nav).toBeTruthy();
      expect(stageLabelFor(page)).toBe(nav!.label); // Targets / Pathways / Drugs / PK & Safety
    }
  });

  it('leaves EVERY result-run field "unavailable"; no code identity is shown stale', async () => {
    for (const page of DOWNSTREAM) {
      const m = await buildStageMethodsManifest(page);
      expect(m.methods.last_run_utc).toBeNull();
      expect(m.methods.method_code_sha256).toBeNull();
      expect(m.methods.environment).toBeNull();
      expect(m.provenance.release_revision).toBeNull();
      expect(m.provenance.raw_sha256).toBeNull();
      expect(m.provenance.canonical_sha256).toBeNull();
      expect(m.provenance.generator_status).toBeNull();
      expect(m.provenance.verifier_status).toBeNull();
      expect(m.provenance.artifact_paths).toEqual([]);
      expect(m.provenance.cs_notebook_url).toBeNull();
      expect(m.methods.method_id).toBeTruthy();
      expect(m.methods.estimand).toBeTruthy();
      expect(m.methods.source_tissue).toBeTruthy(); // source-backed tissue fact, stated pre-run
      expect(methodText(m)).not.toMatch(/0315b99|40bb6539|2c73218|fixture|\bdemo\b/i);
    }
  });

  it('the four pages differ (method_id + estimand)', async () => {
    const ms = await Promise.all(DOWNSTREAM.map((p) => buildStageMethodsManifest(p)));
    expect(new Set(ms.map((m) => m.methods.method_id)).size).toBe(4);
    expect(new Set(ms.map((m) => m.methods.estimand)).size).toBe(4);
  });

  it('carries NO batch / confound / replicate / reliability wording (machine-only fields)', async () => {
    for (const page of DOWNSTREAM) {
      const m = await buildStageMethodsManifest(page);
      expect(methodText(m)).not.toMatch(NO_BATCH);
    }
    const t = await buildStageMethodsManifest('targets');
    expect(t.methods.estimand).toMatch(/population program-projection difference-in-differences/);
    expect(t.methods.masks_qc ?? '').toMatch(/frozen 30-kb/);
    expect(t.methods.masks_qc ?? '').not.toMatch(/~/);
  });

  it('targets Methods discloses the UPSTREAM ontarget_significant eligibility, consumed verbatim (spot emits no p/q/FDR)', async () => {
    const t = await buildStageMethodsManifest('targets');
    const blob = `${t.methods.masks_qc ?? ''} ${t.methods.limitations.join(' ')}`;
    expect(blob).toMatch(/ontarget_significant/);
    expect(blob).toMatch(/Marson GWCD4i release'?s own DESeq2/i);
    expect(blob).toMatch(/verbatim/i);
    expect(blob).toMatch(/no p \/ q \/ FDR of its own/i); // spot does NOT reinterpret it as its own inference
    expect(blob).toMatch(/missing_qc:ontarget_significant/);
  });

  it('pathways preserves the TWO-universe design and per-lane coverage (never blended, not bounded by 10,282)', async () => {
    const p = await buildStageMethodsManifest('pathways');
    const est = p.methods.estimand ?? '';
    // enrichment lane = perturbation-target universe; convergence lane = DE-readout universe
    expect(est).toMatch(/perturbation-target universe \(11,526 = 11,522 ENSG \+ 4 symbol-only/);
    expect(est).toMatch(/10,282-gene DE-readout universe/);
    const lims = p.methods.limitations.join(' ');
    // exact per-lane source-coverage denominators, not conflated
    expect(lims).toMatch(/39\.6069%/); // Reactome, target-enrichment lane
    expect(lims).toMatch(/51\.4288%/); // GO-BP, target-enrichment lane
    expect(lims).toMatch(/40\.1817%/); // Reactome, DE-readout convergence lane
    expect(lims).toMatch(/56\.5884%/); // GO-BP, DE-readout convergence lane
    expect(lims).not.toMatch(/bounded by the 10,282-gene measured universe/);
    // the real, verified gene-set canonical hashes (moved from record_id text into the hash field)
    expect(p.provenance.source_chain.find((s) => s.label === 'Reactome')?.canonical_sha256).toBe(REACTOME_CANON);
    expect(p.provenance.source_chain.find((s) => /GO Biological/.test(s.label))?.canonical_sha256).toBe(GO_CANON);
  });

  it('pksafety lists DailyMed + openFDA as method sources with W8 licensing and NO evidence before acquisition', async () => {
    const k = await buildStageMethodsManifest('pksafety');
    const dm = k.provenance.source_chain.find((s) => /DailyMed/.test(s.label));
    const of = k.provenance.source_chain.find((s) => /openFDA/i.test(s.label));
    expect(dm).toBeTruthy();
    expect(of).toBeTruthy();
    // DailyMed: no verified blanket open-data licence; openFDA: CC0 with marked exceptions
    expect(dm!.license).toMatch(/No blanket licence verified/i);
    expect(of!.license).toMatch(/CC0/);
    expect(of!.license).toMatch(/exceptions/i);
    // no response has been acquired → hashes + retrieval null (never implies supplied evidence)
    for (const s of [dm!, of!]) {
      expect(s.raw_sha256).toBeNull();
      expect(s.canonical_sha256).toBeNull();
      expect(s.retrieval_utc).toBeNull();
    }
    // PK also declares its Stage-3 reuse-only + live-acquisition sources
    const labels = k.provenance.source_chain.map((s) => s.label).join(' | ');
    expect(labels).toMatch(/ChEMBL 37 \(reused from Stage 3; Stage-4 reuse-only\)/);
    expect(labels).toMatch(/UniProt 2026_02 \(reused from Stage 3; Stage-4 reuse-only\)/);
    expect(labels).toMatch(/PubChem PUG REST/);
    expect(labels).toMatch(/RxNorm/);
  });

  it('Methods↔References agree: Targets data_input names all five inputs; Pathways carries pseudobulk; PK names roles', async () => {
    const t = await buildStageMethodsManifest('targets');
    for (const f of [
      'GWCD4i.DE_stats.h5ad',
      'GWCD4i.pseudobulk_merged.h5ad',
      'GWCD4i.DE_stats.by_guide.h5mu',
      'GWCD4i.DE_stats.by_donors.h5mu',
      'sgrna_library_metadata.suppl_table.csv',
    ]) {
      expect(t.methods.data_input).toContain(f);
    }
    // Pathways transitive chain includes pseudobulk (bound Direct producer requires it) — not partial
    const p = await buildStageMethodsManifest('pathways');
    expect(p.provenance.source_chain.some((s) => /pseudobulk_merged\.h5ad/.test(s.record_id))).toBe(true);
    // PK data_input names roles matching its source chain, none implying an unacquired response
    const k = await buildStageMethodsManifest('pksafety');
    expect(k.methods.data_input).toMatch(/PubChem \+ RxNorm/);
    expect(k.methods.data_input).toMatch(/reused from Stage 3/);
    expect(k.methods.data_input).toMatch(/label evidence/);
  });

  it('Stage-3 estimand names the typed inverse_direction_hypothesis (not observed gain-of-function)', async () => {
    const d = await buildStageMethodsManifest('drugs');
    expect(d.methods.estimand).toMatch(/inverse_direction_hypothesis/);
    expect(d.methods.estimand).toMatch(/NOT an observed gain-of-function/);
    expect(d.methods.estimand).toMatch(/never conflated with the observed direction/);
  });

  it('Stage-4 states incomplete CNS-MPO (missing logD7.4 / pKa) + organ-system not_evaluated (source-backed only)', async () => {
    const k = await buildStageMethodsManifest('pksafety');
    const lims = k.methods.limitations.join(' ');
    expect(lims).toMatch(/logD7\.4/);
    expect(lims).toMatch(/most-basic pKa/);
    expect(lims).toMatch(/full CNS-MPO score is incomplete/);
    expect(lims).toMatch(/labels do not establish measured brain exposure/i);
    expect(k.methods.masks_qc ?? '').toMatch(/unspecified \/ not_evaluated/);
    expect(k.methods.masks_qc ?? '').toMatch(/never inferred from target, mechanism, class, or drug name/);
    // source-tissue row is SOURCE-CONDITIONAL, not an unconditional "organ-system shown" claim;
    // Marson has no tissue/organ axis, so nothing is inferred from target/mechanism/class/drug name.
    expect(k.methods.source_tissue ?? '').toMatch(/emitted only from an admitted structured source field/);
    expect(k.methods.source_tissue ?? '').toMatch(/never inferred from target, mechanism, class, or drug name/);
    expect(k.methods.source_tissue ?? '').not.toMatch(/are shown only from source-backed label evidence/);
  });

  it('Reactome/GO/Wager/Grossman reference precision: derived-bundle labels, exact release URLs, dated raw snapshots', async () => {
    const p = await buildStageMethodsManifest('pathways');
    const reactome = p.provenance.source_chain.find((s) => s.label === 'Reactome')!;
    expect(reactome.url).toBe('https://reactome.org/download/97/ReactomePathways.gmt.zip');
    expect(reactome.record_id).toMatch(/derived-bundle hashes .*NOT the upstream ZIP/i);
    const go = p.provenance.source_chain.find((s) => /GO Biological/.test(s.label))!;
    expect(go.url).toBe('https://geneontology.org/docs/go-citation-policy/');
    expect(go.record_id).toMatch(/release IDs from cached file headers/i);

    const k = await buildStageMethodsManifest('pksafety');
    expect(k.provenance.source_chain.find((s) => /Grossman/.test(s.label))!.record_id).toMatch(/dated 2026-07-11 response snapshot; canonical is reproducible/);
    expect(k.provenance.source_chain.find((s) => /Wager/.test(s.label))!.record_id).toMatch(/dated 2026-07-11 fetch snapshot/);
  });
});

describe('reproduce commands: verified real CLIs OR honest "unavailable" (never a wrong command)', () => {
  it('a present reproduce_command is a comment-free, ellipsis-free, repo-root-executable command line', async () => {
    for (const page of DOWNSTREAM) {
      const cmd = (await buildStageMethodsManifest(page)).methods.reproduce_command;
      if (cmd === null) continue; // targets + pathways: unavailable by policy (integrated producer pending)
      expect(cmd).not.toMatch(/[…]|\.\.\./); // no ellipsis
      expect(cmd.trimStart().startsWith('#')).toBe(false); // no leading comment
      // repo-root-executable: cd <stage-dir> && [ENV=val ...] python -m <real module> <flags>
      expect(cmd).toMatch(/^cd \S+ && ([A-Za-z_][A-Za-z0-9_]*=\S+ )*(PYTHONPATH=\S+ )?python -m [A-Za-z0-9_.]+ /);
    }
  });

  it('EVERY route reproduce is UNAVAILABLE — a command may reproduce only an ADMITTED bound artifact', async () => {
    // No admitted bundle is bound on ANY route (Stage-2 integrated producer pending; Stage-3/4 no
    // admitted bundle). A --help-valid generic invocation does not reproduce a bound artifact, so
    // publishing one would be a wrong command. All four stay null ("unavailable").
    for (const page of DOWNSTREAM) {
      expect((await buildStageMethodsManifest(page)).methods.reproduce_command).toBeNull();
    }
  });

  it('INVARIANT: when run status / hashes / artifact_paths are all unavailable, reproduce_command is null (every route)', async () => {
    for (const page of DOWNSTREAM) {
      const m = await buildStageMethodsManifest(page);
      const runUnbound =
        m.methods.method_code_sha256 === null &&
        m.methods.last_run_utc === null &&
        m.provenance.raw_sha256 === null &&
        m.provenance.canonical_sha256 === null &&
        m.provenance.artifact_paths.length === 0;
      expect(runUnbound).toBe(true);
      expect(m.methods.reproduce_command).toBeNull(); // no admitted artifact ⇒ no reproduce command
    }
  });
});

describe('content address is PINNED, not self-sealing — one-byte mutation attacks', () => {
  it('a one-byte mutation of a limitation is REJECTED against the pinned hash', async () => {
    const raw = stageMethodsRaw('targets');
    raw.methods.limitations[0] = raw.methods.limitations[0] + '.';
    let err: unknown;
    try {
      await parseStageMethodsManifest(raw, STAGE_METHODS_HASHES.targets, 'Targets');
    } catch (e) {
      err = e;
    }
    expect(err).toBeInstanceOf(AdapterError);
    expect((err as AdapterError).code).toBe('content_hash_mismatch');
  });

  it('ATTACK: mutating the pinned source_tissue is REJECTED (source-tissue is hashed)', async () => {
    const raw = stageMethodsRaw('targets');
    expect(raw.methods.source_tissue).toBeTruthy();
    raw.methods.source_tissue = (raw.methods.source_tissue ?? '') + ' (edited)';
    await expect(
      parseStageMethodsManifest(raw, STAGE_METHODS_HASHES.targets, 'Targets'),
    ).rejects.toMatchObject({ code: 'content_hash_mismatch' });
  });

  it('ATTACK: mutating the pinned stage_label is REJECTED (stage_label is hashed)', async () => {
    const raw = stageMethodsRaw('drugs');
    raw.stage_label = raw.stage_label + 'X';
    await expect(
      parseStageMethodsManifest(raw, STAGE_METHODS_HASHES.drugs, 'Drugs'),
    ).rejects.toMatchObject({ code: 'content_hash_mismatch' });
  });

  it('ATTACK: mutating a bound source canonical hash is REJECTED', async () => {
    const raw = stageMethodsRaw('pathways');
    const reactome = raw.provenance.source_chain.find((s) => s.label === 'Reactome')!;
    reactome.canonical_sha256 = 'deadbeef' + (reactome.canonical_sha256 ?? '').slice(8);
    await expect(
      parseStageMethodsManifest(raw, STAGE_METHODS_HASHES.pathways, 'Pathways'),
    ).rejects.toMatchObject({ code: 'content_hash_mismatch' });
  });

  it('FIREWALL: an un-mutated manifest presented under the wrong stage label is REJECTED', async () => {
    // hash passes (raw unchanged) so only the stage firewall can fire
    await expect(
      parseStageMethodsManifest(stageMethodsRaw('targets'), STAGE_METHODS_HASHES.targets, 'Drugs'),
    ).rejects.toMatchObject({ code: 'stage_label_mismatch' });
  });

  it('the un-mutated raw verifies against the pinned hash under its canonical label (round-trips)', async () => {
    for (const page of DOWNSTREAM) {
      const m = await parseStageMethodsManifest(stageMethodsRaw(page), STAGE_METHODS_HASHES[page], stageLabelFor(page));
      expect(m.methods.method_id).toBeTruthy();
      expect(m.stage_label).toBe(stageLabelFor(page));
    }
  });

  it('the PINNED hashes equal a fresh canonical recompute (pins are not stale)', async () => {
    const fresh = await computeStageMethodsHashes();
    expect(fresh).toEqual({
      targets: STAGE_METHODS_HASHES.targets,
      pathways: STAGE_METHODS_HASHES.pathways,
      drugs: STAGE_METHODS_HASHES.drugs,
      pksafety: STAGE_METHODS_HASHES.pksafety,
    });
  });
});

describe('drawer renders verified source hashes; absent hash subfields are omitted (no filler)', () => {
  afterEach(() => cleanup());

  it('pathways: the drawer shows the verified Reactome/GO canonical + Marson raw hashes', async () => {
    const m = await buildStageMethodsManifest('pathways');
    render(<ProvenanceDrawer open title="Pathways" provenance={null} methods={m} onClose={() => {}} />);
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveTextContent(REACTOME_CANON);
    expect(dialog).toHaveTextContent(GO_CANON);
    expect(dialog).toHaveTextContent(MARSON_DE_RAW);
  });

  it('pksafety: DailyMed/openFDA appear WITHOUT any fabricated hash and without "unavailable" filler', async () => {
    const m = await buildStageMethodsManifest('pksafety');
    render(<ProvenanceDrawer open title="PK & Safety" provenance={null} methods={m} onClose={() => {}} />);
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveTextContent(/DailyMed/);
    expect(dialog).toHaveTextContent(/openFDA/i);
    expect(dialog).toHaveTextContent('90ffdf2a07f742f58128bdafeeebedb3d3779640884142783152113fc6473937'); // Grossman real hash
    // un-acquired labels: their absent raw/canonical subfields are OMITTED, never "unavailable"
    expect(within(dialog).queryAllByText('unavailable')).toHaveLength(0);
  });
});

describe('CLEAN unbound state — one route status, exactly zero "unavailable" (resolved manifest, per route)', () => {
  afterEach(() => cleanup());
  const CASES: [PageKey, string, string][] = [
    ['targets', 'Targets', 'No admitted Stage-2 run bundle bound'],
    ['pathways', 'Pathways', 'No admitted Stage-2 pathway bundle bound'],
    ['drugs', 'Drugs', 'No admitted Stage-3 bundle bound'],
    ['pksafety', 'PK & Safety', 'No admitted Stage-4 bundle bound'],
  ];
  for (const [page, label, status] of CASES) {
    it(`${page}: exactly one "${status}" and zero "unavailable" rows`, async () => {
      const m = await buildStageMethodsManifest(page);
      render(<ProvenanceDrawer open title={label} provenance={null} methods={m} onClose={() => {}} />);
      const d = screen.getByRole('dialog');
      expect(within(d).getAllByText(status)).toHaveLength(1); // exactly one main run-provenance status
      expect(within(d).queryAllByText('unavailable')).toHaveLength(0); // no wall of filler
      expect(within(d).getByText('References')).toBeInTheDocument(); // method-source References kept
    });
  }

  it('rendered drawer uses CURRENT method identities and contains NO retired IDs', async () => {
    const RETIRED = [
      'spot.stage03_drug_candidate_set.v1',
      'spot.stage04_scorecard_set.v1',
      'spot.stage02_screen.v1', // retired as a METHOD id (it is the screen SCHEMA, not the method)
    ];
    for (const page of DOWNSTREAM) {
      const m = await buildStageMethodsManifest(page);
      render(<ProvenanceDrawer open title={m.stage_label} provenance={null} methods={m} onClose={() => {}} />);
      const txt = screen.getByRole('dialog').textContent ?? '';
      for (const id of RETIRED) expect(txt).not.toContain(id);
      cleanup();
    }
    // current authoritative identities
    expect((await buildStageMethodsManifest('drugs')).methods.method_id).toContain('spot.stage03_drug_annotation.v1');
    expect((await buildStageMethodsManifest('pksafety')).methods.method_id).toContain('stage4-evidence-v2');
    expect((await buildStageMethodsManifest('pksafety')).methods.upstream_model).toContain('spot.stage03_drug_annotation.v1');
    expect((await buildStageMethodsManifest('targets')).methods.method_id).toContain('masked_program_projection');
  });

  it('an ADMITTED merged manifest binds the real run rows + reproduce (no unbound status row)', async () => {
    const staticDef = await buildStageMethodsManifest('targets');
    const admitted: UiReleaseManifest = {
      schema_version: UI_RELEASE_SCHEMA_VERSION,
      stage_label: 'Targets',
      method_id: staticDef.methods.method_id!,
      release_revision: 'spot.stage02.direct@rev1',
      raw_sha256: 'a'.repeat(64),
      canonical_sha256: 'b'.repeat(64),
      method_code_sha256: 'c'.repeat(64),
      environment: 'conda:stage2@lock-9f1',
      last_run_utc: '2026-07-13T04:00:00Z',
      generator_status: 'generated',
      verifier_status: 'admitted',
      reproduce_command: 'cd 02_geneskew && python -m analysis.direct.run_arms --condition Rest --out-root $OUT',
      cs_notebook_url: 'https://science.example.org/notebooks/stage02-abc',
      artifact_paths: ['out/arms/bundle.json'],
      source_artifact_ids: ['marson2025_gwcd4_perturbseq@c355f535'],
    };
    const merged = mergeAdmittedManifest(staticDef, admitted);
    render(<ProvenanceDrawer open title="Targets" provenance={null} methods={merged} onClose={() => {}} />);
    const d = screen.getByRole('dialog');
    expect(within(d).queryByText('No admitted Stage-2 run bundle bound')).toBeNull(); // unbound status REPLACED
    expect(within(d).getByText('Release')).toBeInTheDocument();
    expect(within(d).getByText('Last run UTC')).toBeInTheDocument();
    expect(within(d).getByText('Code sha256')).toBeInTheDocument();
    expect(d).toHaveTextContent('2026-07-13T04:00:00Z');
    expect(d).toHaveTextContent('spot.stage02.direct@rev1');
    expect(within(d).getByRole('button', { name: /Copy reproduce command/ })).toBeInTheDocument();
    expect(d).toHaveTextContent(/run_arms --condition Rest/);
    expect(d).toHaveTextContent('marson2025_gwcd4_perturbseq@c355f535'); // preserved source artifact id
    expect(d).toHaveTextContent(/Direct & temporal effects/); // static definition preserved
  });

  it('the "no admitted P2S bundle bound" status appears EXACTLY once, only on Targets (neutral Reference label)', async () => {
    const t = await buildStageMethodsManifest('targets');
    render(<ProvenanceDrawer open title="Targets" provenance={null} methods={t} onClose={() => {}} />);
    const td = screen.getByRole('dialog').textContent ?? '';
    expect((td.match(/no independently admitted P2S bundle is bound/gi) ?? []).length).toBe(1); // stated once (Upstream step)
    expect(td).toMatch(/Perturb2State/); // neutral Reference label retains commit/archive/license
    expect(td).not.toMatch(/Perturb2State \(secondary, unadmitted\)/); // no duplicated status in the label
    cleanup();
    for (const page of ['pathways', 'drugs', 'pksafety'] as const) {
      const m = await buildStageMethodsManifest(page);
      render(<ProvenanceDrawer open title={page} provenance={null} methods={m} onClose={() => {}} />);
      const d = screen.getByRole('dialog').textContent ?? '';
      expect(d).not.toMatch(/Perturb2State|independently admitted P2S bundle/i); // P2S only on Targets
      cleanup();
    }
  });

  it('drawer geometry matches Stage-1 exactly (600px/94vw/16px corner, 340ms cubic-bezier, step grid, paddings)', async () => {
    const m = await buildStageMethodsManifest('targets');
    render(<ProvenanceDrawer open title="Targets" provenance={null} methods={m} onClose={() => {}} />);
    const aside = screen.getByRole('dialog');
    const cls = aside.className;
    expect(cls).toContain('w-[600px]');
    expect(cls).toContain('max-w-[94vw]');
    expect(cls).toContain('rounded-l-2xl'); // 16px corner
    expect(cls).toContain('duration-[340ms]');
    expect(cls).toContain('ease-[cubic-bezier(.4,0,.2,1)]');
    // header: gap 10px, padding 11/9, ONE 16px title, 26x26 BORDERLESS sunken close
    const header = aside.querySelector('header') as HTMLElement;
    expect(header.className).toMatch(/gap-\[10px\]/);
    expect(header.className).toMatch(/pt-\[11px\].*pb-\[9px\]/);
    expect(within(aside).getByRole('heading', { level: 2 }).textContent).toBe('Methods & provenance');
    const close = within(aside).getByRole('button', { name: /Close methods/ });
    expect(close.className).toContain('h-[26px]');
    expect(close.className).toContain('w-[26px]');
    expect(close.className).toContain('bg-sunken');
    expect(close.className).not.toMatch(/\bborder\b/); // borderless
    // body 2/12
    const body = aside.querySelector('.overflow-y-auto') as HTMLElement;
    expect(body.className).toMatch(/pt-\[2px\].*pb-\[12px\]/);
    // step: inline grid 26px 1fr, gap 12px, padding 7px 0 (read from element.style — jsdom-safe); sunken divider
    const step = aside.querySelector('[data-section="methods"] > div') as HTMLElement;
    expect(step.style.gridTemplateColumns).toBe('26px 1fr');
    expect(step.style.columnGap).toBe('12px');
    expect(step.style.padding).toBe('7px 0px');
    expect(step.className).toContain('border-sunken');
    const h4 = step.querySelector('h4') as HTMLElement;
    expect(h4.style.margin).toBe('1px 0px 3px');
    expect(h4.className).toContain('text-[13px]');
    // the LAST rendered step (provenance) ALSO keeps the sunken divider — no last:border-b-0 regression
    const provStep = aside.querySelector('[data-section="provenance"] > div') as HTMLElement;
    expect(provStep.className).toContain('border-sunken');
  });
});

describe('manifestFromProvenance — cs_session frame_ref is NEVER a notebook URL', () => {
  it('sets cs_notebook_url null even when a cs_session frame_ref is present', () => {
    const prov = {
      artifact_id: 'research:stage02:x@abcdef012345',
      schema_version: 'spot.stage02_gene_lever_set.v1',
      namespace: 'research_only',
      production_eligible: false,
      hashes: { raw_sha256: 'a'.repeat(64), canonical_sha256: 'b'.repeat(64) },
      method: { method_id: 'm', config_id: 'c', code_ref: 'r', env_ref: 'e' },
      sources: [],
      cs_session: { session_ref: 'sess-1', frame_ref: 'frame-42' },
      upstream_ref: null,
    } as unknown as Provenance;
    expect(manifestFromProvenance('Targets', prov).provenance.cs_notebook_url).toBeNull();
  });
});

describe('StageIsland production drawer — real method definition, run-status unavailable', () => {
  beforeEach(() => {
    window.history.pushState({}, '', '/targets.html');
    window.localStorage.clear();
    window.sessionStorage.clear();
  });
  afterEach(() => {
    cleanup();
    window.localStorage.clear();
    window.sessionStorage.clear();
    window.history.pushState({}, '', '/02_page.html');
  });

  function renderIsland(page: PageKey, subtitle: string) {
    render(
      <StageIsland page={page} subtitle={subtitle} purpose="p" regions={[]} enqueueTarget="x" renderDemo={() => null} />,
    );
  }

  /** Re-click Methods until the ASYNC real manifest resolves into the drawer snapshot. */
  async function openRealDrawer(match: RegExp): Promise<HTMLElement> {
    await waitFor(() => {
      fireEvent.click(screen.getByRole('button', { name: /Methods/ }));
      expect(within(screen.getByRole('dialog')).getByText(match)).toBeInTheDocument();
    });
    return screen.getByRole('dialog');
  }

  it('targets: real method_id/estimand/sources; CLEAN unbound (one status, zero unavailable); no batch copy', async () => {
    renderIsland('targets', 'Targets');
    const d = await openRealDrawer(/masked_program_projection/);
    expect(d).toHaveTextContent(/difference-in-differences/);
    expect(d).toHaveTextContent(/Direct & temporal effects/); // route-specific estimand heading
    expect(d).toHaveTextContent(MARSON_DE_RAW); // source raw hash rendered in References
    expect(within(d).getAllByText(/Marson GWCD4i/).length).toBeGreaterThan(0);
    // clean-unbound: one route status row, no wall of "unavailable", no stale/wrong reproduce command
    expect(within(d).getAllByText('No admitted Stage-2 run bundle bound')).toHaveLength(1);
    expect(within(d).queryAllByText('unavailable')).toHaveLength(0);
    expect(within(d).queryByText(/fixture/i)).toBeNull();
    expect(within(d).queryByText(/analysis\.direct\.cli/)).toBeNull(); // stale interface not published
    expect(d.textContent ?? '').not.toMatch(NO_BATCH);
  });

  it('pksafety drawer differs from targets (CNS-MPO / Grossman, Stage-4 id; clean unbound, no reproduce)', async () => {
    renderIsland('pksafety', 'PK & Safety');
    const d = await openRealDrawer(/stage4-evidence-v2/);
    expect(d).toHaveTextContent(/CNS-MPO/);
    expect(within(d).getAllByText(/Grossman/).length).toBeGreaterThan(0);
    expect(within(d).getAllByText('No admitted Stage-4 bundle bound')).toHaveLength(1);
    expect(within(d).queryByText(/masked_program_projection/)).toBeNull();
    expect(within(d).queryByText(/analysis\.run_stage4/)).toBeNull(); // no command reproduces an unbound artifact
  });

  it('<main> stays clean/pending (the real manifest lives ONLY in the drawer)', async () => {
    renderIsland('targets', 'Targets');
    const main = screen.getByRole('main');
    await waitFor(() => expect(within(main).getByText(/pending independent admission/i)).toBeInTheDocument());
    expect(main).not.toHaveTextContent(/masked_program_projection/);
    expect(main).not.toHaveTextContent(/GENE_A/);
    expect(main.textContent ?? '').not.toMatch(NO_BATCH);
  });
});
