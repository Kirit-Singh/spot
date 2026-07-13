// REAL per-stage method-DEFINITION manifest — the content the shared Methods & Provenance
// drawer shows, loaded INDEPENDENT of any result-run admission. Every value here is a verified
// method-definition fact (method id / estimand / inputs / sources / masking / reproduce command
// only when it reproduces an ADMITTED bound artifact). Every RESULT-RUN field (last run,
// generator/verifier verdict, run raw/canonical hashes, artifact paths, run release, reproduce)
// is left null. The DRAWER does NOT render a wall of "unavailable": null definition fields are
// omitted, and unbound run provenance collapses to ONE terse route status row (see ProvenanceDrawer
// isRunBound / DefRow). A definition is never presented as a completed run; nothing is invented;
// nothing is fixture data.
//
// CONTENT ADDRESS (independent, not self-sealing): each page's raw manifest is hashed ONCE and the
// sha256 is PINNED below in STAGE_METHODS_HASHES (committed in code, separate from the raw). The
// consumer verifies the raw against that PINNED constant via parseStageMethodsManifest — so a
// one-byte mutation of ANY bound value (a source raw/canonical hash, a reproduce command, the
// source-tissue fact, or the stage_label) is REJECTED (content_hash_mismatch). stage_label AND
// source_tissue are pinned INSIDE the hashed manifest — a tamper-evident stage identity and a
// source-backed tissue claim; the adapter additionally firewalls the hashed stage_label against the
// code-bound page label (a manifest cannot be relabelled onto another stage).
//
// Sources (verified, CURRENT — the stale 02_geneskew/README Treg→Th1 example is NOT used):
//   · REAL_RUN_SPEC.md, STAGE2_INVOCATION_MATRIX.md, STAGE2_TEMPORAL_METHOD.md
//   · Stage-2 SCHEMAS (bundle identity, kept OUT of the Method row): spot.stage02_screen.v3 (Direct,
//     analysis/direct/emit.py SCHEMA_SCREEN), spot.stage02_pathway_record.v1 (pathway) — bound to the
//     GENERIC spot.stage01_selection.v3 contract. Method identities are the emit.py method IDs.
//   · Stage-3: 03_druglink/README (druglink.run_stage3; UniProt + ChEMBL 37 — a real universe-cache
//     acquisition exists under the current run but NO candidate bundle is admitted, so every
//     Stage-3 run-status field stays "unavailable" until admission).
//   · Stage-4: 04_PKPD/METHODS.md + method/sources.json + acquisition_sources_v1.json.
//   · Served Stage-1 release: 01_programs/app/data/stage01_release_manifest.json.
// UI constraint (REAL_RUN_SPEC): temporal BATCH/confound fields are MACHINE-ONLY — NO batch,
// confound, replicate or reliability wording appears in any field here or on the canvas.

import type { PageKey } from './pages';
import type { StageMethodsManifest } from '../domain/methodsManifest';
import { parseStageMethodsManifest } from '../adapters/methodsManifestAdapter';
import { canonicalJson, sha256Hex } from '../stage1/canonical';

// ── verified content-addresses (full 64-hex, consistent across the CURRENT sources) ──
const MARSON_DE_STATS = 'c355f535ff32cf7ba1edc49cf9c6039fe84f2c9ebe4d005515cba75790cfbb62';
const MARSON_PSEUDOBULK = 'fd2b8c21d357f8699ec34e2d5ebc1639612c27a0147a9ca94d4983822d93247e';
const GROSSMAN_RAW = '8bb0324def170ae1f9aa26e906c8b7327690b8c6eebcd3d3e29f5e5a88b23f47';
const GROSSMAN_CANONICAL = '90ffdf2a07f742f58128bdafeeebedb3d3779640884142783152113fc6473937';
const WAGER_RAW = '731fe2b7f7ce435de88a19f77dbd5e3b5482a12036574d6f378fbbb816113133';
// Ensembl-rekeyed gene-set bundles (verified against the geneset-cache provenance emitted by builder
// spot.stage02.geneset_rekey.symbol_to_ensembl.v1). raw = the on-disk *.genesets.json bytes;
// canonical = the order-independent canonical hash. Replaces the earlier stale short hashes.
const REACTOME_RAW = '81cf184f9c2697236c8bbc1b445ce8b28ecf17ca90a2f0aafe709d3028a36469';
const REACTOME_CANONICAL = '9cc416d14a16ff4bdbf700780e67d40a6f88c5235690fadc79abab83fd68218e';
const GO_BP_RAW = '4f8b124432e9c1f75f4780b233bd55a29b04150e36d71e04d183d85e5914d2a6';
const GO_BP_CANONICAL = '5b62e8bc36cb798ec615c078bc1c8ee2d3331d61dafb24d80cac6b18ab3bc310';
// Served Stage-1 v3 release identity (stage01_release_manifest.v2 self_canonical_sha256) — bound
// only as an UPSTREAM source, never as any downstream stage's own result release.
const STAGE1_RELEASE_CANONICAL = '9c8e72d141e8721fc3b45468f6eb89ccc1acc6ec17888fe394b81008d5096805';

