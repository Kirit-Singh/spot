"""Fail-closed behaviour of the public-release assembler.

Every refusal branch must (a) raise Refusal and (b) leave NOTHING staged.
"""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
DEPLOY = os.path.dirname(HERE)
REPO = os.path.dirname(DEPLOY)
sys.path.insert(0, DEPLOY)

import assemble_release as ar  # noqa: E402

LANES = ("stage1", "stage2", "stage3", "stage4")


def _receipt(tmp, lane, verdict="ADMIT", name=None):
    # `name` MUST differ from the default when a test overrides a lane: _spec() regenerates
    # the default files for every lane, which would otherwise clobber the override.
    p = tmp / (name or f"{lane}_receipt.json")
    p.write_text(json.dumps({"lane": lane, "verdict": verdict, "verifier": "independent"}), encoding="utf-8")
    return str(p)


def _artifact(tmp, lane, body=None, name=None):
    p = tmp / (name or f"{lane}_artifact.json")
    p.write_text(body if body is not None else json.dumps({"lane": lane, "value": 1}), encoding="utf-8")
    return str(p)


def _spec(tmp, **overrides):
    lanes = {}
    for lane in LANES:
        lanes[lane] = {
            "status": "ADMIT",
            "receipt": {"src": _receipt(tmp, lane), "dst": f"lanes/{lane}/receipt.json"},
            "artifacts": [{"src": _artifact(tmp, lane), "dst": f"{lane}.json"}],
        }
    for lane, patch in overrides.items():
        if patch is None:
            lanes.pop(lane)
        else:
            lanes[lane].update(patch)
    spec = {"release_id": "spot-public-test", "lanes": lanes}
    p = tmp / "spec.json"
    p.write_text(json.dumps(spec), encoding="utf-8")
    return str(p)


def _staging(tmp):
    return str(tmp / "staging")


# --------------------------------------------------------------------------- happy path
def test_all_lanes_admit_stages_and_emits_content_addressed_manifest(tmp_path):
    staging = _staging(tmp_path)
    m = ar.assemble(_spec(tmp_path), staging, run_utc="2026-07-13T00:00:00Z")

    assert m["uploaded"] is False
    assert set(m["lanes"]) == set(LANES)
    assert all(v["status"] == "ADMIT" for v in m["lanes"].values())
    assert os.path.isfile(os.path.join(staging, "MANIFEST.json"))
    assert os.path.isfile(os.path.join(staging, "DEPLOY_HANDOFF.json"))

    # every lane artifact + receipt and every repo-public file is staged
    for lane in LANES:
        assert os.path.isfile(os.path.join(staging, "lanes", lane, f"{lane}.json"))
        assert os.path.isfile(os.path.join(staging, "lanes", lane, "receipt.json"))
    for rel in ar.REPO_PUBLIC_ALLOWLIST:
        assert os.path.isfile(os.path.join(staging, "public", rel))

    # manifest hashes are MEASURED from the staged bytes, not invented
    for rec in m["files"]:
        assert rec["sha256"] == ar.sha256_file(os.path.join(staging, rec["path"]))

    # content address is reproducible from the manifest's own content
    content = {"release_id": m["release_id"], "lanes": m["lanes"], "routes": m["routes"],
               "files": [{k: r[k] for k in ("path", "sha256", "size", "lane", "role")} for r in m["files"]]}
    assert ar.canonical_sha256(content) == m["manifest_content_sha256"]


def test_manifest_leaks_no_source_machine_paths(tmp_path):
    staging = _staging(tmp_path)
    ar.assemble(_spec(tmp_path), staging, run_utc="2026-07-13T00:00:00Z")
    blob = open(os.path.join(staging, "MANIFEST.json"), encoding="utf-8").read()
    assert str(tmp_path) not in blob          # no absolute source path
    for _, pat in ar.MACHINE_PATTERNS:
        assert not pat.search(blob)


# --------------------------------------------------------------------------- refusals
def _refuses(tmp_path, spec_path, staging=None, **kw):
    staging = staging or _staging(tmp_path)
    with pytest.raises(ar.Refusal) as exc:
        ar.assemble(spec_path, staging, run_utc="2026-07-13T00:00:00Z", **kw)
    # fail-closed: nothing staged
    assert not os.path.exists(staging) or not os.listdir(staging)
    return str(exc.value)


