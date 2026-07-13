"""The CLIs must REFUSE cleanly — the entrypoints Round-4 will actually type.

Every Stage-3 CLI wraps its work in `try/except (…typed errors…)` and prints a refusal.
Python evaluates that except TUPLE lazily — only when an exception actually propagates —
so a stale name inside it is invisible on the happy path and explodes only when something
goes wrong. Which is the one moment the refusal has to work.

That is exactly what happened. Both acquisition CLIs still caught `ac.NamespaceError`, a
leftover of the `namespace` vocabulary retired in r6 (the class is `ArtifactClassError`).
The library was fine and every test passed, because the tests call `acquire()` / `verify()`
directly and never drove `main()` down a refusal path. So:

    python -m druglink.acquire_public --artifact_class analysis --direct-run /nonexistent …
    -> AttributeError: module 'druglink.artifact_class' has no attribute 'NamespaceError'

instead of `REFUSED [analysis]: <reason>` and exit 2. A fail-closed path that crashes
instead of refusing is not fail-closed; it is just a different way to not know.

These tests drive each CLI's refusal path for real, through `main()`, and hold it to a
typed message and a nonzero exit.
"""
from __future__ import annotations

import pytest

from druglink import acquire_public, verify_acquisition


def test_acquire_public_refuses_a_bad_direct_run_cleanly(tmp_path, capsys):
    rc = acquire_public.main([
        "--artifact_class", "analysis",
        "--direct-run", str(tmp_path / "nonexistent"),
        "--direct-inputs-root", str(tmp_path / "nonexistent"),
        "--top-per-arm", "1",
        "--cache-root", str(tmp_path / "cache"),
    ])
    assert rc == 2, "a bad Direct run must REFUSE with exit 2, not crash"
    assert "REFUSED" in capsys.readouterr().out


def test_verify_acquisition_fails_a_missing_cache_as_a_NAMED_check(tmp_path, capsys):
    """A missing cache is not an abort — it is a check that FAILS, by name.

    This is the better behaviour of the two: an absent manifest is a verification
    RESULT, not an internal error, so it is reported as a named failing gate rather
    than a traceback. Held here so it cannot silently degrade into a crash.
    """
    rc = verify_acquisition.main([
        "--cache-root", str(tmp_path / "nonexistent"),
        "--direct-run", str(tmp_path / "nonexistent"),
        "--direct-inputs-root", str(tmp_path / "nonexistent"),
    ])
    out = capsys.readouterr().out
    assert rc != 0, "an unreadable cache must FAIL, not pass"
    assert "[FAIL] acquisition_manifest_is_present" in out
    assert "0/1 checks passed, 1 failed" in out


def test_acquire_public_refuses_an_unknown_source(tmp_path, capsys):
    rc = acquire_public.main([
        "--artifact_class", "analysis",
        "--direct-run", str(tmp_path), "--direct-inputs-root", str(tmp_path),
        "--top-per-arm", "1", "--cache-root", str(tmp_path / "cache"),
        "--sources", "uniprot,lincs",          # LINCS is not in this release
    ])
    assert rc == 2
    assert "unknown source" in capsys.readouterr().out


@pytest.mark.parametrize("module", [acquire_public, verify_acquisition])
def test_no_cli_catches_a_retired_exception_name(module):
    """The bug in one line: the except tuple named a class that no longer exists.

    Resolve every exception the CLI claims to catch. A name that does not resolve is a
    refusal path that crashes instead of refusing — and no happy-path test can see it.
    """
    import inspect
    import re

    src = inspect.getsource(module.main)
    caught = re.findall(r"(\w+)\.(\w*Error)\b", src)
    for mod_alias, exc_name in caught:
        mod = getattr(module, mod_alias, None)
        assert mod is not None, f"{module.__name__}: unknown alias {mod_alias!r}"
        exc = getattr(mod, exc_name, None)
        assert exc is not None, (
            f"{module.__name__}.main catches {mod_alias}.{exc_name}, which does not "
            f"exist — that refusal path raises AttributeError instead of refusing")
        assert isinstance(exc, type) and issubclass(exc, BaseException)
