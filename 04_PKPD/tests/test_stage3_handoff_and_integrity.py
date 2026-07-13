"""The post-build audit's attacks, and the real Stage-3 -> Stage-4 handoff.

Every test here corresponds to something an independent audit actually reproduced against
a previous build.

The Stage-3 documents are REAL Stage-3 emissions — produced by Stage 3's own code, with
its own hasher — and committed under `tests/fixtures/stage3/` (see PROVENANCE.json there).
They are not a Stage-4 imitation of Stage 3's contract, so `analysis/stage3_contract.py`
reconstructing their hashes is a genuine generator-vs-evaluator cross-check.

They are committed rather than generated at test time because the Stage-3 package is not
in this repository yet. The previous version of this module hard-coded one developer's
absolute worktree path and skipped when it was absent, so the release gate ran with ZERO
Stage-3 integration coverage on every other machine. Nothing here skips now.
`test_committed_stage3_bundles_match_a_live_stage3` is the one test that may skip, and it
is a drift check, not the handoff itself.
"""

from __future__ import annotations

import json
import os
import shutil

import pytest
import pyarrow as pa
import pyarrow.parquet as pq

from analysis.integrity import check_referential_integrity
from analysis.firewall import Rejection
from analysis.method_config import STAGE4_DIR, load_method_bundle
from analysis.pipeline import run_pipeline
from analysis.stage3_adapter import ADAPTER_ID, adapt, load_stage3_bundle
from analysis.stage3_annotation import adapt_annotation_bundle
from analysis.stage3_contract import cjson, sha256_hex
from fixtures import stage4_inputs

METHOD = load_method_bundle()

# Real Stage-3 wire emissions, committed. Present in every checkout.
STAGE3_FIXTURE_DIR = os.path.join(STAGE4_DIR, "tests", "fixtures", "stage3")
COMMITTED_BUNDLES = {
    "fixture": os.path.join(STAGE3_FIXTURE_DIR, "fx_c5b44dd8bee36b7d"),
    "research_only": os.path.join(STAGE3_FIXTURE_DIR, "ra_11eaff3028912b24"),
}


PINNED_ANNOTATION_BUNDLE = os.path.normpath(
    os.path.join(STAGE3_FIXTURE_DIR, "..", "stage3_annotation", "s3_0b119088734643bf"))


def stage3_source_root() -> str | None:
    """A live Stage-3 checkout, if one is reachable. Never an absolute developer path."""
    env = os.environ.get("SPOT_STAGE3_ROOT")
    if env and os.path.isdir(os.path.join(env, "analysis", "druglink")):
        return env
    repo_root = os.path.dirname(STAGE4_DIR)
    candidate = os.path.join(repo_root, "03_druglink")
    if os.path.isdir(os.path.join(candidate, "analysis", "druglink")):
        return candidate
    return None


@pytest.fixture(scope="module")
def stage3_bundles():
    """The committed real Stage-3 bundles. This fixture cannot skip."""
    for ns, path in COMMITTED_BUNDLES.items():
        assert os.path.isdir(path), (
            f"the committed Stage-3 {ns} bundle is missing at {path}. The Stage-3 handoff "
            "is a required gate and must never be skipped."
        )
    return dict(COMMITTED_BUNDLES)


def _reseal_manifest(manifest: dict) -> dict:
    manifest["manifest_sha256"] = sha256_hex(cjson(
        {k: v for k, v in manifest.items() if k not in ("manifest_sha256", "created_at")}))
    return manifest


def _rewrite_parquet(path: str, rows: list[dict], schema: pa.Schema | None = None) -> None:
    table = pq.read_table(path)
    pq.write_table(pa.Table.from_pylist(rows, schema=schema or table.schema), path)


def _load(copy) -> tuple[dict, dict]:
    with open(copy / "fixture_bundle.json", encoding="utf-8") as fh:
        doc = json.load(fh)
    with open(copy / "manifest.json", encoding="utf-8") as fh:
        manifest = json.load(fh)
    return doc, manifest