def test_shipped_template_refuses_as_is(tmp_path):
    msg = _refuses(tmp_path, os.path.join(DEPLOY, "release_spec.template.json"))
    assert "status is 'PENDING'" in msg


def test_non_admit_lane_refused(tmp_path):
    msg = _refuses(tmp_path, _spec(tmp_path, stage3={"status": "HOLD"}))
    assert "[stage3] status is 'HOLD'" in msg


def test_missing_lane_refused(tmp_path):
    msg = _refuses(tmp_path, _spec(tmp_path, stage4=None))
    assert "[stage4] lane missing from spec" in msg


def test_missing_artifact_file_refused(tmp_path):
    spec = _spec(tmp_path, stage2={"artifacts": [{"src": str(tmp_path / "nope.json"), "dst": "x.json"}]})
    assert "missing file" in _refuses(tmp_path, spec)


def test_missing_receipt_refused(tmp_path):
    spec = _spec(tmp_path, stage1={"receipt": {"src": str(tmp_path / "gone.json"), "dst": "lanes/stage1/receipt.json"}})
    assert "verifier receipt missing" in _refuses(tmp_path, spec)


def test_sha256_mismatch_refused_and_not_silently_fixed(tmp_path):
    bad = "0" * 64
    spec = _spec(tmp_path, stage1={"artifacts": [{"src": _artifact(tmp_path, "stage1"),
                                                  "dst": "s1.json", "expected_sha256": bad}]})
    msg = _refuses(tmp_path, spec)
    assert "sha256 mismatch" in msg and bad in msg


def test_negative_verdict_receipt_refused(tmp_path):
    neg = _receipt(tmp_path, "stage2", verdict="REFUSE", name="neg_receipt.json")
    spec = _spec(tmp_path, stage2={"receipt": {"src": neg, "dst": "lanes/stage2/receipt.json"}})
    assert "negative verdict" in _refuses(tmp_path, spec)


def test_receipt_without_positive_verdict_refused_but_allowed_when_lenient(tmp_path):
    r = tmp_path / "bare_receipt.json"
    r.write_text(json.dumps({"note": "ran something"}), encoding="utf-8")
    spec = _spec(tmp_path, stage1={"receipt": {"src": str(r), "dst": "lanes/stage1/receipt.json"}})
    assert "no positive verdict" in _refuses(tmp_path, spec)
    # lenient mode still stages (a negative verdict would still refuse)
    ar.assemble(spec, str(tmp_path / "staging_lenient"), run_utc="2026-07-13T00:00:00Z", lenient_receipt=True)


def test_unparseable_receipt_refused(tmp_path):
    r = tmp_path / "broken_receipt.json"
    r.write_text("{not json", encoding="utf-8")
    spec = _spec(tmp_path, stage3={"receipt": {"src": str(r), "dst": "lanes/stage3/receipt.json"}})
    assert "not readable/valid JSON" in _refuses(tmp_path, spec)


def test_secret_in_artifact_refused(tmp_path):
    leaky = _artifact(tmp_path, "stage4", body='{"token": "hf_' + "a" * 40 + '"}', name="leaky_secret.json")
    spec = _spec(tmp_path, stage4={"artifacts": [{"src": leaky, "dst": "s4.json"}]})
    assert "secret pattern" in _refuses(tmp_path, spec)


def test_machine_local_path_in_artifact_refused(tmp_path):
    leaky = _artifact(tmp_path, "stage2", body='{"host_path": "tcedirector:/home/tcelab/x.h5ad"}',
                      name="leaky_machine_path.json")
    spec = _spec(tmp_path, stage2={"artifacts": [{"src": leaky, "dst": "s2.json"}]})
    assert "machine-local path" in _refuses(tmp_path, spec)


def test_official_url_containing_home_is_not_a_false_positive(tmp_path):
    ok = _artifact(tmp_path, "stage3", body='{"url": "https://www.ncbi.nlm.nih.gov/home/about/policies/"}',
                   name="official_url.json")
    spec = _spec(tmp_path, stage3={"artifacts": [{"src": ok, "dst": "s3.json"}]})
    ar.assemble(spec, _staging(tmp_path), run_utc="2026-07-13T00:00:00Z")  # must NOT refuse


def test_denied_extension_refused(tmp_path):
    raw = tmp_path / "source.h5ad"
    raw.write_bytes(b"\x00raw matrix bytes")
    spec = _spec(tmp_path, stage1={"artifacts": [{"src": str(raw), "dst": "source.h5ad"}]})
    assert "denied extension" in _refuses(tmp_path, spec)


