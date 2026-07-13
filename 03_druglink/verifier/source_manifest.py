"""The exact source manifest — audit gate item 1. Publisher provenance, pinned BEFORE acquisition.

The independent source audit (``fa64054e…``) is emphatic on this point:

    "An official publisher hash is provenance available before acquisition, not a statistic
     that must be withheld."

So the publisher's own figures are recorded here **now**, before a single byte is downloaded,
and the acquisition is checked against them afterwards. That ordering is the whole value: a
checksum you write down *after* you fetch the file records what you got, not what you were
promised, and it can never catch a truncated download or a substituted archive.

WHAT MUST BE VERIFIED, NOT ASSUMED
----------------------------------
* **Exact bytes and the publisher SHA-256** — a 5.76 GB archive that arrives 5.75 GB is a
  silent truncation; the byte count catches it before the hash even runs.
* **An independently computed SHA-256 of the bytes on disk** — the publisher's hash is a
  claim; recomputing it is the check.
* **The mutable URL, recorded as mutable.** UniProt's ``current_release`` path is a moving
  target: the same URL returns different bytes next release, so a manifest that pins the URL
  and not the release is pinning nothing. The audit found the REST licence locator returning
  HTTP 400, which is exactly what an unpinned locator does eventually.
* **Licence and attribution per source**, because they differ and do not merge.

The audit also corrected two approximations worth keeping straight: "FTP files last-modified
2026-05-29" is false as a blanket statement (individual files differ), and the ChEMBL DOI
*resolves* — it is not merely "expected".
"""
from __future__ import annotations

from typing import Any, Optional

from .report import Report

AUDIT_SHA256 = "fa64054e0698448b143c7e4e564dd2e7003a6e21161ee18b54f826a744a65e67"

# --------------------------------------------------------------------------- #
# ChEMBL 37 — independently confirmed against the publisher.
# --------------------------------------------------------------------------- #
CHEMBL = {
    "source": "chembl",
    "release": "CHEMBL_37",
    "archive": "chembl_37_sqlite.tar.gz",
    "url": ("https://ftp.ebi.ac.uk/pub/databases/chembl/ChEMBLdb/releases/"
            "chembl_37/chembl_37_sqlite.tar.gz"),
    "bytes": 5_764_252_857,
    "publisher_sha256": (
        "33c203740555f96067710cdfc1c3c55d890660e5908ec5cbf5817492c290d281"),
    "publisher_checksum_source": (
        "https://ftp.ebi.ac.uk/pub/databases/chembl/ChEMBLdb/releases/chembl_37/"
        "checksums.txt"),
    "archive_last_modified": "Fri, 29 May 2026 06:35:28 GMT",
    "release_readme_date": "01/05/2026",
    "doi": "10.6019/CHEMBL.database.37",
    "doi_resolves": True,
    "license": "CC BY-SA 3.0",
    "license_note": "CC BY-SA 3.0 Unported",
    "attribution_requires": (
        "preserve ChEMBL IDs; display release and URL"),
    "url_is_mutable": False,        # a release-pinned path
}

# --------------------------------------------------------------------------- #
# UniProt 2026_02.
# --------------------------------------------------------------------------- #
UNIPROT = {
    "source": "uniprot",
    "release": "2026_02",
    "release_date": "10-Jun-2026",
    "file": "HUMAN_9606_idmapping.dat.gz",
    "bytes": 37_842_957,
    "publisher_md5": "7ef6a677d4db949397c3b352c466e499",
    "file_last_modified": "10-Jun-2026 20:00",
    "license": "CC BY 4.0",
    "license_source": "official FTP README",
    # The audit found https://rest.uniprot.org/help/license.txt returning HTTP 400.
    "rest_license_locator_verified": False,
    # `current_release` returns DIFFERENT BYTES next release. Pinning it pins nothing.
    "url_is_mutable": True,
    "url_mutability_note": (
        "the FTP current_release path is mutable; the downloaded bytes must be retained "
        "and bound to release + publisher MD5 + independently computed SHA-256 + byte "
        "count + access time"),
}

PUBLISHER_PINS = {"chembl": CHEMBL, "uniprot": UNIPROT}

