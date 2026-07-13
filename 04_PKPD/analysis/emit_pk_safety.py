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
import re
from typing import Any, Optional

from .pk_safety_compact import build

WRITER_ID = "spot.stage04.pk_safety_compact_writer.v1"

# Vocabulary Stage 3 RETIRED. `direction_compatible` and `observed_sign_state` allowed an AGONIST to
# be carried as a CRISPRi phenocopy while its action OPPOSED the desired direction. If either
# reappears in a served row, the emit is refused: a retired field that still renders is a retired
# field still being believed.
RETIRED_STAGE3_FIELDS: tuple[str, ...] = ("direction_compatible", "observed_sign_state")


def canonical_json(obj: Any) -> str:
    """STAGE 3'S RULE, adopted verbatim: sorted keys, compact separators, ensure_ascii=True.

    Verified against W16's final files — their declared `content_sha256` reproduces under exactly
    this and NOT under `ensure_ascii=False`, which is what Stage 4 was using. One chain, one
    canonicalization: two rules for one hash means each side verifies its own idea of the bytes.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def content_sha256(doc: dict[str, Any]) -> str:
    """Deterministic: the document's own canonical bytes, minus the hash field."""
    return hashlib.sha256(
        canonical_json({k: v for k, v in doc.items() if k != "content_sha256"}).encode()).hexdigest()


def verify_stage3_content_hash(doc: dict[str, Any], name: str) -> str:
    """RECOMPUTE Stage 3's self-declared content hash. Never merely copy it.

    The hash Stage 4 binds is the SELF-DECLARED `content_sha256` — not the raw file hash, which
    moves whenever the file is reformatted and says nothing about what the document means. A
    declared hash Stage 4 has not recomputed is a hash it is taking on trust, and the whole point of
    binding it is to not do that.
    """
    declared = str(doc.get("content_sha256") or "")
    if not declared:
        raise ValueError(f"{name} declares no content_sha256; there is nothing to bind to.")

    actual = hashlib.sha256(
        canonical_json({k: v for k, v in doc.items() if k != "content_sha256"}).encode()).hexdigest()
    if actual != declared:
        raise ValueError(
            f"{name} declares content_sha256={declared[:16]}… and Stage 4 recomputes {actual[:16]}… "
            "from its bytes. A hash the document asserts about itself proves only that the document "
            "can hash; this one does not describe these bytes.")
    return declared


def assert_servable(doc: dict[str, Any]) -> None:
    """A served document carries NO machine path and NO retired field.

    A public source URL is not a machine path — `https://www.ncbi.nlm.nih.gov/home/about/policies/`
    contains the substring `/home` and is exactly the licence document a reader must be able to
    open. What is forbidden is a path that names THIS filesystem.
    """
    blob = json.dumps(doc, ensure_ascii=False)

    leaked = re.findall(r'"[^"]*(?:/home/|/Users/|/tmp/|/var/folders/)[^"]*"', blob)
    machine_paths = [s for s in leaked if not s.startswith('"http')]
    if machine_paths:
        raise ValueError(
            f"{len(machine_paths)} absolute machine path(s) would be served, e.g. "
            f"{machine_paths[0][:90]}. A served document that discloses where this machine keeps its "
            "files has told the reader nothing about the science and something true about the box.")

    for field in RETIRED_STAGE3_FIELDS:
        if f'"{field}"' in blob:
            raise ValueError(
                f"the served document carries the RETIRED Stage-3 field {field!r}. It let an "
                "AGONIST be labelled a CRISPRi phenocopy while its action opposed the desired "
                "direction; a retired field that still renders is a retired field still believed.")


