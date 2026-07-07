"""Smoke test: the package imports cleanly and exposes a version."""

import spot_core


def test_package_imports_and_has_version() -> None:
    assert isinstance(spot_core.__version__, str)
    assert spot_core.__version__
