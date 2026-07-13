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