def test_staging_inside_repo_refused(tmp_path):
    inside = os.path.join(REPO, "_release_staging_should_never_exist")
    with pytest.raises(ar.Refusal, match="OUTSIDE the repo"):
        ar.assemble(_spec(tmp_path), inside, run_utc="2026-07-13T00:00:00Z")
    assert not os.path.exists(inside)


def test_relative_staging_refused(tmp_path):
    with pytest.raises(ar.Refusal, match="absolute path"):
        ar.assemble(_spec(tmp_path), "relative/staging", run_utc="2026-07-13T00:00:00Z")


# ------------------------------------------- receipt <-> artifact binding (W3 / bc3b10b lesson)
def _stage2_receipt(tmp, artifact_path, name="s2_receipt.json", **patch):
    """A receipt shaped like the real spot.stage02.display_projection independent verifier."""
    doc = {
        "verifier_id": "spot.stage02.display_projection.independent_verifier.v1",
        "generator_is_not_verifier": True,
        "rebuilt_from_admitted_native_bytes": True,
        "subject": {
            "projection_file": os.path.basename(artifact_path),
            "projection_raw_sha256": ar.sha256_file(artifact_path),
            "self_hash_agrees": True,
        },
        "n_arms": 2,
        "n_failed": 0,
        "failures": [],
        "verdict": "admit",
    }
    doc.update(patch)
    p = tmp / name
    p.write_text(json.dumps(doc), encoding="utf-8")
    return str(p)


def _stage2_spec(tmp, artifact, receipt, **patch):
    art = {"src": artifact, "dst": "stage2_display_projection.json", "bound_by_receipt": True}
    art.update(patch.pop("artifact", {}))
    return _spec(tmp, stage2={"receipt": {"src": receipt, "dst": "lanes/stage2/receipt.json"},
                              "artifacts": [art]})


def test_receipt_bound_artifact_admits_when_receipt_names_those_bytes(tmp_path):
    art = _artifact(tmp_path, "stage2", body='{"schema_version":"spot.stage02_display_projection.v2"}',
                    name="stage2_display_projection.json")
    spec = _stage2_spec(tmp_path, art, _stage2_receipt(tmp_path, art))
    m = ar.assemble(spec, _staging(tmp_path), run_utc="2026-07-13T00:00:00Z")
    assert m["lanes"]["stage2"]["status"] == "ADMIT"


def test_altered_artifact_with_original_receipt_is_refused(tmp_path):
    """The exact defect bc3b10b names: alter the projection, keep the original receipt."""
    art = _artifact(tmp_path, "stage2", body='{"arm_value": 1.6758342617}',
                    name="stage2_display_projection.json")
    receipt = _stage2_receipt(tmp_path, art)                      # judges the ORIGINAL bytes
    with open(art, "w", encoding="utf-8") as fh:                  # ...now alter the artifact
        fh.write('{"arm_value": 125.1318342617}')
    msg = _refuses(tmp_path, _stage2_spec(tmp_path, art, receipt))
    assert "receipt does not name these bytes" in msg
    assert "not staged" in msg      # and the bytes it DID judge are absent


def test_receipt_naming_bytes_that_are_not_staged_is_refused(tmp_path):
    art = _artifact(tmp_path, "stage2", body='{"a":1}', name="stage2_display_projection.json")
    other = _artifact(tmp_path, "stage2", body='{"b":2}', name="other.json")
    receipt = _stage2_receipt(tmp_path, other)   # judged a file we are not staging
    msg = _refuses(tmp_path, _stage2_spec(tmp_path, art, receipt))
    assert "the receipt's subject is absent" in msg


@pytest.mark.parametrize("patch,expect", [
    ({"failures": ["a_gate_failed"], "n_failed": 1}, "but claims admit"),
    ({"rebuilt_from_admitted_native_bytes": False}, "rebuilt_from_admitted_native_bytes=false"),
    ({"generator_is_not_verifier": False}, "generator_is_not_verifier=false"),
])
def test_receipt_contradicting_its_own_body_is_refused(tmp_path, patch, expect):
    art = _artifact(tmp_path, "stage2", body='{"a":1}', name="stage2_display_projection.json")
    receipt = _stage2_receipt(tmp_path, art, **patch)   # verdict still says "admit"
    assert expect in _refuses(tmp_path, _stage2_spec(tmp_path, art, receipt))