// Canonical, code-fixed stage identity per page — the exact semantic route labels (Programs ·
// Targets · Pathways · Drugs · PK & Safety). PINNED INSIDE the hashed manifest and used as the
// firewall's code-bound label; a test asserts these agree with the nav's PAGES labels.
const STAGE_LABELS: Record<'targets' | 'pathways' | 'drugs' | 'pksafety', string> = {
  targets: 'Targets',
  pathways: 'Pathways',
  drugs: 'Drugs',
  pksafety: 'PK & Safety',
};

// Source-backed tissue fact per page — stated even before an arm is generated (not a per-run value).
// PINNED INSIDE the hashed manifest so it is tamper-evident; must match domain stageSourceTissue().
const ST_MARSON_CD4 =
  'Primary human CD4 T cells (Marson GWCD4i) — one experimental source, across donor/stimulation conditions; no tissue/organ sampling axis or multi-tissue expression measurements in GWCD4i; the publication\'s HPA/GTEx analysis is external.';
const SOURCE_TISSUE: Record<'targets' | 'pathways' | 'drugs' | 'pksafety', string> = {
  targets: ST_MARSON_CD4,
  pathways: ST_MARSON_CD4,
  drugs:
    'Biological input is the Stage-2 program/perturbation result from the Marson primary-human-CD4 dataset; drug evidence comes from separately listed public sources.',
  pksafety:
    'Organ-system context is emitted only from an admitted structured source field; otherwise not_evaluated / unspecified — never inferred from target, mechanism, class, or drug name.',
};

interface RawSource {
  label: string;
  record_id: string;
  url: string | null;
  license: string | null;
  retrieval_utc: string | null;
  raw_sha256: string | null;
  canonical_sha256: string | null;
}
/** Raw manifest — stage_label + methods.source_tissue are PART of the hashed content (tamper-evident). */
interface RawManifest {
  stage_label: string;
  methods: {
    data_input: string | null;
    source_tissue: string | null;
    estimand: string | null;
    masks_qc: string | null;
    upstream_model: string | null;
    limitations: string[];
    method_id: string | null;
    method_code_sha256: string | null;
    environment: string | null;
    last_run_utc: string | null;
    reproduce_command: string | null;
  };
  provenance: {
    release_revision: string | null;
    raw_sha256: string | null;
    canonical_sha256: string | null;
    generator_status: string | null;
    verifier_status: string | null;
    cs_notebook_url: string | null;
    artifact_paths: string[];
    source_chain: RawSource[];
  };
}

const src = (
  label: string,
  record_id: string,
  opts: Partial<Omit<RawSource, 'label' | 'record_id'>> = {},
): RawSource => ({
  label,
  record_id,
  url: opts.url ?? null,
  license: opts.license ?? null,
  retrieval_utc: opts.retrieval_utc ?? null,
  raw_sha256: opts.raw_sha256 ?? null,
  canonical_sha256: opts.canonical_sha256 ?? null,
});

// RESULT-RUN status — none is admitted yet, so every one is null ("unavailable"). The method-code
// hash / environment / last-run are NOT shown: the final integrated Stage-2 method identity is still
// pending (W1), and we will not pin a provisional, moving commit — a later data-only reseal binds it.
const RUN_STATUS_UNAVAILABLE = { method_code_sha256: null, last_run_utc: null, environment: null } as const;
const PROV_RUN_STATUS_UNAVAILABLE = {
  release_revision: null, // no admitted RUN → no result release (Stage-1 release is upstream-only)
  raw_sha256: null,
  canonical_sha256: null,
  generator_status: null,
  verifier_status: null,
  cs_notebook_url: null,
  artifact_paths: [] as string[],
} as const;

// The DE_stats + pseudobulk files come from the official CZI Virtual Cell Models dataset page
// (v1.0, 22 Dec 2025, MIT, no PII), which lists GWCD4i.DE_stats.h5ad (33,983 × 10,282) + pseudobulk.
const CZI_MARSON_URL = 'https://virtualcellmodels.cziscience.com/dataset/genome-scale-tcell-perturb-seq';

