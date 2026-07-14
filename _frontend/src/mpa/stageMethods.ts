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
// GO-BP-ONLY release: GO-BP is the one released gene-set source, so it is the one bundle pinned here.
// (The Reactome V97 bundle hashes are deliberately NOT carried in the runtime manifest — see the
// source_chain note in pathwaysRaw. Its licence/history record belongs in the repo, not on the page.)
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
    'Candidate context originates from the Marson primary-human-CD4 perturbation analysis through Stage 3. The PK/safety evidence is molecule-level public evidence; the current compact artifact emits no tissue-specific or organ-system classification.',
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
const OPENFDA_LABEL = src('openFDA drug/label (api.fda.gov)', 'api.fda.gov/drug/label.json', {
  url: 'https://open.fda.gov/terms/',
  license:
    'Generally CC0, with marked exceptions where third-party rights are asserted; data are unvalidated and the response disclaimer is retained.',
});
const DAILYMED_LABEL = src('DailyMed SPL v2 REST (NLM)', 'dailymed.nlm.nih.gov/dailymed/services/v2/spls/{setid}.xml', {
  url: 'https://dailymed.nlm.nih.gov/dailymed/app-support-web-services.cfm',
  license: 'No blanket licence verified — DailyMed publishes no blanket licence statement and some SPL content carries third-party copyright; in-use labelling may differ from FDA-approved labelling and is not NLM-reviewed.',
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
  url: 'https://lhncbc.nlm.nih.gov/RxNav/APIs/RxNormAPIs.html',
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
        'Marson GWCD4i target-masked perturbation signatures + the Ensembl-keyed GO-BP gene-set bundle (go-basic 2026-06-15 + goa_human GOC snapshot 2026-05-21, 13,805 sets, canonical 5b62e8bc). Two gene universes, never conflated: perturbation-target (11,526 = 11,522 ENSG + 4 symbol-only) and DE-readout (10,282).',
      source_tissue: SOURCE_TISSUE.pathways,
      estimand:
        "Target-ranked pathway convergence over the full target-masked perturbation signatures (not the marker panels): (A) per-arm ranked enrichment scored in the perturbation-target universe (11,526 = 11,522 ENSG + 4 symbol-only, with per-set namespace eligibility) — a weighted running-sum statistic over one arm's ranking with its leading edge, computed once per arm and never summed across arms, with per-arm coverage / headline eligibility; (B) signature convergence scored in the 10,282-gene DE-readout universe — cosine on the shared unmasked support, requiring ≥2 measured perturbations. No p / q / FDR — there is no calibrated null.",
      masks_qc:
        'Gene sets are pinned by source + release + sha256 and namespace-enforced (Ensembl-keyed against the perturbation-target universe); a set with source_coverage < 0.50 in the target namespace is descriptive_only and excluded from headline ranking, still fully computed and emitted.',
      upstream_model:
        'Required upstream: an admitted Stage-2 Direct arm bundle (schema spot.stage02_screen.v3) bound to a generic spot.stage01_selection.v3 contract.',
      limitations: [
        'A convergence claim requires ≥2 measured perturbations; single-target sets are emitted flagged single_target_support, never dropped.',
        'Source-coverage loss is reported per gene-set, per universe, never blended: ranked enrichment uses the 11,526-gene perturbation-target universe (GO-BP loses 51.4288% of member slots); signature convergence uses the 10,282-gene DE-readout universe (GO-BP 56.5884%).',
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
        // GO-BP-ONLY release: GO-BP is the sole released gene-set source, so it is the sole gene-set
        // record in this chain. A second source listed here — with a licence, a URL and bundle hashes —
        // reads as a released co-input of the pathway method, which is exactly what the GO-BP-only rule
        // forbids; the parked Reactome licence/history record lives in the repo's DATA_LICENSES, not in
        // the runtime manifest a served page advertises.
        src('GO Biological Process', 'go-basic 2026-06-15 + goa_human GOC snapshot 2026-05-21 (release IDs from cached file headers) · 13,805 sets · pins identify the derived go_bp_ensembl.genesets.json bytes', {
          url: 'https://geneontology.org/docs/go-citation-policy/', // HTTPS official citation/license (GO download URLs are mutable)
          license: 'CC BY 4.0',
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
        'Within-condition Stage-2 arms.parquet and target_identity.json for the selected endpoint. The browser projection takes the first 200 evaluable targets from each arm in Stage-2 rank order, then joins exact typed target identities to the frozen UniProt 2026_02 / ChEMBL 37 universe store. Rest and Stim8hr bind separate Stage-2 source hashes. No pathway gene sets were read by the current drug artifacts.',
      source_tissue: SOURCE_TISSUE.drugs,
      estimand:
        'Two independent arm views. For each target, the artifact preserves the Stage-2 arm value and rank and attaches exact typed-target ChEMBL mechanisms. evidence_relation is putative_crispri_phenocopy only when mechanism_phenocopies_modality=true; directional_evidence_status separately records whether the measured CRISPRi knockdown supports or opposes the requested program change. Agonism is never labelled a CRISPRi phenocopy and may only appear as an untested inverse hypothesis. No combined drug score or drug ranking is computed.',
      masks_qc:
        'Exact typed-identity join to the frozen target universe. Only unambiguous human single-protein general assertions are usable; complexes, target families, non-human targets, ambiguous identities, symbol-only targets and variant-specific assertions do not become general drug evidence. ChEMBL action type, mechanism and max phase are carried from the source. The 200-target limit is display-only. Current artifacts declare receipt_verified=false and pathway_context_status=not_parsed_no_gene_sets_read.',
      upstream_model: 'Development preview over source-hashed Stage-2 Direct arm and target-identity artifacts. The aggregate Stage-2 receipt was not verified for these artifacts, and no pathway bundle was consumed.',
      limitations: [
        'The current files are development-unadmitted browser projections.',
        'Absence of a linked ChEMBL mechanism is not evidence that a target is undruggable.',
        'A mechanism match does not establish potency in primary CD4 T cells, clinical efficacy or safety.',
      ],
      method_id: 'druglink.dev_emit_ui.build · spot.stage03_ui_drugs.v1 · stage3-modality-v2-observed-sign',
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
        'Condition-specific spot.stage03_ui_drugs.v1 bytes plus the cached spot.stage04_prefetch_receipt.v1. Stage 4 recomputes the Stage-3 raw and canonical content hashes. PubChem property responses and openFDA label responses supply the displayed acquired fields; RxNorm and DailyMed supply identity/product-resolution outcomes retained for unresolved candidates. ChEMBL and UniProt mechanism context is carried from Stage 3.',
      source_tissue: SOURCE_TISSUE.pksafety,
      estimand:
        'Separate evidence lanes, not a ranking: sourced physicochemical properties; CNS-MPO component availability; direct human or nonhuman CNS evidence with evidence type and locator; and verbatim regulatory-label safety sections. A full six-component CNS-MPO total is emitted only when all accepted inputs exist. NEBPI is an evidence framework; the compact preview does not infer a brain-penetrance class from physicochemical proxies or clinical indication.',
      masks_qc:
        'Cached response bytes are verified against their recorded raw SHA-256 before parsing. The current accepted CNS-MPO components are molecular weight, TPSA and HBD; cLogP, cLogD7.4 and most-basic pKa remain missing unless separately sourced under the frozen calculator policy. PubChem XLogP and ChEMBL ALogP remain named proxies and do not silently fill cLogP. Label rows bind label ID, effective time, SPL set ID, application number, brand name, raw response hash and source URL. No LOINC code, label-version field or organ-system field is emitted by this compact schema.',
      upstream_model: 'Current preview: a development Stage-3 UI-drug artifact whose raw and canonical hashes are independently recomputed by Stage 4; the public-evidence receipt is prefetch_only (stage4_admissible=false).',
      limitations: [
        'No full CNS-MPO total is available for the current candidates.',
        'Only direct measured human CNS evidence may change the human brain-evidence status; animal total-radioactivity distribution remains separately typed.',
        'Direct human brain evidence does not establish unbound tumour exposure or glioblastoma exposure.',
        'The compact preview is not a drug ranking and does not emit organ-system safety groups.',
        'Candidates without acquired public evidence remain reported as unacquired or not prefetched rather than dropped.',
      ],
      method_id: 'spot.stage04.pk_safety_compact_writer.v1 · spot.stage04_pk_safety_compact.v1',
      // UNAVAILABLE: no admitted Stage-4 scorecard/result bundle is bound to this page. The real
      // engine is analysis.run_stage4 (valid --help), but a generic invocation does not reproduce a
      // bound admitted artifact — it stays "unavailable" until a concrete admitted bundle is bound.
      reproduce_command: null,
      ...RUN_STATUS_UNAVAILABLE,
    },
    provenance: {
      source_chain: [
        src('Grossman et al., Neuro-Oncology 2026 (NEBPI method framing; no class computed)', 'PMC13338342 · DOI 10.1093/neuonc/noag051 · raw is a dated 2026-07-11 response snapshot; canonical is reproducible', {
          url: 'https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi/BioC_xml/PMC13338342/unicode',
          license: 'CC BY 4.0',
          retrieval_utc: '2026-07-11',
          raw_sha256: GROSSMAN_RAW,
          canonical_sha256: GROSSMAN_CANONICAL,
        }),
        src('Wager et al., ACS Chem Neurosci 2010 (CNS-MPO method framing; no total computed)', 'PMC3368654 · DOI 10.1021/cn100008c · raw is a dated 2026-07-11 fetch snapshot (a live re-fetch may differ)', {
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
  // GO-BP-only Pathways manifest (Reactome removed from data_input / limitations / source_chain).
  pathways: 'f2fd05dbd362ef03db516b5543df61d247fe36bb415ec300cee2fa5abdfcd29e',
  drugs: 'a2705f02676576e92f1fbbc567c388f993440874639412d3ff084d64ffcee310',
  pksafety: '2e3bbb5acd366dc656fa14329a557f8067b8bb6ae8d8d1f9a95ddf1516538d61',
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
