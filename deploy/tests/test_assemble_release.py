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


def test_non_empty_staging_refused_and_never_deleted(tmp_path):
    staging = tmp_path / "staging"
    staging.mkdir()
    keep = staging / "pre_existing.txt"
    keep.write_text("do not delete me", encoding="utf-8")
    with pytest.raises(ar.Refusal, match="not empty"):
        ar.assemble(_spec(tmp_path), str(staging), run_utc="2026-07-13T00:00:00Z")
    assert keep.read_text(encoding="utf-8") == "do not delete me"   # never destructive