// Upstream Stage-1 v3 release — bound as an UPSTREAM source (never a downstream result release).
// Served same-origin at data/stage01_release_manifest.json; spot artifacts are MIT (© 2026 Kirit Singh).
const STAGE1_RELEASE_UPSTREAM = src(
  'Stage-1 v3 release (upstream)',
  'spot.stage01_release_manifest.v2',
  { url: '/data/stage01_release_manifest.json', license: 'MIT (spot; © 2026 Kirit Singh)', canonical_sha256: STAGE1_RELEASE_CANONICAL },
);
const HPA_EXTERNAL_LINK = src(
  'Human Protein Atlas (external gene page link only)',
  'proteinatlas.org/{Ensembl gene ID}',
  { url: 'https://www.proteinatlas.org/about/help/dataaccess',
    license: 'External link only; no HPA expression or tissue data is copied into this release.' },
);
const MARSON_DE = src('Marson GWCD4i Perturb-seq (CZI v1.0)', 'marson2025_gwcd4_perturbseq · GWCD4i.DE_stats.h5ad (33,983 × 10,282)', {
  url: CZI_MARSON_URL,
  license: 'MIT',
  raw_sha256: MARSON_DE_STATS,
});
const MARSON_PB = src('Marson GWCD4i Perturb-seq (CZI v1.0)', 'marson2025_gwcd4_perturbseq · GWCD4i.pseudobulk_merged.h5ad', {
  url: CZI_MARSON_URL,
  license: 'MIT',
  raw_sha256: MARSON_PSEUDOBULK,
});
// Distinct provenance facts, kept separate and NOT conflated with the CZI DE/pseudobulk source above:
// the pinned HuggingFace mirror is the Stage-1 NTC (non-targeting-control) dataset (ntc_clustered.h5ad),
// NOT the source of the Stage-2 perturbation bytes (those are the CZI GWCD4i.DE_stats/pseudobulk); and
// the bioRxiv preprint (the paper). Each with its own verified licence.
const MARSON_HF_MIRROR = src('Stage-1 NTC mirror (pinned HF)', 'huggingface.co/datasets/KiritSingh/spot-CD4-Marson @ e5fcf98b · ntc_clustered.h5ad', {
  url: 'https://huggingface.co/datasets/KiritSingh/spot-CD4-Marson/tree/e5fcf98b56a9302921d402e97fc5a190bd88f9a6',
  license: 'MIT',
  raw_sha256: '2edc6d318415c8b0ee779d707ab86e26ddb6f0274db51ab4a12f21ebfda50e43', // ntc_clustered.h5ad (stage01_input_manifest)
});
const MARSON_PREPRINT = src('Marson genome-scale CRISPRi perturb-seq · bioRxiv', 'DOI 10.64898/2025.12.23.696273', {
  url: 'https://www.biorxiv.org/content/10.64898/2025.12.23.696273v1',
  license: 'CC BY 4.0',
});
// Perturb2State — a SECONDARY arm-wise reconstruction-support lane on Targets. It is an IMPLEMENTED
// lane, explicitly deferred_not_part_of_this_run in the complete Stage-2 run manifest, and its emitted
// verification reports independent_verification: pending — so NO independently admitted P2S bundle is
// bound (the pinned upstream repo/commit itself is not a draft). Only METHOD provenance is bound: the
// pinned upstream commit, its git-archive hash (raw), and the full MIT-LICENSE file hash (in the
// licence). No P2S run hash / result / reproduce command exists; it never modifies Direct ranks or
// implies validation / causality / p / q.
const PERTURB2STATE = src(
  'Perturb2State',
  'emdann/pert2state_model @ 2c2e30959ffafadecc6af5d4d7b5bde868ab5313',
  {
    url: 'https://github.com/emdann/pert2state_model/tree/2c2e30959ffafadecc6af5d4d7b5bde868ab5313',
    license: 'MIT — LICENSE sha256 d48090a9395192c9e988a495f5fe0bc96c5194b3611435baf4b2a4ca8000657e',
    raw_sha256: '108d6633289826219dfc23779c10aad3313d957e40537a3fd1077db5a1fa3fea', // git-archive sha256
  },
);
// Stage-4 label-evidence APIs the method CONSUMES (declared method-definition sources). A real run
// RE-HASHES each response, so raw/canonical + retrieval stay null here — neither has supplied
// evidence before acquisition. Licensing verbatim from the W8 acquisition source
// (agent/stage4-acquisition-core@b287f72): DailyMed carries NO verified blanket open-data licence;
// openFDA is generally CC0 WITH marked third-party-rights exceptions.
const DAILYMED_LABEL = src('DailyMed SPL v2 REST (NLM)', 'dailymed.nlm.nih.gov/dailymed/services/v2/spls/{setid}.xml', {
  url: 'https://dailymed.nlm.nih.gov/dailymed/app-support-web-services.cfm',
  license:
    'No blanket licence verified — DailyMed publishes no blanket licence statement and some SPL content carries third-party copyright; in-use labelling may differ from FDA-approved labelling and is not NLM-reviewed.',
});
const OPENFDA_LABEL = src('openFDA drug/label (api.fda.gov)', 'api.fda.gov/drug/label.json', {
  url: 'https://open.fda.gov/terms/',
  license:
    'Generally CC0, with marked exceptions where third-party rights are asserted; data are unvalidated and the response disclaimer is retained.',
});
// Load-bearing CZI inputs the Direct/signature methods consume (same CZI dataset, MIT) — bound with
// their raw file hashes so Targets/Pathways account for every input, not only DE + pseudobulk.
const MARSON_BY_GUIDE = src('Marson GWCD4i Perturb-seq (CZI v1.0)', 'marson2025_gwcd4_perturbseq · GWCD4i.DE_stats.by_guide.h5mu', {
  url: CZI_MARSON_URL,
  license: 'MIT',
  raw_sha256: 'b30937cccc6aa104c4b73fb4854d70678fe8c8d9df035bebb571910a0eed46ff',
});
const MARSON_BY_DONORS = src('Marson GWCD4i Perturb-seq (CZI v1.0)', 'marson2025_gwcd4_perturbseq · GWCD4i.DE_stats.by_donors.h5mu', {
  url: CZI_MARSON_URL,
  license: 'MIT',
  raw_sha256: '2ee3cf90925600eb044619021da2bdd47d661f306a204586652256facf17af64',
});
const MARSON_SGRNA = src('Marson GWCD4i sgRNA library metadata', 'sgrna_library_metadata.suppl_table.csv', {
  url: CZI_MARSON_URL,
  license: 'MIT',
  raw_sha256: '00a1bec2afc2082fc79765531696d7e22672a8ba904ea54c035858f425a657a8',
});
// Stage-3 drug-evidence sources REUSED read-only by Stage-4 — authoritative TERMS URLs from the
// Stage-4 acquisition ledger (not a release-notes URL); label states release + reuse-only.
const CHEMBL_37_REUSE = src('ChEMBL 37 (reused from Stage 3; Stage-4 reuse-only)', 'chembl_37', {
  url: 'https://chembl.gitbook.io/chembl-interface-documentation/about',
  license: 'CC BY-SA 3.0 · Stage-4 reuse-only',
});
const UNIPROT_REUSE = src('UniProt 2026_02 (reused from Stage 3; Stage-4 reuse-only)', 'uniprot_2026_02', {
  url: 'https://www.uniprot.org/help/license',
  license: 'CC BY 4.0 · Stage-4 reuse-only',
});
// Stage-4 live-acquisition sources (declared method-definition endpoints; no response hashes until a
// real run acquires + re-hashes each response). Licensing mirrors acquisition_sources_v1.json.
const PUBCHEM_PUG = src('PubChem PUG REST', 'pubchem.ncbi.nlm.nih.gov/rest/pug', {
  url: 'https://pubchem.ncbi.nlm.nih.gov/docs/pug-rest', // official PUG REST docs (200; the bare endpoint 400s without a query)
  license: 'NCBI usage policy — no NCBI restriction, but third-party rights may exist; terms: ncbi.nlm.nih.gov/home/about/policies/',
});
const RXNORM = src('RxNorm (NLM RxNav)', 'rxnav.nlm.nih.gov/REST', {
  url: 'https://lhncbc.nlm.nih.gov/RxNav/APIs/RxNormAPIs.html', // official RxNorm API docs (200)
  license: 'NLM RxNorm terms — source-vocabulary restrictions may apply; terms: nlm.nih.gov/research/umls/rxnorm/docs/termsofservice.html',
});

