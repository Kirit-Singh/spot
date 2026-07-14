# 03_druglink — link perturbation targets to public drug evidence

Stage 3 consumes the two independent Stage-2 target arms and links them to public drug/target
evidence. The current release binds ChEMBL-derived drug facts and UniProt protein identities.
DGIdb, Open Targets, LINCS and DepMap-family sources are historical or deferred; they are not
advertised as evidence in the admitted release.

Direction is explicit: a drug mechanism is shown as CRISPRi-aligned, opposed or not evaluable for
each arm. A molecule present in both arms may be highlighted as shared set membership, but the app
does not collapse the two arms into a joint score or clinical ranking.

The result is a drug-link hypothesis, not evidence that pharmacology reproduces genetic
knockdown, reaches the brain, benefits glioblastoma or is safe. Stage 4 displays those evidence
questions separately where public records were acquired.

- `inputs/` — admitted Stage-2 target/pathway artifacts
- `analysis/` — target/drug identity, direction, evidence contracts and verifiers
- release artifacts — bounded drug/target records with source releases and provenance
