"""Tests for the file-size guard (deterministic logic -> must test)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_file_size as guard  # noqa: E402


def _write(path: Path, n_lines: int, opt_out: bool = False) -> Path:
    body = ["x = 1\n"] * n_lines
    if opt_out:
        body.insert(0, f"# {guard.OPT_OUT}: test reason\n")
    path.write_text("".join(body))
    return path


def test_small_file_passes(tmp_path: Path) -> None:
    f = _write(tmp_path / "ok.py", 10)
    violations, exemptions = guard.check([f])
    assert violations == []
    assert exemptions == []


def test_large_file_is_flagged(tmp_path: Path) -> None:
    f = _write(tmp_path / "big.py", guard.MAX_LINES + 1)
    violations, exemptions = guard.check([f])
    assert len(violations) == 1
    assert exemptions == []


def test_large_file_with_optout_is_exempt(tmp_path: Path) -> None:
    f = _write(tmp_path / "big.py", guard.MAX_LINES + 1, opt_out=True)
    violations, exemptions = guard.check([f])
    assert violations == []
    assert len(exemptions) == 1