function targetsRaw(): RawManifest {
  return {
    stage_label: STAGE_LABELS.targets,
    methods: {
      data_input:
        'Marson GWCD4i Perturb-seq inputs: GWCD4i.DE_stats.h5ad, GWCD4i.pseudobulk_merged.h5ad, GWCD4i.DE_stats.by_guide.h5mu, GWCD4i.DE_stats.by_donors.h5mu, and sgrna_library_metadata.suppl_table.csv; DE-readout 10,282; perturbation-target 11,526 = 11,522 Ensembl + 4 symbol-only.',
      source_tissue: SOURCE_TISSUE.targets,
      estimand:
        'Two independent Direct arms (away_from_A / toward_B): each a target-masked measured transcriptional-effect screen scored as one signed program projection with a deterministic within-arm rank; no combined/balanced/weighted score. A pair is the JOIN of two independent arms on a join-time Pareto view (display only — never a combined score). Temporal (ordered from→to conditions): population program-projection difference-in-differences per arm; inference_status not_calibrated (no p/q/significance); not lineage tracing, fate mapping, a per-cell transition, or a rate. Each UI effect–rank facet is confined to one selected program and context: x = −arm_value for its matched decrease arm and +arm_value for its matched increase arm; y = −log10(rank / N ranked) within that direction. This y-axis is a descriptive transform of native rank, not a p-value, q-value, FDR or independent uncertainty statistic. Labels are the frozen crosswalk symbols; HPA links are generated only from the typed Ensembl ID and import no HPA tissue values.',
      masks_qc:
        "Target-masked: each estimate removes the target's own gene, its frozen 30-kb neighbourhood mask and its guides' off-target alignments before the panel and control means are taken; an absent mask and an empty mask are distinct claims (null when unresolved). Ranking eligibility consumes an UPSTREAM significance flag — obs.ontarget_significant (a per target×condition boolean at GWCD4i.DE_stats.h5ad:obs.ontarget_significant, computed by the Marson GWCD4i release's own DESeq2 DE model, not by spot): it is read as a released boolean verbatim, so spot re-thresholds nothing and emits no p / q / FDR of its own; a target flagged false is ranking-ineligible and a missing flag is a non-evaluable disposition (missing_qc:ontarget_significant).",
      upstream_model:
        'Stage-1 binding: spot.stage01_selection.v3 generic program contrast (Stage-1 continuous v3.0.1 release). Secondary lane: Perturb2State (emdann/pert2state_model, MIT) — an arm-wise reconstruction-support model that never modifies Direct ranks and implies no validation, causality, or p / q. Spot integration status: an implemented secondary lane, explicitly deferred_not_part_of_this_run in the complete Stage-2 run manifest, whose emitted verification still reports independent_verification: pending — so no independently admitted P2S bundle is bound.',
      limitations: [
        'One in-vitro primary-human-CD4 dataset (Marson GWCD4i); a gene-lever result is suggestive and requires external validation, not a confirmed target.',
      ],
      method_id: 'spot.stage02.direct.masked_program_projection · spot.stage02.pareto.two_arm.v1 · spot.stage02.temporal_cross_condition.v1',
      // Run-specific command UNAVAILABLE by policy (renders "unavailable"): Targets spans within-condition
      // Direct (the content-addressed all-arm producer run_arms) AND cross-condition temporal. Do not seal
      // a command against the provisional W18 interface (a1191e6, interface-evidence only) — the Direct +
      // temporal producers are in W1/W5 integration. Sealed only from the final integrated wrapper dry-run;
      // a later data-only reseal binds it. (Orchestration policy stays here in code, not in the drawer.)
      reproduce_command: null,
      ...RUN_STATUS_UNAVAILABLE,
    },
    provenance: {
      source_chain: [
        MARSON_DE, MARSON_PB, MARSON_BY_GUIDE, MARSON_BY_DONORS, MARSON_SGRNA,
        MARSON_HF_MIRROR, MARSON_PREPRINT, PERTURB2STATE, STAGE1_RELEASE_UPSTREAM,
        HPA_EXTERNAL_LINK,
      ],
      ...PROV_RUN_STATUS_UNAVAILABLE,
    },
  };
}