def test_receipt_with_self_hash_disagreement_is_refused(tmp_path):
    art = _artifact(tmp_path, "stage2", body='{"a":1}', name="stage2_display_projection.json")
    r = json.loads(open(_stage2_receipt(tmp_path, art), encoding="utf-8").read())
    r["subject"]["self_hash_agrees"] = False
    p = tmp_path / "bad_self_hash.json"
    p.write_text(json.dumps(r), encoding="utf-8")
    assert "self_hash_agrees=false" in _refuses(tmp_path, _stage2_spec(tmp_path, art, str(p)))


# --------------------------------------------------------------- dist (Cloudflare) + HF + dry-run
def test_dist_is_staged_and_hashed(tmp_path):
    dist = tmp_path / "dist"
    (dist / "data").mkdir(parents=True)
    (dist / "01_page.html").write_text("<!doctype html>ok", encoding="utf-8")
    (dist / "data" / "x.json").write_text('{"ok":1}', encoding="utf-8")
    spec_path = _spec(tmp_path)
    spec = json.loads(open(spec_path, encoding="utf-8").read())
    spec["dist"] = {"src": str(dist)}
    open(spec_path, "w", encoding="utf-8").write(json.dumps(spec))

    staging = _staging(tmp_path)
    m = ar.assemble(spec_path, staging, run_utc="2026-07-13T00:00:00Z")
    assert m["dist"]["file_count"] == 2
    assert os.path.isfile(os.path.join(staging, "dist", "01_page.html"))
    assert os.path.isfile(os.path.join(staging, "dist", "data", "x.json"))
    handoff = json.loads(open(os.path.join(staging, "DEPLOY_HANDOFF.json"), encoding="utf-8").read())
    assert handoff["cloudflare"]["dist_dir"] == "dist"


def test_missing_dist_dir_refused(tmp_path):
    spec_path = _spec(tmp_path)
    spec = json.loads(open(spec_path, encoding="utf-8").read())
    spec["dist"] = {"src": str(tmp_path / "no_such_dist")}
    open(spec_path, "w", encoding="utf-8").write(json.dumps(spec))
    assert "[dist] not a directory" in _refuses(tmp_path, spec_path)


def test_hf_placeholder_revision_refused_but_null_is_fine(tmp_path):
    man = tmp_path / "hf_manifest.json"
    card = tmp_path / "hf_card.md"
    card.write_text("# card", encoding="utf-8")

    def _write(rel_rev):
        man.write_text(json.dumps({
            "status": "TEMPLATE_ONLY_NOT_UPLOADED",
            "immutable_source": {"hf_revision": "e5fcf98b56a9302921d402e97fc5a190bd88f9a6"},
            "stage1_v3_release": {"stage1_release_hf_revision": rel_rev},
        }), encoding="utf-8")

    def _spec_with_hf():
        sp = _spec(tmp_path)
        d = json.loads(open(sp, encoding="utf-8").read())
        d["hf"] = {"card": str(card), "manifest": str(man)}
        open(sp, "w", encoding="utf-8").write(json.dumps(d))
        return sp

    _write("PENDING")                       # a placeholder is NOT a revision
    assert "must be null" in _refuses(tmp_path, _spec_with_hf())

    _write(None)                            # null == not yet uploaded: fine
    m = ar.assemble(_spec_with_hf(), str(tmp_path / "staging_hf"), run_utc="2026-07-13T00:00:00Z")
    assert m["hf"]["stage1_release_hf_revision"] is None


def test_dry_run_writes_nothing_and_reports_inventory(tmp_path):
    staging = _staging(tmp_path)
    m = ar.assemble(_spec(tmp_path), staging, run_utc="2026-07-13T00:00:00Z", dry_run=True)
    assert m["dry_run"] is True and m["would_stage"] > 0
    assert all(len(f["sha256"]) == 64 for f in m["files"])
    assert not os.path.exists(staging)       # dry run stages nothing


def test_shipped_closeout_spec_refuses_with_pending_lanes(tmp_path):
    msg = _refuses(tmp_path, os.path.join(DEPLOY, "release_spec.closeout.json"))
    for lane in LANES:
        assert f"[{lane}] status is 'PENDING'" in msg


