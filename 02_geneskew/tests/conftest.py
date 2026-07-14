"""Make the Stage-2 ``direct`` package importable and provide tiny fixtures."""
import os
import sys

import numpy as np
import pytest

# analysis/ holds the ``direct`` package.
_ANALYSIS = os.path.join(os.path.dirname(__file__), "..", "analysis")
sys.path.insert(0, os.path.abspath(_ANALYSIS))


@pytest.fixture
def gene_index():
    # five-gene universe
    return {f"ENSG{i}": i for i in range(5)}


@pytest.fixture
def prog_a():
    # panel = g0,g1 ; control = g2,g3,g4 ; high pole
    return {"panel": ["ENSG0", "ENSG1"],
            "control": ["ENSG2", "ENSG3", "ENSG4"], "sign": +1}


@pytest.fixture
def prog_b():
    return {"panel": ["ENSG0"], "control": ["ENSG2", "ENSG3"], "sign": +1}
