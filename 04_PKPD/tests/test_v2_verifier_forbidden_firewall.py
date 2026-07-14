"""The v2 verifier bound the v1 method — so a RESEALED statistic passed the independent verifier.

Blocker 1 fixed the GENERATOR: `run_stage4.main` now selects the method bundle from the contract
the evidence bundle declares, so a v2 run loads `safety_taxonomy_v2.json` and refuses a p-value at
emit time.

The independent re-audit found the mirror image, and it is the worse half:

  * `verifier/reconstruct.py::load_method()` hard-coded five **v1** filenames — including
    `safety_taxonomy_v1.json`. It never loaded `safety_taxonomy_v2.json`, whatever the release
    said it was.
  * `verifier/checks.py` then scanned with `safety_taxonomy.prohibited_outputs.
    forbidden_field_names` — the v1 list, which does not contain `p_value`, `q_value`, `fdr`,
    `adjusted_p`, or the organ/toxicity score names.

So the v2 forbidden names were never loaded by the verifier at all. `_scan_forbidden` is properly
recursive; it was simply handed the wrong list. A v2 release carrying a fully RESEALED `p_value`
— every hash recomputed, the release internally valid — passed every check.

That is the dangerous shape. The generator refusing is a guard; the *verifier* refusing is the
proof, and it is the only thing standing between a tampered release and a reader. These three
attacks reseal the release on disk, so nothing but the forbidden-key firewall can catch them:

    1. `p_value`  — top level of a candidate
    2. `q_value`  — nested one level down
    3. `fdr`      — buried deep

Stage 4 computes no statistic and consumes none, so any of them in an emitted document is a
fabrication. v1 must be untouched: its taxonomy never forbade these names, and a v1 release is
never asked for a rule that did not exist when it was written.
"""

from __future__ import annotations

import json
import os

import pytest

from analysis.canonical import content_sha256, sha256_file
from analysis.contract_version import ContractVersion
from analysis.emit import emit
from analysis.method_config import load_method_bundle
from analysis.pipeline import run_pipeline
from fixtures import stage4_inputs, stage4_inputs_v2
from verifier.checks import verify_release

METHOD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "method")


def _emit(tmp_path, inputs, version):
    method = load_method_bundle(version=version)
    out, _ = emit(inputs, run_pipeline(inputs, method), method, str(tmp_path))
    return out


def _reseal_scorecards(out_dir: str, doc: dict) -> None:
    """Write the tampered document and reseal EVERY hash the manifest declares over it.

    A tamper that leaves a stale hash behind is caught by arithmetic, and catching it proves
    nothing about the firewall. This one is resealed: the release is internally consistent, so
    only a rule that knows `p_value` may not appear can refuse it.
    """
    path = os.path.join(out_dir, "scorecards.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, sort_keys=True)

    manifest_path = os.path.join(out_dir, "manifest.json")
    with open(manifest_path, encoding="utf-8") as fh:
        manifest = json.load(fh)

    for art in manifest["artifacts"]:
        if art["filename"] == "scorecards.json":
            art["content_sha256"] = content_sha256(doc)
            art["file_sha256"] = sha256_file(path)

    manifest.pop("manifest_content_sha256", None)
    manifest["manifest_content_sha256"] = content_sha256(manifest)
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, sort_keys=True)


def _read_scorecards(out_dir: str) -> dict:
    with open(os.path.join(out_dir, "scorecards.json"), encoding="utf-8") as fh:
        return json.load(fh)


# The three attacks, at three depths. Each returns the document, mutated in place.
def _attack_top_level_p_value(doc: dict) -> str:
    doc["candidates"][0]["p_value"] = "0.003"
    return "p_value"


def _attack_nested_q_value(doc: dict) -> str:
    doc["candidates"][0]["lanes"]["q_value"] = "0.01"      # one level down, inside a real container
    return "q_value"


def _attack_deep_fdr(doc: dict) -> str:
    doc["candidates"][0]["evidence"] = {"potency": {"summary": {"statistics": {"fdr": "0.05"}}}}
    return "fdr"


ATTACKS = [
    pytest.param(_attack_top_level_p_value, id="top_level_p_value"),
    pytest.param(_attack_nested_q_value, id="nested_q_value"),
    pytest.param(_attack_deep_fdr, id="deep_fdr"),
]


@pytest.mark.parametrize("attack", ATTACKS)
def test_a_RESEALED_statistic_in_a_v2_release_is_REFUSED_by_the_independent_verifier(
        attack, tmp_path):
    """The exact re-audit finding: these passed 220/220 before the verifier loaded the v2 method."""
    out = _emit(tmp_path, stage4_inputs_v2(), ContractVersion.V2)
    assert verify_release(out, METHOD_DIR)["status"] == "pass", "the clean v2 release must verify"

    doc = _read_scorecards(out)
    name = attack(doc)
    _reseal_scorecards(out, doc)

    report = verify_release(out, METHOD_DIR)
    failed = {c["check_id"]: c["detail"] for c in report["checks"] if c["status"] == "fail"}

    assert report["status"] == "fail", (
        f"a v2 release carrying a RESEALED {name!r} passed the independent verifier. Stage 4 "
        "computes no statistic and consumes none, so this is a fabrication that reached a reader.")

    # BY NAME, by the forbidden-field firewall itself — not incidentally by some other check that
    # happened to notice. `no_composite_clinical_score` is the check that scans the emitted
    # document for every prohibited output name, recursively.
    assert "no_composite_clinical_score" in failed, (
        f"{name!r} was refused, but not by the forbidden-field firewall: {sorted(failed)}. Another "
        "check catching it is luck: a forbidden name that happened to be prose-bound would pass.")
    assert name in failed["no_composite_clinical_score"], (
        f"the firewall fired but does not name {name!r}: {failed['no_composite_clinical_score']}")


def test_the_v2_verifier_loads_the_v2_taxonomy_and_its_extra_forbidden_names():
    """Directly: the names must actually be in the list the verifier scans with."""
    from verifier.reconstruct import load_method

    v1 = load_method(METHOD_DIR, "v1")
    v2 = load_method(METHOD_DIR, "v2")

    assert "safety_taxonomy_v2" in v2, "the v2 verifier never loads safety_taxonomy_v2.json"
    assert "safety_taxonomy_v2" not in v1, "a v2 method file leaked into v1 verification"

    extra = v2["safety_taxonomy_v2"]["prohibited_outputs_v2"]["additional_forbidden_field_names"]
    for name in ("p_value", "q_value", "fdr", "adjusted_p"):
        assert name in extra, f"{name} is not forbidden at v2"


def test_a_v1_release_is_verified_by_exactly_the_v1_taxonomy(tmp_path):
    """v1 is frozen. Its taxonomy never forbade `p_value`, and a v1 release may not be judged
    against a rule invented after it was written — that would make a historical artifact
    'unverifiable', which is not the same answer as 'wrong'."""
    out = _emit(tmp_path, stage4_inputs(), ContractVersion.V1)
    assert verify_release(out, METHOD_DIR)["status"] == "pass"

    from verifier.reconstruct import load_method
    v1 = load_method(METHOD_DIR, "v1")
    v1_forbidden = v1["safety_taxonomy"]["prohibited_outputs"]["forbidden_field_names"]
    assert "p_value" not in v1_forbidden, (
        "`p_value` became forbidden under v1. The v1 method files are hashed into the identity of "
        "every release ever emitted; they may not change.")