def _save(copy, doc: dict | None = None, manifest: dict | None = None) -> None:
    if doc is not None:
        with open(copy / "fixture_bundle.json", "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2, sort_keys=True)
            fh.write("\n")
    if manifest is not None:
        with open(copy / "manifest.json", "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, indent=2, sort_keys=True)
            fh.write("\n")


def _copy_bundle(stage3_bundles, tmp_path, name="fixture"):
    """Copy under the SAME directory name: the dir name binds the bundle id."""
    src = stage3_bundles[name]
    dst = tmp_path / os.path.basename(src)
    shutil.copytree(src, dst)
    return dst


def _file_sha(path) -> str:
    with open(path, "rb") as fh:
        return sha256_hex(fh.read())


def test_fixture_handoff_admits_candidates_in_the_fixture_namespace(stage3_bundles):
    """A real spot.fixture.stage03_bundle.v1, adapted end to end."""
    doc, bundle = load_stage3_bundle(stage3_bundles["fixture"])
    admission = adapt(doc, bundle)

    cset = admission.candidate_set
    assert cset is not None
    assert cset.namespace.value == "fixture"
    assert cset.is_fixture is True
    assert len(cset.candidates) == admission.inspection.admitted_as_candidates > 0

    # Stage 3's own integrity claims were re-verified, and its identity is carried.
    b = cset.stage3_binding
    assert b.stage3_schema_version == "spot.fixture.stage03_bundle.v1"
    assert b.adapter_id == ADAPTER_ID
    assert b.document_sha256 == doc["document_sha256"]
    assert b.table_hashes  # every shipped parquet was hashed and matched
    assert b.stage3_method["code_tree_sha256"] and b.stage3_method["env_lock_sha256"]

    # Eligibility is NOT upgraded by passing through Stage 4.
    assert b.stage4_eligible is False
    assert b.production_candidate is False

    # Drug form and identifiers survive the crossing.
    forms = {c.active_moiety.administered_form for c in cset.candidates}
    assert "prodrug" in forms  # Stage 3's fixture set contains one
    assert any(c.compound_ids.chembl_id for c in cset.candidates)

    # Every source keeps its class.
    assert {s.source_class for s in admission.source_records.values()} == {"synthetic_fixture"}


def test_research_only_handoff_is_inspected_but_admits_nothing(stage3_bundles):
    """Stage 3: "an ANNOTATION, never a candidate set." Nothing was acquired, either."""
    doc, bundle = load_stage3_bundle(stage3_bundles["research_only"])
    admission = adapt(doc, bundle)

    assert admission.candidate_set is None  # zero Stage-4 candidates
    i = admission.inspection
    assert i.stage3_namespace == "research_only"
    assert i.stage3_eligible is False and i.stage4_eligible is False
    assert i.production_candidate is False
    assert i.admitted_as_candidates == 0
    assert "annotation, not a candidate set" in i.refusal_reason
    # The real state of the world: nothing acquired.
    assert i.source_status["n_acquired_public"] == 0
    assert i.source_status["n_not_acquired"] > 0
    assert {s.source_class for s in admission.source_records.values()} == {"not_acquired"}


def test_a_tampered_stage3_document_is_refused(stage3_bundles, tmp_path):
    """Stage 3's hashes are re-verified by a reimplementation, not imported from it."""
    copy = _copy_bundle(stage3_bundles, tmp_path)
    doc, _ = _load(copy)
    doc["counts"]["n_forms"] = 999  # inside the hashed body
    _save(copy, doc=doc)

    with pytest.raises(Rejection) as exc:
        adapt(*load_stage3_bundle(str(copy)))
    assert exc.value.code == "stage3_document_hash_mismatch"


def test_a_tampered_stage3_parquet_is_refused(stage3_bundles, tmp_path):
    """Raw byte tampering: the file hash alone catches this one."""
    copy = _copy_bundle(stage3_bundles, tmp_path)
    with open(copy / "candidates.parquet", "ab") as fh:
        fh.write(b"\x00")

    with pytest.raises(Rejection) as exc:
        adapt(*load_stage3_bundle(str(copy)))
    assert exc.value.code == "stage3_file_hash_mismatch"


# ------------------------------- the content-hash-trust attack, and its whole family
#
# The audit's attack: mutate a parquet CELL, re-seal the file sha and the manifest self
# hash, and leave the declared CONTENT sha stale. The old adapter compared the document's
# declared hash with the manifest's declared hash — two declarations agreeing with each
# other — and never looked at a row. It admitted a mutated `form_class=prodrug`.


def test_mutated_row_with_resealed_file_and_manifest_is_refused(stage3_bundles, tmp_path):
    """THE preserved attack. Content sha left stale on purpose; rows must be recomputed."""
    copy = _copy_bundle(stage3_bundles, tmp_path)
    doc, manifest = _load(copy)

    target_form = doc["fixture_candidates"][0]["form_ids"][0]
    path = copy / "drug_forms.parquet"
    rows = pq.read_table(path).to_pylist()
    row = next(r for r in rows if r["form_id"] == target_form)
    before = row["form_class"]
    row["form_class"] = "prodrug" if before != "prodrug" else "parent"
    _rewrite_parquet(str(path), rows)

    entry = next(f for f in manifest["files"] if f["file"] == "drug_forms.parquet")
    stale = entry["content_sha256"]
    entry["file_sha256"] = _file_sha(path)          # resealed
    _save(copy, manifest=_reseal_manifest(manifest))  # resealed
    # entry["content_sha256"] deliberately left stale.

    with pytest.raises(Rejection) as exc:
        adapt(*load_stage3_bundle(str(copy)))
    assert exc.value.code == "stage3_table_content_hash_mismatch"
    assert exc.value.context["declared"] == stale
    assert exc.value.context["recomputed_from_rows"] != stale


def test_a_consistently_resealed_declaration_that_still_disagrees_with_rows_is_refused(
        stage3_bundles, tmp_path):
    """Every declaration agrees with every other declaration — and none agrees with the rows.

    This is the attack a declaration-vs-declaration check can never catch, no matter how
    many declarations it cross-checks.
    """
    copy = _copy_bundle(stage3_bundles, tmp_path)
    doc, manifest = _load(copy)

    path = copy / "drug_forms.parquet"
    rows = pq.read_table(path).to_pylist()
    rows[0]["form_class"] = "prodrug" if rows[0]["form_class"] != "prodrug" else "parent"
    _rewrite_parquet(str(path), rows)

    forged = "f" * 64  # a hash of nothing; the rows hash to something else entirely
    doc["table_hashes"]["drug_forms"] = forged
    manifest["table_hashes"]["drug_forms"] = forged
    entry = next(f for f in manifest["files"] if f["file"] == "drug_forms.parquet")
    entry["content_sha256"] = forged
    entry["file_sha256"] = _file_sha(path)

    # Re-seal the document's own two hashes so the declarations are mutually consistent.
    from analysis.stage3_verify import canonical_content
    content = sha256_hex(cjson(canonical_content(doc, "fixture")))
    doc["canonical_content_sha256"] = content
    doc["fixture_bundle_id"] = "fx_" + content[:16]
    doc["document_sha256"] = sha256_hex(cjson(
        {k: v for k, v in doc.items() if k != "document_sha256"}))
    manifest["canonical_content_sha256"] = content
    manifest["document_sha256"] = doc["document_sha256"]
    _save(copy, doc=doc, manifest=_reseal_manifest(manifest))

    doc_entry = next(f for f in manifest["files"] if f["file"] == "fixture_bundle.json")
    doc_entry["content_sha256"] = content
    doc_entry["file_sha256"] = _file_sha(copy / "fixture_bundle.json")
    _save(copy, manifest=_reseal_manifest(manifest))

    with pytest.raises(Rejection) as exc:
        adapt(*load_stage3_bundle(str(copy)))
    # It never gets as far as believing the declarations: the rows do not hash to what
    # every one of them claims. This is the gate a declaration-vs-declaration check lacks.
    assert exc.value.code == "stage3_table_content_hash_mismatch"


def test_a_dropped_row_is_refused(stage3_bundles, tmp_path):
    """Row COUNT is recomputed from the rows, not read off the manifest."""
    copy = _copy_bundle(stage3_bundles, tmp_path)
    _, manifest = _load(copy)
    path = copy / "drug_identifiers.parquet"
    rows = pq.read_table(path).to_pylist()[:-1]          # drop one
    _rewrite_parquet(str(path), rows)

    entry = next(f for f in manifest["files"] if f["file"] == "drug_identifiers.parquet")
    entry["file_sha256"] = _file_sha(path)              # resealed; n_rows left stale
    _save(copy, manifest=_reseal_manifest(manifest))

    with pytest.raises(Rejection) as exc:
        adapt(*load_stage3_bundle(str(copy)))
    assert exc.value.code in ("stage3_table_content_hash_mismatch",
                             "stage3_table_row_count_mismatch")


def test_a_changed_dtype_is_refused(stage3_bundles, tmp_path):
    """`n_ingredients` as a STRING is a different table, whatever it looks like rendered."""
    copy = _copy_bundle(stage3_bundles, tmp_path)
    _, manifest = _load(copy)
    path = copy / "drug_forms.parquet"

    table = pq.read_table(path)
    rows = table.to_pylist()
    for r in rows:
        r["n_ingredients"] = str(r["n_ingredients"])   # int64 -> string
    fields = [pa.field("n_ingredients", pa.string()) if f.name == "n_ingredients" else f
              for f in table.schema]
    _rewrite_parquet(str(path), rows, schema=pa.schema(fields))

    entry = next(f for f in manifest["files"] if f["file"] == "drug_forms.parquet")
    entry["file_sha256"] = _file_sha(path)
    _save(copy, manifest=_reseal_manifest(manifest))

    with pytest.raises(Rejection) as exc:
        adapt(*load_stage3_bundle(str(copy)))
    assert exc.value.code == "stage3_table_dtype_mismatch"


def test_an_unknown_column_is_refused(stage3_bundles, tmp_path):
    copy = _copy_bundle(stage3_bundles, tmp_path)
    _, manifest = _load(copy)
    path = copy / "dispositions.parquet"
    table = pq.read_table(path)
    rows = [dict(r, smuggled="x") for r in table.to_pylist()]
    schema = pa.schema(list(table.schema) + [pa.field("smuggled", pa.string())])
    _rewrite_parquet(str(path), rows, schema=schema)

    entry = next(f for f in manifest["files"] if f["file"] == "dispositions.parquet")
    entry["file_sha256"] = _file_sha(path)
    _save(copy, manifest=_reseal_manifest(manifest))

    with pytest.raises(Rejection) as exc:
        adapt(*load_stage3_bundle(str(copy)))
    assert exc.value.code == "stage3_table_columns_mismatch"


def test_row_order_does_not_change_the_reconstructed_content(stage3_bundles, tmp_path):
    """Stage 3's content hash is row-order-invariant BY CONSTRUCTION (it sorts first).

    So a reordered parquet with a resealed file hash is the SAME table scientifically, and
    is accepted — while the exact byte order stays pinned by file_sha256, which is why the
    un-resealed reorder in the previous test is caught. Row order carries no claim here;
    this test states that boundary rather than pretending to enforce one.
    """
    copy = _copy_bundle(stage3_bundles, tmp_path)
    _, manifest = _load(copy)
    path = copy / "drug_identifiers.parquet"
    rows = list(reversed(pq.read_table(path).to_pylist()))
    _rewrite_parquet(str(path), rows)

    entry = next(f for f in manifest["files"] if f["file"] == "drug_identifiers.parquet")
    entry["file_sha256"] = _file_sha(path)
    _save(copy, manifest=_reseal_manifest(manifest))

    admission = adapt(*load_stage3_bundle(str(copy)))
    assert admission.candidate_set is not None  # same multiset of rows, same content hash


def test_a_reordered_parquet_without_a_resealed_file_hash_is_refused(stage3_bundles, tmp_path):
    copy = _copy_bundle(stage3_bundles, tmp_path)
    path = copy / "drug_identifiers.parquet"
    _rewrite_parquet(str(path), list(reversed(pq.read_table(path).to_pylist())))

    with pytest.raises(Rejection) as exc:
        adapt(*load_stage3_bundle(str(copy)))
    assert exc.value.code == "stage3_file_hash_mismatch"


def test_a_bundle_in_a_directory_that_is_not_its_id_is_refused(stage3_bundles, tmp_path):
    """The directory name IS the canonical content hash. Re-seal everything and it moves."""
    src = stage3_bundles["fixture"]
    copy = tmp_path / "innocent_looking_name"
    shutil.copytree(src, copy)

    with pytest.raises(Rejection) as exc:
        adapt(*load_stage3_bundle(str(copy)))
    assert exc.value.code == "stage3_bundle_directory_mismatch"


def test_an_undeclared_file_in_the_bundle_is_refused(stage3_bundles, tmp_path):
    copy = _copy_bundle(stage3_bundles, tmp_path)
    (copy / "PRODUCTION_POINTER.json").write_text("{}\n", encoding="utf-8")

    with pytest.raises(Rejection) as exc:
        adapt(*load_stage3_bundle(str(copy)))
    assert exc.value.code == "stage3_undeclared_file"


def test_a_path_traversal_manifest_entry_is_refused(stage3_bundles, tmp_path):
    copy = _copy_bundle(stage3_bundles, tmp_path)
    _, manifest = _load(copy)
    manifest["files"].append({"file": "../../etc/passwd", "n_rows": 0,
                              "content_sha256": "0" * 64, "file_sha256": "0" * 64})
    _save(copy, manifest=_reseal_manifest(manifest))

    with pytest.raises(Rejection) as exc:
        adapt(*load_stage3_bundle(str(copy)))
    assert exc.value.code == "stage3_unsafe_file_entry"


def test_a_missing_table_is_refused(stage3_bundles, tmp_path):
    copy = _copy_bundle(stage3_bundles, tmp_path)
    _, manifest = _load(copy)
    manifest["files"] = [f for f in manifest["files"] if f["file"] != "lincs_support.parquet"]
    _save(copy, manifest=_reseal_manifest(manifest))
    os.remove(copy / "lincs_support.parquet")

    with pytest.raises(Rejection) as exc:
        adapt(*load_stage3_bundle(str(copy)))
    assert exc.value.code == "stage3_table_contract_mismatch"


# --------------------------------------------------------------- drift vs a live Stage 3

# ------------------------------------------- the EXPLICIT Stage-3 integration root
# The old test here drove a live Stage-3 build of `spot.stage03_research_annotation.v1` and
# SKIPPED when that failed. Both halves were wrong.
#
#   * The contract is RETIRED. Stage 3 no longer emits that schema and `load()` no longer takes
#     `namespace=`. The TypeError was the retirement, not a transient broken import — waiting
#     for it to "come back" would wait forever on an API that has been removed on purpose.
#   * A SKIP on an explicitly-configured integration root is a cross-lane NO-GO wearing a
#     pass's clothes. If someone points Stage 4 at a Stage-3 bundle and it cannot be consumed,
#     that is a failure. Silence is the one answer that must not be available.
#
# Stage 4 now consumes the PINNED, hash-verified `spot.stage03_drug_annotation.v1` bundle, and
# an explicit root that cannot be consumed FAILS at a named check.

def test_the_explicit_stage3_integration_root_is_consumable():
    """An explicitly configured Stage-3 root MUST be consumable. It may never skip.

    Default (no env var) is the pinned bundle, so this test always runs — there is no
    configuration under which it silently does nothing.
    """
    root = os.environ.get("SPOT_STAGE3_BUNDLE") or PINNED_ANNOTATION_BUNDLE
    assert os.path.isdir(root), (
        f"the configured Stage-3 integration root {root!r} does not exist. An explicit "
        "integration root that cannot be read is a failure, not a skip.")

    admission = adapt_annotation_bundle(root)
    assert admission.schema_version == "spot.stage03_drug_annotation.v1"
    assert admission.artifact_class == "analysis"
    assert admission.admitted_as_candidates > 0, (
        "the Stage-3 bundle queued no candidate for assessment")


def test_a_broken_or_incompatible_stage3_root_fails_loudly(tmp_path):
    """A root Stage 4 cannot consume must FAIL at a named check — never skip, never pass.

    Three ways a root goes bad, and the exact code each must raise.
    """
    # 1. the RETIRED contract, which is what the live worktree emitted until it was removed
    retired = tmp_path / "retired"
    retired.mkdir()
    (retired / "research_annotation.json").write_text(json.dumps({
        "schema_version": "spot.stage03_research_annotation.v1",
        "namespace": "research_only", "bundle_id": "ra_deadbeefdeadbeef"}))
    (retired / "manifest.json").write_text(json.dumps({
        "schema_version": "spot.stage03_manifest.v1", "bundle_id": "ra_deadbeefdeadbeef"}))
    with pytest.raises(Rejection) as exc:
        adapt_annotation_bundle(str(retired))
    assert exc.value.code == "stage3_bundle_incomplete"

    # 2. a document that IS present but declares the retired schema
    wrong = tmp_path / "wrong_schema"
    shutil.copytree(PINNED_ANNOTATION_BUNDLE, wrong)
    doc = json.loads((wrong / "drug_annotation.json").read_text())
    doc["schema_version"] = "spot.stage03_research_annotation.v1"
    (wrong / "drug_annotation.json").write_text(json.dumps(doc))
    with pytest.raises(Rejection) as exc:
        adapt_annotation_bundle(str(wrong))
    assert exc.value.code == "stage3_schema_unsupported"

    # 3. a directory that is not a Stage-3 bundle at all
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(Rejection) as exc:
        adapt_annotation_bundle(str(empty))
    assert exc.value.code == "stage3_bundle_incomplete"

    # 4. and a root that does not exist
    with pytest.raises(Rejection) as exc:
        adapt_annotation_bundle(str(tmp_path / "nope"))
    assert exc.value.code == "stage3_bundle_missing"


def test_no_stage3_integration_path_can_silently_skip():
    """The guard on the guard: nothing in this module skips on a Stage-3 root any more."""
    src = open(os.path.join(STAGE4_DIR, "tests",
                            "test_stage3_handoff_and_integrity.py"), encoding="utf-8").read()
    # built at runtime so this guard cannot match its own source line
    forbidden = "pytest" + ".skip("
    assert forbidden not in src, (
        "a Stage-3 integration test regained a skip. An explicit integration root that cannot "
        "be consumed must FAIL — a skip is a cross-lane NO-GO wearing a pass's clothes.")


def test_an_unknown_stage3_schema_is_refused():
    with pytest.raises(Rejection) as exc:
        adapt({"schema_version": "spot.stage03_something_else.v9"})
    assert exc.value.code == "stage3_schema_unknown"


# --------------------------------------------------- referential integrity attacks

def test_a_measurement_bound_to_the_wrong_context_is_refused():
    """The audit compared an IV 999-g measurement against an oral 150-mg context."""
    inputs = stage4_inputs()
    inputs.exposures[0] = inputs.exposures[0].model_copy(
        update={"route": "intravenous", "dose": "999 g"})
    with pytest.raises(Rejection) as exc:
        check_referential_integrity(inputs)
    assert exc.value.code == "measurement_context_disagreement"


def test_a_row_bound_to_the_wrong_active_moiety_is_refused():
    inputs = stage4_inputs()
    inputs.potencies[0] = inputs.potencies[0].model_copy(
        update={"active_moiety_id": "SOME-OTHER-MOIETY"})
    with pytest.raises(Rejection) as exc:
        check_referential_integrity(inputs)
    assert exc.value.code == "moiety_mismatch"


def test_a_nebpi_observation_naming_a_nonexistent_measurement_is_refused():
    inputs = stage4_inputs()
    idx = next(i for i, o in enumerate(inputs.nebpi_observations)
               if o.criterion_id.value == "pk_in_neb")
    inputs.nebpi_observations[idx] = inputs.nebpi_observations[idx].model_copy(
        update={"measurement_id": "MEASUREMENT-DOES-NOT-EXIST"})
    with pytest.raises(Rejection) as exc:
        check_referential_integrity(inputs)
    assert exc.value.code == "dangling_measurement_ref"


def test_a_nebpi_observation_naming_another_candidates_potency_is_refused():
    inputs = stage4_inputs()
    idx = next(i for i, o in enumerate(inputs.nebpi_observations)
               if o.criterion_id.value == "pk_in_neb")
    inputs.nebpi_observations[idx] = inputs.nebpi_observations[idx].model_copy(
        update={"potency_id": "POT-003"})  # belongs to FIXTURE-003
    with pytest.raises(Rejection) as exc:
        check_referential_integrity(inputs)
    assert exc.value.code == "observation_potency_mismatch"


def test_evidence_citing_an_unacquired_source_is_refused():
    """not_acquired means there are no bytes, so there is no evidence behind the row."""
    inputs = stage4_inputs()
    sid = inputs.properties[0].provenance.source_record_id
    inputs.sources[sid] = inputs.sources[sid].model_copy(update={
        "acquisition_status": "not_acquired", "raw_sha256": None, "raw_bytes": None})
    with pytest.raises(Rejection) as exc:
        check_referential_integrity(inputs)
    assert exc.value.code == "evidence_from_unacquired_source"


def test_a_dangling_search_manifest_is_refused():
    inputs = stage4_inputs()
    inputs.search_manifests = []
    with pytest.raises(Rejection) as exc:
        check_referential_integrity(inputs)
    assert exc.value.code == "dangling_search_manifest"


def test_duplicate_ids_are_refused():
    inputs = stage4_inputs()
    inputs.potencies.append(inputs.potencies[0])
    with pytest.raises(Rejection) as exc:
        check_referential_integrity(inputs)
    assert exc.value.code == "duplicate_id"


# ------------------------------------------------------------- verifier independence

def test_verifier_is_independent_of_the_generator():
    """A verifier that imports the generator can only prove the generator agrees with
    itself. Nothing under verifier/ may import analysis/.

    Parsed with ast, not grepped: `canon.py`'s docstring says "Deliberately NOT
    analysis.canonical", and a text scan would read that as an import.
    """
    import ast

    verifier_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "verifier")
    offenders = []
    for name in sorted(os.listdir(verifier_dir)):
        if not name.endswith(".py"):
            continue
        with open(os.path.join(verifier_dir, name), encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                mods = [node.module or ""]
            else:
                continue
            if any(m == "analysis" or m.startswith("analysis.") for m in mods):
                offenders.append(f"{name}:{node.lineno}")
    assert offenders == [], f"verifier modules importing the generator: {offenders}"


def test_the_verifier_reconstructs_rather_than_rehashes(tmp_path):
    """It must rebuild the NEBPI class, the CNS-MPO components and the margins itself."""
    from analysis.emit import emit
    from verifier.checks import verify_release

    inputs = stage4_inputs()
    out, _ = emit(inputs, run_pipeline(inputs, METHOD), METHOD, str(tmp_path))
    report = verify_release(out, "method")

    assert report["status"] == "pass"
    ids = {c["check_id"].split("::")[0] for c in report["checks"]}
    for family in ("cns_mpo_component", "cns_mpo_total", "margin_value", "nebpi_class",
                   "nebpi_derived_pk", "json_parquet_nebpi", "json_parquet_exposure",
                   "production_eligibility"):
        assert family in ids, f"the verifier never reconstructed {family}"


def test_an_extra_production_looking_artifact_fails_verification(tmp_path):
    """The audit dropped one in and verification still passed."""
    from analysis.emit import emit
    from analysis.verify import verify_output_dir

    inputs = stage4_inputs()
    out, _ = emit(inputs, run_pipeline(inputs, METHOD), METHOD, str(tmp_path))
    with open(os.path.join(out, "selection_FINAL.json"), "w", encoding="utf-8") as fh:
        json.dump({"selected": ["a real drug"]}, fh)

    v = verify_output_dir(out, inputs, METHOD)
    assert v["status"] == "fail"
    assert any(c["check_id"] == "artifact_allowlist_exact" and c["status"] == "fail"
               for c in v["checks"])


def test_verification_without_inputs_is_reported_as_partial(tmp_path):
    """Called without the inputs, the old verifier returned an unqualified pass."""
    from analysis.emit import emit
    from analysis.verify import verify_output_dir

    inputs = stage4_inputs()
    out, _ = emit(inputs, run_pipeline(inputs, METHOD), METHOD, str(tmp_path))

    partial = verify_output_dir(out)
    assert partial["scope"] == "partial_no_inputs"
    assert "NOT a full verification" in partial["scope_note"]

    full = verify_output_dir(out, inputs, METHOD)
    assert full["scope"] == "full_reconstruction_and_identity"


def test_a_release_it_cannot_reconstruct_is_failed_not_crashed(tmp_path):
    """A release from a different Stage-4 is unverifiable, not verified.

    The verifier used to raise KeyError on a release whose tables predate the input
    bundle. A verifier that crashes has not said 'no' — it has said nothing.
    """
    from analysis.emit import emit
    from verifier.checks import verify_release

    inputs = stage4_inputs()
    out, _ = emit(inputs, run_pipeline(inputs, METHOD), METHOD, str(tmp_path))
    # Simulate an older release: drop the canonical input bundle.
    for table in ("contexts", "potency_evidence", "nebpi_observations", "nebpi_decisions"):
        os.remove(os.path.join(out, f"{table}.parquet"))

    report = verify_release(out, "method")
    assert report["status"] == "fail"
    assert report["scope"] == "unverifiable_release_shape"
    assert any(c["check_id"] == "release_reconstructable" and c["status"] == "fail"
               for c in report["checks"])


def test_json_parquet_disagreement_fails_verification(tmp_path):
    """The generator's two faces must say the same thing."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    from analysis.emit import emit
    from analysis.contract_version import ContractVersion
    from analysis.tables import table_schemas
    TABLE_SCHEMAS = table_schemas(ContractVersion.V1)
    from analysis.verify import verify_output_dir

    inputs = stage4_inputs()
    out, _ = emit(inputs, run_pipeline(inputs, METHOD), METHOD, str(tmp_path))

    path = os.path.join(out, "safety_evidence.parquet")
    rows = pq.read_table(path).to_pylist()
    rows[0]["finding_text"] = "quietly edited so the parquet disagrees with the JSON"
    pq.write_table(pa.Table.from_pylist(rows, schema=TABLE_SCHEMAS["safety_evidence"]), path)

    v = verify_output_dir(out, inputs, METHOD)
    assert v["status"] == "fail"
    assert any(c["check_id"].startswith("json_parquet_safety") and c["status"] == "fail"
               for c in v["checks"])