function pathwaysRaw(): RawManifest {
  return {
    stage_label: STAGE_LABELS.pathways,
    methods: {
      data_input:
        'Marson GWCD4i target-masked perturbation signatures + Ensembl-keyed gene-set bundles: Reactome V97 (2,868 sets, canonical 9cc416d1) and GO-BP (go-basic 2026-06-15 + goa_human 2026-05-21, 13,805 sets, canonical 5b62e8bc). Two gene universes, never conflated: perturbation-target (11,526 = 11,522 ENSG + 4 symbol-only) and DE-readout (10,282).',
      source_tissue: SOURCE_TISSUE.pathways,
      estimand:
        "Target-ranked pathway convergence over the full target-masked perturbation signatures (not the marker panels): (A) per-arm ranked enrichment scored in the perturbation-target universe (11,526 = 11,522 ENSG + 4 symbol-only, with per-set namespace eligibility) — a weighted running-sum statistic over one arm's ranking with its leading edge, computed once per arm and never summed across arms, with per-arm coverage / headline eligibility; (B) signature convergence scored in the 10,282-gene DE-readout universe — cosine on the shared unmasked support, requiring ≥2 measured perturbations. No p / q / FDR — there is no calibrated null.",
      masks_qc:
        'Gene sets are pinned by source + release + sha256 and namespace-enforced (Ensembl-keyed against the perturbation-target universe); a set with source_coverage < 0.50 in the target namespace is descriptive_only and excluded from headline ranking, still fully computed and emitted.',
      upstream_model:
        'Required upstream: an admitted Stage-2 Direct arm bundle (schema spot.stage02_screen.v3) bound to a generic spot.stage01_selection.v3 contract.',
      limitations: [
        'A convergence claim requires ≥2 measured perturbations; single-target sets are emitted flagged single_target_support, never dropped.',
        'Source-coverage loss is reported per gene-set, per universe, never blended: ranked enrichment uses the 11,526-gene perturbation-target universe (Reactome loses 39.6069% of member slots, GO-BP 51.4288%); signature convergence uses the 10,282-gene DE-readout universe (Reactome 40.1817%, GO-BP 56.5884%).',
      ],
      method_id: 'spot.stage02.pathway.ranked_arm_enrichment.v2 · spot.stage02.pathway.signature_convergence.v2',
      // Run-specific command UNAVAILABLE by policy: the production pathway pipeline is dependency-aware
      // (Direct discovery → content-addressed bundle DISCOVERY via bundle_index → signature_matrix STEP 0
      // requiring the external direct-mask-report anchor → run_pathway_arms). A hand-written chain that
      // assumes the bundle root / omits the mask-report anchor is NOT production-valid, and --help alone
      // does not validate producer→consumer flow. Sealed only from the committed run_stage2.sh dependency
      // wrapper after its dry-run admission; until then this stays "unavailable" (never a wrong command).
      reproduce_command: null,
      ...RUN_STATUS_UNAVAILABLE,
    },
    provenance: {
      source_chain: [
        MARSON_DE,
        MARSON_PB, // pseudobulk is a required input to the bound Direct producer (run_screen --pseudobulk)
        MARSON_BY_GUIDE,
        MARSON_BY_DONORS,
        MARSON_SGRNA,
        MARSON_HF_MIRROR,
        MARSON_PREPRINT,
        src('Reactome', 'V97 · 2,868 sets · derived-bundle hashes are reactome_ensembl.genesets.json (Ensembl-rekeyed), NOT the upstream ZIP', {
          url: 'https://reactome.org/download/97/ReactomePathways.gmt.zip', // exact V97 archive
          license: 'CC0-1.0',
          raw_sha256: REACTOME_RAW,
          canonical_sha256: REACTOME_CANONICAL,
        }),
        src('GO Biological Process', 'go-basic 2026-06-15 + goa_human 2026-05-21 (release IDs from cached file headers) · 13,805 sets · pins identify the derived go_bp_ensembl.genesets.json bytes', {
          url: 'https://geneontology.org/docs/go-citation-policy/', // HTTPS official citation/license (GO download URLs are mutable)
          license: 'CC-BY-4.0',
          raw_sha256: GO_BP_RAW,
          canonical_sha256: GO_BP_CANONICAL,
        }),
        STAGE1_RELEASE_UPSTREAM,
      ],
      ...PROV_RUN_STATUS_UNAVAILABLE,
    },
  };
}

