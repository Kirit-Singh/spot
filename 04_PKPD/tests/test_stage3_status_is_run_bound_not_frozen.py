"""A current STATUS is not a method PARAMETER, and freezing one guarantees it goes stale.

`method/stage4_prose_v1.json` carries a `stage3_contract_status` blob, and `scorecards.json`
copies it verbatim into `upstream.stage3_contract_status`. Method files are immutable and their
bytes are hashed into the identity of every release ever emitted — which is right for a *method
parameter* (Wager's inflection points are true forever for that method version) and exactly wrong
for a *status* (is Stage 3 frozen? which contract revision? how many tests does it have?).

The consequence is on disk today: the v1 prose says `stage3_frozen: false` and pins the **r5**
contract. Stage 3 has since frozen, and Stage 4 was retranscribed onto **r8**. Every v1 release
ever emitted therefore carries a claim that is now false, and cannot be corrected — correcting it
would rewrite the identity of releases that already exist. **And v2 inherited it.**

THE DESIGN (option ii of the two offered):

    A current-status field does not belong in immutable method prose at all. So v2 does not serve
    one. In its place, `upstream.stage3_admission` carries the bundle THIS RUN actually admitted —
    the Stage-3 document's schema version, id, namespace and hashes, taken from `Stage3Binding`.

    Those facts are already inside `scorecard_set_id_inputs` (the id key binds the whole
    `stage3_binding`), so they are anti-tampered and prose-bound for free: change what the release
    says about its upstream and the release id moves. A status blob could never offer that,
    because it described the world rather than the run.

    v1 is untouched — byte-frozen, still emitting the frozen snapshot, still verified against it.
    A historical release is not judged against a rule invented after it was written.
"""

from __future__ import annotations

import json
import os

from analysis.contract_version import ContractVersion
from analysis.emit import emit
from analysis.method_config import load_method_bundle
from analysis.pipeline import run_pipeline
from analysis.run_stage4 import adapt, load_stage3_bundle
from fixtures import stage4_inputs, stage4_inputs_v2
from test_stage3_handoff_and_integrity import COMMITTED_BUNDLES
from verifier.checks import verify_release

METHOD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "method")


def _emit(tmp_path, inputs, version):
    method = load_method_bundle(version=version)
    out, manifest = emit(inputs, run_pipeline(inputs, method), method, str(tmp_path))
    with open(os.path.join(out, "scorecards.json"), encoding="utf-8") as fh:
        return out, json.load(fh), manifest


def _real_binding():
    """The Stage3Binding of a REAL admitted Stage-3 bundle — schema version, id, hashes."""
    return adapt(*load_stage3_bundle(COMMITTED_BUNDLES["fixture"])).candidate_set.stage3_binding


def _v2_inputs_with_a_real_binding():
    """v2 evidence, carrying the binding of a genuinely admitted Stage-3 document.

    The engine's own fixture candidate set has `stage3_binding = None` (it never came through a
    door), so on its own it cannot exercise the block at all.
    """
    i = stage4_inputs_v2()
    i.candidate_set = i.candidate_set.model_copy(update={"stage3_binding": _real_binding()})
    return i


# ------------------------------------------------------------------ why v1 cannot just be fixed

def test_the_frozen_v1_prose_is_provably_stale_and_that_is_the_whole_problem():
    """Not an accusation — a demonstration. This is why the repair is versioning, not editing."""
    with open(os.path.join(METHOD_DIR, "stage4_prose_v1.json"), encoding="utf-8") as fh:
        prose = json.load(fh)

    status = prose["stage3_contract_status"]
    assert status["stage3_frozen"] is False, (
        "if this is no longer False, someone edited a frozen method file and silently moved the "
        "identity of every v1 release ever emitted")
    assert "r5" in json.dumps(status)

    # Stage 3 IS frozen and Stage 4 rides r8. The file cannot say so, and must not be made to:
    # its bytes are hashed into releases that already exist.