# ------------------------------------------- GO-BP-only critical path; Reactome PARKED
GO_BP_OK = {
    "schema_version": "spot.stage02_pathway_arm_release.v1",
    "source": "go_bp",
    "release_id": "go_bp-2026-05-01",
    # THE authoritative pinned Ensembl-keyed GO-BP bundle
    "geneset_sha256": ar.GO_BP_GENESET_SHA256,
    "sets": [{"set_id": "GO:0006955", "name": "immune response"}],
}


def _pathway(tmp, doc, name="pathway_arm_release.json"):
    p = tmp / name
    p.write_text(json.dumps(doc), encoding="utf-8")
    return str(p)


def _pathway_spec(tmp, doc, collection="go_bp"):
    src = _pathway(tmp, doc)
    return _spec(tmp, stage2={"artifacts": [
        {"src": src, "dst": "pathway_arm_release.json", "pathway_collection": collection}]})


def test_go_bp_pathway_artifact_admits(tmp_path):
    ar.assemble(_pathway_spec(tmp_path, GO_BP_OK), _staging(tmp_path), run_utc="2026-07-13T00:00:00Z")


def test_reactome_collection_is_parked_and_refused(tmp_path):
    doc = dict(GO_BP_OK, source="reactome")
    msg = _refuses(tmp_path, _pathway_spec(tmp_path, doc, collection="reactome"))
    assert "PARKED" in msg


def test_pathway_artifact_naming_reactome_is_refused(tmp_path):
    doc = dict(GO_BP_OK, provenance={"note": "cross-checked against Reactome R-HSA-168256"})
    msg = _refuses(tmp_path, _pathway_spec(tmp_path, doc))
    assert "names 'reactome'" in msg and "PARKED" in msg


def test_undated_go_bp_release_is_refused(tmp_path):
    doc = dict(GO_BP_OK, release_id="go_bp-latest")
    assert "is not dated" in _refuses(tmp_path, _pathway_spec(tmp_path, doc))


def test_pathway_without_geneset_byte_pin_is_refused(tmp_path):
    doc = {k: v for k, v in GO_BP_OK.items() if k != "geneset_sha256"}
    assert "no 64-hex gene-set byte pin" in _refuses(tmp_path, _pathway_spec(tmp_path, doc))


def test_pathway_without_release_id_is_refused(tmp_path):
    doc = {k: v for k, v in GO_BP_OK.items() if k != "release_id"}
    assert "names no gene-set release_id" in _refuses(tmp_path, _pathway_spec(tmp_path, doc))


def test_pathway_binding_the_WRONG_geneset_bundle_is_refused(tmp_path):
    """A well-formed pin is not enough: it must be THE authoritative GO-BP bundle."""
    doc = dict(GO_BP_OK, geneset_sha256="d" * 64)
    msg = _refuses(tmp_path, _pathway_spec(tmp_path, doc))
    assert "does not bind the authoritative GO-BP gene-set bundle" in msg
    assert ar.GO_BP_GENESET_SHA256[:16] in msg


def test_authoritative_geneset_sha_is_the_pinned_one(tmp_path):
    assert ar.GO_BP_GENESET_FILE == "go_bp_ensembl.genesets.json"
    assert ar.GO_BP_GENESET_SHA256 == \
        "4f8b124432e9c1f75f4780b233bd55a29b04150e36d71e04d183d85e5914d2a6"


# --------------------------------- Stage-3/4 shape DISCOVERED from the final receipt, never guessed
def _receipt_with_subject(tmp, artifact, name, subject_file=None):
    doc = {
        "verifier_id": "spot.stage03.independent_verifier.v1",
        "subject": {"artifact_file": subject_file or os.path.basename(artifact),
                    "raw_sha256": ar.sha256_file(artifact)},
        "verdict": "admit",
    }
    p = tmp / name
    p.write_text(json.dumps(doc), encoding="utf-8")
    return str(p)


def test_stage3_shape_is_taken_from_its_receipt(tmp_path):
    art = _artifact(tmp_path, "stage3", body='{"drug":"x"}', name="whatever_producer_named_it.json")
    rc = _receipt_with_subject(tmp_path, art, "s3_receipt.json", subject_file="druglink_release.json")
    spec = _spec(tmp_path, stage3={
        "receipt": {"src": rc, "dst": "lanes/stage3/receipt.json"},
        "artifacts": [{"src": art, "dst": None, "dst_from_receipt": True, "bound_by_receipt": True}]})
    staging = _staging(tmp_path)
    ar.assemble(spec, staging, run_utc="2026-07-13T00:00:00Z")
    # the public name came from the RECEIPT's subject, not from the spec
    assert os.path.isfile(os.path.join(staging, "lanes", "stage3", "druglink_release.json"))