function drugsRaw(): RawManifest {
  return {
    stage_label: STAGE_LABELS.drugs,
    methods: {
      data_input:
        'Requires an admitted, re-hashed Stage-2 Direct run mapped to a frozen offline drug-evidence cache (top-25 targets per arm) from UniProt + ChEMBL; optional Stage-2 pathway-hypothesis document.',
      source_tissue: SOURCE_TISSUE.drugs,
      estimand:
        'Direction-aware target→drug link: each Stage-2 screen row becomes exactly two arm-lever rows; ENSG⟷UniProt⟷ChEMBL SINGLE PROTEIN identity join (complexes/families refused); action_type carried verbatim and max_phase carried, never recomputed by spot; no combined / headline / overall score; direct_target (observed_perturbation) and pathway_node (pathway_hypothesis) origins are never merged, and a separate typed inverse_direction_hypothesis state — distinct from observed_perturbation/direct_target and NOT an observed gain-of-function — is carried, never conflated with the observed direction. Offline join, no per-click API.',
      masks_qc:
        'Frozen identity join: human Ensembl ⟷ UniProt ⟷ ChEMBL at the SINGLE PROTEIN level only (complexes / families refused); action_type is carried verbatim and max_phase is carried, never recomputed by spot.',
      upstream_model: 'Required upstream: an admitted Stage-2 Direct run — two independent arms (away_from_A / toward_B).',
      limitations: [
        'Only UniProt identity + ChEMBL mechanism are wired; ChEMBL activity, Open Targets, DGIdb, DrugBank and DepMap-PRISM are not.',
        'ChEMBL is CC BY-SA 3.0 (ShareAlike): redistributed ChEMBL-derived fields inherit attribution and ShareAlike obligations.',
      ],
      method_id: 'stage3-druglink reusable-arm candidates · native schema spot.stage03_drug_annotation.v2 · browser projection spot.ui.stage03_candidates.v2',
      // UNAVAILABLE: a reproduce command may be shown ONLY when it reproduces the ADMITTED bound
      // artifact. No admitted Stage-3 candidate bundle is bound to this page, so a generic
      // druglink.run_stage3 invocation (valid --help notwithstanding) does not reproduce a bound
      // result — it stays "unavailable" until a concrete admitted bundle + inputs + hashes are bound.
      reproduce_command: null,
      ...RUN_STATUS_UNAVAILABLE,
    },
    provenance: {
      source_chain: [
        src('ChEMBL 37', 'chembl_37', {
          url: 'https://ftp.ebi.ac.uk/pub/databases/chembl/ChEMBLdb/releases/chembl_37/',
          license: 'CC BY-SA 3.0',
        }),
        src('UniProt 2026_02', 'uniprot_2026_02', {
          url: 'https://www.uniprot.org/release-notes/2026-06-10-release',
          license: 'CC BY 4.0',
        }),
      ],
      ...PROV_RUN_STATUS_UNAVAILABLE,
    },
  };
}