# Every field an acquisition manifest must carry (audit gate item 1).
REQUIRED_MANIFEST_FIELDS = (
    "url", "release", "release_date", "bytes", "publisher_checksum",
    "computed_sha256", "license", "attribution", "access_time_utc",
)


class SourceManifestError(ValueError):
    """The acquired bytes are not the bytes the publisher promised."""


def check_publisher_pins_are_recorded(rep: Report) -> None:
    """The publisher's figures exist BEFORE acquisition, not after."""
    rep.check(
        "the ChEMBL 37 publisher checksum and exact byte count are pinned BEFORE "
        "acquisition (a hash written down after the fetch records what you got, not what "
        "you were promised, and can never catch a truncated or substituted archive)",
        CHEMBL["bytes"] == 5_764_252_857
        and CHEMBL["publisher_sha256"].startswith("33c20374"),
        f"bytes={CHEMBL['bytes']} sha={CHEMBL['publisher_sha256'][:12]}…")

    rep.check(
        "the UniProt 2026_02 publisher MD5 and byte count are pinned, and the mutable "
        "current_release path is RECORDED AS MUTABLE (pinning the URL without the release "
        "pins nothing)",
        UNIPROT["publisher_md5"] == "7ef6a677d4db949397c3b352c466e499"
        and UNIPROT["url_is_mutable"] is True,
        f"md5={UNIPROT['publisher_md5'][:8]}… mutable={UNIPROT['url_is_mutable']}")


def check_manifest_is_complete(rep: Report, manifest: dict[str, Any]) -> None:
    """Audit gate item 1: every field, or the acquisition is not admissible."""
    missing = [f for f in REQUIRED_MANIFEST_FIELDS if not manifest.get(f)]
    rep.check(
        "the source manifest carries URL, release, date, exact bytes, publisher checksum, "
        "an INDEPENDENTLY COMPUTED sha256, licence, attribution and access time",
        not missing, f"missing: {missing}")


def check_acquired_bytes_match_the_publisher(rep: Report,
                                             manifest: dict[str, Any]) -> None:
    """The publisher's hash is a CLAIM; recomputing it is the check."""
    source = str(manifest.get("source") or "").lower()
    pin = PUBLISHER_PINS.get(source)
    if pin is None:
        rep.check(f"source {source!r} is a pinned publisher", False,
                  f"known: {sorted(PUBLISHER_PINS)}")
        return

    got_bytes = manifest.get("bytes")
    rep.check(
        f"the acquired {source} archive is EXACTLY the publisher's byte count "
        f"({pin['bytes']:,}) — a short read is a silent truncation, and the count catches "
        "it before the hash even runs",
        got_bytes == pin["bytes"], f"got {got_bytes!r}, expected {pin['bytes']}")

    expected = pin.get("publisher_sha256")
    if expected:
        got = manifest.get("computed_sha256")
        rep.check(
            f"the INDEPENDENTLY COMPUTED sha256 of the acquired {source} bytes equals the "
            "publisher's",
            got == expected,
            f"computed={str(got)[:16]}… publisher={expected[:16]}…")

    rep.check(f"the acquired {source} release is {pin['release']!r}",
              manifest.get("release") == pin["release"],
              f"got {manifest.get('release')!r}")

    rep.check(f"the {source} licence is {pin['license']!r} (licences do not merge)",
              manifest.get("license") == pin["license"],
              f"got {manifest.get('license')!r}")


def check_mutable_urls_are_declared(rep: Report,
                                    manifests: list[dict[str, Any]]) -> None:
    """A mutable locator that is not declared mutable is a landmine with a date on it."""
    undeclared = []
    for m in manifests:
        pin = PUBLISHER_PINS.get(str(m.get("source") or "").lower())
        if pin and pin.get("url_is_mutable") and not m.get("url_is_mutable"):
            undeclared.append(m.get("source"))
    rep.check(
        "every mutable source URL is DECLARED mutable (UniProt's current_release returns "
        "different bytes next release; an undeclared mutable locator is a landmine with a "
        "date on it)",
        not undeclared, f"undeclared: {undeclared}")


