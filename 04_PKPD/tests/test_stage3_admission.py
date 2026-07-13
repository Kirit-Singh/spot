"""Admission of a FROZEN Stage-3 bundle: the pin, and the two-gate door.

Stage 3 froze its contract (r7, `cb99125…`). This suite covers Stage 4's rebase onto it:

  * the FROZEN pin — the handoff/contract/schema-set hashes, re-hashed on receipt;
  * the admission DOOR — `admit()` = Stage-4's own restatement (gate 1) AND Stage-3's own
    `verifier.verify_stage3` (gate 2, out-of-process). Neither gate alone admits a bundle.

The combined-objective firewall that gate 1 enforces has its own suite,
`test_stage3_combined_objective`. Forge helpers: `_stage3_forge`.
"""

from __future__ import annotations

import hashlib
import os

import pytest

from _stage3_forge import copy_bundle, edit_doc
from analysis.firewall import Rejection
from analysis.stage3_admission import (
    ENV_CACHE_ROOT,
    ENV_DIRECT_INPUTS,
    ENV_DIRECT_RUN,
    ENV_VERIFIER_ROOT,
    NOT_RUN,
    PASSED,
    admit,
)
from analysis.stage3_frozen import (
    BANNED_KEYS,
    STAGE3_CONTRACT_SHA256,
    STAGE3_HANDOFF_SHA256,
    STAGE3_SCHEMA_SET_SHA256,
    STAGE3_SCHEMA_SHA256,
)

VERIFIER_ENV = (ENV_VERIFIER_ROOT, ENV_CACHE_ROOT, ENV_DIRECT_RUN, ENV_DIRECT_INPUTS)


@pytest.fixture(autouse=True)
def _no_ambient_verifier_context(monkeypatch):
    """A developer's exported Stage-3 context must not silently change what these test."""
    for name in VERIFIER_ENV:
        monkeypatch.delenv(name, raising=False)


# ------------------------------------------------------------------------- the frozen pin


def test_the_pinned_schema_set_digest_reproduces_from_the_pinned_file_hashes():
    """Internal consistency of the pin — runs on every machine, checkout or not.

    Stage 3's digest is sorted-name + NUL + per-file-hash + NL. Recomputing it from the
    per-file hashes Stage 4 transcribed proves the transcription is self-consistent: a
    mistyped file hash cannot reproduce the set digest.
    """
    h = hashlib.sha256()
    for name in sorted(STAGE3_SCHEMA_SHA256):
        h.update(name.encode())
        h.update(b"\0")
        h.update(STAGE3_SCHEMA_SHA256[name].encode())
        h.update(b"\n")
    assert h.hexdigest() == STAGE3_SCHEMA_SET_SHA256
    assert STAGE3_SCHEMA_SHA256["spot.stage03_drug_annotation.v1.json"] == STAGE3_CONTRACT_SHA256


def _frozen_stage3_root() -> str | None:
    """A Stage-3 checkout carrying the FROZEN artifacts (schemas/ + verifier/).

    The frozen work lives on `agent/stage3-druglink`; this worktree's own `03_druglink` is
    pre-freeze and carries neither. So the root comes from the environment or not at all —
    never an absolute developer path baked into a test.
    """
    root = os.environ.get("SPOT_STAGE3_ROOT")
    if not root:
        return None
    if not (os.path.isdir(os.path.join(root, "schemas"))
            and os.path.isdir(os.path.join(root, "verifier"))):
        pytest.fail(
            f"SPOT_STAGE3_ROOT={root!r} is set but carries no schemas/ + verifier/. An "
            "explicitly configured Stage-3 root that cannot be read is a FAILURE, not a skip.")
    return root


needs_frozen_stage3 = pytest.mark.skipif(
    not os.environ.get("SPOT_STAGE3_ROOT"),
    reason="no SPOT_STAGE3_ROOT configured; the pin is still checked for internal "
           "consistency by test_the_pinned_schema_set_digest_reproduces_from_the_pinned_file_hashes")


