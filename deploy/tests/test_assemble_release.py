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
    content = {"release_id": m["release_id"], "lanes": m["lanes"],
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
    assert "negative/unusable verdict" in _refuses(tmp_path, spec)


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


def test_non_empty_staging_refused_and_never_deleted(tmp_path):
    staging = tmp_path / "staging"
    staging.mkdir()
    keep = staging / "pre_existing.txt"
    keep.write_text("do not delete me", encoding="utf-8")
    with pytest.raises(ar.Refusal, match="not empty"):
        ar.assemble(_spec(tmp_path), str(staging), run_utc="2026-07-13T00:00:00Z")
    assert keep.read_text(encoding="utf-8") == "do not delete me"   # never destructive
