"""Path setup + synthetic fixtures for the Perturb2State tests (plan §6.9)."""
import os
import sys

import numpy as np
import pandas as pd
import pytest

# analysis/ holds both the ``direct`` and ``perturb2state`` packages.
_ANALYSIS = os.path.join(os.path.dirname(__file__), "..", "..", "analysis")
sys.path.insert(0, os.path.abspath(_ANALYSIS))


@pytest.fixture
def rng():
    return np.random.default_rng(0)


@pytest.fixture
def synthetic_matrix(rng):
    """genes x perturbations DE matrix with a known contributor structure."""
    n_genes, n_pert = 300, 8
    genes = [f"ENSG{i:05d}" for i in range(n_genes)]
    perts = [f"ENSGT{j:02d}" for j in range(n_pert)]
    X = pd.DataFrame(rng.normal(size=(n_genes, n_pert)), index=genes, columns=perts)
    return X, genes, perts
