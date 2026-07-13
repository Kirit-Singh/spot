"""THE ONE SEALED, SELECTION-INDEPENDENT STORE — built ONCE, and asked every question.

Every question in the selection-view suite is a projection of THIS store. That is not a test
convenience: it is the architectural claim under test. If materializing a view required its own
store, the store would not be reusable, and the second question would be answered over one the
first had already edited.

Nothing here is a scientific finding: every program is ``FIXTURE_PROG_*``, every target
``FIXTURE_TGT_*``, and the artifact class is ``fixture``, which the analysis path refuses by name.

The helpers read the programs and conditions OUT OF THE ADMITTED RELEASE. No test may write a
program or a condition down: a test that only passed for one favoured pair would have proved
nothing about the next one.
"""
from __future__ import annotations

import os

import native_aggregate_fixture as NAF
import pytest
import selection_fixture as SF
from v2_fixture import load_fixture_store, write_store

from druglink import artifacts_v2 as av2
from druglink import bundle_v2 as bv2
from druglink import candidates_v2 as cv2
from druglink import selection_v3 as s3
from druglink import selection_view as sv

WITHIN = s3.MODE_WITHIN
TEMPORAL = s3.MODE_TEMPORAL

_HERE = os.path.dirname(os.path.abspath(__file__))
STAGE3 = os.path.abspath(os.path.join(_HERE, ".."))
# The concrete example W12 builds against today, and the script that regenerates it.
FIXTURE_PATH = os.path.join(STAGE3, "selection_view.fixture.v1.json")
EMIT_SCRIPT = os.path.join(_HERE, "emit_view_fixture.py")


# --------------------------------------------------------------------------- #
# ONE global, selection-INDEPENDENT store, built ONCE. Every question is asked of it.
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def world(tmp_path_factory):
    root = tmp_path_factory.mktemp("selection_view")
    paths = NAF.build(str(root / "aggregate"))
    aggregate = NAF.admit(paths)
    store_dir = write_store(str(root / "store"))
    store = load_fixture_store(store_dir)

    tables = cv2.build(artifact_class="fixture", aggregate=aggregate, store=store)
    tables["provenance"] = bv2.provenance_rows(
        aggregate=aggregate, store=store,
        report=bv2.bind_report(paths["report"], aggregate),
        method=bv2.method_block(store))
    document = bv2.build_document(
        artifact_class="fixture", aggregate=aggregate, store=store,
        report=bv2.bind_report(paths["report"], aggregate),
        table_hashes=av2.table_content_hashes(tables), tables=tables)

    admission = sv.admit_receipt(paths["receipt"], aggregate=aggregate,
                                 report_path=paths["report"])
    return {"paths": paths, "aggregate": aggregate, "tables": tables, "document": document,
            "manifest": paths["manifest_doc"], "admission": admission, "root": str(root)}


def _selection(world, *, a, b, mode, conditions, a_dir="high", b_dir="high", **kw):
    """A verified v3 selection over the ADMITTED release's own programs and conditions."""
    release = world["manifest"]["stage1_v3_release"]
    doc = SF.selection(
        a_program=a, a_direction=a_dir, b_program=b, b_direction=b_dir,
        analysis_mode=mode, conditions=conditions,
        registry_view_sha256=release["registry_scorer_view_canonical_sha256"], **kw)
    return doc


def _verified(world, **kw):
    return s3.verify(_selection(world, **kw))


def _view(world, selection):
    return sv.materialize(selection=selection, aggregate=world["aggregate"],
                          document=world["document"], tables=world["tables"],
                          manifest=world["manifest"], admission=world["admission"])


def _programs(world):
    return list(world["aggregate"].program_ids)


def _conditions(world):
    return list(world["manifest"]["stage1_v3_release"]["conditions"])
