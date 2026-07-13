# Synthetic acquisition fixtures

**Every byte in this directory is invented.** These are response-SHAPED documents used to
exercise the acquisition adapters offline. No real drug, CID, RxCUI, UNII, set ID or FDA
application number appears here, and nothing in this directory is evidence about anything.

Real responses are **never** committed. The acquisition layer caches live bytes outside Git,
under a caller-supplied run root (`RunRoot` refuses a cache inside the working tree), and
DailyMed in particular has **no verified blanket licence** — full live labels must not enter
this repository. See `04_PKPD/method/acquisition_sources_v1.json`.

| File | Shape of | Used for |
|---|---|---|
| `pubchem_name_cids.json` | PUG REST `compound/name/{name}/cids/JSON` | one CID — the happy path |
| `pubchem_name_cids_ambiguous.json` | same | two CIDs — refusal |
| `pubchem_cid_properties.json` | PUG REST `compound/cid/{cid}/property/…/JSON` | supported descriptors only |
| `rxnorm_rxcui.json` | RxNav `rxcui.json?name=…` | RxCUI crosswalk |
| `rxnorm_rxcui_ambiguous.json` | same | two RxCUIs — refusal |
| `dailymed_spls.json` | DailyMed v2 `spls.json?drug_name=…` | one product — deterministic selection |
| `dailymed_spls_ambiguous.json` | same | two products — refusal, never a first hit |
| `dailymed_spl.xml` | DailyMed v2 `spls/{setid}.xml` | UNII identity **and** nested warnings |
| `openfda_label.json` | openFDA `drug/label.json` | set-ID → application number |
| `openfda_label_conflicting.json` | same | a second UNII — identity conflict |
| `drugsfda.json` | openFDA `drug/drugsfda.json` | approval cross-check |
| `drugsfda_conflicting.json` | same | a different application number — approval conflict |