function pksafetyRaw(): RawManifest {
  return {
    stage_label: STAGE_LABELS.pksafety,
    methods: {
      data_input:
        'Requires an admitted Stage-3 candidate binding. Sources by role: NEBPI review + CNS-MPO article (method framework); PubChem + RxNorm (compound identity / descriptors, live acquisition); ChEMBL + UniProt (mechanism / protein identity, reused from Stage 3); DailyMed + openFDA (regulatory label evidence). Every scientific number binds to a source-response hash; no response is implied before acquisition.',
      source_tissue: SOURCE_TISSUE.pksafety,
      estimand:
        'CNS-MPO (Wager 2010) six-parameter physicochemical desirability (ClogP, ClogD7.4, MW, TPSA, HBD, most-basic pKa), an equal-weight 0–6 sum — a design heuristic, not measured brain permeability. NEBPI (Grossman 2026) criterion-level brain-penetrance classification keyed to (moiety × route × formulation × dose × schedule × tumour × potency): a class belongs to a context, never to a drug. Exposure / potency margins only from sourced measurements; label safety in five evidence states where no_evidence_found never renders as safe.',
      masks_qc:
        'Label adapters are pure parsers over cached bytes (no network); each row binds set-ID / application number, active moiety, label version, effective date, the LOINC-coded section, and the raw response hash. A label is never summarised from memory. Organ-system safety groups: with no admitted source supplying the organ-system field, the current adapters emit unspecified / not_evaluated — source-backed only, never inferred from target, mechanism, class, or drug name.',
      upstream_model: 'Required upstream: an admitted Stage-3 drug-candidate bundle (spot.stage03_drug_annotation.v2; artifact_class analysis).',
      limitations: [
        'NEBPI (Grossman 2026) is an expert-consensus review, not FDA guidance; its transcription and interpretation calls need clinical / pharmacology review before any real use.',
        'The current public acquisition lacks logD7.4 and most-basic pKa, so a full CNS-MPO score is incomplete unless those exact sourced values are acquired; drug labels do not establish measured brain exposure.',
      ],
      method_id: 'stage4-evidence-v2 · cns_mpo_wager2010_v1 · nebpi_source_framing_v2 · safety_taxonomy_v2',
      // UNAVAILABLE: no admitted Stage-4 scorecard/result bundle is bound to this page. The real
      // engine is analysis.run_stage4 (valid --help), but a generic invocation does not reproduce a
      // bound admitted artifact — it stays "unavailable" until a concrete admitted bundle is bound.
      reproduce_command: null,
      ...RUN_STATUS_UNAVAILABLE,
    },
    provenance: {
      source_chain: [
        src('Grossman et al., Neuro-Oncology 2026 (NEBPI)', 'PMC13338342 · DOI 10.1093/neuonc/noag051 · raw is a dated 2026-07-11 response snapshot; canonical is reproducible', {
          url: 'https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi/BioC_xml/PMC13338342/unicode',
          license: 'CC BY 4.0',
          retrieval_utc: '2026-07-11',
          raw_sha256: GROSSMAN_RAW,
          canonical_sha256: GROSSMAN_CANONICAL,
        }),
        src('Wager et al., ACS Chem Neurosci 2010 (CNS-MPO)', 'PMC3368654 · DOI 10.1021/cn100008c · raw is a dated 2026-07-11 fetch snapshot (a live re-fetch may differ)', {
          url: 'https://pmc.ncbi.nlm.nih.gov/articles/PMC3368654/',
          license: 'ACS copyright — numeric facts only, not redistributed',
          retrieval_utc: '2026-07-11',
          raw_sha256: WAGER_RAW,
        }),
        CHEMBL_37_REUSE,
        UNIPROT_REUSE,
        PUBCHEM_PUG,
        RXNORM,
        DAILYMED_LABEL,
        OPENFDA_LABEL,
      ],
      ...PROV_RUN_STATUS_UNAVAILABLE,
    },
  };
}