def test_dst_from_receipt_without_a_named_subject_is_refused(tmp_path):
    art = _artifact(tmp_path, "stage3", body='{"a":1}', name="s3.json")
    r = tmp_path / "no_subject_receipt.json"
    r.write_text(json.dumps({"verdict": "admit", "subject": {"raw_sha256": ar.sha256_file(art)}}),
                 encoding="utf-8")
    spec = _spec(tmp_path, stage3={
        "receipt": {"src": str(r), "dst": "lanes/stage3/receipt.json"},
        "artifacts": [{"src": art, "dst": None, "dst_from_receipt": True, "bound_by_receipt": True}]})
    assert "must name exactly ONE subject file" in _refuses(tmp_path, spec)


def test_dst_from_receipt_requires_bound_by_receipt(tmp_path):
    art = _artifact(tmp_path, "stage3", body='{"a":1}', name="s3.json")
    rc = _receipt_with_subject(tmp_path, art, "s3_rc.json")
    spec = _spec(tmp_path, stage3={
        "receipt": {"src": rc, "dst": "lanes/stage3/receipt.json"},
        "artifacts": [{"src": art, "dst": None, "dst_from_receipt": True}]})
    assert "requires bound_by_receipt" in _refuses(tmp_path, spec)


def test_dist_advertising_reactome_is_refused(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "01_page.html").write_text("<p>pathways via Reactome</p>", encoding="utf-8")
    sp = _spec(tmp_path)
    d = json.loads(open(sp, encoding="utf-8").read())
    d["dist"] = {"src": str(dist)}
    open(sp, "w", encoding="utf-8").write(json.dumps(d))
    msg = _refuses(tmp_path, sp)
    assert "advertises the PARKED source" in msg and "GO-BP-only" in msg


# ------------------------------- producer-pending may never admit; consumers bind to admitted bytes
@pytest.mark.parametrize("state", ["pending", "pending_independent_verification"])
def test_producer_pending_state_is_refused_even_when_lenient(tmp_path, state):
    """The producer's own honest pre-admission state is NOT an admission."""
    r = tmp_path / "producer_pending.json"
    r.write_text(json.dumps({"lane": "stage2", "verdict": state}), encoding="utf-8")
    spec = _spec(tmp_path, stage2={"receipt": {"src": str(r), "dst": "lanes/stage2/receipt.json"}})
    assert "negative verdict" in _refuses(tmp_path, spec)
    # even --lenient-receipt must not let it through
    with pytest.raises(ar.Refusal):
        ar.assemble(spec, str(tmp_path / "s_len"), run_utc="2026-07-13T00:00:00Z", lenient_receipt=True)


def test_stage3_consuming_an_admitted_stage2_artifact_is_accepted(tmp_path):
    art = _artifact(tmp_path, "stage2", body='{"a":1}', name="s2_for_consume.json")
    sha = ar.sha256_file(art)
    spec = _spec(tmp_path,
                 stage2={"artifacts": [{"src": art, "dst": "s2.json"}]},
                 stage3={"consumes": [{"lane": "stage2", "artifact_sha256": sha}]})
    ar.assemble(spec, _staging(tmp_path), run_utc="2026-07-13T00:00:00Z")


def test_stage3_consuming_an_unnamed_upstream_artifact_is_refused(tmp_path):
    spec = _spec(tmp_path, stage3={"consumes": [{"lane": "stage2", "artifact_sha256": None}]})
    assert "must be named by the bytes it is" in _refuses(tmp_path, spec)


def test_stage3_consuming_bytes_no_one_admitted_is_refused(tmp_path):
    spec = _spec(tmp_path, stage3={"consumes": [{"lane": "stage2", "artifact_sha256": "c" * 64}]})
    assert "not among that lane's admitted staged artifacts" in _refuses(tmp_path, spec)


# ---------------- release-envelope source topology: GO-BP-only, Reactome never named as a source
def _envelope(tmp, doc, name="current.json"):
    p = tmp / name
    p.write_text(json.dumps(doc), encoding="utf-8")
    return str(p)


