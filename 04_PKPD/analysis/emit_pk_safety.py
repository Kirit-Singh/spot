"""Emit the compact PK/safety rows the UI consumes, from cached public bytes only.

    python -m analysis.emit_pk_safety --prefetch <dir> --out <file.json> \
        [--stage3-drugs <stage3 rest/stim8 drug json> --selection rest|stim8]

With `--stage3-drugs` the rows are the SELECTION's candidates and the Stage-3 file's own SHA-256 is
carried into the output, so the drug set can be traced back to the exact upstream bytes that chose
it. Without it, the output is the selection-INDEPENDENT public-evidence store over every acquired
moiety, and it says so — it is not a Rest or a Stim8 result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from typing import Any, Optional

from .pk_safety_compact import build


def _stage3_source(path: Optional[str]) -> tuple[
        Optional[dict[str, Any]], Optional[set[str]], dict[str, list[dict[str, Any]]]]:
    """The upstream drug set + the EXACT hash of the bytes that chose it + each drug's arms."""
    if not path:
        return None, None, {}
    with open(path, "rb") as fh:
        raw = fh.read()
    doc = json.loads(raw)

    # `spot.stage03_ui_drugs.v1`: arms -> targets -> drugs. The drug's identity is its ChEMBL
    # molecule id, and the ARM it sits on is carried with it — a drug reached through the
    # `treg_like|decrease` arm and one reached through `th1_like|increase` are on different sides of
    # the question, and flattening them into one list would lose exactly that.
    ids: set[str] = set()
    arms_by_drug: dict[str, list[dict[str, Any]]] = {}
    for arm in doc.get("arms") or []:
        for target in arm.get("targets") or []:
            for drug in target.get("drugs") or []:
                cid = str(drug.get("molecule_chembl_id") or "")
                if not cid:
                    continue
                ids.add(cid)
                arms_by_drug.setdefault(cid, []).append({
                    "arm_key": arm.get("arm_key"),
                    "role": arm.get("role"),
                    "program_id": arm.get("program_id"),
                    "desired_change": arm.get("desired_change"),
                    "target_id": target.get("target_id"),
                    "target_id_namespace": target.get("target_id_namespace"),
                    "observed_sign_state": target.get("observed_sign_state"),
                    "arm_rank": target.get("arm_rank"),
                    "mechanism_of_action": drug.get("mechanism_of_action"),
                    "action_type_source": drug.get("action_type_source"),
                    "direction_compatible": drug.get("direction_compatible"),
                    "evidence_relation": drug.get("evidence_relation"),
                    "claim_is_equivalence": drug.get("claim_is_equivalence"),
                    "max_phase_source": drug.get("max_phase_source"),
                    "pref_name": drug.get("pref_name"),
                    "source_locator": drug.get("source_locator"),
                    "source_release": drug.get("source_release"),
                })

    source = {
        "path": os.path.abspath(path),
        # The EXACT upstream bytes that chose this drug set. Preserved so the set can be traced back.
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "content_sha256": doc.get("content_sha256"),
        "schema_version": doc.get("schema_version"),
        "question": doc.get("question"),
        "condition": doc.get("condition"),
        "analysis_mode": doc.get("analysis_mode"),
        "direction_rule": doc.get("direction_rule"),
        "arm_keys": [a.get("arm_key") for a in (doc.get("arms") or [])],
        "n_candidates_named": len(ids),
    }
    return source, ids, arms_by_drug


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="emit_pk_safety", description=__doc__)
    ap.add_argument("--prefetch", required=True, help="the prefetch run root (holds the receipt)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--stage3-drugs", help="the Stage-3 compact drug JSON for this selection")
    ap.add_argument("--selection", help="rest | stim8 — a label, carried into the output")
    args = ap.parse_args(argv)

    source, ids, arms_by_drug = _stage3_source(args.stage3_drugs)
    doc = build(args.prefetch, stage3_source=source, only=ids)
    doc["selection"] = args.selection

    # Carry each drug's Stage-3 arm context onto its row, and REPORT the named candidates that have
    # no cached public evidence — they are part of the selection and their absence is a finding, not
    # a gap to be quietly closed by omitting them.
    for row in doc["candidates"]:
        row["stage3_arms"] = arms_by_drug.get(str(row["candidate_id"]), [])
    for row in doc["unacquired"]:
        row["stage3_arms"] = arms_by_drug.get(str(row["candidate_id"]), [])

    if ids:
        emitted = {str(r["candidate_id"]) for r in doc["candidates"] + doc["unacquired"]}
        missing = sorted(ids - emitted)
        doc["named_by_stage3_but_absent_from_the_prefetch"] = {
            "candidate_ids": missing,
            "n": len(missing),
            "state": "not_evaluated",
            "reason": ("these candidates are named by the Stage-3 selection and no public evidence "
                       "was ever requested for them in this prefetch run. Nothing is known about "
                       "them here — which is not the same as nothing being true of them."),
        }
        doc["counts"]["n_named_by_stage3"] = len(ids)
        doc["counts"]["n_named_but_not_prefetched"] = len(missing)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True, ensure_ascii=False)

    raw = open(args.out, "rb").read()
    print(f"wrote {args.out}")
    print(f"  sha256      : {hashlib.sha256(raw).hexdigest()}")
    print(f"  rows        : {doc['counts']['n_rows']} acquired, "
          f"{doc['counts']['n_unacquired_reported']} unacquired (reported, not dropped)")
    print(f"  stage3 bound: {source['raw_sha256'] if source else 'NOT BOUND'}")
    if source:
        print(f"  question    : {source['question']}")
        print(f"  arms        : {source['arm_keys']}")
        c = doc["counts"]
        print(f"  named by s3 : {c.get('n_named_by_stage3')} | with evidence: {c['n_rows']} | "
              f"no evidence acquired: {c['n_unacquired_reported']} | "
              f"never requested: {c.get('n_named_but_not_prefetched')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