/** The raw (label-independent) method-definition manifest for a page. Exported for the content-hash attack test. */
export function stageMethodsRaw(page: PageKey): RawManifest {
  switch (page) {
    case 'pathways':
      return pathwaysRaw();
    case 'drugs':
      return drugsRaw();
    case 'pksafety':
      return pksafetyRaw();
    case 'targets':
    default:
      return targetsRaw();
  }
}

/**
 * PINNED content addresses — sha256 over canonicalJson(stageMethodsRaw(page)), computed ONCE and
 * committed here separate from the raw. The consumer verifies the raw against THIS constant, so a
 * one-byte mutation of the raw is rejected (content_hash_mismatch). Regenerate via the pinned-hash
 * test if a manifest's verified content legitimately changes.
 */
export const STAGE_METHODS_HASHES: Record<'targets' | 'pathways' | 'drugs' | 'pksafety', string> = {
  targets: '90c11e80a8338443e2550581f89330e2de44a38eafa071d5158d354d7c8adabb',
  pathways: '3d0294fe0b6d0beb618a477b65a0cd82a736fdd60ef875baf2f6eb9a3864f657',
  drugs: '9b4fea60d229dd04418ac67e0cf9ad48338fecb6d32814761e2934cf51f0c320',
  pksafety: '1b8e6ab3631f949f57c7998d9366d7c060d47d3dbcd6605257a2d6ac85ef3c5a',
};

function keyFor(page: PageKey): keyof typeof STAGE_METHODS_HASHES {
  return (page === 'programs' ? 'targets' : page) as keyof typeof STAGE_METHODS_HASHES;
}
function pinnedFor(page: PageKey): string {
  return STAGE_METHODS_HASHES[keyFor(page)];
}
/** Canonical, code-fixed stage label for a page — the firewall's code-bound label AND the value
 *  pinned inside the hashed manifest (they must agree). Exported for the label-consistency test. */
export function stageLabelFor(page: PageKey): string {
  return STAGE_LABELS[keyFor(page)];
}

/**
 * Build the REAL, content-addressed method-definition manifest for a page. The stage label is
 * derived from the page (STAGE_LABELS) — it is NOT caller-supplied: it is pinned INSIDE the hashed
 * manifest AND passed as the adapter's code-bound label, so the hashed stage_label must equal it or
 * the manifest is rejected. The raw is verified against the PINNED hash by
 * {@link parseStageMethodsManifest} (fail-closed). Loaded independent of result admission; every
 * result-run field stays "unavailable".
 */
export async function buildStageMethodsManifest(page: PageKey): Promise<StageMethodsManifest> {
  return parseStageMethodsManifest(stageMethodsRaw(page), pinnedFor(page), stageLabelFor(page));
}

/** Recompute the canonical content hashes (used by the pinned-hash test to regenerate constants). */
export async function computeStageMethodsHashes(): Promise<Record<string, string>> {
  const out: Record<string, string> = {};
  for (const page of ['targets', 'pathways', 'drugs', 'pksafety'] as const) {
    out[page] = await sha256Hex(canonicalJson(stageMethodsRaw(page)));
  }
  return out;
}
