"""Make `analysis` and `fixtures` importable when pytest runs from anywhere."""

from __future__ import annotations

import os
import sys

STAGE4_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS_DIR = os.path.join(STAGE4_DIR, "tests")

for p in (STAGE4_DIR, TESTS_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)