def test_a_v1_release_still_serves_the_frozen_snapshot_verbatim(tmp_path):
    """v1 is byte-frozen. It keeps emitting exactly what it always emitted, stale or not — a
    historical artifact records what was believed when it was written."""
    with open(os.path.join(METHOD_DIR, "stage4_prose_v1.json"), encoding="utf-8") as fh:
        prose = json.load(fh)

    _out, sc, _m = _emit(tmp_path, stage4_inputs(), ContractVersion.V1)
    assert sc["upstream"]["stage3_contract_status"] == prose["stage3_contract_status"]
    assert "stage3_admission" not in sc["upstream"], "a v2 field leaked into the frozen v1 shape"


# --------------------------------------------------- v2: run-bound provenance, not frozen status

def test_a_v2_release_does_NOT_serve_the_frozen_status_snapshot(tmp_path):
    _out, sc, _m = _emit(tmp_path, _v2_inputs_with_a_real_binding(), ContractVersion.V2)
    assert "stage3_contract_status" not in sc["upstream"], (
        "v2 still inherits the frozen status blob, so it still ships `stage3_frozen: false` and "
        "an r5 pin that stopped being true")


def test_a_v2_release_binds_the_STAGE3_BUNDLE_IT_ACTUALLY_ADMITTED(tmp_path):
    """The replacement is not another sentence about the world. It is this run's upstream."""
    binding = _real_binding()
    _out, sc, _m = _emit(tmp_path, _v2_inputs_with_a_real_binding(), ContractVersion.V2)

    adm = sc["upstream"]["stage3_admission"]
    assert adm["stage3_document_admitted"] is True
    assert adm["stage3_schema_version"] == binding.stage3_schema_version
    assert adm["stage3_document_id"] == binding.stage3_document_id
    assert adm["stage3_namespace"] == binding.stage3_namespace.value
    assert adm["canonical_content_sha256"] == binding.canonical_content_sha256
    assert adm["document_sha256"] == binding.document_sha256


def test_a_v2_run_on_the_engines_own_fixtures_says_no_document_was_admitted(tmp_path):
    """No Stage-3 document came through a door, and the release says so rather than implying one.
    Absence is stated, never dressed up."""
    _out, sc, _m = _emit(tmp_path, stage4_inputs_v2(), ContractVersion.V2)

    adm = sc["upstream"]["stage3_admission"]
    assert adm["stage3_document_admitted"] is False
    assert "stage3_document_id" not in adm, "a document id with no document is a fiction"


def test_the_v2_admission_block_carries_no_frozen_status_claim(tmp_path):
    """Whatever v2 says about its upstream must be re-derivable from the bundle — never a
    hard-coded fact about Stage 3's condition that drifts the moment Stage 3 moves."""
    _out, sc, _m = _emit(tmp_path, _v2_inputs_with_a_real_binding(), ContractVersion.V2)
    blob = json.dumps(sc["upstream"])

    for gone in ("stage3_frozen", "r5", "production_stage3_producible_today", " tests"):
        assert gone not in blob, f"a frozen status claim ({gone!r}) survived into the v2 release"


def test_the_admission_facts_are_bound_into_the_release_IDENTITY(tmp_path):
    """Why this is stronger than the blob it replaces: tamper with what the release says about
    its upstream and the release id moves, because the id key binds the whole `stage3_binding`.
    A status sentence could never offer that — it described the world, not the run."""
    _out, sc, manifest = _emit(tmp_path, _v2_inputs_with_a_real_binding(), ContractVersion.V2)

    id_key = json.dumps(manifest["scorecard_set_id_inputs"])
    adm = sc["upstream"]["stage3_admission"]
    for field in ("stage3_schema_version", "stage3_document_id",
                  "canonical_content_sha256", "document_sha256"):
        assert adm[field] in id_key, (
            f"{field} is displayed but not bound into scorecard_set_id — it could be rewritten "
            "without moving the id")


def test_a_v2_release_with_run_bound_admission_VERIFIES(tmp_path):
    """The independent verifier admits it — in particular `no_unbound_prose`: every string in the
    admission block is bound, because it comes from the id key rather than from a method file."""
    out, _sc, _m = _emit(tmp_path, _v2_inputs_with_a_real_binding(), ContractVersion.V2)

    report = verify_release(out, METHOD_DIR)
    failed = [(c["check_id"], c["detail"]) for c in report["checks"] if c["status"] == "fail"]
    assert report["status"] == "pass", f"a v2 release with run-bound admission does not verify: {failed}"