def _stage3_source(path: Optional[str]) -> tuple[
        Optional[dict[str, Any]], Optional[set[str]], dict[str, list[dict[str, Any]]]]:
    """The upstream drug set + the EXACT hash of the bytes that chose it + each drug's arms."""
    if not path:
        return None, None, {}
    with open(path, "rb") as fh:
        raw = fh.read()
    doc = json.loads(raw)

    # The SELF-DECLARED content hash, RECOMPUTED. This is what Stage 4 binds — not the raw file
    # hash, which moves on a reformat and says nothing about what the document means.
    declared_content = verify_stage3_content_hash(doc, os.path.basename(path))

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
                # THE CURRENT VOCABULARY. `direction_compatible` and the target's
                # `observed_sign_state` are RETIRED: they let an AGONIST be labelled a CRISPRi
                # phenocopy while its action opposed the desired direction. The status now says so
                # directly (`directional_evidence_status: opposed`, with its reason), and Stage 4
                # carries Stage 3's word rather than re-deriving one.
                arms_by_drug.setdefault(cid, []).append({
                    "arm_key": arm.get("arm_key"),
                    "role": arm.get("role"),
                    "program_id": arm.get("program_id"),
                    "desired_change": arm.get("desired_change"),
                    "target_id": target.get("target_id"),
                    "target_symbol": target.get("target_symbol"),
                    "target_id_namespace": target.get("target_id_namespace"),
                    "observed_perturbation_modality": target.get("observed_perturbation_modality"),
                    "arm_rank": target.get("arm_rank"),
                    "pref_name": drug.get("pref_name"),
                    "mechanism_of_action": drug.get("mechanism_of_action"),
                    "action_type_source": drug.get("action_type_source"),
                    "action_type_normalized": drug.get("action_type_normalized"),
                    "directional_evidence_status": drug.get("directional_evidence_status"),
                    "directional_evidence_reason": drug.get("directional_evidence_reason"),
                    "observed_perturbation_support": drug.get("observed_perturbation_support"),
                    "intervention_effect": drug.get("intervention_effect"),
                    "intervention_effect_reason": drug.get("intervention_effect_reason"),
                    "stage3_evidence_class": drug.get("stage3_evidence_class"),
                    "evidence_relation": drug.get("evidence_relation"),
                    # The corrected rule: a phenocopy claim iff the mechanism actually phenocopies
                    # the observed modality. This is the field that stops an AGONIST being carried
                    # as a CRISPRi phenocopy while its action opposes the desired direction.
                    "mechanism_phenocopies_modality": drug.get("mechanism_phenocopies_modality"),
                    "claim_is_equivalence": drug.get("claim_is_equivalence"),
                    "origin_type": drug.get("origin_type"),
                    "max_phase_source": drug.get("max_phase_source"),
                    "source_locator": drug.get("source_locator"),
                    "source_release": drug.get("source_release"),
                })

    source = {
        # ROLE + NAME + HASH, never a machine path. The exact path is in the internal sidecar.
        "artifact_role": "stage3_ui_drugs",
        "artifact_name": os.path.basename(path),
        # The EXACT upstream bytes that chose this drug set. Preserved so the set can be traced back.
        # BOUND: Stage 3's self-declared content hash, recomputed by Stage 4 from its bytes.
        "content_sha256": declared_content,
        "content_sha256_recomputed_by_stage4": True,
        # Carried for completeness; NOT what the binding rests on.
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
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

    # DETERMINISTIC identity, computed over the document itself.
    doc["writer_id"] = WRITER_ID
    doc["content_sha256"] = content_sha256(doc)

    # The served document must leak no machine path and carry no retired field. Refuse, don't warn.
    assert_servable(doc)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True, ensure_ascii=False)

    raw = open(args.out, "rb").read()

    # THE SIDECAR is internal and NOT served: it is where the exact paths live, so the served
    # document can name its inputs by role + hash and still be traceable by someone with the box.
    sidecar = {
        "note": "INTERNAL — not served. Exact filesystem paths for the artifacts the JSON names.",
        "served_document": os.path.abspath(args.out),
        "served_raw_sha256": hashlib.sha256(raw).hexdigest(),
        "served_content_sha256": doc["content_sha256"],
        "writer_id": WRITER_ID,
        "stage3_drugs_path": os.path.abspath(args.stage3_drugs) if args.stage3_drugs else None,
        "stage3_raw_sha256": source["raw_sha256"] if source else None,
        "stage3_content_sha256": source.get("content_sha256") if source else None,
        "prefetch_root": os.path.abspath(args.prefetch),
        "prefetch_receipt": os.path.join(os.path.abspath(args.prefetch), "prefetch_receipt.json"),
    }
    side_path = args.out.replace(".json", ".sidecar.json")
    with open(side_path, "w", encoding="utf-8") as fh:
        json.dump(sidecar, fh, indent=2, sort_keys=True)

    print(f"wrote {args.out}")
    print(f"  raw sha256  : {hashlib.sha256(raw).hexdigest()}")
    print(f"  content hash: {doc['content_sha256']}")
    print(f"  sidecar     : {side_path} (internal, not served)")
    print(f"  rows        : {doc['counts']['n_rows']} acquired, "
          f"{doc['counts']['n_unacquired_reported']} unacquired (reported, not dropped)")
    print(f"  stage3 raw  : {source['raw_sha256'] if source else 'NOT BOUND'}")
    if source:
        print(f"  stage3 content: {source['content_sha256']}  (recomputed by Stage 4)")
        print(f"  question    : {source['question']}")
        print(f"  arms        : {source['arm_keys']}")
        c = doc["counts"]
        print(f"  named by s3 : {c.get('n_named_by_stage3')} | with evidence: {c['n_rows']} | "
              f"no evidence acquired: {c['n_unacquired_reported']} | "
              f"never requested: {c.get('n_named_but_not_prefetched')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