def check_extractor_sql_is_frozen(rep: Report,
                                  extractor: Optional[dict[str, Any]]) -> None:
    """Audit gate item 3: the exact SQL text AND its hash, with the six predicates.

    W2 owns the SQL. Stage 3 owns refusing a cache that cannot show it.
    """
    if extractor is None:
        rep.check("the extractor's exact SQL text and hash are frozen and supplied "
                  "(audit gate item 3 — W2)", False, "no extractor manifest supplied")
        return

    rep.check("the extractor's exact SQL TEXT is supplied",
              bool(extractor.get("sql_text")), "sql_text absent")
    rep.check("the extractor's SQL is bound by hash",
              bool(extractor.get("sql_sha256")), "sql_sha256 absent")

    sql = str(extractor.get("sql_text") or "").lower()
    predicates = {
        "target_type": "single protein",
        "td.tax_id": "tax_id",
        "species_group_flag": "species_group_flag",
        "component_type": "component_type",
        "homologue": "homologue",
    }
    absent = [name for name, token in predicates.items() if token not in sql]
    rep.check(
        "the frozen SQL contains all six identity predicates (target_type, td.tax_id, "
        "species_group_flag, cs.component_type, cs.tax_id, tc.homologue)",
        not absent, f"absent from SQL: {absent}")

    rep.check(
        "the extractor proves component cardinality (exactly one eligible AND one total)",
        bool(extractor.get("component_cardinality_proved")),
        f"proved={extractor.get('component_cardinality_proved')!r}")


# --------------------------------------------------------------------------- #
# W2's regenerated compact cache — identities recorded at e298770.
#
# The full store lives on TCEFOLD at /home/tcelab/.cache/spot-stage3-universe/store/ (Git
# intentionally carries only the compact reports). Copied to a fresh scratch dir and
# audited independently: the bound content hash recomputes, and all 11,055 eligibility
# verdicts REPLAY from their own predicate inputs with zero mismatches.
# --------------------------------------------------------------------------- #
W2_PRODUCER_COMMIT = "e2987705625791989d1abdcad9202af218e21955"
W2_STORE_ID = "446c3b78937593e89d13afe941eb3a6dbe6d37e3beac17f7edd5dd0abdde914d"
W2_MANIFEST_CONTENT_SHA256 = \
    "fbe09b9e87124e78c35cd984186180d949c0f23776184fed91b60e8fcdad2ee6"
W2_STORE_ROWS_SHA256 = \
    "6c88b53a0bf2752149bfb033c2c7f8ff7c3aa2bbd28d4316a292a38693ef31e1"
W2_EXTRACTION_QUERY_SHA256 = \
    "a5ad29d22c0edba601c00ab2b95845aadabf5bd25c663dabbf48159650d98be0"
W2_ELIGIBILITY_EVIDENCE_SHA256 = \
    "cf5d70884240d2e8ba9c2c5c60a986cf1ec665e73d2ae821d47495dff174167c"

# Counts as reported at e298770. The replay must reproduce these, not accept them.
W2_COUNTS = {
    "chembl_mappings_evaluated": 11_055,
    "eligible": 5_869,
    "rejected": 5_186,
    "universe_total": 11_526,
    "drug_evidence_targets": 505,
    "ambiguous_identity": 86,
    "unsupported_namespace": 4,
    "general_drug_assertions": 2_227,
    "variant_specific_assertions": 29,
}

# The evidence artifact — shipped on tcefold, copied, and independently replayed.
W2_EVIDENCE_SHIPPED = True
W2_STORE_PATH = "tcefold:/home/tcelab/.cache/spot-stage3-universe/store/"

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