def test_envelope_naming_reactome_as_a_released_source_is_refused(tmp_path):
    """The exact defect served at :8347 — pack_ui_projections.mjs hard-codes ['reactome','go_bp']."""
    env = _envelope(tmp_path, {"pathway_sources": ["reactome", "go_bp"],
                               "active_pathway_source": "reactome"})
    spec = _spec(tmp_path, stage2={"artifacts": [{"src": env, "dst": "current.json"}]})
    msg = _refuses(tmp_path, spec)
    assert "lists PARKED source(s) ['reactome']" in msg
    assert "a PARKED source may never be active" in msg


def test_envelope_active_source_null_while_unadmitted_is_accepted(tmp_path):
    env = _envelope(tmp_path, {"pathway_sources": ["go_bp"], "active_pathway_source": None})
    spec = _spec(tmp_path, stage2={"artifacts": [{"src": env, "dst": "current.json"}]})
    ar.assemble(spec, _staging(tmp_path), run_utc="2026-07-13T00:00:00Z")   # must NOT refuse


def test_envelope_claiming_active_go_bp_without_an_admitted_pathway_is_refused(tmp_path):
    """The active source must be DERIVED from the admitted topology, not asserted."""
    env = _envelope(tmp_path, {"pathway_sources": ["go_bp"], "active_pathway_source": "go_bp"})
    spec = _spec(tmp_path, stage2={"artifacts": [{"src": env, "dst": "current.json"}]})
    msg = _refuses(tmp_path, spec)
    assert "no admitted GO-BP pathway artifact is staged" in msg


def test_envelope_awaiting_admission_marker_is_accepted(tmp_path):
    env = _envelope(tmp_path, {"pathway_sources": ["go_bp"],
                               "active_pathway_source": "go_bp:awaiting_admission"})
    spec = _spec(tmp_path, stage2={"artifacts": [{"src": env, "dst": "current.json"}]})
    ar.assemble(spec, _staging(tmp_path), run_utc="2026-07-13T00:00:00Z")


def test_dist_current_json_naming_reactome_is_refused(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "current.json").write_text(
        json.dumps({"pathway_sources": ["reactome", "go_bp"], "active_pathway_source": "reactome"}),
        encoding="utf-8")
    sp = _spec(tmp_path)
    d = json.loads(open(sp, encoding="utf-8").read())
    d["dist"] = {"src": str(dist)}
    open(sp, "w", encoding="utf-8").write(json.dumps(d))
    assert "PARKED" in _refuses(tmp_path, sp)


# ------------- unadmitted producer outputs are EXCLUDED; fixtures may never be labelled production
def test_unadmitted_producer_output_is_excluded_not_merely_pending(tmp_path):
    src = tmp_path / "output" / "pathway-117ccc4-stream1w8-unadmitted" / "47a0d01fd23f705e" / "pathway_arm_release.json"
    src.parent.mkdir(parents=True)
    src.write_text(json.dumps(GO_BP_OK), encoding="utf-8")
    spec = _spec(tmp_path, stage2={"artifacts": [{"src": str(src), "dst": "pathway_arm_release.json"}]})
    msg = _refuses(tmp_path, spec)
    assert "UNADMITTED producer run" in msg and "not merely labelled pending" in msg


def test_fixture_path_may_not_enter_the_release(tmp_path):
    src = tmp_path / "tests" / "fixtures" / "canonical_two_arm_run.json"
    src.parent.mkdir(parents=True)
    src.write_text('{"a":1}', encoding="utf-8")
    spec = _spec(tmp_path, stage2={"artifacts": [{"src": str(src), "dst": "arm.json"}]})
    assert "fixture/demo path" in _refuses(tmp_path, spec)


@pytest.mark.parametrize("doc,expect", [
    ({"is_fixture": True}, "may never be released as production"),
    ({"namespace": "fixture"}, "may not be labelled production"),
    ({"source": "fixture", "schema_version": "x"}, "gene-set source is 'fixture'"),
])
def test_fixture_or_demo_may_not_be_labelled_production(tmp_path, doc, expect):
    src = _artifact(tmp_path, "stage2", body=json.dumps(doc), name="claims_production.json")
    spec = _spec(tmp_path, stage2={"artifacts": [{"src": src, "dst": "a.json"}]})
    assert expect in _refuses(tmp_path, spec)


