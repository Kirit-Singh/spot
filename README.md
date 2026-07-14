# spot

**spot** is a public-data decision-support workbench that connects continuous
CD4 T-cell transcriptional programs to perturbation targets, pathways, drug
links, and brain-exposure / safety evidence.

**Live reviewer site:** [spotpathways.com](https://spotpathways.com/)

Reviewer access is supplied with the submission.

## Current release

The deployed app has four connected stages across five pages:

1. **Programs** — continuous transcriptional-program scores over the Marson
   GWCD4i CD4 Perturb-seq non-targeting-control cells. These are RNA-program
   measurements, not categorical cell identities.
2. **Targets and pathways** — direct CRISPRi target projections, endpoint
   comparisons, and GO Biological Process context for the two selected program
   directions. The two arms remain separate; the app does not create a hidden
   combined score.
3. **Drugs** — public target-to-drug evidence linked to each desired
   perturbation direction, with molecules shared across the two arms visibly
   identified.
4. **PK & Safety** — public physicochemical, human CNS, exposure, and safety
   evidence, where acquired, shown as separate fields. Missing measurements
   stay unevaluated; physicochemical properties do not confirm brain exposure.

The end-to-end review chain currently covers **Rest** and **Stim8hr**. GO-BP is
the active pathway collection. Reactome and incomplete Stim48hr downstream
chains are deliberately parked rather than presented as finished. Stage 5
(trial design) remains a placeholder and is not part of this release.

## Scientific boundaries

- The workbench generates testable hypotheses; it does not validate a target,
  drug, mechanism, clinical benefit, or safety.
- Stage-1 scores are continuous panel-minus-control RNA measurements. They do
  not establish lineage, protein expression, suppressive function, or
  cytotoxicity.
- The displayed Stage-2 lanes do not report calibrated p-values, q-values, or
  FDR. Rank-derived plot height is descriptive.
- Temporal views compare population-level perturbation effects at two
  endpoints. They do not track individual cells or claim fate conversion.
- PET target engagement is not a CSF concentration, Kp,uu, brain:plasma ratio,
  tumor exposure measurement, efficacy result, or safety result.
- The biological dataset has four donors and is one in vitro CD4 system;
  external biological confirmation remains necessary.

## Repository map

```text
01_programs/   continuous CD4 program scorer, artifacts, and verification
02_geneskew/   direct target, temporal, Pareto, and pathway analysis
03_druglink/   public drug-link contracts and evidence processing
04_PKPD/       PK, CNS-exposure, and safety evidence engine
05_trial/      unimplemented placeholder
_frontend/     Programs / Targets / Pathways / Drugs / PK & Safety UI
deploy/        static release and Cloudflare Pages tooling
functions/     reviewer-access gate and canonical-host routing
```

Stage-specific methods and provenance are available from the **Methods &
provenance** control in each app tab and in the corresponding stage directory.

## Reproducibility and provenance

The repository keeps method definitions, schemas, verification code, and the
small derived display artifacts needed by the app. Large source matrices are
not committed. Stage 1 pins its public H5AD input and reproducibility chain;
downstream artifacts bind their upstream selection and method identities.

All scientific sources must be traceable to a public locator. Model-generated
text is not treated as scientific evidence. Source-specific licensing and
redistribution boundaries are recorded in [`DATA_LICENSES.md`](DATA_LICENSES.md).

## Development

```bash
cd _frontend
npm ci
npm test
npm run build
```

Stage-specific environments and commands are documented in
[`01_programs/README.md`](01_programs/README.md),
[`02_geneskew/README.md`](02_geneskew/README.md),
[`03_druglink/README.md`](03_druglink/README.md), and
[`04_PKPD/README.md`](04_PKPD/README.md).

## License

Project code is MIT licensed. Third-party data and reference material retain
their own terms; the MIT license does not override them. See
[`DATA_LICENSES.md`](DATA_LICENSES.md) before redistributing derived data.
