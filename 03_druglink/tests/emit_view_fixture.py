"""Regenerate the concrete selection-view example W12 (frontend) and W6 (Stage 4) build against.

    python 03_druglink/tests/emit_view_fixture.py

It writes ``03_druglink/selection_view.fixture.v1.json`` — a REAL view, produced by the REAL
materializer over the sealed non-production store. NOTHING IN IT IS A SCIENTIFIC FINDING: every
program is ``FIXTURE_PROG_*``, every target ``FIXTURE_TGT_*``, every molecule ``FIXTURE_CHEMBL_*``,
and the document declares ``artifact_class: "fixture"``, which the analysis path refuses by name.

It is emitted by the shipped code rather than hand-written, so the example a consumer builds
against cannot drift from the contract the producer emits. ``test_selection_view.py`` re-derives
it and fails if the SHAPE moves.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "analysis")))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..")))
sys.path.insert(0, _HERE)

import native_aggregate_fixture as NAF                                    # noqa: E402
from v2_fixture import load_fixture_store, write_store                    # noqa: E402
import selection_fixture as SF                                            # noqa: E402

from druglink import artifacts_v2 as av2                                  # noqa: E402
from druglink import bundle_v2 as bv2                                     # noqa: E402
from druglink import candidates_v2 as cv2                                 # noqa: E402
from druglink import selection_v3 as s3                                   # noqa: E402
from druglink import selection_view as sv                                 # noqa: E402
from druglink import view_contract as vc                                  # noqa: E402

OUT = os.path.abspath(os.path.join(_HERE, "..", "selection_view.fixture.v1.json"))


def build_view(root: str) -> dict:
    paths = NAF.build(os.path.join(root, "aggregate"))
    aggregate = NAF.admit(paths)
    store = load_fixture_store(write_store(os.path.join(root, "store")))

    tables = cv2.build(artifact_class="fixture", aggregate=aggregate, store=store)
    report = bv2.bind_report(paths["report"], aggregate)
    tables["provenance"] = bv2.provenance_rows(
        aggregate=aggregate, store=store, report=report, method=bv2.method_block(store))
    document = bv2.build_document(
        artifact_class="fixture", aggregate=aggregate, store=store, report=report,
        table_hashes=av2.table_content_hashes(tables), tables=tables)
    # The store is BOUND TO DISK first: the materializer re-derives all eight table hashes from
    # these bytes before it projects a row, and refuses if they are not the ones the document
    # names. A view whose store nobody re-hashed republishes a digest it never checked.
    bundle_dir = av2.write_bundle(
        output_root=os.path.join(root, "bundle"), artifact_class="fixture", document=document,
        doc_id=document["bundle_id"], tables=tables, created_at="2026-07-13T00:00:00Z")

    release = paths["manifest_doc"]["stage1_v3_release"]
    programs = list(aggregate.program_ids)
    conditions = list(release["conditions"])
    # An ORDERED cross-time question, because it is the one that exercises everything: the
    # temporal DiD arms, the ENDPOINT pathway panels (A at from_condition, B at to_condition),
    # and the two typed measured origins staying apart.
    selection = s3.verify(SF.selection(
        a_program=programs[0], a_direction="high",
        b_program=programs[1], b_direction="high",
        analysis_mode=s3.MODE_TEMPORAL, conditions=[conditions[0], conditions[2]],
        registry_view_sha256=release["registry_scorer_view_canonical_sha256"]))

    view = sv.materialize(
        selection=selection, aggregate=aggregate, document=document, tables=tables,
        manifest=paths["manifest_doc"], bundle_dir=bundle_dir,
        admission=sv.admit_receipt(paths["receipt"], aggregate=aggregate,
                                   report_path=paths["report"]))
    vc.validate(view)                    # it leaves only if it satisfies its own contract
    return view


def main() -> None:
    with tempfile.TemporaryDirectory() as root:
        view = build_view(root)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(view, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(f"wrote {OUT}")
    print(f"  view_id      {view['view_id']}")
    print(f"  question     {view['selection']['analysis_mode']} "
          f"{view['selection']['conditions']}")
    print(f"  arms         {view['selected_arms']['gene_arm_keys']}")
    print(f"  candidates   {len(view['tables']['candidates'])}")
    print(f"  edges        {len(view['tables']['target_drug_edges'])}")


if __name__ == "__main__":
    main()
