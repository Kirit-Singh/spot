"""Path setup and pytest fixtures for the P2S v2 reusable-arm lane.

The BUILDERS live in ``fixtures_p2s`` — a uniquely named module, because a bare ``conftest``
collides with the other Stage-2 test packages' conftests when the whole suite is collected
together. Same convention as ``tests/direct/fixtures_direct.py``.
"""
from __future__ import annotations

import os
import sys
from typing import Any

import pytest

# analysis/ holds the `direct`, `perturb2state` and `p2s_arms` packages.
_ANALYSIS = os.path.join(os.path.dirname(__file__), "..", "..", "analysis")
sys.path.insert(0, os.path.abspath(_ANALYSIS))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fixtures_p2s as fx  # noqa: E402


@pytest.fixture
def release():
    return fx.make_release()


@pytest.fixture
def view(release) -> dict[str, Any]:
    from direct import scorer_view
    return scorer_view.view(release)


@pytest.fixture
def bundle_dir(tmp_path, view) -> str:
    """A REAL Direct bundle: all ten shipped files, un-admitted (the producer's empty slot)."""
    return fx.write_full_bundle(str(tmp_path / "direct"), view)


@pytest.fixture
def w10_report(tmp_path, bundle_dir, view) -> str:
    """A REAL W10 ADMIT report — content-addressed over its own body, bound to those bytes."""
    return fx.write_w10_report(str(tmp_path / "W10_ADMIT.json"), bundle_dir, view)


@pytest.fixture
def env_lock() -> str:
    """The REAL committed stage02_solver_lock.txt. The pin is the mechanism."""
    return fx.REAL_SOLVER_LOCK


@pytest.fixture
def inputs(tmp_path) -> dict[str, str]:
    d = tmp_path / "inputs"
    d.mkdir()
    return {
        "cells": fx.make_cells(str(d / "cells.npz")),
        "effects": fx.make_effects(str(d / "effects.npz")),
        "masks": fx.make_masks(str(d / "masks.parquet")),
        "eligible": fx.make_eligible(str(d / "eligible.parquet")),
    }


@pytest.fixture
def fit():
    return fx.linear_fit
