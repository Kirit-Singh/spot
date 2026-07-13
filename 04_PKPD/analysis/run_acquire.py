"""Stage-4 public acquisition CLI.

    python -m analysis.run_acquire --stage3-bundle <dir> --run-root <dir>
    python -m analysis.run_acquire --stage3-bundle <dir> --run-root <dir> \
        --acquire-identity temozolomide --allow-network [--dailymed-setid <setid>]

The default run touches no network at all. It admits the Stage-3 bundle through BOTH gates
(`stage3_admission.admit`), carries Stage 3's own ChEMBL/UniProt source records across verbatim,
states every lane Stage 3 never acquired as `not_evaluated`, and writes two artifacts under the
run root:

    acquisition_manifest.json   every response this run stands on + every stated absence
    acquisition_receipt.json    what was admitted, what was acquired, what was refused

Raw bytes are cached under the run root, addressed by their own SHA-256. The run root may not be
inside a Git working tree — a live label committed by accident is a licensing problem that no
later `git rm` undoes.

What this CLI will not do:

  * acquire a candidate implicitly. Identity acquisition is per-moiety and EXPLICIT
    (`--acquire-identity NAME`), and it needs `--allow-network` on top. There is no bulk sweep.
  * re-query ChEMBL or UniProt. Stage 3 already acquired and hashed those responses; a second
    copy from a different release would be a second, unreconciled provenance for the same number.
  * rank, score, select or recommend anything. This layer acquires evidence. A name that is not
    a candidate in the admitted bundle is recorded as a `reference_probe` and can never be
    reported as a candidate.

Missing evidence stays missing, in writing.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Optional

from .acquire_http import Client
from .acquisition import (
    ACQUISITION_SCHEMA_ID,
    HARD_RULES,
    AcquisitionManifest,
    AcquisitionRecord,
    MissingEvidence,
    RunRoot,
    manifest_content_sha256,
)
from .dailymed_select import acquire_label, acquire_rxcui
from .firewall import Rejection
from .identity import claims_from, resolve_identity
from .openfda_approval import acquire_approval
from .organ_system import LabelRef, extract_organ_system
from .pubchem import acquire_pubchem_identity
from .stage3_admission import admit
from .stage3_reuse import reuse_stage3_sources, stage3_missing_lanes

RECEIPT_FILE = "acquisition_receipt.json"



def _access_date(doc: dict[str, Any]) -> Optional[str]:
    """The date Stage 3 states it acquired its bytes — or None, because it states none.

    This used to fall back to `1970-01-01`. An epoch placeholder is not a missing value: it is a
    FABRICATED provenance claim, it reads as a real access date, and it went into every reused
    record. Stage 3's `source_records` carry no timestamp at all — they pin their bytes by
    `raw_sha256`, `source_release` and `access_record_sha256`, which identify a response far better
    than a wall clock does. So the honest answer is that Stage 4 does not know when Stage 3
    fetched them, and the record says so rather than inventing a day.
    """
    acq = doc.get("acquisition") or {}
    for key in ("acquired_at", "access_date", "acquisition_date"):
        value = acq.get(key)
        if isinstance(value, str) and len(value) >= 10:
            return value[:10]
    return None


def _candidate_names(tables: dict[str, list[dict[str, Any]]]) -> dict[str, str]:
    """preferred name (upper) -> candidate_id, for the rows Stage 3 QUEUED. A lookup, not a rank."""
    queued = {c["active_moiety_id"] for c in tables["candidates"]
              if c.get("stage4_assessment_status") == "queued"}
    return {
        str(m.get("preferred_name") or "").strip().upper(): str(m["active_moiety_id"])
        for m in tables["active_moieties"]
        if m.get("active_moiety_id") in queued and m.get("preferred_name")
    }


def acquire_identity(client: Client, run_root: RunRoot, name: str, *,
                     setid: Optional[str] = None) -> tuple[dict[str, Any], list[AcquisitionRecord]]:
    """Public identity for ONE named moiety, across four sources. Conflicts refuse."""
    records: list[AcquisitionRecord] = []

    pubchem, pubchem_records = acquire_pubchem_identity(client, run_root, name)
    records += pubchem_records
    rxcui, rxnorm_record = acquire_rxcui(client, run_root, name)
    records.append(rxnorm_record)
    label, label_records = acquire_label(client, run_root, name, setid=setid)
    records += label_records
    approval, approval_records = acquire_approval(client, run_root, label.listing.setid)
    records += approval_records

    identity = resolve_identity(
        claims_from(pubchem=pubchem, rxcui=rxcui, label=label, approval=approval),
        active_moiety_name=name)

    # W9's optional v2 organ_system. Source-backed or `unspecified` — never inferred from the
    # target, the mechanism or the drug name. The raw record it was looked for in travels with
    # it, so `unspecified` cannot be confused with `never checked`.
    spl = next(r for r in label_records if (r.raw_media_type or "").endswith("xml"))
    organ_system = extract_organ_system(
        LabelRef(source_record_id=spl.acquisition_record_id, setid=label.listing.setid,
                 label_version=label.label.label_version, raw_response_sha256=spl.raw_sha256),
        source_key="dailymed")

    resolved = {
        "inchikey": identity.inchikey,
        "unii": identity.unii,
        "pubchem_cid": identity.pubchem_cid,
        "rxcui": identity.rxcui,
        "dailymed_setid": identity.dailymed_setid,
        # EVERY application the label declares (TEMODAR: capsule NDA + injection NDA), and every
        # product's marketing status. Nothing here was chosen by position.
        "fda_application_numbers": list(identity.fda_application_numbers),
        "administered_form": identity.administered_form,
        "descriptors_acquired": sorted(pubchem.descriptors),
        # Named, not implied: the two CNS-MPO inputs no public source in the ledger supplies.
        "descriptors_not_available": list(pubchem.not_available),
        "label_version": label.label.label_version,
        "label_effective_date": label.label.effective_date,
        "marketing_statuses": list(approval.marketing_statuses),
        "n_labeled_findings": len(label.label.findings),
        # W9 v2 (optional). Field names are `evidence_records.Provenance`'s, not new ones.
        "organ_system": {
            "organ_system": organ_system.organ_system,
            "value_kind": organ_system.value_kind,
            "evidence_state": organ_system.evidence_state,
            "source_key": organ_system.source_key,
            "source_record_id": organ_system.source_record_id,
            "setid": organ_system.setid,
            "label_version": organ_system.label_version,
            "raw_response_sha256": organ_system.raw_response_sha256,
            "section_code": organ_system.section_code,
            "subsection_code": organ_system.subsection_code,
            "locator": organ_system.locator,
            "extraction_transform": organ_system.extraction_transform,
            "reason": organ_system.reason,
        },
        "source_record_ids": [r.acquisition_record_id for r in records],
    }
    return resolved, records


def run(bundle_dir: str, run_root_dir: str, *, names: list[str], allow_network: bool,
        setid: Optional[str], require_external_verifier: bool,
        client: Optional[Client] = None) -> tuple[int, dict[str, Any]]:
    admission = admit(bundle_dir, require_external_verifier=require_external_verifier)
    run_root = RunRoot(run_root_dir)

    source_rows = admission.tables["source_records"]
    records = reuse_stage3_sources(source_rows, access_date=_access_date(admission.document))
    missing: list[MissingEvidence] = stage3_missing_lanes(source_rows)

    queued_by_name = _candidate_names(admission.tables)
    identities: list[dict[str, Any]] = []

    if names:
        http = client or Client(allow_network=allow_network)
        for name in names:
            resolved, acquired = acquire_identity(http, run_root, name, setid=setid)
            candidate_id = queued_by_name.get(name.strip().upper())

            # BIND the bytes to the candidate they were acquired FOR, on a typed field.
            #
            # These records used to be appended unchanged, so nothing downstream could tell which
            # candidate a PubChem or DailyMed response belonged to. The materializer then fell back
            # to guessing -- matching a Stage-3 SOURCE id, or a substring of the source key -- and a
            # freshly fetched record matched neither. Every response acquired for a real queued
            # candidate was silently treated as unmatched and contributed no property and no safety
            # row, while the receipt cheerfully called the probe `candidate_identity`.
            #
            # A name that is NOT a queued candidate stays candidate_id=None: it is a reference
            # probe (temozolomide, acquired to prove the adapter works), and a probe is never
            # reported as a candidate.
            acquired = [r.model_copy(update={"candidate_id": candidate_id}) for r in acquired]
            records += acquired
            if resolved["organ_system"]["evidence_state"] != "observed":
                missing.append(MissingEvidence(
                    lane="organ_system",
                    evidence_state="not_evaluated",
                    source_key="dailymed",
                    reason=f"{name}: {resolved['organ_system']['reason']}"))
            identities.append({
                "moiety_name": name,
                # A probe is a probe. Nothing here promotes it to a candidate, and no candidate
                # is characterised by having been probed.
                "role": "candidate_identity" if candidate_id else "reference_probe",
                "candidate_id": candidate_id,
                "identity": resolved,
            })
        # `missing` is NOT trimmed here. Acquiring identity for one named moiety — a reference
        # probe above all — fills nothing for the candidates Stage 3 queued. Clearing the lane
        # because *something* was fetched from PubChem is exactly the overclaim this layer
        # exists to prevent: the absence is per candidate, and it is still absent.

    manifest = AcquisitionManifest(
        schema_id=ACQUISITION_SCHEMA_ID,
        run_id=admission.bundle_id,
        stage3_binding={
            "bundle_id": admission.bundle_id,
            "document_sha256": admission.document["document_sha256"],
            "canonical_content_sha256": admission.document["canonical_content_sha256"],
            "stage3_frozen_commit": admission.stage3_frozen_commit,
            "external_verifier": admission.external_verifier,
            "gates": ",".join(admission.gates),
        },
        source_ledger_sha256=_ledger_sha(),
        records=records,
        missing=missing,
    )
    run_root.write_manifest(manifest)

    receipt = {
        "schema_id": "spot.stage04_acquisition_receipt.v1",
        "stage3": {
            "bundle_id": admission.bundle_id,
            "schema_version": admission.document["schema_version"],
            "document_sha256": admission.document["document_sha256"],
            "external_verifier": admission.external_verifier,
            "external_verifier_detail": admission.external_verifier_detail,
            "gates": list(admission.gates),
        },
        "acquisition": {
            "manifest_content_sha256": manifest_content_sha256(manifest),
            "reused_from_stage3": sum(1 for r in records if r.origin == "reused_from_stage3"),
            "fetched_public": sum(1 for r in records if r.origin == "fetched_public"),
            "observed": sum(1 for r in records if r.evidence_state == "observed"),
            # COUNTED, not asserted. This was hard-coded to 0, so a receipt could report seven
            # fetched records for a queued candidate and still say nothing had been acquired for
            # any candidate. A count that cannot change is not a count.
            #
            # A candidate counts only when a record was BOUND to it AND actually observed: a
            # refusal, a 404 or a reference probe is not an acquisition.
            "candidates_acquired": len({
                r.candidate_id for r in records
                if r.candidate_id and r.evidence_state == "observed"
            }),
            "identities_acquired": identities,
        },
        "missing": [m.model_dump(exclude_none=True) for m in manifest.missing],
        "hard_rules": HARD_RULES + [
            "No drug is ranked, scored, selected or recommended by this layer.",
            "A name that is not a queued Stage-3 candidate is a reference_probe, and a probe is "
            "never reported as a candidate.",
        ],
    }
    path = os.path.join(run_root.root, RECEIPT_FILE)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(receipt, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return 0, receipt


def _ledger_sha() -> str:
    from .public_sources import ledger_sha256

    return ledger_sha256()



def _route(annotation: Optional[str], legacy: Optional[str]) -> str:
    """Exactly one door, named for what it opens.

    This CLI consumes Stage 3's DRUG-ANNOTATION bundle (`spot.stage03_drug_annotation.v1`) through
    `stage3_annotation.py`. The flag used to be called `--stage3-bundle`, which is the name of the
    OTHER door — the wire bundle (`stage3_adapter.py`) — so a caller who read the flag and handed
    it a wire bundle got a confusing failure deep inside the annotation reader, and a caller who
    read the README was told to run the wrong command.

    The legacy name is not silently accepted: a wrong bundle admitted under a right-looking flag is
    exactly how evidence gets bound to the wrong upstream.
    """
    if legacy and annotation:
        raise Rejection(
            "stage3_bundle_flag_ambiguous",
            "--stage3-bundle and --stage3-annotation-bundle were both given. They are different "
            "doors; supply exactly one.",
        )
    if legacy:
        raise Rejection(
            "stage3_bundle_flag_retired",
            "--stage3-bundle is retired here. This command reads Stage 3's DRUG-ANNOTATION bundle "
            "(spot.stage03_drug_annotation.v1) via analysis/stage3_annotation.py, not the wire "
            "bundle. Re-run with --stage3-annotation-bundle. The flag was renamed because the old "
            "name pointed at the other door, and a bundle admitted through the wrong door binds "
            "evidence to the wrong upstream.",
        )
    if not annotation:
        raise Rejection("stage3_bundle_missing", "--stage3-annotation-bundle is required")
    return annotation


def main(argv: Optional[list[str]] = None, *, client: Optional[Client] = None) -> int:
    ap = argparse.ArgumentParser(prog="run_acquire", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage3-annotation-bundle", dest="annotation_bundle",
                    help="an ADMITTED Stage-3 drug-annotation bundle "
                         "(spot.stage03_drug_annotation.v1)")
    ap.add_argument("--stage3-bundle", dest="legacy_bundle",
                    help=argparse.SUPPRESS)   # legacy name; routed to a refusal, see below
    ap.add_argument("--run-root", required=True,
                    help="where raw bytes and the manifest are written. Must be OUTSIDE Git.")
    ap.add_argument("--acquire-identity", action="append", default=[], metavar="NAME",
                    help="acquire public identity for ONE named active moiety (repeatable). "
                         "Requires --allow-network. There is no bulk candidate sweep.")
    ap.add_argument("--dailymed-setid",
                    help="pin the DailyMed product when discovery returns more than one")
    ap.add_argument("--allow-network", action="store_true",
                    help="permit requests to the ledgered public hosts. Off by default.")
    ap.add_argument("--require-external-verifier", action="store_true",
                    help="a REAL run: refuse a bundle Stage-3's own verifier.verify_stage3 has "
                         "not actually passed")
    args = ap.parse_args(argv)

    try:
        bundle = _route(args.annotation_bundle, args.legacy_bundle)
        code, receipt = run(
            bundle, args.run_root,
            names=list(args.acquire_identity),
            allow_network=args.allow_network,
            setid=args.dailymed_setid,
            require_external_verifier=args.require_external_verifier,
            client=client,
        )
    except Rejection as exc:
        print(f"REFUSED [{exc.code}] {exc.detail}", file=sys.stderr)
        return 2

    acq = receipt["acquisition"]
    print(f"stage3 bundle    : {receipt['stage3']['bundle_id']} "
          f"(external_verifier={receipt['stage3']['external_verifier']})")
    print(f"run root         : {args.run_root}")
    print(f"manifest         : {acq['manifest_content_sha256']}")
    print(f"reused (Stage 3) : {acq['reused_from_stage3']}  fetched: {acq['fetched_public']}")
    print(f"missing lanes    : {len(receipt['missing'])} stated absence(s)")
    for probe in acq["identities_acquired"]:
        ident = probe["identity"]
        print(f"identity         : {probe['moiety_name']} [{probe['role']}] "
              f"unii={ident['unii']} cid={ident['pubchem_cid']} "
              f"applications={','.join(ident['fda_application_numbers']) or 'none'}")
    print("\nThis layer ACQUIRES evidence. No drug is ranked, scored, selected or recommended, "
          "and nothing here asserts brain penetrance or safety.")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
