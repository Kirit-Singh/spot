# Data and release policy

spot is an open, reproducible analysis project. Code is released under MIT; each
third-party dataset retains its own terms. `DATA_LICENSES.md` is the authoritative
license inventory and `THIRD_PARTY_NOTICES.md` records the source-specific
attributions.

## Three storage classes

### 1. Git: code and reviewable release metadata

Git may contain:

- source code, tests, schemas, environment locks and documentation;
- content-addressed manifests, registries, small fixtures and compact derived tables;
- static-app assets that are required for an offline review, provided they are derived,
  non-identifying and named in a release manifest; and
- a small, deterministic crosswalk or summary when its source, method, license, row
  count and SHA-256 are recorded.

The normal ceiling for a new data-like Git artifact is **5 MiB**. A larger file needs
an explicit exception in its release manifest and must remain below the hosting
provider's file limit. The currently tracked Stage-1 40,000-cell display JSON files
(approximately 18–21 MiB each) are legacy static-app exceptions. They are display
derivatives, not source matrices or the authoritative 396,000-cell score table. New
large scientific artifacts go to the immutable data release instead. The exact legacy
exceptions, hashes, current roles and retirement conditions are frozen in
`release/legacy_large_file_exceptions.json`.

Do not commit raw single-cell matrices, full differential-expression matrices, full
score Parquet files, model weights, downloaded database snapshots, credentials, tokens,
machine-local paths or transient run products.

### 2. Hugging Face: immutable large public artifacts

Large public inputs and derived release artifacts belong in a versioned Hugging Face
dataset revision. This includes H5AD/Parquet matrices, full score tables and any other
file that is too large or too costly to duplicate in Git. A release must include:

- a dataset card describing the biological source and every transformation;
- an exact immutable revision, per-file SHA-256 and machine-readable manifest;
- matrix dimensions, identifier namespaces, normalization and missing-value semantics;
- the upstream license, attribution and any platform terms; and
- the Git commit and reproduction command that generated each derived output.

Code and manifests must fetch by immutable revision and reject a byte mismatch. A
mutable branch such as `main` is never a scientific pin. Superseding revisions preserve
history; they do not silently replace prior claims. The current public-versus-staged
state and the non-executed publication gate are recorded in
`docs/HF_SUPERSEDING_RELEASE_CHECKLIST.md`.

### 3. Local/compute storage: ignored caches and run outputs

Raw downloads, source-database caches, temporary conversions, solver caches, logs,
scratch directories and complete run outputs stay outside Git. They are either
re-fetched from a pinned public source or reconstructed from a manifest. Recommended
locations are a user-selected `SPOT_DATA_ROOT`, `SPOT_CACHE_ROOT` and `SPOT_RUN_ROOT`;
no machine hostname or absolute path is part of scientific identity.

Secrets are supplied through the host's credential store or process environment and
must never appear in a command transcript, manifest, log, test fixture or repository.

## Required provenance for every admitted source

Before a source or derived statistic enters a release, record:

1. canonical provider URL and identifier (DOI, accession, release or commit);
2. title/provider, version or release date, and UTC access time;
3. exact license and redistribution status;
4. downloaded-file SHA-256 where bytes are cached;
5. source field, method, units and identifier namespace for every displayed number;
6. input/output dimensions and missing-value handling; and
7. the generating Git commit, command, environment lock and run timestamp.

Model-generated references are provisional until independently resolved against a
primary paper or official provider. See the project source-validation rule used for
release review.

## Privacy and public-data boundary

Only publicly released data may enter spot. Coded donor/library identifiers may remain
joinable to the public source but are not anonymous; do not enrich them with donor
demographics or attempt re-identification. Run a field-level privacy review before any
new cell-level artifact is published.

## Release checklist

- Working tree is clean and the exact Git commit is recorded.
- Every data-like file is classified as Git, immutable external artifact or ignored
  cache; no file is present merely because it was convenient locally.
- Source URLs, versions, licenses and claims have been independently verified.
- Manifests re-hash every downloaded and generated file.
- Reproduction starts from public inputs and a solver-locked environment.
- The repo-wide path and credential release tests pass. Machine-specific strings are
  permitted only when named by the narrow, reviewed allowlist as immutable historical,
  environment-build or verifier-test provenance; executable defaults remain portable.
- Scientific hashes are re-derived independently; display/provenance-only changes are
  identified separately from scientific changes.
