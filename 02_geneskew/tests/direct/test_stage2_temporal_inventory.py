"""GATE-7 CLEANUP invariants: the temporal package ships ONLY the reusable-arm lane, and
the stage2_run bridge reaches temporal ONLY through ``temporal.arms``.

The retired fixed-pair flat lane (``temporal/{admission,cli,config,estimand,policy,records,
run_temporal,verify_temporal}.py`` + ``batch_policy.v1.json``) is gone from the production
package and the reproduction chain. These tests fail closed if any of it comes back, or if a
survivor — the Stage-1 v3 bridge above all — imports it again.
"""
from __future__ import annotations

import ast
import os
import sys

_ANALYSIS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "analysis"))
_TEMPORAL = os.path.join(_ANALYSIS, "direct", "temporal")

# The eight modules + the JSON policy that made up the retired flat lane.
RETIRED_MODULES = frozenset({
    "admission", "cli", "config", "estimand", "policy", "records",
    "run_temporal", "verify_temporal"})
RETIRED_FILES = frozenset({f"{m}.py" for m in RETIRED_MODULES} | {"batch_policy.v1.json"})


def _flat_temporal_import(node: ast.AST) -> list[str]:
    """The retired-flat-lane names a node imports, if any.

    Catches ``from .temporal import run_temporal`` / ``from direct.temporal import config``
    (the flat module is an imported NAME) and ``import direct.temporal.policy`` (it is inside
    the dotted module). Never fires on ``.temporal.arms`` — the arm subpackage owns its own
    ``config``/``estimand``, which are different modules that merely share a leaf name.
    """
    hits: list[str] = []
    if isinstance(node, ast.ImportFrom):
        mod = node.module or ""
        parts = mod.split(".")
        if parts and parts[-1] == "temporal":            # from [..].temporal import X
            hits += [a.name for a in node.names if a.name in RETIRED_MODULES]
        if "temporal" in parts:                          # from a.temporal.<flat> import ...
            i = parts.index("temporal")
            if i + 1 < len(parts) and parts[i + 1] in RETIRED_MODULES:
                hits.append(parts[i + 1])
    elif isinstance(node, ast.Import):
        for a in node.names:
            parts = a.name.split(".")
            if "temporal" in parts:
                i = parts.index("temporal")
                if i + 1 < len(parts) and parts[i + 1] in RETIRED_MODULES:
                    hits.append(parts[i + 1])
    return hits


def _imports_of(path: str) -> list[str]:
    tree = ast.parse(open(path).read())
    out: list[str] = []
    for node in ast.walk(tree):
        out += _flat_temporal_import(node)
    return out


def test_the_temporal_package_ships_only_arms_and_init():
    """The production inventory: ``__init__.py`` + the ``arms`` subpackage, nothing else."""
    present = {n for n in os.listdir(_TEMPORAL) if n != "__pycache__"}
    assert present == {"__init__.py", "arms"}, (
        f"the temporal package carries more than arms/ + __init__: {sorted(present)}")
    leaked = present & RETIRED_FILES
    assert not leaked, f"a retired flat-lane file is still shipped: {sorted(leaked)}"


def test_stage2_run_binds_the_temporal_method_only_through_temporal_arms():
    """The bridge that admits the temporal estimator reaches temporal ONLY via temporal.arms.

    The retired flat modules are gone from disk, so ``estimator_registry`` completing at all
    proves it imports none of them (a stale ``from .temporal import run_temporal`` would
    ImportError here). The ``sys.modules`` scan is the belt-and-suspenders check — and it does
    NOT clear the module cache, which would desync fixtures other tests have already bound.
    """
    from direct import stage1_v3

    reg = stage1_v3.estimator_registry()

    pulled = {k for k in sys.modules if k.startswith("direct.temporal.")}
    offenders = sorted(
        m for m in pulled
        if "arms" not in m.split(".") and len(m.split(".")) > 2
        and m.split(".")[2] in RETIRED_MODULES)
    assert offenders == [], f"stage2_run reached the retired flat lane: {offenders}"
    # and it still binds a real, arms-derived method identity
    assert reg["temporal_cross_condition_v1"]["method_sha256"]


def test_the_stage1_v3_bridge_source_names_no_retired_flat_module():
    """A static guard, independent of import order: the bridge's source imports config from
    ``temporal.arms`` and never bare ``.temporal``."""
    imports = _imports_of(os.path.join(_ANALYSIS, "direct", "stage1_v3.py"))
    assert imports == [], f"stage1_v3 imports retired flat-lane modules: {imports}"
    src = open(os.path.join(_ANALYSIS, "direct", "stage1_v3.py")).read()
    assert "from .temporal.arms import config" in src


def test_no_surviving_module_imports_the_retired_flat_temporal_lane():
    """No file left under ``analysis/direct`` imports any retired flat-lane module."""
    offenders: list[str] = []
    for dirpath, _dirs, files in os.walk(os.path.join(_ANALYSIS, "direct")):
        if "__pycache__" in dirpath:
            continue
        for f in files:
            if f.endswith(".py"):
                path = os.path.join(dirpath, f)
                hits = _imports_of(path)
                if hits:
                    offenders.append(f"{os.path.relpath(path, _ANALYSIS)}: {sorted(set(hits))}")
    assert offenders == [], f"survivors still import the retired flat lane: {offenders}"