@needs_frozen_stage3
def test_the_live_frozen_stage3_matches_the_pin():
    """Re-hash the frozen Stage-3 on receipt. A drift in ANY schema goes red here."""
    root = _frozen_stage3_root()
    schema_dir = os.path.join(root, "schemas")
    on_disk = {n for n in os.listdir(schema_dir) if n.endswith(".json")}
    assert on_disk == set(STAGE3_SCHEMA_SHA256), (
        "the frozen Stage-3 schema SET changed (added/renamed/deleted): "
        f"{sorted(on_disk ^ set(STAGE3_SCHEMA_SHA256))}")

    for name, pinned in sorted(STAGE3_SCHEMA_SHA256.items()):
        with open(os.path.join(schema_dir, name), "rb") as fh:
            got = hashlib.sha256(fh.read()).hexdigest()
        assert got == pinned, (
            f"{name} changed: {got} != pinned {pinned}. The Stage-3 contract is FROZEN and "
            "Stage 4 binds to these bytes — do not re-pin without a new handoff.")


@needs_frozen_stage3
def test_the_stage4_denylist_covers_the_frozen_stage3_denylist():
    """Stage 4 RESTATES the denylist rather than importing it, so it must not drift behind.

    If Stage 3 bans a new combined objective and Stage 4 has not, this goes red — which is
    the only thing that keeps a restatement honest.
    """
    import sys
    root = _frozen_stage3_root()
    sys.path.insert(0, root)
    try:
        for mod in [m for m in sys.modules if m == "verifier" or m.startswith("verifier.")]:
            del sys.modules[mod]
        from verifier import policy
        stage3_banned = set(policy.BANNED_KEYS)
    finally:
        sys.path.remove(root)
        for mod in [m for m in sys.modules if m == "verifier" or m.startswith("verifier.")]:
            del sys.modules[mod]

    missing = sorted(stage3_banned - BANNED_KEYS)
    assert not missing, (
        f"the frozen Stage-3 verifier bans {missing}, and Stage 4's restated denylist does "
        "not. Add them to analysis/stage3_frozen.BANNED_KEYS.")


# ------------------------------------------------------------------- the admission door


def test_admission_records_that_the_external_verifier_did_not_run(tmp_path):
    """No Stage-3 build context exists yet, and the record says exactly that — in the object,
    not in a comment. `data_bound_integration_ready` is the flag a GO claim must consult."""
    got = admit(copy_bundle(str(tmp_path)))
    assert got.external_verifier == NOT_RUN
    assert got.gates == ("stage4_restatement",)
    assert got.data_bound_integration_ready is False
    assert got.stage3_handoff_sha256 == STAGE3_HANDOFF_SHA256
    assert got.bundle_id == "s3_0b119088734643bf"


def test_require_external_verifier_refuses_a_bundle_the_verifier_never_saw(tmp_path):
    """The data-bound gate. When the real Stage-2 run lands, this is what forbids a GO on a
    bundle Stage-3's own verifier never actually passed."""
    with pytest.raises(Rejection) as exc:
        admit(copy_bundle(str(tmp_path)), require_external_verifier=True)
    assert exc.value.code == "stage3_external_verifier_not_run"


def test_admission_still_refuses_the_smuggled_objective(tmp_path):
    """Gate 1 runs inside the door, not beside it."""
    bundle = copy_bundle(str(tmp_path))
    edit_doc(bundle, lambda d: d.update({"overall_rank": 1}))
    with pytest.raises(Rejection) as exc:
        admit(bundle)
    assert exc.value.code == "stage3_combined_objective_present"


def test_a_partial_verifier_context_is_refused(tmp_path, monkeypatch):
    """Half a context is a configuration error, not a licence to admit on a weaker gate."""
    monkeypatch.setenv(ENV_VERIFIER_ROOT, str(tmp_path))
    with pytest.raises(Rejection) as exc:
        admit(copy_bundle(str(tmp_path)))
    assert exc.value.code == "stage3_verifier_context_incomplete"


def _stub_verifier(tmp_path, exit_code: int) -> str:
    """A stand-in `verifier.verify_stage3` that exits as told.

    This tests STAGE 4's wiring — that a non-zero exit is a refusal and a zero exit is a
    pass. The real verifier's 60 checks are Stage-3's to prove, and they are proven (60/60);
    what Stage 4 owns is whether it actually gates on the answer.
    """
    root = os.path.join(tmp_path, f"verifier_root_{exit_code}")
    pkg = os.path.join(root, "verifier")
    os.makedirs(pkg)
    with open(os.path.join(pkg, "__init__.py"), "w", encoding="utf-8") as fh:
        fh.write("")
    with open(os.path.join(pkg, "verify_stage3.py"), "w", encoding="utf-8") as fh:
        fh.write("import sys\n"
                 "print('[FAIL] the document carries no combined/headline objective key')\n"
                 f"sys.exit({exit_code})\n")
    return root