# ------------------------------------------------- excluded / internal-path scan
@pytest.mark.parametrize("relpath", [
    "cache/blob.json",
    ".cache/blob.json",
    "prefetch/blob.json",
    "drug_cache/blob.json",
    "logs/run.json",
    "run.log",
    "__pycache__/x.json",
    "pipeline/datasets/blob.json",
])
def test_prefetch_cache_and_private_logs_are_excluded(tmp_path, relpath):
    src = tmp_path / "internal" / relpath
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text('{"internal":1}', encoding="utf-8")
    spec = _spec(tmp_path, stage3={"artifacts": [{"src": str(src), "dst": "s3.json"}]})
    assert "excluded" in _refuses(tmp_path, spec)


def test_internal_dst_path_is_excluded_even_from_a_clean_source(tmp_path):
    """A clean source may not be published UNDER an internal-looking release path."""
    src = _artifact(tmp_path, "stage3", body='{"ok":1}', name="clean.json")
    spec = _spec(tmp_path, stage3={"artifacts": [{"src": src, "dst": "cache/clean.json"}]})
    assert "excluded cache_or_prefetch on the release path" in _refuses(tmp_path, spec)


def test_build_staging_source_is_NOT_excluded(tmp_path):
    """The Stage-1 scores parquet legitimately lives under a build-staging dir; excluding
    staging/temp by name would refuse a real result."""
    src = tmp_path / "_t8_staging" / "stage01_scores_full.json"
    src.parent.mkdir(parents=True)
    src.write_text('{"scores":1}', encoding="utf-8")
    spec = _spec(tmp_path, stage1={"artifacts": [{"src": str(src), "dst": "stage01_scores_full.json"}]})
    ar.assemble(spec, _staging(tmp_path), run_utc="2026-07-13T00:00:00Z")   # must NOT refuse


def test_artifact_provenance_ships_and_declares_no_invented_values(tmp_path):
    prov = json.loads(open(os.path.join(REPO, "schemas/artifact_provenance.json"), encoding="utf-8").read())
    assert "schemas/artifact_provenance.json" in ar.REPO_PUBLIC_ALLOWLIST
    for a in prov["artifacts"]:
        assert a["sha256"] is None and a["rerun_utc"] is None and a["admitted"] is False, \
            f"{a['id']}: no artifact may carry a hash/timestamp/admission before a real run"
    lanes = {a["lane"] for a in prov["artifacts"]}
    assert {"stage1", "stage2"} <= lanes
    kinds = {a["id"] for a in prov["artifacts"]}
    for required in ("stage1_scores_full", "stage1_display_overlay", "stage2_arm_direct",
                     "stage2_arm_temporal", "stage2_arm_pathway_go_bp_rest"):
        assert required in kinds

    # the pathway lane is GO-BP only; the gene-set bundle is PINNED and present...
    pw = next(a for a in prov["artifacts"] if a["id"] == "stage2_arm_pathway_go_bp_rest")
    assert pw["geneset_collection"] == "go_bp"
    assert pw["geneset_bundle"]["sha256"] == ar.GO_BP_GENESET_SHA256
    assert pw["geneset_bundle"]["status"] == "PINNED_AND_PRESENT"
    # ...but the producer bundles are UNADMITTED, so the artifact still carries no hash/admission
    assert pw["sha256"] is None and pw["admitted"] is False
    states = {b["state"] for b in pw["producer_bundles"]}
    assert states == {"COMPLETE_UNADMITTED", "RUNNING_UNADMITTED"}
    # no machine-local host path leaked into the tracked provenance
    assert "/home/" not in json.dumps(pw)

    # Reactome is parked, and recorded as parked rather than deleted
    parked = {p["id"]: p for p in prov["parked_sources"]}
    assert parked["reactome"]["status"] == "PARKED"
    assert "reactome" not in {a.get("geneset_collection") for a in prov["artifacts"]}


def test_non_empty_staging_refused_and_never_deleted(tmp_path):
    staging = tmp_path / "staging"
    staging.mkdir()
    keep = staging / "pre_existing.txt"
    keep.write_text("do not delete me", encoding="utf-8")
    with pytest.raises(ar.Refusal, match="not empty"):
        ar.assemble(_spec(tmp_path), str(staging), run_utc="2026-07-13T00:00:00Z")
    assert keep.read_text(encoding="utf-8") == "do not delete me"   # never destructive
