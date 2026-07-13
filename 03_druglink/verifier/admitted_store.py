"""The ADMITTED universe store, bound by exact identity. Verifier side.

Stage-3 target admission consumes the store and manifest from **tcefold**, by exact
identity. Git carries only compact reports, so a checked-in report is NOT the binding —
binding to one is how a stale store gets consumed while everything still looks green.
"""
from __future__ import annotations

from typing import Any

from .report import Report


# --------------------------------------------------------------------------- #
# THE ADMITTED UNIVERSE STORE. Bound by exact identity — this is the only one.
#
# Git carries only compact reports, so the CHECKED-IN reports are NOT the binding. Stage-3
# target admission consumes the store and manifest by EXACT IDENTITY.
#
# Independently re-derived from those bytes (not accepted from the producer): the bound
# content hashes recompute, all 11,055 eligibility verdicts REPLAY with zero mismatches,
# and the PRODUCER's own gate refuses a mutated and a deleted provenance by name.
# Sealed report: STAGE3_UNIVERSE_CACHE_FINAL_ADMISSION.4aba8b58.md
#
# RE-PINNED at the NAMESPACE-VOCABULARY standardisation. The store was re-emitted so it
# serializes the tokens Stage 2 (W3) serializes — `ensembl_gene_id` / `gene_symbol` — because
# exact-token equality against the old `ensembl_gene` / `symbol` refused every real Ensembl row
# and produced ZERO edges. The identity necessarily MOVED (the typed universe hashes the
# identity PAIR); the SCIENCE did not, and that is proved rather than asserted: the store's
# scientific content hash — every row with `target_id_namespace` projected out — is IDENTICAL
# on both sides at 95f81cb1…. Same 11,526 rows, same 2,262 assertions, same 505 targets, same
# 1,923 molecules, same licences and provenance bytes. See `druglink.universe_repin`.
# --------------------------------------------------------------------------- #
# WHERE THE BYTES ARE, said accurately rather than conveniently. The EXTRACTION ran on tcefold
# (it needed the 30 GB ChEMBL SQLite); the vocabulary RE-PIN is a pure re-serialisation of those
# same bytes and ran on tcedirector, which is where the admitted store now sits. Either way it
# is an out-of-repo cache: Git carries only compact reports, so a checked-in report is NOT the
# binding — binding to one is how a stale store gets consumed while everything still looks green.
ADMITTED_STORE_PATH = "/home/tcelab/.cache/spot-stage3-universe-w3tokens/store/"
ADMITTED_STORE_IS_OUT_OF_REPO = True
EXTRACTION_HOST = "tcefold"
SOURCE_EXTRACTION_STORE_PATH = "tcefold:/home/tcelab/.cache/spot-stage3-universe/store/"
ADMITTED_PRODUCER_COMMIT = "d268a74f339d346609951e73810ab26e2e654d86"
ADMITTED_STORE_ID = \
    "625c921fce2daf60b69fb0ae33570a9f074a0a0042b1717ee2111f81c1160bff"
ADMITTED_MANIFEST_CONTENT_SHA256 = \
    "c07d24038ac10f1051607d3a9c1532d8384e7bf4a95d1a2f1f4a104c7222736f"
ADMITTED_TYPED_UNIVERSE_SHA256 = \
    "1c19db2b5d666a8f33c715cb634cf111953c7cdd6c23d082e9b375643a3e7cc8"
# Carried through the re-pin byte-for-byte, and pinned to prove it.
ADMITTED_ELIGIBILITY_EVIDENCE_SHA256 = \
    "cf5d70884240d2e8ba9c2c5c60a986cf1ec665e73d2ae821d47495dff174167c"
ADMITTED_PROVENANCE_SHA256 = \
    "72ef88dcb0538f39b2ea04982495ce6e6eb0be04ed80bd5b0b72bbd81f6ca81c"
ADMISSION_REPORT_SHA256 = \
    "4aba8b5882e5ea32707875fc5026ca6b0b5d811ad01412bfa4b121c29b283bfb"
# The invariant the re-pin had to preserve, and did. A vocabulary moved; no science did.
ADMITTED_SCIENTIFIC_CONTENT_SHA256 = \
    "95f81cb11abf1b39d9345edb182344f0b90b60e08dd7605145b40c08eda391eb"