def _configure(monkeypatch, root: str, tmp_path) -> None:
    monkeypatch.setenv(ENV_VERIFIER_ROOT, root)
    for name in (ENV_CACHE_ROOT, ENV_DIRECT_RUN, ENV_DIRECT_INPUTS):
        monkeypatch.setenv(name, str(tmp_path))


def test_a_verifier_refusal_is_a_stage4_refusal(tmp_path, monkeypatch):
    """Stage 4 does not admit what Stage 3's own verifier rejects — the whole point of the
    owner's rule. Non-zero exit, and the bundle is out."""
    _configure(monkeypatch, _stub_verifier(str(tmp_path), 1), tmp_path)
    with pytest.raises(Rejection) as exc:
        admit(copy_bundle(str(tmp_path)))
    assert exc.value.code == "stage3_external_verifier_refused"
    assert "combined/headline objective" in str(exc.value.context["failures"])


def test_a_verifier_pass_is_recorded_as_an_actual_pass(tmp_path, monkeypatch):
    """Exit 0 — and only then does the door report the second gate as run."""
    _configure(monkeypatch, _stub_verifier(str(tmp_path), 0), tmp_path)
    got = admit(copy_bundle(str(tmp_path)), require_external_verifier=True)
    assert got.external_verifier == PASSED
    assert got.gates == ("stage4_restatement", "verifier.verify_stage3")
    assert got.data_bound_integration_ready is True


def test_a_configured_verifier_that_cannot_run_is_a_refusal_not_a_skip(tmp_path, monkeypatch):
    """A configured root holding no `verifier/` package. The rule that matters: a verifier
    that cannot run has NOT passed."""
    empty = os.path.join(str(tmp_path), "empty_root")
    os.makedirs(empty)
    _configure(monkeypatch, empty, tmp_path)
    with pytest.raises(Rejection) as exc:
        admit(copy_bundle(str(tmp_path)))
    assert exc.value.code == "stage3_verifier_unavailable"


def test_the_LIVE_consumer_routes_through_the_door(tmp_path):
    """A gate nothing calls is not a gate. `adapt_annotation_bundle` is the real consumer
    entry point, so the door has to be ON that path — not beside it in a module."""
    from analysis.stage3_annotation import adapt_annotation_bundle

    got = adapt_annotation_bundle(copy_bundle(str(tmp_path)))
    assert got.external_verifier == NOT_RUN
    assert got.gates == ("stage4_restatement",)

    bundle = copy_bundle(str(tmp_path / "attacked"))
    edit_doc(bundle, lambda d: d.update({"overall_rank": 1}))
    with pytest.raises(Rejection) as exc:
        adapt_annotation_bundle(bundle)
    assert exc.value.code == "stage3_combined_objective_present"


def test_the_LIVE_consumer_can_require_the_external_verifier(tmp_path, monkeypatch):
    """And the data-bound flag reaches it, so a real run can demand gate 2."""
    from analysis.stage3_annotation import adapt_annotation_bundle

    with pytest.raises(Rejection) as exc:
        adapt_annotation_bundle(copy_bundle(str(tmp_path)), require_external_verifier=True)
    assert exc.value.code == "stage3_external_verifier_not_run"

    _configure(monkeypatch, _stub_verifier(str(tmp_path), 0), tmp_path)
    got = adapt_annotation_bundle(copy_bundle(str(tmp_path / "ok")), require_external_verifier=True)
    assert got.external_verifier == PASSED
    assert got.gates == ("stage4_restatement", "verifier.verify_stage3")


def test_no_admission_path_can_silently_skip():
    """The guard on the guard. Nothing in this module skips on a Stage-3 BUNDLE.

    The two `needs_frozen_stage3` marks skip only when no Stage-3 CHECKOUT is reachable —
    they re-hash a foreign worktree's schemas, which simply does not exist on most machines,
    and the pin is still checked for internal consistency without one. An explicitly
    configured root that cannot be read calls `pytest.fail`, never skip.
    """
    with open(__file__, encoding="utf-8") as fh:
        source = fh.read()
    forbidden = "pytest" + ".skip("
    assert forbidden not in source, (
        "an admission test regained an unconditional skip. A Stage-3 bundle that fails "
        "admission must FAIL — a skip is a cross-lane NO-GO wearing a pass's clothes.")
