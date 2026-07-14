"""The NATIVE-v2 door: W16's membership receipt + the hash-bound selection view it names.

THIS MODULE EXISTS BECAUSE `build_v2_projection` HAD NO CALLER. Every gate in the membership seam —
the receipt re-hash, the ordered A/B roles, the exactly-one typed column, the join reconciliation —
was reachable only from its own tests. A gate with no production caller is a gate that never runs,
and a suite that is its only consumer proves the code works, not that the pipeline uses it.

It lives beside `run_stage4`, not inside it: that file was already over the 500-line rule, and a door
is a separable thing from the dispatch that chooses between doors. The legacy doors are untouched —
`--stage3-annotation-bundle` remains the current frozen-Stage-3 contract and `--stage3-bundle`
remains the real-emission adapter.
"""

from __future__ import annotations

import json
import os
from typing import Optional

from .firewall import Rejection
from .projection import build_v2_projection
from .stage3_receipt import load_receipt

def run_membership_door(receipt_path: str, bundle_dir: str, outputs_root: str,
                        write_pointer: bool, store_dir: Optional[str] = None) -> int:
    """Run it. -> 0 on the contract path; raises on any refusal (main prints it and exits 2).

    PRODUCTION IS REFUSED FOR A FIXTURE, BY NAME. W16's exported view and receipt are
    `artifact_class: fixture` — the real shape, from the real producer, judged by the real verifier,
    but NOT production. The contract path runs against them (that is what they are for); the
    production path refuses them as `stage3_bundle_is_a_fixture` rather than incidentally, so the
    refusal says what is actually wrong.
    """
    receipt, view = load_receipt(receipt_path, bundle_dir=bundle_dir, store_dir=store_dir)

    artifact_class = str(receipt.get("artifact_class") or "")
    if write_pointer and artifact_class != "analysis":
        raise Rejection(
            "stage3_bundle_is_a_fixture",
            f"the Stage-3 receipt declares artifact_class={artifact_class!r}, and a production "
            "pointer may only be written from an `analysis` bundle. These bytes are the real SHAPE "
            "— real producer, real verifier — but they are not a result, and publishing them would "
            "publish a fixture as a finding.",
            {"artifact_class": artifact_class, "receipt": receipt_path},
        )

    candidates = list((view.get("tables") or {}).get("candidates") or [])
    # No drug has been fetched, so every candidate enters with NO evidence. That is stated, not
    # filled in: a scorecard with no acquired evidence is `not_evaluated`, never a zero.
    scorecards = {"scorecard_set_id": None,
                  "candidates": [{"candidate_id": c.get("candidate_id")} for c in candidates]}

    doc = build_v2_projection(scorecards, candidates, view,
                              stage3_receipt_path=receipt_path, stage3_bundle_dir=bundle_dir,
                              stage3_store_dir=store_dir)

    os.makedirs(outputs_root, exist_ok=True)
    out = os.path.join(outputs_root, "browser_projection.v2.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)

    counts = doc["counts"]
    print(f"stage3 receipt   : {receipt['receipt_sha256'][:12]}… verdict={receipt['verdict']} "
          f"artifact_class={artifact_class}")
    print(f"membership       : {counts['n_displayed']} displayed / "
          f"{counts['n_out_of_view']} out of view "
          f"of {counts['n_stage3_view_candidates']} view candidate(s)")
    print(f"typed placements : {doc['typed_arm_placements_corroborated']} corroborated "
          "(exactly-one, active arms)")
    print(f"projection       : {out}")
    print("NOT A RESULT     : no drug fetched, none ranked; every scorecard field is "
          "not_evaluated until real evidence is acquired.")
    return 0
