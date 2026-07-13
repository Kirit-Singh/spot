"""Replay the target-eligibility decision. The producer's verdict is a CLAIM, not a result.

The compact cache **cannot prove its own accepted mappings**. The producer applies the six
identity predicates and then discards the fields it applied them to, shipping only the
verdict. So a row that says ``accepted`` is asking to be believed: nothing downstream can
check whether the taxon really was 9606, whether the component really was a PROTEIN, whether
``homologue`` really was 0, or whether the target really had exactly one component.

An unfalsifiable "accepted" is not evidence of eligibility. It is a promise about a
computation nobody kept the inputs to.

So a **sanitized target_eligibility_evidence artifact** is required for EVERY mapping — both
accepted and rejected — carrying the predicate INPUTS, and Stage 3 **re-derives the verdict
from them** rather than reading it.

WHY THE CONTENT HASH CANNOT BE THE DEFENCE
------------------------------------------
A content hash catches tampering by someone who forgets to reseal. It catches nothing from
an attacker who mutates a record and recomputes the hash — the artifact is then perfectly,
internally consistent and says the wrong thing.

What catches a **resealed** attack is the REPLAY: flip an accepted record's ``tax_id`` to
10090 and reseal, and the hash now verifies while the replay says *reject* where the record
says *accept*. The contradiction is between the record's own inputs and its own verdict, and
no amount of resealing can remove it — the only way to hide it is to also change the verdict
to ``rejected``, which is exactly the honest outcome.

Both checks ship. The hash proves the bytes are the ones that were judged; the replay proves
the judgement was right.

REJECTED ROWS MATTER AS MUCH AS ACCEPTED ONES
---------------------------------------------
Coverage is over BOTH. A producer that drops its rejections looks identical to one that had
none — and "no rejections" from a store that contains mouse targets, homologues and
multi-component entries is not a clean bill of health, it is a missing gate.

Schema is coordinated with W2 (see ``EVIDENCE_SCHEMA`` / ``REQUIRED_RECORD_FIELDS``).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Optional

from . import cache_identity as ci
from . import policy
from .report import Report

EVIDENCE_SCHEMA = "spot.stage03_target_eligibility_evidence.v1"
EVIDENCE_FILENAME = "target_eligibility_evidence.json"

ACCEPTED = "accepted"
REJECTED = "rejected"
VERDICTS = (ACCEPTED, REJECTED)

# The predicate INPUTS. Every one of these is a field the producer currently discards.
REQUIRED_RECORD_FIELDS = (
    "target_chembl_id", "accession",
    "target_type", "tax_id", "species_group_flag",
    "component_type", "component_tax_id", "homologue",
    "n_components_total", "n_components_eligible",
    "verdict",
)

# The artifact's own identity + the identity of what produced it.
REQUIRED_BINDINGS = (
    "schema_version", "store_id", "content_sha256",
    "query_sha256", "chembl_release", "source_sha256", "extractor_code_sha256",
)


class EligibilityEvidenceError(ValueError):
    """The eligibility evidence is absent, incomplete, or does not survive replay."""


def _int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# The replay. Independently re-derives the verdict from the record's OWN inputs.
# --------------------------------------------------------------------------- #
def replay(record: dict[str, Any]) -> tuple[str, str]:
    """Re-derive (verdict, reason) from the predicate inputs. Never reads `verdict`.

    Mirrors the six frozen predicates plus the cardinality proof, using the same constants
    as ``cache_identity`` so the two cannot drift apart.
    """
    missing = [f for f in REQUIRED_RECORD_FIELDS if f not in record]
    if missing:
        return REJECTED, f"{ci.DISP_CACHE_TOO_COARSE}: missing {missing}"

    if record["target_type"] != ci.SINGLE_PROTEIN:
        return REJECTED, ci.DISP_NOT_SINGLE_PROTEIN
    if _int(record["tax_id"]) != ci.HUMAN_TAX_ID:
        return REJECTED, ci.DISP_NON_HUMAN_TARGET
    if _int(record["species_group_flag"]) != 0:
        return REJECTED, ci.DISP_SPECIES_GROUP
    if record["component_type"] != ci.COMPONENT_PROTEIN:
        return REJECTED, ci.DISP_NON_PROTEIN_COMPONENT
    if _int(record["component_tax_id"]) != ci.HUMAN_TAX_ID:
        return REJECTED, ci.DISP_NON_HUMAN_COMPONENT
    if _int(record["homologue"]) != ci.HOMOLOGUE_EXACT:
        return REJECTED, ci.DISP_HOMOLOGUE
    if _int(record["n_components_total"]) != 1 or \
            _int(record["n_components_eligible"]) != 1:
        return REJECTED, ci.DISP_COMPONENT_CARDINALITY

    return ACCEPTED, "human_single_protein_exactly_one_eligible_and_one_total_component"


def canonical_content_sha256(records: list[dict[str, Any]]) -> str:
    """Canonical rows over the predicate inputs + verdict. Order-independent."""
    rows = sorted(
        json.dumps({k: r.get(k) for k in REQUIRED_RECORD_FIELDS},
                   sort_keys=True, separators=(",", ":"))
        for r in records)
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Checks.
# --------------------------------------------------------------------------- #
def check_evidence_is_present(rep: Report,
                              evidence: Optional[dict[str, Any]]) -> bool:
    """No evidence artifact means no admission. An unfalsifiable 'accepted' proves nothing."""
    if evidence is None:
        rep.check(
            f"the cache ships a sanitized {EVIDENCE_FILENAME} (without it, an 'accepted' "
            "mapping is a promise about a computation nobody kept the inputs to — the "
            "producer discards the taxon, component type, homologue and cardinality it "
            "judged on)",
            False, "absent")
        return False

    rep.check(f"the eligibility evidence declares {EVIDENCE_SCHEMA}",
              evidence.get("schema_version") == EVIDENCE_SCHEMA,
              f"got {evidence.get('schema_version')!r}")

    missing = [b for b in REQUIRED_BINDINGS if not evidence.get(b)]
    rep.check(
        "the evidence binds its own identity AND what produced it (store_id, "
        "content_sha256, query_sha256, chembl_release, source_sha256, "
        "extractor_code_sha256)",
        not missing, f"missing: {missing}")
    return True


def check_coverage(rep: Report, *, evidence: dict[str, Any],
                   store_accessions: set[str], store_targets: set[str]) -> None:
    """EVERY mapping — accepted AND rejected — has a record. A dropped rejection is a gap."""
    records = evidence.get("records") or []
    seen_acc = {r.get("accession") for r in records}
    seen_tgt = {r.get("target_chembl_id") for r in records}

    missing_acc = sorted(store_accessions - seen_acc)
    missing_tgt = sorted(store_targets - seen_tgt)

    rep.check(
        "every accession in the store has an eligibility evidence record",
        not missing_acc, f"{len(missing_acc)} uncovered: {missing_acc[:3]}")
    rep.check(
        "every ChEMBL target in the store has an eligibility evidence record",
        not missing_tgt, f"{len(missing_tgt)} uncovered: {missing_tgt[:3]}")

    verdicts = {r.get("verdict") for r in records}
    unknown = verdicts - set(VERDICTS)
    rep.check("every record carries a verdict of exactly 'accepted' or 'rejected'",
              not unknown, f"unknown verdicts: {sorted(unknown)}")

    rep.check(
        "the evidence covers REJECTED mappings too (a producer that drops its rejections "
        "looks identical to one that had none — and 'no rejections' from a store holding "
        "mouse targets, homologues and multi-component entries is a missing gate, not a "
        "clean bill of health)",
        REJECTED in verdicts or not records,
        f"{sum(1 for r in records if r.get('verdict') == REJECTED)} rejected record(s)")


def check_predicate_replay(rep: Report, evidence: dict[str, Any]) -> None:
    """THE check. Re-derive every verdict from the record's own inputs and compare.

    This is what survives a RESEAL: the contradiction is between a record's inputs and its
    own verdict, and rehashing cannot remove it.
    """
    records = evidence.get("records") or []
    mismatches = []
    for r in records:
        derived, reason = replay(r)
        claimed = r.get("verdict")
        if derived != claimed:
            mismatches.append(
                f"{r.get('target_chembl_id')}/{r.get('accession')}: producer says "
                f"{claimed!r}, replay says {derived!r} ({reason})")

    rep.check(
        "every eligibility verdict REPLAYS from its own predicate inputs (a resealed "
        "artifact hashes perfectly and still contradicts itself here — the only way to "
        "hide a mutated taxon is to also flip the verdict to 'rejected', which is the "
        "honest outcome)",
        not mismatches, "; ".join(mismatches[:3]))

    # A rejection must also NAME why, and the name must be a known disposition.
    unnamed = [f"{r.get('target_chembl_id')}" for r in records
               if r.get("verdict") == REJECTED
               and r.get("rejection_reason") not in ci.NON_RANKABLE_DISPOSITIONS]
    rep.check(
        "every rejection names a known disposition (a rejection with no reason cannot be "
        "audited, and cannot be distinguished from a row that was simply lost)",
        not unnamed, f"{len(unnamed)} unnamed: {unnamed[:3]}")


def check_content_hash(rep: Report, evidence: dict[str, Any]) -> None:
    """The bytes that were judged are the bytes that shipped."""
    records = evidence.get("records") or []
    declared = evidence.get("content_sha256")
    recomputed = canonical_content_sha256(records)
    rep.check(
        "the evidence content_sha256 recomputes from its own canonical rows",
        declared == recomputed,
        f"declared {str(declared)[:16]}…, recomputed {recomputed[:16]}…")


def check_store_binding(rep: Report, *, evidence: dict[str, Any],
                        manifest: dict[str, Any]) -> None:
    """The evidence is bound to THIS store and THIS extraction, not to some other run."""
    for field, label in (("store_id", "store"),
                         ("query_sha256", "extraction query"),
                         ("chembl_release", "ChEMBL release"),
                         ("source_sha256", "source archive"),
                         ("extractor_code_sha256", "extractor code")):
        want, got = manifest.get(field), evidence.get(field)
        rep.check(
            f"the eligibility evidence binds the SAME {label} as the store manifest "
            f"({field})",
            want is not None and want == got,
            f"manifest={str(want)[:16]!r} evidence={str(got)[:16]!r}")


def check_evidence_is_sanitized(rep: Report, evidence: dict[str, Any]) -> None:
    """Sanitized means sanitized: no machine-local path anywhere, at any depth."""
    leaks = policy.contains_local_path(evidence)
    rep.check(
        "the eligibility evidence leaks no machine-local path (it is a PUBLIC artifact; a "
        "/home/... path names the producer's machine and cannot be resolved anywhere else)",
        not leaks, str(leaks[:3]))


def verify(rep: Report, *, evidence: Optional[dict[str, Any]],
           manifest: dict[str, Any],
           store_accessions: set[str], store_targets: set[str]) -> None:
    """The full gate. No evidence, no admission."""
    if not check_evidence_is_present(rep, evidence):
        return
    assert evidence is not None
    check_evidence_is_sanitized(rep, evidence)
    check_coverage(rep, evidence=evidence, store_accessions=store_accessions,
                   store_targets=store_targets)
    check_content_hash(rep, evidence)
    check_store_binding(rep, evidence=evidence, manifest=manifest)
    check_predicate_replay(rep, evidence)


# --------------------------------------------------------------------------- #
# ADMISSION MUST HASH THE BYTES ON DISK.
#
# A manifest pin proves nothing about a file nobody opened. The producer's verifier can
# hold a correct hash in the manifest while the 3.5 MB evidence file on disk has been
# altered — the pin and the file are only connected if someone actually reads the file and
# recomputes it. Passing an already-parsed dict into the checker does not do that: it
# verifies whatever was handed over, which may not be what is on disk.
#
# So production admission LOADS the file itself and hashes what it read.
# --------------------------------------------------------------------------- #
def load_and_hash(path: str) -> tuple[dict[str, Any], str]:
    """Read the evidence file FROM DISK and canonically hash what was actually read."""
    with open(path, "r", encoding="utf-8") as fh:
        doc = json.load(fh)
    return doc, canonical_content_sha256(doc.get("records") or [])


def check_on_disk_evidence_matches_the_pin(rep: Report, *, evidence_path: str,
                                           manifest: dict[str, Any],
                                           content_hash_fn: Any) -> Optional[dict[str, Any]]:
    """Open the real file, hash it, and compare to the manifest's pin.

    ``content_hash_fn`` is the producer's canonical hash rule (its own ``content_hash``),
    so the comparison is against the rule the pin was computed under — not a rule Stage 3
    invented, which would fail for the wrong reason.
    """
    import os
    if not os.path.isfile(evidence_path):
        rep.check(
            "the eligibility evidence file exists ON DISK and is loaded for admission (a "
            "manifest pin proves nothing about a file nobody opened)",
            False, f"not found: {evidence_path}")
        return None

    with open(evidence_path, "r", encoding="utf-8") as fh:
        doc = json.load(fh)

    recomputed = content_hash_fn(doc)
    pinned = (manifest.get("extraction") or {}).get("eligibility_evidence_sha256") \
        or manifest.get("eligibility_evidence_sha256")

    rep.check(
        "the eligibility evidence ON DISK re-hashes to the manifest's pin (the producer's "
        "verifier can hold a correct pin while the file beside it has been altered — the "
        "pin and the file are only connected if someone opens the file and recomputes it)",
        recomputed == pinned,
        f"on-disk {str(recomputed)[:16]}… vs pinned {str(pinned)[:16]}…")
    return doc