# Every store Stage 3 has seen and REFUSED. Kept so a stale binding cannot be reintroduced
# by accident — and because `bdf41b69` under the WRONG PRODUCER is still a refusal: the
# bytes were fine, the gate that shipped with them was not.
REFUSED_STORES = {
    "bdf41b69df2be61d3f625aafa0429e643581fe50823698e77e079054c6145160":
        "RETIRED NAMESPACE VOCABULARY: types its rows `ensembl_gene`/`symbol` while Stage 2 "
        "serializes `ensembl_gene_id`/`gene_symbol`, so the exact-typed join refuses all "
        "11,522 of its Ensembl rows and yields ZERO edges. Its science is CARRIED FORWARD "
        "byte-for-byte in 625c921f… — same rows, same assertions, same scientific content hash "
        "(95f81cb1…). Re-admitting it would re-open the divergence the re-pin closed.",
    "446c3b78937593e89d13afe941eb3a6dbe6d37e3beac17f7edd5dd0abdde914d":
        "pre-repair (e298770): nested ambiguous assertions rankable; no provenance binding",
    "b20ec29bf3d829a23b1c13cd60cd37779fb78c69328d2531b376d0d4bf2f886e":
        "MY RETRACTED ADMISSION (0e349b1): I passed it on my own verifier while the "
        "PRODUCER's gate was fail-open on a deleted provenance file",
}
REFUSED_PRODUCERS = {
    "d6066b7759a8bc57190365732f316b111eab85a1":
        "shipped the provenance-gate REPORT, not the gate; verify_from_disk still returned "
        "ok=True on a deleted provenance. Same store bytes as d268a74 — still refused.",
}

# Counts INDEPENDENTLY RE-DERIVED from the admitted store. Reproduced, never accepted.
ADMITTED_COUNTS = {
    "chembl_mappings_evaluated": 11_055,
    "eligible": 5_869,
    "rejected": 5_186,
    "universe_total": 11_526,
    "universe_ensg": 11_522,
    "universe_symbol_only": 4,
    "drug_evidence_targets": 505,
    "no_drug_evidence": 10_931,
    "ambiguous_identity": 86,
    "unsupported_namespace": 4,
    "assertion_occurrences": 2_262,
    "unique_source_mechanism_rows": 2_258,
    "general_drug_assertions": 2_227,
    "variant_specific_assertions": 29,
}


def check_admitted_store_is_bound(rep: Report, binding: dict[str, Any]) -> None:
    """Stage-3 target admission consumes the admitted store by EXACT identity."""
    store_id = binding.get("store_id")

    refused = REFUSED_STORES.get(str(store_id))
    if refused:
        rep.check(
            f"the bound store is not a REFUSED one ({str(store_id)[:8]}…)",
            False, refused)
        return

    rep.check(f"the bundle binds the ADMITTED store_id ({ADMITTED_STORE_ID[:8]}…), not a "
              "checked-in report",
              store_id == ADMITTED_STORE_ID, f"got {str(store_id)[:16]}…")
    rep.check(f"the bundle binds the admitted manifest content hash "
              f"({ADMITTED_MANIFEST_CONTENT_SHA256[:8]}…)",
              binding.get("manifest_content_sha256") == ADMITTED_MANIFEST_CONTENT_SHA256,
              f"got {str(binding.get('manifest_content_sha256'))[:16]}…")

    producer = binding.get("producer_commit")
    refused_p = REFUSED_PRODUCERS.get(str(producer))
    rep.check(
        f"the bound producer is the admitted one ({ADMITTED_PRODUCER_COMMIT[:7]}) — the "
        "SAME BYTES under a different producer are NOT admitted",
        producer == ADMITTED_PRODUCER_COMMIT,
        refused_p or f"got {str(producer)[:7]}")

# The evidence artifact — shipped on tcefold, copied, and independently replayed.
W2_EVIDENCE_SHIPPED = True
W2_STORE_PATH = ADMITTED_STORE_PATH

# Independently reproduced by Stage 3 against the real bytes (not accepted from W2):
W2_REPLAY = {
    "eligibility_records_replayed": 11_055,
    "verdict_mismatches": 0,
    "ambiguous_identity_rows": 86,
    "ambiguous_rows_carrying_drug_evidence": 0,
    "variant_assertions": 29,
    "variant_assertions_leaking_into_general_ranking": 0,
    "variant_undefined_mutation_sentinels": 10,     # variant_id == -1
    "store_rows": 11_526,
}


# The store is on TCEFOLD; Git carries only compact reports. Independently re-derived from
# the admitted bytes — reproduced, never accepted from the producer's own report.
EVIDENCE_SHIPPED = True

ADMITTED_REPLAY = {
    "eligibility_records_replayed": 11_055,
    "verdict_mismatches": 0,
    "ambiguous_identity_rows": 86,
    "ambiguous_rows_carrying_drug_evidence": 0,
    "ambiguous_nested_assertions": 6,               # mec 6210/6862 on CALM1/2/3
    "ambiguous_nested_assertions_rankable": 0,      # closed at d268a74
    "variant_assertions": 29,
    "variant_assertions_leaking_into_general_ranking": 0,
    "variant_undefined_mutation_sentinels": 10,     # variant_id == -1
    "store_rows": 11_526,
    "producer_gate_rejects_mutated_provenance": True,
    "producer_gate_rejects_deleted_provenance": True,
}
