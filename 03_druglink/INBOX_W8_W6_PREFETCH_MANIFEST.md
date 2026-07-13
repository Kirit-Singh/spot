# W16 → W8, W6: PREFETCH-ONLY drug-candidate manifest — **v2, CORRECTED**

## ⚠ RETRACTION — do not fetch from the previous version

The first manifest (`353b7920…`) emitted **`source_locator: null` and `source_release: null` on all
455 rows**, while this handoff claimed every row carried "the exact public-source lookup key".

Those field names did not exist on the store's edges. `.get()` returned `None`, and the nulls were
published as keys. Nothing crashed; nothing failed a schema; the manifest was content-addressed,
deterministic and internally consistent — **and wrong in the way that is hardest to see: a field
that is absent, presented as a field that is present.** W8 was one step from fetching against 455
nulls.

`353b7920…` is superseded and must not be consumed.

## The artifact

```
path             /home/tcelab/.spot-runs/stage3-universe-20260713/prefetch/
                   prefetch_manifest.ed29138bbf3210ac.json
raw_sha256       8532b85b5cd23fe0e0318b117909983e5f44b5d60b58026e003911a33d70954e
manifest_sha256  ed29138bbf3210acf21d987b18369a2278790fc8def6d1b9538d5cc93efd2b72
schema           spot.stage03_prefetch_manifest.v1
artifact_class   prefetch_only
```

## Counts

| | |
|---|---|
| Direct arms | 60 |
| target ids in Direct prefixes (union, deduped) | 2,841 |
| resolved in the admitted universe | 2,841 — **0 unresolved, 0 ambiguous** |
| targets carrying a qualifying record | 101 |
| **prefetch records (what W8 fetches)** | **455** |
| **records with a stated source_locator** | **455 / 455** |
| records with no source_locator | **0** |
| distinct molecules | 439 |

## Every record — verified non-null across all 455

```json
{
  "target_id":            "ENSG00000004487",
  "target_id_namespace":  "ensembl_gene_id",
  "molecule_chembl_id":   "CHEMBL4297289",
  "molecule_pref_name":   "BOMEDEMSTAT",          // SOURCE-VERBATIM
  "source_locator":       "chembl:CHEMBL_37:drug_mechanism/8350",
  "lookup_key_status":    "stated",
  "machine_lookup_key":   "CHEMBL4297289",
  "machine_lookup_key_kind": "molecule_chembl_id",
  "source_release":       "CHEMBL_37",
  "mec_id":               8350,
  "action_type_source":   "INHIBITOR",            // verbatim, uninterpreted
  "mechanism_of_action":  "...",
  "mechanism_refs":       ["https://www.fda.gov/...", "https://www.ema.europa.eu/..."],
  "cross_ref_provenance": {"pubchem_cid": "not_in_pinned_sqlite_source", ...}
}
```

`source_locator` is built by the **producer's own** `assertions_v2.source_locator`, which
**refuses** rather than emit a locator that resolves to nothing. Where one cannot be built, the row
says **`lookup_key_status: not_available`** and W8 falls back to `machine_lookup_key`
(`molecule_chembl_id`), which is an exact machine key. **A null is never dressed as a key.**

(In this run: 455/455 stated, 0 not_available.)

## Phrasing correction: absence

We now say **"no qualifying drug evidence in the bound store"** — *never* "has no drug".

The store is ChEMBL 37, filtered to the general-gene rankable lane. A target absent from it may
still carry evidence **in a source this store does not bind, in a lane it excludes, or in a later
release**. "Has no drug" states a fact about the *world* when we only have a fact about *this
store* — and a reader who believes it stops looking.

**2,740 of the 2,841 resolved targets have no qualifying drug evidence in the bound store.** That is
a finding, not a gap.

## Attribution (required by licence — please carry it)

ChEMBL 37 · `10.6019/CHEMBL.database.37` · **CC BY-SA 3.0** — preserve ChEMBL IDs and display the
release. UniProt 2026_02 · CC BY 4.0.

## Still cannot become a result

`artifact_class: prefetch_only` is refused by Stage-3's own `artifact_class.require()` — there are
exactly two classes, `analysis` and `fixture`. Admission raises `ArtifactClassError` before a row is
read. **A type error, not a convention.** No score, no rank, no cross-arm ordering; records sort by
identity, an order that carries no claim.

17 regression tests now hold this, each asserting a **value** — a key-existence test would have
passed on the broken manifest.