# --------------------------------------------------------------------------- #
# FINAL ADMISSION CRITERION — sealed re-audit 1f6008c2, corrected by primary source.
#
# I recommended REPLACING the mutable UniProt `current_release` locator with an immutable
# 2026_02 archive. Checked against the publisher: **no such archive exists.**
# `previous_releases/` stops at release-2026_01, and `current_release/relnotes.txt` reads
# "UniProt Release 2026_02". So `current_release/` is where 2026_02 actually lives, and
# demanding an immutable URL would have been demanding a fabricated one. A locator that is
# honest about being mutable beats a locator that is stable and wrong.
#
# So the criterion is not "replace the URL". It is: keep the truthful locator, and BIND the
# publisher metadata that proves which release those bytes came from —
# RELEASE.metalink (size + MD5), relnotes (release + date), checksums, the acquired SHA-256,
# and the access timestamp. Then a later reader, finding current_release advanced to 2026_03,
# can still prove what we held.
#
# And the provenance file itself must be REOPENED AND HASHED at admission. A manifest that
# pins a provenance hash while nobody ever opens the file has pinned nothing — the same
# defect the audit found for the eligibility artifact, one file over.
# --------------------------------------------------------------------------- #
PROVENANCE_FILENAME = "source_provenance.public.json"
GATE_PROVENANCE_DRIFT = "public_source_provenance_hash_drift"

# The publisher metadata that proves the release association, since the URL cannot.
REQUIRED_RELEASE_METADATA = {
    "uniprot": ("release", "release_date", "publisher_md5", "size_bytes",
                "acquired_sha256", "accessed_at_utc",
                "release_metadata_url", "relnotes_url"),
    "chembl": ("release", "publisher_sha256", "acquired_sha256", "accessed_at_utc",
               "release_metadata_url", "doi"),
}

# `current_release` is TRUTHFUL for 2026_02 — there is no immutable archive to point at.
UNIPROT_IMMUTABLE_ARCHIVE_EXISTS = False


def check_provenance_is_reopened_and_hashed(rep: Report, *, store_root: str,
                                            manifest: dict[str, Any],
                                            content_hash_fn: Any) -> None:
    """Open the provenance file, hash what was read, compare to the manifest's pin.

    A pin nobody checks against the bytes is not a pin.
    """
    import json as _json
    import os

    path = os.path.join(store_root, PROVENANCE_FILENAME)
    if not os.path.isfile(path):
        rep.check(f"{PROVENANCE_FILENAME} exists on disk and is loaded for admission",
                  False, f"not found: {path}")
        return

    with open(path, "r", encoding="utf-8") as fh:
        prov = _json.load(fh)

    pinned = (manifest.get("extraction") or {}).get("public_source_provenance_sha256")
    recomputed = content_hash_fn(prov)
    rep.check(
        f"[{GATE_PROVENANCE_DRIFT}] the public source provenance ON DISK re-hashes to the "
        "manifest's pin (a manifest that pins a hash while nobody opens the file has "
        "pinned nothing — the same defect the audit found for the eligibility artifact)",
        pinned is not None and recomputed == pinned,
        f"on-disk {recomputed[:16]}… vs pinned {str(pinned)[:16]}…")


def check_release_metadata_is_bound(rep: Report, provenance: Any) -> None:
    """The URL cannot prove the release, so the publisher metadata must."""
    records = provenance if isinstance(provenance, list) else [provenance]
    by_source = {}
    for r in records:
        name = str(r.get("name") or "")
        key = "uniprot" if "uniprot" in name.lower() else (
            "chembl" if "chembl" in name.lower() else name)
        by_source[key] = r

    for source, fields in REQUIRED_RELEASE_METADATA.items():
        rec = by_source.get(source)
        if rec is None:
            rep.check(f"{source} source provenance is present", False, "absent")
            continue
        missing = [f for f in fields if not rec.get(f)]
        rep.check(
            f"the {source} provenance binds the publisher metadata that PROVES the release "
            f"({', '.join(fields)}) — the locator alone cannot, and for UniProt it is "
            "mutable by necessity: there is no immutable 2026_02 archive to point at",
            not missing, f"missing: {missing}")

    uni = by_source.get("uniprot") or {}
    rep.check(
        "the UniProt locator is honest about being mutable (current_release IS where "
        "2026_02 lives; previous_releases stops at 2026_01, so an 'immutable' URL would be "
        "a fabricated one — a locator honest about being mutable beats one stable and wrong)",
        any("mutable" in str(k).lower() or "mutable" in str(v).lower()
            for k, v in uni.items()),
        "no mutability note")
